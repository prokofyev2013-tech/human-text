"""Ограничение частоты запросов: не более N запросов за окно с одного IP."""

from __future__ import annotations

import time
from collections import deque


class RateLimiter:
    """Простой in-memory лимитер по скользящему окну."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max = max(1, max_requests)
        self._window = max(1, window_seconds)
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> tuple[bool, int]:
        """Возвращает (разрешено, сколько секунд ждать при отказе)."""
        now = time.monotonic()
        bucket = self._hits.setdefault(key, deque())

        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) >= self._max:
            retry_after = max(1, int(self._window - (now - bucket[0])) + 1)
            return False, retry_after

        bucket.append(now)
        return True, 0

    def reset(self) -> None:
        """Очищает историю — используется в тестах."""
        self._hits.clear()
