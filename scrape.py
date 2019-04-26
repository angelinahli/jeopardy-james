import os
import logging
import socket
from threading import Thread

from bs4 import BeautifulSoup

HOST = "j-archive.com"
PORT = 80
THREADS = 1
WAIT_SECONDS = 20
END_ID = 6256
MAX_RETRIES = 3

if os.getenv("DEBUG") == "true": logging.basicConfig(level=logging.DEBUG)
LOG = logging.getLogger("crawler")

DEFAULT_HEADERS = {
    "Host": HOST,
    "Connection": "Close"
}

###############
## HTTP Code ##
###############

class Response:
    def __init__(self, resp):
        resp = resp.strip()
        self.resp = resp
        split_resp = resp.split("\r\n\r\n")
        if len(split_resp) == 1:
            self.headers, self.body_content = split_resp[0], ''
        elif len(split_resp) == 2:
            self.headers, self.body_content = split_resp
        else:
            raise Exception('Got invalidly sized response')
        self.headers = self.headers.split("\r\n")

    def body(self):
        # for some reason, some responses seem to have \r\n in the HTML. But the
        # responses are never chunked, so just drop the first line (initial size)
        # and last line (always "0", since there's nothing left)
        body_lines = self.body_content.split("\r\n")[1:-1]
        return "\r\n".join(body_lines)

    def status_code(self):
        split_line = self.headers[0].split(' ')
        return int(split_line[1])

    def __str__(self):
        return self.resp

    def __repr__(self):
        return self.resp

def build_header_str(headers={}):
    headers.update(DEFAULT_HEADERS)
    return "\n".join(["{}: {}".format(k, v) for k, v in headers.iteritems()])

def build_path(game_id):
    return "/showscores.php?game_id=%d" % game_id

def send_req(req_str):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    s.connect((HOST, PORT))
    LOG.debug("Sending:")
    LOG.debug(req_str)
    buf = ""
    s.sendall(req_str)
    resp = s.recv(10000)

    while len(resp):
        buf += resp
        resp = s.recv(10000)

    resp = Response(buf)
    LOG.debug("\nGot:")
    LOG.debug(str(resp))
    LOG.debug("\Body:")
    LOG.debug(resp.body())
    s.close()
    return resp

def get(path, headers={}):
    LOG.debug(path)
    req = "GET {} HTTP/1.1\n{}\n\n".format(path, build_header_str(headers))
    return send_req(req)

###############
## HTML Code ##
###############
cur_id = 1

class ProcessRequestThread(Thread):
    def __init__(self, url):
        Thread.__init__(self)
        self.url = url
        self.result = None
        self.retries = 0

    def run(self):
        resp = get(self.url)
        while resp.status_code() is not 200 and self.retries < MAX_RETRIES:
            LOG.debug('Abnormal status: ' + str(resp.status_code()))
            resp = get(self.url)

        if resp.status_code() is not 200:
            LOG.info("failed to get %s (%d)" % (self.url, resp.status_code()))
            return
        content = resp.body()
        soup = BeautifulSoup(content, 'html.parser')

        all_rows = soup.select(".scores_table tr")
        first_round_scores = all_rows[1:31]
        dd_scores = all_scores[32:62]
        import pdb; pdb.set_trace()

ProcessRequestThread(build_path(cur_id)).run()
