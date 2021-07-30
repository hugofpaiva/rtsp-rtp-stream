# RTSP and RTP Streaming Client Using Credentials

With the work made by [gabrieljablonski](https://github.com/gabrieljablonski/rtsp-rtp-stream) and having the need to do RTSP authentication in native Python, I changed the source code, removing the server and changing the client to support authentication using the MD5 algorithm.
 
### **DISCLAIMER: PYQT IS AVAILABLE THROUGH THE GPL LICENSE. THE MIT LICENSE ONLY APPLIES TO NON-PYQT CODE**

## Installation

1. Clone the repository

2. Having python>=3.6 installed, create a virtual environment by running `python -m venv venv` inside the cloned folder

3. Activate the virtual environment (`source venv/bin/activate` on Linux, `.\venv\Scripts\activate` on Windows).

4. Install the requirements with `python -m pip install -r requirements.txt`.


## Usage

1. Go to the source folder with `cd src/`
2. Find the usage running:
```
python3 main_client.py -h 
```