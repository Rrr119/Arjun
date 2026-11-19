import contextlib
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import arjun.core.config as mem
from arjun.core.adaptive import build_tiers
from arjun.core.utils import compatible_path, reader


ARJUN_DIR = compatible_path(mem.__file__.replace(compatible_path('/core/config.py'), ''))
LARGE_WORDLIST = ARJUN_DIR + '/db/large.txt'
# names present in the bundled large list and its first (small.txt) tier
SECRET_PARAMS = ('attachment_id', 'author_id')
# a name only present in medium/large tiers, used to prove early stopping
LATE_TIER_PARAM = 'category_id'


class RecordingHandler(BaseHTTPRequestHandler):

    server_version = 'arjun-test/1.0'

    def log_message(self, format, *args):
        pass

    def _serve(self, query):
        self.server.request_count += 1
        body = ['<html><body>static baseline response']
        for name in SECRET_PARAMS:
            if name in query and query[name][0]:
                body.append('reflected %s %s' % (name, query[name][0]))
        body.append('</body></html>')
        payload = '\n'.join(body).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._serve(parse_qs(urlparse(self.path).query))


class LargeWordlistTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), RecordingHandler)
        cls.server.request_count = 0
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = 'http://127.0.0.1:%d/scan' % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        from arjun.__main__ import initialize

        def quiet_initialize(*args, **kwargs):
            with open(os.devnull, 'w') as devnull, contextlib.redirect_stdout(devnull):
                return initialize(*args, **kwargs)
        self.initialize = quiet_initialize
        self.request = {
            'url': self.base_url,
            'method': 'GET',
            'headers': {},
            'include': {}
        }

    def _config(self, **overrides):
        config = {
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
            'adaptive': False,
            'ignore_case': False,
            'max_requests': 0,
            'request_count': 0,
            'budget_exhausted': False,
            'wordlist': LARGE_WORDLIST
        }
        config.update(overrides)
        mem.var = config

    def test_large_wordlist_finishes_with_bounded_requests_and_time(self):
        words = reader(LARGE_WORDLIST, mode='lines')
        self._config()
        start = time.monotonic()
        found = self.initialize(self.request, [words], single_url=False)
        elapsed = time.monotonic() - start
        self.assertIsInstance(found, list)
        self.assertEqual(set(found), set(SECRET_PARAMS))
        self.assertLess(mem.var['request_count'], 200)
        self.assertLess(elapsed, 30.0)

    def test_adaptive_mode_stops_after_first_successful_tier(self):
        self._config(adaptive=True, wordlist=LARGE_WORDLIST)
        words = reader(LARGE_WORDLIST, mode='lines')
        tiers = build_tiers(words)
        self.assertEqual(len(tiers), 3)
        self.assertNotIn(LATE_TIER_PARAM, tiers[0])
        start = time.monotonic()
        found = self.initialize(self.request, tiers, single_url=False)
        elapsed = time.monotonic() - start
        self.assertIsInstance(found, list)
        self.assertEqual(set(found), set(SECRET_PARAMS))
        self.assertNotIn(LATE_TIER_PARAM, found)
        # tier 1 alone only needs a handful of chunk/verify requests
        self.assertLess(mem.var['request_count'], 40)
        self.assertLess(elapsed, 15.0)

    def test_request_budget_is_hard_capped(self):
        words = reader(LARGE_WORDLIST, mode='lines')
        self._config(max_requests=10)
        result = self.initialize(self.request, [words], single_url=False)
        self.assertEqual(result, 'skipped')
        self.assertTrue(mem.var['budget_exhausted'])
        self.assertLessEqual(mem.var['request_count'], 11)

    def test_results_are_deduplicated(self):
        words = ['attachment_id', 'Attachment_Id', 'author_id']
        self._config(wordlist='/tmp/custom-words.txt', ignore_case=True)
        found = self.initialize(self.request, [words], single_url=False)
        self.assertEqual(len(found), len(set(name.lower() for name in found)))
        self.assertIn('attachment_id', found)


if __name__ == '__main__':
    unittest.main()
