from __future__ import annotations

import threading
from collections import deque
from functools import wraps

from flask import request

from app import clock
from app.errors import RateLimited


class RateLimiter:
    """Sliding-window limiter, in-memory, per key. Single process by design."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = clock.now().timestamp()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def rate_limited(limiter: RateLimiter):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            key = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
            if not limiter.allow(key):
                raise RateLimited("Too many requests, slow down")
            return fn(*a, **kw)

        return wrapper

    return deco


login_limiter = RateLimiter(limit=10, window_seconds=60)
webhook_limiter = RateLimiter(limit=60, window_seconds=60)
