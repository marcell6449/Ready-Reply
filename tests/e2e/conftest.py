"""Runs the real server on a free port and drives Chromium with Playwright."""

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from readyreply.config import Settings
from readyreply.infrastructure.network.lan import lan_ip
from readyreply.main import create_app

CHROMIUM = os.environ.get("RR_E2E_CHROMIUM", "/opt/pw-browsers/chromium")
VIEWPORTS = {"desktop": {"width": 1280, "height": 800}, "phone": {"width": 360, "height": 740}}
SCREENSHOTS = Path(__file__).resolve().parents[2] / "docs" / "screenshots"
ADMIN_PASSWORD = "admin-pass-1"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class LiveServer:
    def __init__(self, database: Path) -> None:
        self.port = _free_port()
        settings = Settings(database_url=f"sqlite:///{database}", open_browser=False,
                            ai_provider="manual", _env_file=None)
        config = uvicorn.Config(create_app(settings), host="0.0.0.0", port=self.port, log_level="warning")
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
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as instance:
        yield instance


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
    context = browser.new_context(viewport=VIEWPORTS[device], device_scale_factor=1,
                                  has_touch=device == "phone", locale="es-CR")
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


def load_demo(page: Page, server: LiveServer, kind: str = "soda") -> None:
    page.goto(f"{server.url}/#/data")
    page.click(f"[data-demo={kind}]")
    page.wait_for_selector(".card")


def search(page: Page, query: str) -> None:
    page.fill("#search-input", query)
    page.wait_for_timeout(400)


def clipboard(page: Page) -> str:
    return str(page.evaluate("navigator.clipboard.readText()"))


def assert_no_horizontal_scroll(page: Page) -> None:
    overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 0, f"page is {overflow}px wider than the screen"
