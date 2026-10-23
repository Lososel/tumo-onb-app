"""Tiny in-memory sliding-window rate limiter (per client IP) to slow down name enumeration."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

WINDOW = 60.0  # seconds


class RateLimiter:
    def __init__(self, per_minute: int, max_keys: int = 10_000):
        self.per_minute = per_minute
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        if self.per_minute <= 0:
            return
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > WINDOW:
            hits.popleft()
        if len(hits) >= self.per_minute:
            raise HTTPException(
                429,
                "Too Many Requests. Please wait a minute before searching again.",
                headers={"Retry-After": str(max(1, int(WINDOW - (now - hits[0])) + 1))},
            )
        hits.append(now)
        if len(self._hits) > self.max_keys:
            self._prune(now)

    def _prune(self, now: float) -> None:
        """Bound memory: forget clients with no hit inside the window. If that still leaves too
        many (a flood of distinct IPs), keep only the most recently active half, so the next
        prune is max_keys/2 new clients away instead of on every request."""
        live = {k: v for k, v in self._hits.items() if v and now - v[-1] <= WINDOW}
        if len(live) > self.max_keys // 2:
            newest = sorted(live, key=lambda k: live[k][-1], reverse=True)[: self.max_keys // 2]
            live = {k: live[k] for k in newest}
        self._hits = defaultdict(deque, live)
