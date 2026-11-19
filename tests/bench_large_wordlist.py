"""
large wordlist timing benchmark against a local HTTP server

run:
    python tests/bench_large_wordlist.py

it scans the bundled 25,890-name large.txt in both plain and adaptive mode
and reports wall time plus the exact number of HTTP requests used.
"""
import threading
import time
import contextlib
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import arjun.core.config as mem
from arjun.__main__ import initialize
from arjun.core.adaptive import build_tiers
from arjun.core.utils import compatible_path, reader


ARJUN_DIR = compatible_path(mem.__file__.replace(compatible_path('/core/config.py'), ''))
LARGE_WORDLIST = ARJUN_DIR + '/db/large.txt'
SECRET_PARAMS = ('attachment_id', 'author_id')


class BenchmarkHandler(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.request_count += 1
        query = parse_qs(urlparse(self.path).query)
        body = ['<html>static benchmark baseline']
        for name in SECRET_PARAMS:
            if name in query and query[name][0]:
                body.append('reflected %s %s' % (name, query[name][0]))
        body.append('</html>')
        payload = '\n'.join(body).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def base_config(adaptive):
    return {
        'kill': False,
        'timeout': 10,
        'delay': 0,
        'stable': False,
        'threads': 8,
        'chunks': 250,
        'method': 'GET',
        'include': {},
        'disable_redirects': False,
        'healthy_url': True,
        'bad_req_count': 0,
        'quiet': True,
        'rate_limit': 9999,
        'adaptive': adaptive,
        'ignore_case': False,
        'max_requests': 0,
        'request_count': 0,
        'budget_exhausted': False,
        'wordlist': LARGE_WORDLIST
    }


def run(label, tiers, adaptive):
    mem.var = base_config(adaptive)
    request = {'url': URL, 'method': 'GET', 'headers': {}, 'include': {}}
    start = time.monotonic()
    with open(os.devnull, 'w') as devnull, contextlib.redirect_stdout(devnull):
        found = initialize(request, tiers, single_url=False)
    elapsed = time.monotonic() - start
    print('%-10s params=%-40s requests=%4d  time=%6.2fs' % (
        label, ','.join(found), mem.var['request_count'], elapsed
    ))
    return mem.var['request_count'], elapsed


server = ThreadingHTTPServer(('127.0.0.1', 0), BenchmarkHandler)
server.request_count = 0
threading.Thread(target=server.serve_forever, daemon=True).start()
URL = 'http://127.0.0.1:%d/bench' % server.server_address[1]

words = reader(LARGE_WORDLIST, mode='lines')
print('large wordlist: %d unique names' % len(set(words)))
full_requests, full_time = run('full', [words], False)
adaptive_requests, adaptive_time = run('adaptive', build_tiers(words), True)
print('savings    requests -%.0f%%  time -%.0f%%' % (
    (1 - adaptive_requests / full_requests) * 100,
    (1 - adaptive_time / full_time) * 100
))
server.shutdown()
