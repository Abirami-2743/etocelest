"""Small in-memory sliding-window limiter (per process)."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > self._window:
            q.popleft()
        if len(q) >= self._limit:
            return False
        q.append(now)
        if len(self._hits) > 10_000:  # bound memory under key churn
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self._window]:
                self._hits.pop(k, None)
        return True
