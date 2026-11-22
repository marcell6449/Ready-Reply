"""In-process memory for double-click guards and login throttling (single-instance v1)."""

import threading
from collections import defaultdict
from datetime import datetime, timedelta

from readyreply.domain.sessions import LOGIN_WINDOW, is_repeat

MAX_TRACKED_KEYS = 10_000


class MemoryRepeatGuard:
    def __init__(self) -> None:
        self._last_seen: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def is_repeat(self, key: str, now: datetime, window: timedelta) -> bool:
        with self._lock:
            repeated = is_repeat(self._last_seen.get(key), now, window)
            if len(self._last_seen) >= MAX_TRACKED_KEYS:
                self._last_seen.clear()
            self._last_seen[key] = now
            return repeated


class MemoryLoginFailureLog:
    def __init__(self) -> None:
        self._failures: dict[str, list[datetime]] = defaultdict(list)
        self._lock = threading.Lock()

    def record(self, key: str, now: datetime) -> None:
        with self._lock:
            if key not in self._failures and len(self._failures) >= MAX_TRACKED_KEYS:
                self._evict(now)
            recent = [moment for moment in self._failures[key] if now - moment < LOGIN_WINDOW]
            self._failures[key] = [*recent, now]

    def _evict(self, now: datetime) -> None:
        """Forget expired keys first; if still full, forget the key with the fewest failures,
        so flooding the log with made-up usernames cannot erase a real lockout."""
        for key in [
            k for k, moments in self._failures.items() if now - moments[-1] >= LOGIN_WINDOW
        ]:
            del self._failures[key]
        if len(self._failures) >= MAX_TRACKED_KEYS:
            weakest = min(
                self._failures, key=lambda k: (len(self._failures[k]), self._failures[k][-1])
            )
            del self._failures[weakest]

    def recent(self, key: str) -> list[datetime]:
        with self._lock:
            return list(self._failures.get(key, []))

    def clear(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
