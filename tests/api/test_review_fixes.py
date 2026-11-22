"""Tests written first for the code-review findings (docs/REVIEW.md)."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from readyreply.infrastructure.security.memory import MAX_TRACKED_KEYS, MemoryLoginFailureLog
from readyreply.infrastructure.security.passwords import Argon2PasswordHasher
from tests.conftest import ADMIN, Api, run_sql


@pytest.fixture
def hash_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"hash": 0, "verify": 0}
    original_hash, original_verify = Argon2PasswordHasher.hash, Argon2PasswordHasher.verify

    def counting_hash(self: Argon2PasswordHasher, password: str) -> str:
        calls["hash"] += 1
        return original_hash(self, password)

    def counting_verify(self: Argon2PasswordHasher, stored: str, password: str) -> bool:
        calls["verify"] += 1
        return original_verify(self, stored, password)

    monkeypatch.setattr(Argon2PasswordHasher, "hash", counting_hash)
    monkeypatch.setattr(Argon2PasswordHasher, "verify", counting_verify)
    return calls


def test_r01_login_does_the_same_work_for_every_outcome(
    admin: Api, app: FastAPI, hash_calls: dict[str, int]
) -> None:
    admin.post("/api/users", json={"username": "off", "password": "12345678", "role": "staff"})
    off_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "off")
    admin.put(f"/api/users/{off_id}", json={"role": "staff", "active": False})
    for username, password in (
        ("ghost", "x" * 8),
        ("off", "12345678"),
        ADMIN,
        ("admin", "bad-1234"),
    ):
        hash_calls.update(hash=0, verify=0)
        with TestClient(app) as other:
            Api(other).login(username, password)
        assert hash_calls == {"hash": 0, "verify": 1}, username


def test_r03_one_address_cannot_try_many_usernames(admin: Api, app: FastAPI) -> None:
    with TestClient(app, client=("192.168.1.50", 5000)) as device:
        api = Api(device)
        codes = [api.login(f"user{i}", "wrong-pass").status_code for i in range(21)]
    assert codes[:20] == [401] * 20
    assert codes[20] == 429


def test_r03_parallel_guesses_are_still_limited(admin: Api, app: FastAPI) -> None:
    def guess(i: int) -> int:
        api = Api(TestClient(app, client=(f"10.0.0.{i}", 5000)))
        return int(api.login("admin", f"wrong-{i}-pass").status_code)

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(guess, range(10)))
    assert codes.count(401) == 5
    assert codes.count(429) == 5


def test_r03_full_failure_log_keeps_recent_lockouts() -> None:
    log = MemoryLoginFailureLog()
    now = datetime(2026, 11, 22, tzinfo=UTC)
    for _ in range(5):
        log.record("user:admin", now)
    for i in range(MAX_TRACKED_KEYS + 10):
        log.record(f"user:fake{i}", now + timedelta(seconds=1))
    assert len(log.recent("user:admin")) == 5


def test_r13_expired_sessions_are_purged_on_login(admin: Api, app: FastAPI) -> None:
    run_sql(app, "UPDATE sessions SET expires_at = '2000-01-01 00:00:00'")
    with TestClient(app) as other:
        assert Api(other).login(*ADMIN).status_code == 200
    assert run_sql(app, "SELECT count(*) FROM sessions")[0][0] == 1


def test_r23_last_admin_is_a_conflict(admin: Api) -> None:
    (me,) = admin.get("/api/users").json()
    response = admin.put(f"/api/users/{me['id']}", json={"role": "staff", "active": True})
    assert (response.status_code, response.json()["code"]) == (409, "user.last_admin")


def test_r02_large_json_body_rejected_before_parsing(anon: Api) -> None:
    huge = b'{"username": "' + b"a" * (2 * 1024 * 1024) + b'", "password": "x"}'
    response = anon.client.post(
        "/api/auth/login", content=huge, headers={"content-type": "application/json"}
    )
    assert (response.status_code, response.json()["code"]) == (413, "request.too_large")


def test_r02_large_chunked_body_rejected(anon: Api) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(40):
            yield b"x" * 65536

    response = anon.client.post("/api/setup", content=chunks())
    assert response.status_code == 413


def test_r02_csv_upload_keeps_its_own_limit(admin: Api) -> None:
    rows = b"".join(b"T%d,,%s,\n" % (i, b"b" * 1000) for i in range(900))
    data = b"title,category,body,tags\n" + rows
    assert 512 * 1024 < len(data) < 1024 * 1024
    response = admin.post("/api/csv/import", content=data)
    assert (response.status_code, response.json()["imported"]) == (200, 900)


@pytest.mark.parametrize("host", ["evil.example", "attacker.com:8000", "x.y.z"])
def test_r04_foreign_host_header_is_rejected(anon: Api, host: str) -> None:
    response = anon.client.get("/api/setup/status", headers={"host": host})
    assert (response.status_code, response.json()["code"]) == (421, "request.bad_host")


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:8000", "localhost:8000", "192.168.1.20:8000", "[::1]:8000", "mi-pc", "mi-pc.local"],
)
def test_r04_local_hosts_are_allowed(anon: Api, host: str) -> None:
    assert anon.client.get("/api/setup/status", headers={"host": host}).status_code == 200


def test_qa05_long_pasted_query_is_cut_not_rejected(admin: Api) -> None:
    assert admin.get("/api/search", params={"q": "horario " * 1000}).status_code == 200
