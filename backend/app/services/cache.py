import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheItem:
    value: Any
    expires_at: float


class TTLCache:
    """Small process-local cache suitable for the MVP and unit tests."""

    def __init__(self) -> None:
        self._items: dict[str, CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at <= time.monotonic():
            self._items.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._items[key] = CacheItem(
            value=value,
            expires_at=time.monotonic() + ttl_seconds,
        )

    def clear(self) -> None:
        self._items.clear()


cache = TTLCache()

