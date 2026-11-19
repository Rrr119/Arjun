import threading
import time
from collections import deque


_instance = None
_instance_lock = threading.Lock()


class RateLimiter:
    """
    thread-safe sliding window rate limiter with adaptive backoff

    ``rate`` is the maximum number of acquisitions allowed inside any
    rolling one-second window. When the target signals throttling, a call
    to ``penalty`` pauses all traffic for a cooldown that doubles on
    repeated penalties and resets automatically once the target recovers.
    """

    def __init__(self, rate):
        self.rate = max(1, int(rate))
        self.lock = threading.Lock()
        self.calls = deque()
        self.backoff = 0.0
        self.cooldown_until = 0.0

    @property
    def min_interval(self):
        return 1.0 / self.rate

    def penalty(self, cooldown):
        """
        back off for ``cooldown`` seconds, doubling it on repeated penalties
        returns the currently active backoff in seconds
        """
        with self.lock:
            now = time.monotonic()
            if now < self.cooldown_until:
                self.backoff = min(self.backoff * 2, 30.0)
            else:
                self.backoff = float(cooldown)
            self.cooldown_until = now + self.backoff
            return self.backoff

    def acquire(self):
        """
        blocks until a request is allowed by the sliding window or cooldown
        """
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self.cooldown_until:
                    wait = self.cooldown_until - now
                else:
                    self.backoff = 0.0
                    window_start = now - 1.0
                    while self.calls and self.calls[0] <= window_start:
                        self.calls.popleft()
                    if len(self.calls) < self.rate:
                        self.calls.append(now)
                        return
                    wait = self.calls[0] + 1.0 - now
            time.sleep(max(0.005, min(wait, 0.5)))


def configure(rate):
    """
    creates the process-wide limiter used by every HTTP request
    """
    global _instance
    with _instance_lock:
        _instance = RateLimiter(rate)
    return _instance


def limiter():
    """
    returns the process-wide limiter configured at startup
    """
    return _instance
