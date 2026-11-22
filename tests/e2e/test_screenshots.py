"""Generates the README screenshots from the real app (docs/screenshots)."""

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import (
    SCREENSHOTS,
    VIEWPORTS,
    LiveServer,
    create_admin,
    load_business,
    search,
)

pytestmark = pytest.mark.e2e


def _capture(page: Page, device: str, name: str) -> None:
    page.wait_for_timeout(300)
    page.screenshot(path=str(SCREENSHOTS / f"{device}-{name}.png"))


def test_capture_screenshots(browser: Browser, live_server: LiveServer, device: str) -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(
        viewport=VIEWPORTS[device], device_scale_factor=2, locale="es-CR", color_scheme="light"
    )
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=live_server.url)
    page = context.new_page()
    create_admin(page, live_server)
    load_business(page, live_server)
    search(page, "a que ora abren")
    expect(page.locator(".card-title").first).to_have_text("Horario")
    page.locator(".card").first.get_by_role("button", name="Copiar").click()
    _capture(page, device, "search")
    search(page, "tienen parqueo")
    expect(page.locator("#recorded-note")).not_to_be_empty(timeout=4000)
    search(page, "aceptan mascotas")
    expect(page.locator("#recorded-note")).not_to_be_empty(timeout=4000)
    page.goto(f"{live_server.url}/#/unanswered")
    page.locator(".list-row").first.get_by_role("button", name="Sugerir con IA").click()
    page.wait_for_selector(".ai-box")
    _capture(page, device, "unanswered")
    page.goto(f"{live_server.url}/#/business")
    _capture(page, device, "business")
    context.close()
