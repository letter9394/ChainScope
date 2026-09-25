from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """Small process-local sliding-window limiter for sensitive auth routes."""

    def __init__(self, max_keys: int = 10_000) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._max_keys = max_keys

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
        now: float | None = None,
    ) -> RateLimitDecision:
        current = monotonic() if now is None else now
        cutoff = current - window_seconds
        with self._lock:
            if key not in self._events and len(self._events) >= self._max_keys:
                self._events.pop(next(iter(self._events)))
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, math.ceil(events[0] + window_seconds - current))
                return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
            events.append(current)
            return RateLimitDecision(allowed=True)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
