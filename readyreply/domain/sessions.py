"""Login sessions and time-window rules (expiry, throttling, double-click dedupe)."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

LOGIN_MAX_FAILURES = 5
ADDRESS_MAX_FAILURES = 20
LOGIN_WINDOW = timedelta(minutes=5)
REFRESH_MARGIN = timedelta(minutes=5)
COPY_REPEAT_WINDOW = timedelta(seconds=3)
UNANSWERED_REPEAT_WINDOW = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class Session:
    token_hash: str
    user_id: int
    business_id: int
    csrf_token: str
    expires_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def refreshed(self, now: datetime, ttl: timedelta) -> "Session | None":
        """A session with a new expiry, or None when the current one is still fresh."""
        if self.expires_at - now > ttl - REFRESH_MARGIN:
            return None
        return replace(self, expires_at=now + ttl)


def is_login_locked(
    failures: Iterable[datetime], now: datetime, limit: int = LOGIN_MAX_FAILURES
) -> bool:
    recent = [moment for moment in failures if now - moment < LOGIN_WINDOW]
    return len(recent) >= limit


def is_repeat(previous: datetime | None, now: datetime, window: timedelta) -> bool:
    return previous is not None and now - previous < window
