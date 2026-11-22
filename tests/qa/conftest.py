"""QA fixtures: live servers with custom settings, Playwright, a controllable clock, helpers.

The fixtures `settings`, `app`, `client`, `anon`, `admin` and `staff` come from tests/conftest.py.
"""

import os
import socket
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from readyreply.config import Settings
from readyreply.infrastructure.clock import SystemClock
from readyreply.main import create_app

CHROMIUM = os.environ.get("RR_E2E_CHROMIUM", "/opt/pw-browsers/chromium")
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 360, "height": 740}}
ADMIN_PASSWORD = "admin-pass-1"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class QaServer:
    """The real app under uvicorn in a thread, with any settings."""

    def __init__(self, database: Path, **overrides: Any) -> None:
        self.port = free_port()
        values: dict[str, Any] = {
            "database_url": f"sqlite:///{database}",
            "open_browser": False,
            "ai_provider": "manual",
        }
        values.update(overrides)
        self.settings = Settings(_env_file=None, **values)
        self.app = create_app(self.settings)
        config = uvicorn.Config(self.app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.url = f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "QaServer":
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("server did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *args: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


class HttpUser:
    """A browser-like httpx client against a live server (cookies + CSRF header)."""

    def __init__(self, base_url: str) -> None:
        self.http = httpx.Client(base_url=base_url, timeout=60)
        self.csrf = ""

    def _pre_csrf(self) -> str:
        return str(self.http.get("/api/setup/status").json()["csrf_token"])

    def setup(self, username: str = "admin", password: str = ADMIN_PASSWORD) -> httpx.Response:
        response = self.http.post(
            "/api/setup",
            json={"username": username, "password": password},
            headers={"x-csrf-token": self._pre_csrf()},
        )
        self.csrf = response.json().get("csrf_token", "")
        return response

    def login(self, username: str, password: str) -> httpx.Response:
        response = self.http.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"x-csrf-token": self._pre_csrf()},
        )
        self.csrf = response.json().get("csrf_token", "")
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.http.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        headers = {"x-csrf-token": self.csrf} | kwargs.pop("headers", {})
        return self.http.post(url, headers=headers, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.http.put(url, headers={"x-csrf-token": self.csrf}, **kwargs)

    def delete(self, url: str) -> httpx.Response:
        return self.http.delete(url, headers={"x-csrf-token": self.csrf})

    def close(self) -> None:
        self.http.close()


@pytest.fixture
def qa_server_factory(tmp_path: Path) -> Iterator[Callable[..., QaServer]]:
    started: list[QaServer] = []

    def start(**overrides: Any) -> QaServer:
        server = QaServer(tmp_path / f"qa-{len(started)}.db", **overrides)
        server.__enter__()
        started.append(server)
        return server

    yield start
    for server in started:
        server.__exit__()


@pytest.fixture
def qa_server(qa_server_factory: Callable[..., QaServer]) -> QaServer:
    return qa_server_factory()


class FakeClock:
    """Replaces SystemClock.now for the whole process during one test."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(SystemClock, "now", lambda _self: clock.now)
    return clock


# --- Playwright -------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qa_playwright(playwright_instance: Playwright) -> Playwright:
    """Shares the single Playwright instance (only one can run per process)."""
    return playwright_instance


@pytest.fixture(scope="session")
def qa_browser(qa_playwright: Playwright) -> Iterator[Browser]:
    browser = qa_playwright.chromium.launch(executable_path=CHROMIUM)
    yield browser
    browser.close()


def new_context(browser: Browser, server: QaServer, device: str = "desktop") -> BrowserContext:
    context = browser.new_context(
        viewport=VIEWPORTS[device],  # type: ignore[arg-type]
        device_scale_factor=1,
        has_touch=device == "phone",
        locale="es-CR",
    )
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=server.url)
    return context


@pytest.fixture
def qa_context(qa_browser: Browser, qa_server: QaServer) -> Iterator[BrowserContext]:
    context = new_context(qa_browser, qa_server)
    yield context
    context.close()


class PageProbe:
    """Collects script errors and dialogs so a test can prove that nothing ran."""

    def __init__(self, page: Page) -> None:
        self.page = page
        self.errors: list[str] = []
        self.dialogs: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("dialog", self._on_dialog)

    def _on_dialog(self, dialog: Any) -> None:
        self.dialogs.append(f"{dialog.type}: {dialog.message}")
        if dialog.type == "confirm":
            dialog.accept()
        else:
            dialog.dismiss()


@pytest.fixture
def qa_page(qa_context: BrowserContext) -> Iterator[Page]:
    page = qa_context.new_page()
    page.probe = PageProbe(page)  # type: ignore[attr-defined]
    yield page


def ui_create_admin(page: Page, server: QaServer) -> None:
    page.goto(server.url)
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector("#search-input")


def ui_search(page: Page, query: str) -> None:
    page.fill("#search-input", query)
    page.wait_for_timeout(450)


def clipboard(page: Page) -> str:
    return str(page.evaluate("navigator.clipboard.readText()"))


def api_as_admin(server: QaServer) -> HttpUser:
    """Log in through the API as the admin created by the browser (or create it)."""
    user = HttpUser(server.url)
    status = user.get("/api/setup/status").json()
    if status["needs_setup"]:
        assert user.setup().status_code == 200
    else:
        assert user.login("admin", ADMIN_PASSWORD).status_code == 200
    return user
