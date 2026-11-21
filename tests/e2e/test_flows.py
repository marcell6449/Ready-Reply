"""Main flows in a real browser, on desktop (1280 px) and phone (360 px)."""

import re
import time

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import (
    LiveServer,
    assert_no_horizontal_scroll,
    clipboard,
    create_admin,
    load_demo,
    search,
)

pytestmark = pytest.mark.e2e


@pytest.mark.promise_p2
@pytest.mark.promise_p3
def test_search_with_typos_and_copy_in_one_click(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server)
    search(page, "a que ora abren")
    first = page.locator(".card").first
    expect(first.locator(".card-title")).to_have_text("Horario")
    first.get_by_role("button", name="Copiar").click()
    expect(page.locator("#toast")).to_contain_text("Copiado")
    text = clipboard(page)
    assert text == ("¡Hola! 👋 En *Soda La Esquina* atendemos lunes a sábado de 6:30 a.m. a "
                    "4:00 p.m. (domingos cerrado). ¡Le esperamos!")


@pytest.mark.promise_p3
def test_line_breaks_and_whatsapp_format_survive_copy(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    page.goto(f"{live_server.url}/#/answers/new")
    page.fill("input[name=title]", "Bienvenida")
    page.fill("textarea[name=body]", "*Hola* 👋\n_Gracias por escribir_\n~Oferta~")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/answers")
    search(page, "bienvenida")
    page.locator(".card").first.get_by_role("button", name="Copiar").click()
    expect(page.locator("#toast")).to_contain_text("Copiado")
    assert clipboard(page) == "*Hola* 👋\n_Gracias por escribir_\n~Oferta~"


def test_missing_variable_blocks_copy(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    page.goto(f"{live_server.url}/#/answers/new")
    page.fill("input[name=title]", "Pago")
    page.click("button.chip-button:has-text('SINPE')")
    expect(page.locator("#variable-usage")).to_contain_text("vacío")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/answers")
    page.evaluate("navigator.clipboard.writeText('antes')")
    search(page, "pago")
    card = page.locator(".card").first
    expect(card.locator(".warning")).to_contain_text("Número de SINPE Móvil")
    card.get_by_role("button", name="Copiar").click(force=True)
    expect(page.locator("#toast")).to_contain_text("sin completar")
    assert clipboard(page) == "antes"


@pytest.mark.promise_p4
def test_unanswered_question_becomes_an_answer(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server)
    search(page, "tienen parqueo")
    expect(page.locator(".empty-title")).to_contain_text("tienen parqueo")
    expect(page.locator("#recorded-note")).to_contain_text("Sin respuesta", timeout=4000)
    page.goto(f"{live_server.url}/#/unanswered")
    row = page.locator(".list-row").filter(has_text="tienen parqueo")
    expect(row).to_contain_text("1")
    row.get_by_role("button", name="Crear respuesta").click()
    expect(page.locator("input[name=title]")).to_have_value("tienen parqueo")
    page.fill("input[name=title]", "Parqueo")
    page.fill("textarea[name=body]", "Sí, tenemos parqueo frente al local.")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/unanswered")
    expect(page.locator(".empty-title")).to_be_visible()
    search(page, "parqueo")
    expect(page.locator(".card-title").first).to_have_text("Parqueo")


@pytest.mark.promise_p5
def test_ai_manual_flow_needs_human_save(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server)
    search(page, "aceptan mascotas")
    expect(page.locator("#recorded-note")).not_to_be_empty(timeout=4000)
    page.goto(f"{live_server.url}/#/unanswered")
    page.get_by_role("button", name="Sugerir con IA").click()
    expect(page.locator(".ai-box textarea[readonly]")).to_have_value(re.compile("aceptan mascotas"))
    answers_before = page.evaluate("fetch('/api/answers').then(r => r.json()).then(a => a.length)")
    page.locator(".ai-box textarea:not([readonly])").fill("¡Sí! Las mascotas son bienvenidas 🐶")
    page.get_by_role("button", name="Revisar y guardar como respuesta").click()
    expect(page.locator("textarea[name=body]")).to_have_value("¡Sí! Las mascotas son bienvenidas 🐶")
    assert page.evaluate("fetch('/api/answers').then(r => r.json()).then(a => a.length)") == answers_before
    page.fill("input[name=title]", "Mascotas")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/unanswered")


def test_staff_sees_only_search_and_unanswered(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    page.goto(f"{live_server.url}/#/users")
    form = page.locator("form.subpanel")
    form.locator("input").nth(0).fill("ana")
    form.locator("input").nth(1).fill("ana-pass-123")
    form.get_by_role("button", name="Crear usuario").click()
    expect(page.locator(".list-row").filter(has_text="ana")).to_be_visible()
    page.click("#logout")
    page.fill("input[name=username]", "ana")
    page.fill("input[name=password]", "ana-pass-123")
    page.click("button[type=submit]")
    page.wait_for_selector("#nav .nav-link")
    assert page.locator("#nav .nav-link").all_inner_texts() == ["🔎\nBuscar", "❓\nSin respuesta"]
    page.goto(f"{live_server.url}/#/users")
    expect(page.locator("#nav [aria-current=page]")).to_contain_text("Buscar")


def test_expired_session_keeps_search(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server)
    search(page, "sinpe")
    expect(page.locator(".card-title").first).to_have_text("Pago por SINPE Móvil")
    page.context.clear_cookies()
    page.locator(".card").first.get_by_role("button", name="Copiar").click()
    expect(page.locator("input[name=username]")).to_be_visible()
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", "admin-pass-1")
    page.click("button[type=submit]")
    expect(page.locator("#search-input")).to_have_value("sinpe")
    expect(page.locator(".card-title").first).to_have_text("Pago por SINPE Móvil")


def test_switch_language_to_english(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    page.click("#lang-toggle")
    expect(page.locator("#search-input")).to_have_attribute("placeholder", "Search an answer… (e.g. hours, sinpe, delivery)")
    expect(page.locator("#nav")).to_contain_text("Search")
    page.reload()
    expect(page.locator("#logout")).to_have_text("Sign out")


def test_html_in_user_data_is_shown_as_text(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    page.goto(f"{live_server.url}/#/answers/new")
    page.fill("input[name=title]", "<img src=x onerror=window.hacked=1>")
    page.fill("textarea[name=body]", "<script>window.hacked=1</script>")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/answers")
    search(page, "img")
    expect(page.locator(".card-title").first).to_have_text("<img src=x onerror=window.hacked=1>")
    assert page.evaluate("window.hacked") is None


def test_no_horizontal_scroll_on_any_screen(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server, "hardware")
    for route in ("search", "unanswered", "answers", "business", "synonyms", "stats", "users",
                  "data", "phone", "answers/new", "more"):
        page.goto(f"{live_server.url}/#/{route}")
        page.wait_for_timeout(250)
        assert_no_horizontal_scroll(page)


def test_copy_works_over_wifi_address(page: Page, live_server: LiveServer, device: str) -> None:
    """F4-06: http://192.168.x.x is not a secure context; the fallback copy must work."""
    if device == "desktop":
        pytest.skip("same behaviour; checked once on the phone viewport")
    create_admin(page, live_server)
    load_demo(page, live_server)
    phone = page.context.new_page()
    phone.goto(live_server.lan_url)
    phone.wait_for_selector("input[name=username]")
    assert phone.evaluate("window.isSecureContext") is False
    phone.fill("input[name=username]", "admin")
    phone.fill("input[name=password]", "admin-pass-1")
    phone.click("button[type=submit]")
    phone.fill("#search-input", "sinpe")
    expect(phone.locator(".card-title").first).to_have_text("Pago por SINPE Móvil")
    phone.locator(".card").first.get_by_role("button", name="Copiar").click()
    expect(phone.locator("#toast")).to_contain_text("Copiado")
    assert "8888-1234" in clipboard(page)


IMPORT_CSV = """async (csv) => {
  const me = await (await fetch('/api/auth/me')).json();
  const response = await fetch('/api/csv/import', {method: 'POST', body: csv,
    headers: {'content-type': 'text/csv', 'x-csrf-token': me.csrf_token}});
  return (await response.json()).imported;
}"""


@pytest.mark.promise_p8
def test_two_seconds_with_1000_answers(page: Page, live_server: LiveServer) -> None:
    create_admin(page, live_server)
    load_demo(page, live_server)
    rows = "\n".join(
        f"Pregunta {i} sobre tema {i % 50},General,Texto de la respuesta {i},t{i}" for i in range(990)
    )
    assert page.evaluate(IMPORT_CSV, "title,category,body,tags\n" + rows) == 990
    count = page.evaluate("fetch('/api/answers').then(r => r.json()).then(a => a.length)")
    assert count >= 1000
    page.goto(f"{live_server.url}/#/search")
    started = time.perf_counter()
    page.fill("#search-input", "simpe")
    expect(page.locator(".card-title").first).to_have_text("Pago por SINPE Móvil")
    page.locator(".card").first.get_by_role("button", name="Copiar").click()
    expect(page.locator("#toast")).to_contain_text("Copiado")
    elapsed = time.perf_counter() - started
    assert "8888-1234" in clipboard(page)
    assert elapsed < 2.0, f"took {elapsed:.2f}s"
