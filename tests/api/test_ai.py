"""F8 and P5: AI suggestions against a fake Ollama / OpenAI-compatible server."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from readyreply.config import Settings
from readyreply.main import create_app
from tests.conftest import Api, set_variables

pytestmark = pytest.mark.promise_p5


class FakeModelServer:
    """Answers like Ollama (/api/generate) or an OpenAI-compatible API (/chat/completions)."""

    def __init__(self) -> None:
        self.reply: Any = {"response": "  Sí, tenemos parqueo. Horario: {hours}  "}
        self.status = 200
        self.requests: list[tuple[str, dict[str, Any], str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                fake.requests.append((self.path, body, self.headers.get("authorization", "")))
                payload = json.dumps(fake.reply).encode()
                self.send_response(fake.status)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def model() -> Iterator[FakeModelServer]:
    server = FakeModelServer()
    yield server
    server.close()


def ai_admin(tmp_path: Path, **settings: Any) -> Iterator[Api]:
    config = Settings(
        database_url=f"sqlite:///{tmp_path / 'ai.db'}",
        open_browser=False,
        _env_file=None,
        **settings,
    )
    with TestClient(create_app(config)) as client:
        api = Api(client)
        api.setup_admin()
        set_variables(api, name="Soda Tica", hours="8 a 5", sinpe="")
        api.post("/api/unanswered", json={"query": "¿Tienen parqueo?"})
        yield api


def suggest(api: Api) -> Any:
    (question,) = api.get("/api/unanswered").json()
    return api.post("/api/ai/suggest", json={"question_id": question["id"]})


def test_ollama_draft_is_never_saved(tmp_path: Path, model: FakeModelServer) -> None:  # F8-01..03
    for api in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        response = suggest(api).json()
        assert response == {
            "kind": "draft",
            "text": "Sí, tenemos parqueo. Horario: {hours}",
            "prompt": None,
            "open_url": None,
            "notice": None,
        }
        assert api.get("/api/answers").json() == []
        assert len(api.get("/api/unanswered").json()) == 1
        path, body, _ = model.requests[0]
        assert (path, body["model"], body["stream"]) == ("/api/generate", "gemma3:4b", False)


def test_prompt_contains_only_business_data(
    tmp_path: Path, model: FakeModelServer
) -> None:  # F8-07
    for api in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        api.post("/api/answers", json={"title": "Horario", "body": "{hours}"})
        suggest(api)
        prompt = model.requests[0][1]["prompt"]
        assert "Soda Tica" in prompt
        assert "{hours} (Horario): 8 a 5" in prompt
        assert "¿Tienen parqueo?" in prompt
        assert "- Horario" in prompt
        assert "{sinpe}" not in prompt
        assert "admin" not in prompt
        assert "admin-pass-1" not in prompt
        assert "español" in prompt


@pytest.mark.parametrize("failure", ["status", "bad_json", "empty", "down"])
def test_unavailable_falls_back_to_manual(  # F8-06
    tmp_path: Path, model: FakeModelServer, failure: str
) -> None:
    url = model.url
    if failure == "status":
        model.status = 404
    elif failure == "bad_json":
        model.reply = {"unexpected": True}
    elif failure == "empty":
        model.reply = {"response": "   "}
    else:
        model.close()
    for api in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=url, ai_timeout_seconds=2):
        response = suggest(api).json()
        assert response["kind"] == "manual"
        assert response["notice"] == "ai.unavailable"
        assert "¿Tienen parqueo?" in response["prompt"]


def test_manual_provider(tmp_path: Path) -> None:  # F8-04
    for api in ai_admin(tmp_path, ai_provider="manual", ai_chat_url="https://chat.example/"):
        response = suggest(api).json()
        assert (response["kind"], response["open_url"], response["notice"]) == (
            "manual",
            "https://chat.example/",
            None,
        )


def test_manual_provider_opens_nothing_by_default(tmp_path: Path) -> None:
    for api in ai_admin(tmp_path, ai_provider="manual"):
        assert suggest(api).json()["open_url"] is None


def test_openai_compatible_provider(tmp_path: Path, model: FakeModelServer) -> None:  # F8-05
    model.reply = {"choices": [{"message": {"content": "Claro que sí."}}]}
    settings = {
        "ai_provider": "openai_compatible",
        "ai_base_url": model.url,
        "ai_api_key": "test-key-123",
        "ai_model": "some-model",
    }
    for api in ai_admin(tmp_path, **settings):
        assert suggest(api).json()["text"] == "Claro que sí."
        path, body, auth = model.requests[0]
        assert (path, body["model"], auth) == (
            "/chat/completions",
            "some-model",
            "Bearer test-key-123",
        )


def test_openai_compatible_bad_reply(tmp_path: Path, model: FakeModelServer) -> None:
    model.reply = {"choices": []}
    settings = {"ai_provider": "openai_compatible", "ai_base_url": model.url, "ai_api_key": "k"}
    for api in ai_admin(tmp_path, **settings):
        assert suggest(api).json()["notice"] == "ai.unavailable"


def test_saving_a_suggestion_is_a_human_action(
    tmp_path: Path, model: FakeModelServer
) -> None:  # F8-02
    for api in ai_admin(tmp_path, ai_provider="ollama", ai_base_url=model.url):
        (question,) = api.get("/api/unanswered").json()
        draft = api.post("/api/ai/suggest", json={"question_id": question["id"]}).json()["text"]
        edited = draft + " ¡Le esperamos!"
        saved = api.post(
            f"/api/unanswered/{question['id']}/answer", json={"title": "Parqueo", "body": edited}
        )
        assert saved.status_code == 201
        assert api.get("/api/unanswered").json() == []


def test_unknown_question(tmp_path: Path) -> None:
    for api in ai_admin(tmp_path, ai_provider="manual"):
        assert api.post("/api/ai/suggest", json={"question_id": 999}).status_code == 404


def test_new_provider_needs_only_a_registry_entry() -> None:  # F8-08
    from readyreply.infrastructure.ai import registry

    assert set(registry.PROVIDERS) == {"ollama", "manual", "openai_compatible"}
    assert set(Settings.model_fields["ai_provider"].annotation.__args__) == set(registry.PROVIDERS)  # type: ignore[union-attr]
