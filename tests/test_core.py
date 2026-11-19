import threading
import time
import unittest

import arjun.core.config as mem
from arjun.core.adaptive import build_tiers, tier_plan
from arjun.core.ratelimiter import RateLimiter
from arjun.core.utils import dedupe, reader, compatible_path


ARJUN_DIR = compatible_path(mem.__file__.replace(compatible_path('/core/config.py'), ''))


class DedupeTest(unittest.TestCase):

    def test_preserves_order_and_first_occurrence(self):
        self.assertEqual(dedupe(['id', 'name', 'id', 'email', 'name']), ['id', 'name', 'email'])

    def test_case_insensitive(self):
        self.assertEqual(
            dedupe(['Id', 'id', 'ID', 'name'], case_insensitive=True),
            ['Id', 'name']
        )

    def test_exact_dedupe_keeps_casing_variants(self):
        self.assertEqual(dedupe(['Id', 'id', 'ID']), ['Id', 'id', 'ID'])


class RateLimiterTest(unittest.TestCase):

    def test_sliding_window_caps_throughput(self):
        limiter = RateLimiter(10)
        start = time.monotonic()
        for _ in range(20):
            limiter.acquire()
        elapsed = time.monotonic() - start
        self.assertGreaterEqual(elapsed, 0.9)

    def test_window_holds_no_more_than_rate(self):
        limiter = RateLimiter(10)
        for _ in range(10):
            limiter.acquire()
        self.assertEqual(len(limiter.calls), 10)
        time.sleep(1.05)
        limiter.acquire()
        self.assertLessEqual(len(limiter.calls), 10)

    def test_concurrent_callers_share_the_window(self):
        limiter = RateLimiter(20)
        results = []

        def worker():
            for _ in range(10):
                limiter.acquire()
            results.append(True)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        start = time.monotonic()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.monotonic() - start
        self.assertEqual(len(results), 4)
        self.assertGreaterEqual(elapsed, 0.9)

    def test_penalty_doubles_backoff_until_recovery(self):
        limiter = RateLimiter(100)
        self.assertEqual(limiter.penalty(1), 1.0)
        self.assertEqual(limiter.penalty(1), 2.0)
        time.sleep(2.1)
        start = time.monotonic()
        limiter.acquire()
        self.assertLess(time.monotonic() - start, 0.2)
        self.assertEqual(limiter.backoff, 0.0)


class AdaptiveWordlistTest(unittest.TestCase):

    def setUp(self):
        mem.var = {'wordlist': ARJUN_DIR + '/db/large.txt'}

    def test_bundled_wordlist_splits_into_frequency_tiers(self):
        words = reader(ARJUN_DIR + '/db/large.txt', mode='lines')
        tiers = build_tiers(words)
        self.assertEqual(len(tiers), 3)
        self.assertEqual([len(tier) for tier in tiers], [578, 6389, 18923])
        self.assertEqual(sum(len(tier) for tier in tiers), len(set(words)))

    def test_tiers_are_disjoint_and_preserve_within_tier_order(self):
        words = reader(ARJUN_DIR + '/db/large.txt', mode='lines')
        tiers = build_tiers(words)
        small = set(reader(ARJUN_DIR + '/db/small.txt', mode='lines'))
        medium = set(reader(ARJUN_DIR + '/db/medium.txt', mode='lines'))
        seen = set()
        for tier in tiers:
            for word in tier:
                self.assertNotIn(word, seen)
                seen.add(word)
        large_unique = list(dict.fromkeys(words))
        self.assertEqual(seen, set(large_unique))
        self.assertEqual(tiers[0], [w for w in large_unique if w in small])
        self.assertEqual(tiers[1], [w for w in large_unique if w not in small and w in medium])
        self.assertEqual(tiers[2], [w for w in large_unique if w not in small and w not in medium])

    def test_custom_wordlist_stays_single_tier(self):
        mem.var['wordlist'] = '/tmp/custom-words.txt'
        tiers = build_tiers(['alpha', 'beta', 'alpha'])
        self.assertEqual(tiers, [['alpha', 'beta']])

    def test_tier_plan_respects_adaptive_flag(self):
        words = reader(ARJUN_DIR + '/db/large.txt', mode='lines')
        mem.var['adaptive'] = False
        self.assertEqual(len(tier_plan(words)), 1)
        mem.var['adaptive'] = True
        self.assertEqual(len(tier_plan(words)), 3)


if __name__ == '__main__':
    unittest.main()
