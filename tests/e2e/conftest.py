"""Runs the real server on a free port and drives Chromium with Playwright."""

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from playwright.sync_api import (
    APIResponse,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    ViewportSize,
)

from readyreply.config import Settings
from readyreply.infrastructure.network.lan import lan_ip
from readyreply.main import create_app
from tests.support.seed import seed_business

CHROMIUM = os.environ.get("RR_E2E_CHROMIUM", "/opt/pw-browsers/chromium")
VIEWPORTS: dict[str, ViewportSize] = {
    "desktop": {"width": 1280, "height": 800},
    "phone": {"width": 360, "height": 740},
}
SCREENSHOTS = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
ADMIN_PASSWORD = "admin-pass-1"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class LiveServer:
    def __init__(self, database: Path) -> None:
        self.port = _free_port()
        settings = Settings(
            database_url=f"sqlite:///{database}",
            open_browser=False,
            ai_provider="manual",
            _env_file=None,
        )
        app = create_app(settings)
        config = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.url = f"http://127.0.0.1:{self.port}"
        self.lan_url = f"http://{lan_ip()}:{self.port}"

    def __enter__(self) -> "LiveServer":
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


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[LiveServer]:
    with LiveServer(tmp_path / "e2e.db") as server:
        yield server


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Iterator[Browser]:
    browser = playwright_instance.chromium.launch(executable_path=CHROMIUM)
    yield browser
    browser.close()


@pytest.fixture(params=list(VIEWPORTS))
def device(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def context(browser: Browser, device: str, live_server: LiveServer) -> Iterator[BrowserContext]:
    context = browser.new_context(
        viewport=VIEWPORTS[device],
        device_scale_factor=1,
        has_touch=device == "phone",
        locale="es-CR",
    )
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server.url)
    yield context
    context.close()


@pytest.fixture
def page(context: BrowserContext) -> Iterator[Page]:
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    assert errors == []


def create_admin(page: Page, server: LiveServer) -> None:
    page.goto(server.url)
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_selector("#search-input")


class _Reply:
    def __init__(self, response: APIResponse) -> None:
        self.status_code = response.status
        self._response = response

    def json(self) -> Any:
        return self._response.json()


class PageApi:
    """API calls that share the browser page's session cookie (for test setup only)."""

    def __init__(self, page: Page, server: LiveServer) -> None:
        self._request = page.request
        self._base = server.url
        self._csrf = str(self._request.get(f"{server.url}/api/auth/me").json()["csrf_token"])

    def _headers(self) -> dict[str, str]:
        return {"x-csrf-token": self._csrf}

    def get(self, url: str, **_: Any) -> _Reply:
        return _Reply(self._request.get(self._base + url))

    def post(self, url: str, **kwargs: Any) -> _Reply:
        response = self._request.post(
            self._base + url, data=kwargs.get("json"), headers=self._headers()
        )
        return _Reply(response)

    def put(self, url: str, **kwargs: Any) -> _Reply:
        response = self._request.put(
            self._base + url, data=kwargs.get("json"), headers=self._headers()
        )
        return _Reply(response)

    def delete(self, url: str) -> _Reply:
        return _Reply(self._request.delete(self._base + url, headers=self._headers()))


def load_business(page: Page, server: LiveServer, kind: str = "soda") -> None:
    """Test data: fill the library with a sample business, then show the search."""
    seed_business(PageApi(page, server), kind)
    page.goto(f"{server.url}/#/search")
    page.reload()
    page.wait_for_selector(".card")


def search(page: Page, query: str) -> None:
    page.fill("#search-input", query)
    page.wait_for_timeout(400)


def clipboard(page: Page) -> str:
    return str(page.evaluate("navigator.clipboard.readText()"))


def assert_no_horizontal_scroll(page: Page) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, f"page is {overflow}px wider than the screen"
