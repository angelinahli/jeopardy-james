import json
import logging
import os
import socket
import time
from threading import Thread

from bs4 import BeautifulSoup

HOST = "j-archive.com"
PORT = 80
THREADS = 10
WAIT_SECONDS = 20
END_ID = 6256
MAX_RETRIES = 3

if os.getenv("LOG") == "debug": logging.basicConfig(level=logging.DEBUG)
elif os.getenv("LOG") == "info": logging.basicConfig(level=logging.INFO)
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

#######################
## HTML Parsing Code ##
#######################
cur_id = 1

class Wager:
    def __init__(self, before_row, after_row):
        self.scores_before = self.parse_scores(BeautifulSoup(before_row, "lxml"))
        self.scores_after = self.parse_scores(BeautifulSoup(after_row, "lxml"))

    def as_json(self):
        wager_index = -1
        for i, score in enumerate(self.scores_after):
            if score != self.scores_before[i]:
                wager_index = i
        assert wager_index != -1, "Could not find wager"
        return self._get_wager_json(wager_index)

    def _get_wager_json(self, wager_index, is_final=False):
        scores_before = self.scores_before[:]
        scores_after = self.scores_after[:]

        wager_before = scores_before.pop(wager_index)
        wager_after = scores_after.pop(wager_index)
        wager = abs(wager_after - wager_before)

        return {
            "final": is_final,
            "score": wager_before,
            "wager": wager,
            "opponent_score_1": sorted(scores_before)[0],
            "opponent_score_2": sorted(scores_before)[0]
        }

    def parse_scores(self, soup):
        scores = soup.select("td")
        if len(scores) == 5: scores = scores[1:4]
        return [ int(s.text.replace("$", "").replace(",", "")) for s in scores ]

class FinalWager(Wager):
    def as_json(self):
        return [ self._get_wager_json(i, True) for i in range(3) ]

class ProcessRequestThread(Thread):
    def __init__(self, url):
        Thread.__init__(self)
        self.url = url
        self.result = None
        self.retries = 0

    def run(self):
        LOG.info("Getting " + self.url)
        resp = get(self.url)
        while resp.status_code() is not 200 and self.retries < MAX_RETRIES:
            LOG.debug("Abnormal status: " + str(resp.status_code()))
            resp = get(self.url)

        if resp.status_code() is not 200:
            LOG.info("failed to get %s (%d)" % (self.url, resp.status_code()))
            return

        content = resp.body()
        soup = BeautifulSoup(content, "lxml")

        all_rows = soup.select("#single_jeopardy_round tr")
        all_rows += soup.select("#double_jeopardy_round tr")
        all_rows += soup.select("#final_jeopardy_round table:first-of-type tr")
        filtered_rows = filter(lambda r: "score_positive" in str(r) or "score_negative" in str(r),
                all_rows)

        # hack to make things easier, implicit first round of $0 for everyone
        first_round = "<tr><td>0</td>" + ("<tr>$0</tr>" * 3) + "<tr>0</td></tr>"
        filtered_rows = [first_round] + filtered_rows

        json_data = []
        for i, row in enumerate(filtered_rows):
            row = str(row)
            if "ddred" not in row: continue
            wager_obj = Wager(str(filtered_rows[i-1]), row)
            json_data.append(wager_obj.as_json())
        final_wager_obj = FinalWager(str(filtered_rows[-2]), str(filtered_rows[-1]))
        json_data += final_wager_obj.as_json()
        self.result = json_data
        return None


data = []
while cur_id < END_ID:
    ids = range(cur_id, min(cur_id + THREADS, END_ID + 1))
    threads = [ ProcessRequestThread(build_path(game_id)) for game_id in ids ]

    [ t.start() for t in threads ]
    [ t.join() for t in threads ]

    [ data.append(t.result) for t in threads ]
    time.sleep(WAIT_SECONDS)
    cur_id += THREADS

with open("data.json", "w") as outfile: json.dump(data, outfile)
