import re
from typing import Optional


class InvalidRTSPRequest(Exception):
    pass


class RTSPPacket:
    RTSP_VERSION = 'RTSP/1.0'

    INVALID = -1
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE = 'DESCRIBE'
    RESPONSE = 'RESPONSE'

    def __init__(
            self,
            request_type,
            user_agent: str = None,
            video_file_path: Optional[str] = None,
            sequence_number: Optional[int] = None,
            dst_port: Optional[int] = None,
            session_id: Optional[str] = None,
            auth_seq: str = None,
            nonce: str = None,
            authentication_method: str = None,
            realm: str = None,
            status_code: int = None,
            timeout: int = None):
        self.request_type = request_type
        self.video_file_path = video_file_path
        self.sequence_number = sequence_number
        self.session_id = session_id
        self.user_agent = user_agent
        self.auth_seq = auth_seq
        self.timeout = timeout

        # To check if it needs authentication
        self.nonce = nonce
        self.authentication_method = authentication_method
        self.realm = realm
        self.status_code = status_code

        # if request_type SETUP
        self.rtp_dst_port = dst_port

    def __str__(self):
        return (f"RTSPPacket({self.request_type}, "
                f"{self.video_file_path}, "
                f"{self.sequence_number}, "
                f"{self.rtp_dst_port}, "
                f"{self.session_id})")

    @classmethod
    def from_response(cls, response: bytes):
        # only response format implemented, taken from server class:
        # """
        #   <RTSP_VERSION> 200 OK\r\n
        #   CSeq: <SEQUENCE_NUMBER>\r\n
        #   Session: <SESSION_ID>\r\n
        # """

        match_setup = re.match(
            r"(?P<rtsp_version>RTSP/\d+.\d+) 200 OK\r?\n"
            r"CSeq: (?P<sequence_number>\d+)\r?\n"
            r"Session: (?P<session_id>\d+);timeout=(?P<timeout>\d+)\r?\n",
            response.decode()
        )

        match = re.match(
            r"(?P<rtsp_version>RTSP/\d+.\d+) 200 OK\r?\n"
            r"CSeq: (?P<sequence_number>\d+)\r?\n"
            r"Session: (?P<session_id>\d+)\r?\n",
            response.decode()
        )  

        match_authorized = re.match(
            r"(?P<rtsp_version>RTSP/\d+.\d+) 200 OK\r?\n"
            r"CSeq: (?P<sequence_number>\d+)\r?\n",
            response.decode()
        )

        match_unauthorized = re.match(
            r"(?P<rtsp_version>RTSP/\d+.\d+) 401 Unauthorized\r?\n"
            r"CSeq: (?P<sequence_number>\d+)\r?\n"
            r"WWW-Authenticate: (?P<authentication_method>[^\s]+) realm=\"(?P<realm>[^\"]+)\", nonce=\"(?P<nonce>[^\"]+)\"\r?\n\r?\n?",
            response.decode()
        )

        if match is None and match_unauthorized is None and match_authorized is None and match_setup is None:
            raise Exception(f"failed to parse RTSP response: {response}")

        if match_unauthorized:
            g = match_unauthorized.groupdict()

            # not used, defaults to 1.0
            # rtsp_version = g.get('rtsp_version')
            sequence_number = g.get('sequence_number')
            authentication_method = g.get('authentication_method')
            realm = g.get('realm')
            nonce = g.get('nonce')

            try:
                sequence_number = int(sequence_number)
            except (ValueError, TypeError):
                raise Exception(f"failed to parse sequence number: {response}")

            

            return cls(
                request_type=RTSPPacket.RESPONSE,
                sequence_number=sequence_number,
                authentication_method=authentication_method,
                realm=realm,
                nonce=nonce,
                status_code=401
            )
        elif match_setup:
            g = match_setup.groupdict()

            # not used, defaults to 1.0
            # rtsp_version = g.get('rtsp_version')
            sequence_number = g.get('sequence_number')
            session_id = g.get('session_id')
            timeout = g.get('timeout')

            try:
                sequence_number = int(sequence_number)
            except (ValueError, TypeError):
                raise Exception(f"failed to parse sequence number: {response}")

            try:
                timeout = int(timeout)
            except (ValueError, TypeError):
                raise Exception(f"failed to parse timeout number: {response}")

            if session_id is None:
                raise Exception(f"failed to parse session id: {response}")

            return cls(
                request_type=RTSPPacket.RESPONSE,
                sequence_number=sequence_number,
                session_id=session_id,
                status_code=200, 
                timeout=timeout
            )
        elif match:
            g = match.groupdict()

            # not used, defaults to 1.0
            # rtsp_version = g.get('rtsp_version')
            sequence_number = g.get('sequence_number')
            session_id = g.get('session_id')

            try:
                sequence_number = int(sequence_number)
            except (ValueError, TypeError):
                raise Exception(f"failed to parse sequence number: {response}")

            if session_id is None:
                raise Exception(f"failed to parse session id: {response}")

            return cls(
                request_type=RTSPPacket.RESPONSE,
                sequence_number=sequence_number,
                session_id=session_id,
                status_code=200
            )

        elif match_authorized:
            g = match_authorized.groupdict()

            # not used, defaults to 1.0
            # rtsp_version = g.get('rtsp_version')
            sequence_number = g.get('sequence_number')

            try:
                sequence_number = int(sequence_number)
            except (ValueError, TypeError):
                raise Exception(f"failed to parse sequence number: {response}")

            return cls(
                request_type=RTSPPacket.RESPONSE,
                sequence_number=sequence_number,
                status_code=200
            )

    @classmethod
    def build_response(cls, sequence_number: int, session_id: str):
        response = '\r\n'.join((
            f"{cls.RTSP_VERSION} 200 OK",
            f"CSeq: {sequence_number}",
            f"Session: {session_id}",
        )) + '\r\n'
        return response

    @classmethod
    def from_request(cls, request: bytes):
        # loosely follows actual rtsp protocol, considering only SETUP, PLAY, PAUSE, and TEARDOWN
        # https://en.wikipedia.org/wiki/Real_Time_Streaming_Protocol
        match = re.match(
            r"(?P<request_type>\w+) rtsp://(?P<video_file_path>\S+) (?P<rtsp_version>RTSP/\d+.\d+)\r?\n"
            r"CSeq: (?P<sequence_number>\d+)\r?\n"
            r"(Range: (?P<play_range>\w+=\d+-\d+\r?\n))?"
            r"(Transport: .*client_port=(?P<dst_port>\d+).*\r?\n)?"  # in case of SETUP request
            r"(Session: (?P<session_id>\d+)\r?\n)?",
            request.decode()
        )

        if match is None:
            raise InvalidRTSPRequest(f"failed to parse request: {request}")

        g = match.groupdict()
        request_type = g.get('request_type')

        if request_type not in (RTSPPacket.SETUP,
                                RTSPPacket.PLAY,
                                RTSPPacket.PAUSE,
                                RTSPPacket.DESCRIBE,
                                RTSPPacket.TEARDOWN):
            raise InvalidRTSPRequest(f"invalid request type: {request}")

        video_file_path = g.get('video_file_path')
        # not used, defaults to `RTSPPacket.RTSP_VERSION`
        # rtsp_version = g.get('rtsp_version')
        sequence_number = g.get('sequence_number')
        dst_port = g.get('dst_port')
        session_id = g.get('session_id')

        if request_type == RTSPPacket.SETUP:
            try:
                dst_port = int(dst_port)
            except (ValueError, TypeError):
                raise InvalidRTSPRequest(f"failed to parse RTP port")
        try:
            sequence_number = int(sequence_number)
        except (ValueError, TypeError):
            raise InvalidRTSPRequest(f"failed to parse sequence number: {request}")

        return cls(
            request_type,
            video_file_path,
            sequence_number,
            dst_port,
            session_id
        )

    def to_request(self) -> bytes:
        # loosely follows actual rtsp protocol, considering only SETUP, PLAY, PAUSE, and TEARDOWN
        # https://en.wikipedia.org/wiki/Real_Time_Streaming_Protocol
        if any((attr is None for attr in (self.request_type,
                                          self.sequence_number))):
            raise InvalidRTSPRequest('missing one attribute of: `request_type`, `sequence_number`, `session_id`')

        if self.session_id is None and self.request_type != self.DESCRIBE:
            raise InvalidRTSPRequest('missing one attribute of: `session_id`')

        if self.request_type in (self.INVALID, self.RESPONSE):
            raise InvalidRTSPRequest(f"invalid request type: {self}")

        request_lines = [
            f"{self.request_type} rtsp://{self.video_file_path} {self.RTSP_VERSION}",
            f"CSeq: {self.sequence_number}"
        ]

        if self.user_agent is not None:
            request_lines.append(
                f"User-Agent: {self.user_agent}"
            )

        if self.auth_seq is not None:
            request_lines.append(
                f"Authorization: {self.auth_seq}"
            )

        if self.request_type == self.SETUP:
            if self.rtp_dst_port is None:
                raise InvalidRTSPRequest(f"missing RTP destination port: {self}")
            request_lines.append(
                f"Transport: RTP/AVP/UDP;unicast;client_port={self.rtp_dst_port}-{self.rtp_dst_port}"
            )
        elif self.request_type != self.DESCRIBE:
            request_lines.append(
                f"Session: {self.session_id}"
            )
        request = '\r\n'.join(request_lines) + '\r\n\r\n'
        print(request.encode())
        return request.encode()
