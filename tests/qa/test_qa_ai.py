"""QA: the AI flow never saves on its own and always falls back to the manual prompt (P5, F8)."""

import json
import logging
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from readyreply.config import Settings
from readyreply.main import create_app
from tests.conftest import Api, run_sql, set_variables
from tests.qa.conftest import free_port

pytestmark = pytest.mark.promise_p5


class FakeModel:
    """Fake Ollama / OpenAI-compatible server with configurable misbehaviour."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.text = "Sí, tenemos parqueo. Abrimos {hours}."
        self.delay = 0.0
        self.prompts: list[str] = []
        self.auth: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                fake.prompts.append(body.get("prompt") or body["messages"][0]["content"])
                fake.auth.append(self.headers.get("authorization", ""))
                try:
                    fake.respond(self)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the app gave up waiting, as it should

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def payload(self) -> bytes:
        if self.mode == "openai":
            return json.dumps({"choices": [{"message": {"content": self.text}}]}).encode()
        if self.mode == "empty":
            return json.dumps({"response": "   "}).encode()
        if self.mode == "not_json":
            return b"<html>502 Bad Gateway</html>"
        if self.mode == "wrong_shape":
            return json.dumps(["unexpected"]).encode()
        return json.dumps({"response": self.text}).encode()

    def respond(self, handler: BaseHTTPRequestHandler) -> None:
        if self.mode == "sleep":
            time.sleep(self.delay)
        body = self.payload()
        handler.send_response(500 if self.mode == "error" else 200)
        handler.send_header("content-type", "application/json")
        handler.send_header("content-length", str(len(body)))
        handler.end_headers()
        if self.mode == "trickle":  # each chunk arrives before the read timeout, total is slow
            for start in range(0, len(body), 8):
                handler.wfile.write(body[start : start + 8])
                handler.wfile.flush()
                time.sleep(self.delay)
        else:
            handler.wfile.write(body)

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def model() -> Iterator[FakeModel]:
    fake = FakeModel()
    yield fake
    fake.close()


def ai_admin(tmp_path: Path, **overrides: Any) -> Iterator[tuple[Api, Any]]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ai.db'}",
        open_browser=False,
        _env_file=None,
        **overrides,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        api = Api(client)
        api.setup_admin("zorrocapo", "SuperSecreta-99")
        set_variables(api, name="Soda Tica", hours="8 a 5")
        api.post("/api/unanswered", json={"query": "¿Tienen parqueo?"})
        yield api, app


def question_id(api: Api) -> int:
    return int(api.get("/api/unanswered").json()[0]["id"])


def answers(app: Any) -> int:
    return int(run_sql(app, "SELECT count(*) FROM answers")[0][0])


def test_draft_is_never_saved_until_save(tmp_path: Path, model: FakeModel) -> None:
    for api, app in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        qid = question_id(api)
        for _ in range(3):
            response = api.post("/api/ai/suggest", json={"question_id": qid}).json()
            assert response["kind"] == "draft"
            assert response["text"] == model.text
        assert answers(app) == 0
        assert [q["id"] for q in api.get("/api/unanswered").json()] == [qid]
        draft = {"title": "Parqueo", "category": "", "body": "Editado: " + model.text, "tags": []}
        assert api.post(f"/api/unanswered/{qid}/answer", json=draft).status_code == 201
        assert answers(app) == 1
        assert api.get("/api/unanswered").json() == []


@pytest.mark.parametrize("mode", ["error", "empty", "not_json", "wrong_shape"])
def test_provider_failures_fall_back_to_manual_prompt(
    tmp_path: Path, model: FakeModel, mode: str
) -> None:
    model.mode = mode
    for api, app in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        response = api.post("/api/ai/suggest", json={"question_id": question_id(api)})
        assert response.status_code == 200
        body = response.json()
        assert body["kind"] == "manual"
        assert body["notice"] == "ai.unavailable"
        assert "¿Tienen parqueo?" in body["prompt"]
        assert answers(app) == 0


def test_ollama_not_running_falls_back(tmp_path: Path) -> None:
    closed = f"http://127.0.0.1:{free_port()}"
    for api, app in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=closed):
        body = api.post("/api/ai/suggest", json={"question_id": question_id(api)}).json()
        assert (body["kind"], body["notice"]) == ("manual", "ai.unavailable")
        assert answers(app) == 0


def test_slow_provider_beyond_timeout_falls_back(tmp_path: Path, model: FakeModel) -> None:
    model.mode, model.delay = "sleep", 3
    for api, _app in ai_admin(
        tmp_path, ai_provider="ollama", ai_base_url=model.url, ai_timeout_seconds=1
    ):
        started = time.monotonic()
        body = api.post("/api/ai/suggest", json={"question_id": question_id(api)}).json()
        assert body["kind"] == "manual"
        assert time.monotonic() - started < 2.5


def test_timeout_is_a_total_deadline_not_per_chunk(tmp_path: Path, model: FakeModel) -> None:
    """F8-06: a reply that takes longer than RR_AI_TIMEOUT_SECONDS must fall back, even when
    the provider keeps sending small pieces (each piece arrives before the read timeout)."""
    model.mode, model.delay = "trickle", 0.4
    for api, _app in ai_admin(
        tmp_path, ai_provider="ollama", ai_base_url=model.url, ai_timeout_seconds=1
    ):
        started = time.monotonic()
        body = api.post("/api/ai/suggest", json={"question_id": question_id(api)}).json()
        elapsed = time.monotonic() - started
        assert elapsed < 2 and body["kind"] == "manual", (
            f"took {elapsed:.1f}s with a 1s timeout and returned {body['kind']}"
        )


def test_manual_provider_needs_no_network_and_saves_nothing(tmp_path: Path) -> None:
    for api, app in ai_admin(tmp_path, ai_provider="manual", ai_chat_url="http://127.0.0.1:9/"):
        body = api.post("/api/ai/suggest", json={"question_id": question_id(api)}).json()
        assert body["kind"] == "manual"
        assert body["notice"] is None
        assert body["open_url"] == "http://127.0.0.1:9/"
        assert answers(app) == 0


def test_openai_compatible_key_is_sent_but_never_logged(
    tmp_path: Path, model: FakeModel, caplog: pytest.LogCaptureFixture
) -> None:
    model.mode = "openai"
    key = "sk-qa-SECRET-0123456789"
    caplog.set_level(logging.DEBUG)
    for api, app in ai_admin(
        tmp_path, ai_provider="openai_compatible", ai_base_url=model.url, ai_api_key=key
    ):
        body = api.post("/api/ai/suggest", json={"question_id": question_id(api)}).json()
        assert body["kind"] == "draft"
        assert model.auth == [f"Bearer {key}"]
        model.mode = "error"
        api.post("/api/ai/suggest", json={"question_id": question_id(api)})
        assert answers(app) == 0
    assert key not in caplog.text


def test_prompt_has_no_usernames_passwords_or_stats(tmp_path: Path, model: FakeModel) -> None:
    for api, _app in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        api.post(
            "/api/users",
            json={"username": "cajera01", "password": "ClaveCajera-1", "role": "staff"},
        )
        api.post(
            "/api/answers", json={"title": "Horario", "category": "", "body": "{hours}", "tags": []}
        )
        answer_id = api.get("/api/answers").json()[0]["id"]
        for _ in range(7):
            api.post(f"/api/answers/{answer_id}/copy")
        api.post("/api/ai/suggest", json={"question_id": question_id(api)})
    prompt = model.prompts[-1]
    for secret in ("zorrocapo", "SuperSecreta-99", "cajera01", "ClaveCajera-1", "argon2"):
        assert secret not in prompt
    assert "Horario" in prompt and "8 a 5" in prompt and "¿Tienen parqueo?" in prompt


def test_staff_cannot_use_ai(tmp_path: Path, model: FakeModel) -> None:
    for api, app in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        api.post(
            "/api/users", json={"username": "cajera", "password": "password-1", "role": "staff"}
        )
        with TestClient(app) as other:
            staff = Api(other)
            staff.login("cajera", "password-1")
            response = staff.post("/api/ai/suggest", json={"question_id": question_id(api)})
            assert response.status_code == 403
    assert model.prompts == []
