"""F6-07, F6-08: session expiry and login throttling."""

from datetime import UTC, datetime, timedelta

from readyreply.domain.sessions import (
    LOGIN_MAX_FAILURES,
    LOGIN_WINDOW,
    Session,
    is_login_locked,
    is_repeat,
)

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)


def session(expires_in: timedelta) -> Session:
    return Session(
        token_hash="h", user_id=1, business_id=1, csrf_token="c", expires_at=NOW + expires_in
    )


def test_expiry() -> None:
    assert session(timedelta(seconds=-1)).is_expired(NOW)
    assert session(timedelta(0)).is_expired(NOW)
    assert not session(timedelta(seconds=1)).is_expired(NOW)


def test_refresh_only_when_worthwhile() -> None:
    ttl = timedelta(hours=12)
    fresh = session(ttl - timedelta(minutes=1))
    assert fresh.refreshed(NOW, ttl) is None
    stale = session(timedelta(hours=1))
    refreshed = stale.refreshed(NOW, ttl)
    assert refreshed is not None
    assert refreshed.expires_at == NOW + ttl


def test_login_lock() -> None:
    recent = [NOW - timedelta(seconds=i) for i in range(LOGIN_MAX_FAILURES)]
    assert is_login_locked(recent, NOW)
    assert not is_login_locked(recent[:-1], NOW)
    old = [NOW - LOGIN_WINDOW - timedelta(seconds=1)] * LOGIN_MAX_FAILURES
    assert not is_login_locked(old, NOW)


def test_is_repeat() -> None:
    window = timedelta(seconds=3)
    assert is_repeat(NOW - timedelta(seconds=2), NOW, window)
    assert not is_repeat(NOW - timedelta(seconds=3), NOW, window)
    assert not is_repeat(None, NOW, window)
