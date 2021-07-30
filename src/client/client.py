import socket
from threading import Thread
from typing import Union, Optional, List, Tuple
from time import sleep
from PIL import Image
from io import BytesIO
import hashlib

from utils.rtsp_packet import RTSPPacket
from utils.rtp_packet import RTPPacket
from utils.video_stream import VideoStream


class Client:
    DEFAULT_CHUNK_SIZE = 4096
    DEFAULT_RECV_DELAY = 20  # in milliseconds

    DEFAULT_LOCAL_HOST = '0.0.0.0'

    RTP_SOFT_TIMEOUT = 5  # in milliseconds
    # for allowing simulated non-blocking operations
    # (useful for keyboard break)
    RTSP_SOFT_TIMEOUT = 100  # in milliseconds
    # if it's present at the end of chunk, client assumes
    # it's the last chunk for current frame (end of frame)
    PACKET_HEADER_LENGTH = 5

    def __init__(
            self,
            host_file_path: str,
            remote_host_address: str,
            remote_host_port: int,
            rtp_port: int,
            user: str = None,
            pw: str = None,
            user_agent: str = "RTSP Client"):
        self._rtsp_connection: Union[None, socket.socket] = None
        self._rtp_socket: Union[None, socket.socket] = None
        self._rtp_receive_thread: Union[None, Thread] = None
        self._frame_buffer: List[Image.Image] = []
        self._current_sequence_number = 0
        self.session_id = ''
        self._user_agent = user_agent

        # Used for Authentication
        self._user = user
        self._pw = pw
        self.realm = None
        self.nounce = None
        self.need_auth = False

        self.current_frame_number = -1

        self.is_rtsp_connected = False
        self.is_receiving_rtp = False

        self.host_file_path = host_file_path
        self.remote_host_address = remote_host_address
        self.remote_host_port = remote_host_port
        self.rtp_port = rtp_port

    def get_next_frame(self) -> Optional[Tuple[Image.Image, int]]:
        if self._frame_buffer:
            self.current_frame_number += 1
            # skip 5 bytes which contain frame length in bytes
            return self._frame_buffer.pop(0), self.current_frame_number
        return None

    @staticmethod
    def _get_frame_from_packet(packet: RTPPacket) -> Image.Image:
        # the payload is already the jpeg
        raw = packet.payload
        frame = Image.open(BytesIO(raw))
        return frame

    def _recv_rtp_packet(self, size=DEFAULT_CHUNK_SIZE) -> RTPPacket:
        recv = bytes()
        print('Waiting RTP packet...')
        while True:
            print("Trying to receive")
            try:
                recv += self._rtp_socket.recv(size)
                if recv.endswith(VideoStream.JPEG_EOF):
                    break
            except socket.timeout:
                continue
        print(f"Received from server: {repr(recv)}")
        return RTPPacket.from_packet(recv)

    def _start_rtp_receive_thread(self):
        self._rtp_receive_thread = Thread(target=self._handle_video_receive)
        self._rtp_receive_thread.setDaemon(True)
        self._rtp_receive_thread.start()

    def _handle_video_receive(self):
        self._rtp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rtp_socket.bind((self.DEFAULT_LOCAL_HOST, self.rtp_port))
        self._rtp_socket.settimeout(self.RTP_SOFT_TIMEOUT / 1000.)
        while True:
            if not self.is_receiving_rtp:
                sleep(self.RTP_SOFT_TIMEOUT/1000.)  # diminish cpu hogging
                continue
            packet = self._recv_rtp_packet()
            frame = self._get_frame_from_packet(packet)
            self._frame_buffer.append(frame)

    def establish_rtsp_connection(self):
        if self.is_rtsp_connected:
            print('RTSP is already connected.')
            return
        print(f"Connecting to {self.remote_host_address}:{self.remote_host_port}...")
        self._rtsp_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._rtsp_connection.connect((self.remote_host_address, self.remote_host_port))
        self._rtsp_connection.settimeout(self.RTSP_SOFT_TIMEOUT / 1000.)
        self.is_rtsp_connected = True

    def close_rtsp_connection(self):
        if not self.is_rtsp_connected:
            print('RTSP is not connected.')
            return
        self._rtsp_connection.close()
        self.is_rtsp_connected = False

    def _generate_auth_string(self, username, password, realm, method, uri, nonce):
        m1 = bytes(hashlib.md5(bytes(username, 'utf-8') + bytes(":", 'utf-8') + bytes(realm, 'utf-8') + bytes(":", 'utf-8') + bytes(password, 'utf-8')).hexdigest(), 'utf-8')
        m2 = bytes(hashlib.md5(bytes(method, 'utf-8') + bytes(":", 'utf-8') + bytes(uri, 'utf-8')).hexdigest(), 'utf-8')
        response = hashlib.md5(m1 + bytes(":", 'utf-8') + bytes(nonce, 'utf-8') + bytes(":", 'utf-8') + m2).hexdigest()
        ret_auth = "Digest "
        ret_auth += "username=\"" + username+ "\", "
        ret_auth += "realm=\"" + realm + "\", "
        ret_auth += "algorithm=\"MD5\", "
        ret_auth += "nonce=\"" + nonce + "\", "
        ret_auth += "response=\"" + response + "\""
        return ret_auth

    def _send_request(self, request_type=RTSPPacket.INVALID) -> RTSPPacket:
        if not self.is_rtsp_connected:
            raise Exception('rtsp connection not established. run `setup_rtsp_connection()`')

        auth_seq = None
        if self.need_auth:
            auth_seq = self._generate_auth_string(self._user, self._pw, self.realm, request_type, '', self.nonce)

        rtsp_host_to_send =  self.remote_host_address + "/" + self.host_file_path if request_type == RTSPPacket.SETUP else self.remote_host_address

        request = RTSPPacket(
            request_type,
            self._user_agent,
            rtsp_host_to_send,
            self._current_sequence_number,
            self.rtp_port,
            self.session_id, 
            auth_seq
        ).to_request()
        print(f"Sending request: {repr(request)}")
        self._rtsp_connection.send(request)
        self._current_sequence_number += 1
        return self._get_response()

    def send_describe_and_authenticate_request(self) -> RTSPPacket:
        response = self._send_request(RTSPPacket.DESCRIBE)

        # Only Digest is supported
        if response.authentication_method == "Digest":
            if not self._user and not self._pw:
                print('\nServer needs authentication info.')
                return
            self.need_auth = True
            self.realm = response.realm
            self.nonce = response.nonce

            response = self._send_request(RTSPPacket.DESCRIBE)
            if response.status_code != 200:
                print('\nAuthentication failed.')
                return
        return response

    def send_setup_request(self) -> RTSPPacket:
        response = self._send_request(RTSPPacket.SETUP)
        self._start_rtp_receive_thread()
        self.session_id = response.session_id
        return response

    def send_play_request(self) -> RTSPPacket:
        response = self._send_request(RTSPPacket.PLAY)
        self.is_receiving_rtp = True
        return response

    def send_pause_request(self) -> RTSPPacket:
        response = self._send_request(RTSPPacket.PAUSE)
        self.is_receiving_rtp = False
        return response

    def send_teardown_request(self) -> RTSPPacket:
        response = self._send_request(RTSPPacket.TEARDOWN)
        self.is_receiving_rtp = False
        self.is_rtsp_connected = False
        return response

    def _get_response(self, size=DEFAULT_CHUNK_SIZE) -> RTSPPacket:
        rcv = None
        while True:
            try:
                rcv = self._rtsp_connection.recv(size)
                break
            except socket.timeout:
                continue
        print(f"Received from server: {repr(rcv)}")
        response = RTSPPacket.from_response(rcv)
        return response
