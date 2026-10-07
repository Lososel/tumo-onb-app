"""Tiny in-memory sliding-window rate limiter (per client IP) to slow down name enumeration."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise HTTPException(429, "Too many lookups. Please wait a minute and try again.")
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory
            self._hits = defaultdict(deque, {k: v for k, v in self._hits.items() if v})
