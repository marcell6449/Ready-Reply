"""P7: data stays on the computer; logs carry nothing sensitive; security headers."""

import logging
import re
import socket
from pathlib import Path
from typing import Any

import pytest

from tests.conftest import ADMIN, Api, answer_payload, set_variables

pytestmark = pytest.mark.promise_p7
STATIC = Path(__file__).resolve().parents[2] / "readyreply" / "web" / "static"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testserver"}


@pytest.fixture
def no_internet(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Fail on any outbound connection that is not to this computer."""
    attempts: list[Any] = []
    original = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK and not str(host).startswith("10.255.255.255"):
            attempts.append(address)
            raise OSError(f"blocked outbound connection to {address}")
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    return attempts


def test_full_usage_never_leaves_the_computer(admin: Api, no_internet: list[Any]) -> None:
    admin.post("/api/demo/soda", json={})
    set_variables(admin, hours="8 a 5")
    results = admin.get("/api/search", params={"q": "sinpe"}).json()
    admin.post(f"/api/answers/{results[0]['answer']['id']}/copy")
    admin.post("/api/unanswered", json={"query": "parqueo"})
    (question,) = admin.get("/api/unanswered").json()
    admin.post("/api/ai/suggest", json={"question_id": question["id"]})
    admin.get("/api/stats")
    admin.get("/api/csv/export")
    admin.get("/api/system/lan")
    admin.get("/api/system/qr.svg")
    assert no_internet == []


def test_static_files_reference_no_external_hosts() -> None:
    pattern = re.compile(r"https?://", re.IGNORECASE)
    offenders = [
        str(path.relative_to(STATIC))
        for path in STATIC.rglob("*")
        if path.is_file()
        and path.suffix in {".html", ".js", ".css"}
        and pattern.search(path.read_text())
    ]
    assert offenders == []


def test_security_headers(anon: Api) -> None:
    headers = anon.get("/").headers
    assert headers["content-security-policy"].startswith("default-src 'self'")
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["referrer-policy"] == "no-referrer"


def test_logs_contain_no_secrets_or_search_text(
    anon: Api, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    anon.setup_admin()
    anon.post("/api/answers", json=answer_payload("Secreto", "texto-privado"))
    anon.get("/api/search", params={"q": "busqueda-privada"})
    anon.post("/api/unanswered", json={"query": "pregunta-privada"})
    server_records = [r for r in caplog.records if not r.name.startswith("httpx")]
    logged = "\n".join(record.getMessage() for record in server_records)
    assert "GET /api/search 200" in logged
    for secret in (ADMIN[1], "busqueda-privada", "pregunta-privada", "texto-privado", anon.csrf):
        assert secret not in logged
    session = anon.client.cookies.get("rr_session") or "missing"
    assert session not in logged


def test_index_served(anon: Api) -> None:
    response = anon.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
