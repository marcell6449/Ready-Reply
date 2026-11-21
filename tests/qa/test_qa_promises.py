"""QA: direct checks of the public promises P1, P6 and P7 (API level)."""

import re
import socket
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from readyreply.config import Settings
from readyreply.main import create_app
from tests.conftest import Api, answer_payload, set_variables

STATIC = Path(__file__).resolve().parents[2] / "readyreply" / "web" / "static"


@pytest.mark.promise_p1
def test_p1_variable_saved_once_fills_every_answer(admin: Api) -> None:
    set_variables(admin, hours="L-V 7–5 🕖")
    bodies = ["Abrimos {hours}.", "*Horario:* {hours}\n¡Le esperamos!", "{hours} — {{hours}}"]
    ids = [
        admin.post("/api/answers", json=answer_payload(f"R{i}", body)).json()["id"]
        for i, body in enumerate(bodies)
    ]

    def copies() -> list[str]:
        return [admin.post(f"/api/answers/{answer_id}/copy").json()["text"] for answer_id in ids]

    assert copies() == [
        "Abrimos L-V 7–5 🕖.",
        "*Horario:* L-V 7–5 🕖\n¡Le esperamos!",
        "L-V 7–5 🕖 — {hours}",
    ]
    set_variables(admin, hours="Todos los días 24 h")
    assert copies() == [
        "Abrimos Todos los días 24 h.",
        "*Horario:* Todos los días 24 h\n¡Le esperamos!",
        "Todos los días 24 h — {hours}",
    ]
    previews = {
        r["answer"]["id"]: r["preview"]["text"]
        for r in admin.get("/api/search", params={"q": ""}).json()
    }
    assert [previews[i] for i in ids] == copies()


@pytest.mark.promise_p1
def test_p1_empty_or_unknown_variable_blocks_copy_and_records_nothing(admin: Api) -> None:
    answer = admin.post("/api/answers", json=answer_payload("Pago", "SINPE {sinpe} {nope}")).json()
    set_variables(admin, sinpe="   ")
    result = admin.post(f"/api/answers/{answer['id']}/copy").json()
    assert result == {"text": None, "missing": ["sinpe", "nope"]}
    assert admin.get("/api/stats").json()["total_copies"] == 0


@pytest.mark.promise_p6
def test_p6_stats_order_and_exclusions(admin: Api, app: Any) -> None:
    ids = {
        t: admin.post("/api/answers", json=answer_payload(t, "x")).json()["id"]
        for t in ("A", "B", "C")
    }
    for title, times in (("A", 5), ("B", 3), ("C", 1)):
        for index in range(times):
            with TestClient(app) as other:
                name = f"u{title.lower()}{index}"
                admin.post(
                    "/api/users", json={"username": name, "password": "password-1", "role": "staff"}
                )
                user = Api(other)
                user.login(name, "password-1")
                user.post(f"/api/answers/{ids[title]}/copy")
    stats = admin.get("/api/stats").json()
    assert [(c["title"], c["copies"]) for c in stats["top_copied"]] == [
        ("A", 5),
        ("B", 3),
        ("C", 1),
    ]
    admin.delete(f"/api/answers/{ids['A']}")
    stats = admin.get("/api/stats").json()
    assert [c["title"] for c in stats["top_copied"]] == ["B", "C"]
    assert stats["total_answers"] == 2


@pytest.mark.promise_p6
def test_p6_demo_twice_has_no_duplicates_and_all_copy(admin: Api) -> None:
    for kind in ("soda", "salon", "hardware"):
        admin.post(f"/api/demo/{kind}", json={"mode": "replace"})
        admin.post(f"/api/demo/{kind}", json={"mode": "replace"})
        answers = admin.get("/api/answers").json()
        assert len(answers) >= 12
        assert len({a["title"] for a in answers}) == len(answers)
        for answer in answers:
            assert admin.post(f"/api/answers/{answer['id']}/copy").json()["missing"] == []
    assert admin.post("/api/demo/soda", json={}).json()["code"] == "demo.confirm_replace"
    before = admin.get("/api/answers").json()
    assert admin.post("/api/demo/unknown", json={"mode": "replace"}).status_code == 404
    assert admin.get("/api/answers").json() == before


@pytest.mark.promise_p7
def test_p7_default_provider_never_leaves_the_computer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts: list[Any] = []
    original = socket.socket.connect

    def guarded(self: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) else str(address)
        lan_probe = self.type == socket.SOCK_DGRAM  # lan_ip(): UDP connect sends no packet
        if host not in {"127.0.0.1", "::1", "localhost"} and not lan_probe:
            attempts.append(address)
            raise OSError("blocked")
        return original(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'p7.db'}", open_browser=False, _env_file=None
    )  # default provider: ollama on 127.0.0.1
    assert settings.ai_provider == "ollama"
    with TestClient(create_app(settings)) as client:
        api = Api(client)
        api.setup_admin()
        api.post("/api/demo/soda", json={})
        api.post("/api/unanswered", json={"query": "parqueo gratis"})
        question = api.get("/api/unanswered").json()[0]
        assert api.post("/api/ai/suggest", json={"question_id": question["id"]}).status_code == 200
        api.get("/api/system/qr.svg")
        api.get("/api/csv/export")
    assert attempts == []


@pytest.mark.promise_p7
def test_p7_no_external_urls_in_static_files_and_csp(anon: Api) -> None:
    pattern = re.compile(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
    offenders = [
        str(p.relative_to(STATIC))
        for p in STATIC.rglob("*")
        if p.is_file()
        and p.suffix in {".html", ".js", ".css", ".svg", ".json"}
        and pattern.search(re.sub(r'xmlns="[^"]*"', "", p.read_text(encoding="utf-8")))
    ]
    assert offenders == []
    csp = anon.get("/").headers["content-security-policy"]
    assert "default-src 'self'" in csp and "script-src" not in csp.replace("default-src", "")
