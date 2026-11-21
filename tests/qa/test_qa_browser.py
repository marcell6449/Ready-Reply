"""QA in a real browser (Chromium): injection, translations, copy, unanswered, AI, speed."""

import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.qa.conftest import (
    PageProbe,
    QaServer,
    api_as_admin,
    clipboard,
    new_context,
    ui_create_admin,
    ui_search,
)
from tests.qa.test_qa_ai import FakeModel

pytestmark = pytest.mark.e2e

PAYLOAD = (
    '<img src=x id=xss1 onerror="window.__xss=1"><b id=xss2>B</b><script>window.__xss=2</script>'
)
SHORT = '<img src=x id=xss3 onerror="window.__xss=3">'
CATALOG = json.loads(
    (
        Path(__file__).resolve().parents[2] / "readyreply/web/static/i18n/translations.json"
    ).read_text(encoding="utf-8")
)
ROUTES = [
    "search",
    "unanswered",
    "answers",
    "answers/new",
    "business",
    "synonyms",
    "stats",
    "users",
    "data",
    "phone",
    "more",
]


def assert_nothing_injected(page: Page) -> None:
    assert page.locator("#xss1, #xss2, #xss3, img[src='x']").count() == 0
    assert page.evaluate("window.__xss") is None
    probe: PageProbe = page.probe  # type: ignore[attr-defined]
    assert probe.errors == []
    assert [d for d in probe.dialogs if not d.startswith("confirm")] == []


def test_html_in_every_field_is_shown_as_text_and_never_runs(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    api = api_as_admin(qa_server)
    variables = api.get("/api/variables").json()
    for variable in variables:
        if variable["key"] == "name":
            variable["value"] = PAYLOAD
    variables += [
        {"key": "wifi", "label": SHORT, "value": PAYLOAD, "builtin": False},
        {"key": "vacia", "label": SHORT, "value": "", "builtin": False},
    ]
    assert api.put("/api/variables", json=variables).status_code == 200
    answer = api.post(
        "/api/answers",
        json={
            "title": PAYLOAD,
            "category": SHORT,
            "body": "{name} | {wifi} | " + PAYLOAD,
            "tags": [SHORT[:40]],
        },
    ).json()
    api.post(
        "/api/answers",
        json={
            "title": "Falta " + SHORT,
            "category": "",
            "body": "Clave: {vacia} {nadie}",
            "tags": [],
        },
    )
    api.post(f"/api/answers/{answer['id']}/copy")
    api.post("/api/unanswered", json={"query": PAYLOAD})
    api.put("/api/synonyms", json={"groups": [["<script>", "<b>x</b>"]]})

    qa_page.goto(f"{qa_server.url}/#/search")
    qa_page.reload()
    qa_page.wait_for_selector(".card")
    card = qa_page.locator(f".card[data-answer-id='{answer['id']}']")
    expect(card.locator(".card-title")).to_have_text(PAYLOAD)
    expect(card.locator(".chip")).to_have_text(SHORT)
    expect(card.locator(".card-text")).to_have_text(f"{PAYLOAD} | {PAYLOAD} | {PAYLOAD}")
    expect(qa_page.locator(".warning").first).to_contain_text(SHORT)
    card.get_by_role("button", name="Copiar", exact=True).click()
    assert clipboard(qa_page) == f"{PAYLOAD} | {PAYLOAD} | {PAYLOAD}"
    assert_nothing_injected(qa_page)

    ui_search(qa_page, PAYLOAD[:150])
    assert_nothing_injected(qa_page)
    for route in ROUTES[1:] + [f"answers/{answer['id']}"]:
        qa_page.goto(f"{qa_server.url}/#/{route}")
        qa_page.wait_for_timeout(300)
        assert_nothing_injected(qa_page)
    qa_page.goto(f"{qa_server.url}/#/unanswered")
    expect(qa_page.locator(".list-row strong").first).to_have_text(PAYLOAD)
    qa_page.goto(f"{qa_server.url}/#/stats")
    expect(qa_page.locator(".ranking li span").first).to_have_text(PAYLOAD)
    qa_page.goto(f"{qa_server.url}/#/answers")
    qa_page.locator(".list-row").filter(has_text="B</b>").first.get_by_role(
        "button", name=CATALOG["es"]["answers.duplicate"]
    ).click()
    qa_page.wait_for_timeout(500)
    expect(qa_page.locator("#toast")).to_contain_text(PAYLOAD)
    assert_nothing_injected(qa_page)


def visible_texts(page: Page) -> str:
    return str(
        page.evaluate(
            "document.body.innerText + '\\n' + [...document.querySelectorAll('[placeholder]')]"
            ".map(e => e.placeholder).join('\\n') + '\\n' + document.title"
        )
    )


SPANISH_ONLY = sorted(
    {
        es
        for key, es in CATALOG["es"].items()
        if es != CATALOG["en"][key]
        and "{" not in es
        and len(es) >= 6
        and not key.startswith(("server.", "error.", "demo."))
    },
    key=len,
    reverse=True,
)


def test_switching_to_english_translates_every_screen_and_is_remembered(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    qa_page.click("#lang-toggle")
    expect(qa_page.locator("#lang-toggle")).to_have_text("ES")
    for route in ROUTES:
        qa_page.goto(f"{qa_server.url}/#/{route}")
        qa_page.wait_for_timeout(300)
        text = visible_texts(qa_page)
        leftovers = [es for es in SPANISH_ONLY if es in text]
        assert leftovers == [], (route, leftovers[:5])
        raw_keys = [key for key in CATALOG["en"] if key in text]
        assert raw_keys == [], (route, raw_keys)
    qa_page.reload()
    qa_page.wait_for_selector("#search-input")
    expect(qa_page.locator("#lang-toggle")).to_have_text("ES")
    expect(qa_page.locator("#nav")).to_contain_text("Search")
    qa_page.click("#logout")
    expect(qa_page.locator("h1")).to_have_text(CATALOG["en"]["login.title"])
    qa_page.click("#lang-toggle")
    qa_page.wait_for_selector("h1")
    expect(qa_page.locator("h1")).to_have_text(CATALOG["es"]["login.title"])


def test_ai_prompt_is_in_the_language_the_user_chose(qa_page: Page, qa_server: QaServer) -> None:
    """F8-07: the prompt asks for a reply in the UI language."""
    ui_create_admin(qa_page, qa_server)
    api = api_as_admin(qa_server)
    api.post("/api/unanswered", json={"query": "do you have parking"})
    qa_page.click("#lang-toggle")
    qa_page.goto(f"{qa_server.url}/#/unanswered")
    qa_page.get_by_role("button", name="Suggest with AI").click()
    prompt = qa_page.locator(".ai-box textarea[readonly]")
    expect(prompt).to_be_visible()
    value = prompt.input_value()
    assert CATALOG["en"]["server.ai.language"] in value, value[:200]


@pytest.mark.promise_p3
@pytest.mark.parametrize("device", ["desktop", "phone"])
def test_p3_one_click_copy_keeps_whatsapp_text_exactly(
    qa_browser: Browser, qa_server: QaServer, device: str
) -> None:
    context = new_context(qa_browser, qa_server, device)
    page = context.new_page()
    page.probe = PageProbe(page)  # type: ignore[attr-defined]
    ui_create_admin(page, qa_server)
    api = api_as_admin(qa_server)
    variables = api.get("/api/variables").json()
    for variable in variables:
        if variable["key"] == "name":
            variable["value"] = "Soda *Tica* 🇨🇷"
    api.put("/api/variables", json=variables)
    body = (
        "*Hola* 👋 desde {name}\n_Gracias_ ~Oferta~ ```código```\n\n"
        "👨\u200d👩\u200d👧 עברית {{literal}}\n• punto\n1. uno   "
    )
    api.post("/api/answers", json={"title": "Bienvenida", "category": "", "body": body, "tags": []})
    expected = (
        "*Hola* 👋 desde Soda *Tica* 🇨🇷\n_Gracias_ ~Oferta~ ```código```\n\n"
        "👨\u200d👩\u200d👧 עברית {literal}\n• punto\n1. uno"
    )
    page.goto(qa_server.url)
    ui_search(page, "bienvenida")
    page.locator(".card").first.get_by_role("button", name="Copiar", exact=True).click()
    expect(page.locator("#toast")).to_contain_text("Copiado")
    assert clipboard(page) == expected
    copies = api.get("/api/stats").json()["total_copies"]
    assert copies == 1
    assert page.probe.errors == []  # type: ignore[attr-defined]
    context.close()


@pytest.mark.promise_p4
def test_p4_unanswered_question_appears_and_disappears_when_answered(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    ui_search(qa_page, "¿Tienen estacionamiento para motos?")
    expect(qa_page.locator("#recorded-note")).not_to_be_empty(timeout=4000)
    qa_page.goto(f"{qa_server.url}/#/unanswered")
    row = qa_page.locator(".list-row").filter(has_text="estacionamiento para motos")
    expect(row).to_contain_text("veces buscada: 1")
    row.get_by_role("button", name="Crear respuesta").click()
    expect(qa_page.locator("input[name=title]")).to_have_value(
        "¿Tienen estacionamiento para motos?"
    )
    qa_page.fill("textarea[name=body]", "Sí, hay espacio para motos al frente 🏍️")
    qa_page.click("button[type=submit]")
    qa_page.wait_for_url("**/#/unanswered")
    expect(qa_page.locator(".list-row")).to_have_count(0)
    ui_search(qa_page, "estacionamiento motos")
    expect(qa_page.locator(".card-title").first).to_have_text("¿Tienen estacionamiento para motos?")


def test_fast_typing_records_nothing(qa_page: Page, qa_server: QaServer) -> None:
    ui_create_admin(qa_page, qa_server)
    for text in ("p", "pa", "par", "parq", "parqu", "parque"):
        qa_page.fill("#search-input", text)
        qa_page.wait_for_timeout(200)
    qa_page.fill("#search-input", "")
    qa_page.wait_for_timeout(2000)
    assert api_as_admin(qa_server).get("/api/unanswered").json() == []


def test_expired_session_on_copy_goes_to_login_and_keeps_the_search(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    api = api_as_admin(qa_server)
    api.post("/api/demo/soda", json={})
    qa_page.goto(qa_server.url)
    ui_search(qa_page, "horario")
    qa_page.context.clear_cookies()
    qa_page.locator(".card").first.get_by_role("button", name="Copiar", exact=True).click()
    expect(qa_page.locator("input[name=username]")).to_be_visible()
    qa_page.fill("input[name=username]", "admin")
    qa_page.fill("input[name=password]", "admin-pass-1")
    qa_page.click("button[type=submit]")
    expect(qa_page.locator("#search-input")).to_have_value("horario")
    assert qa_page.probe.errors == []  # type: ignore[attr-defined]


@pytest.fixture
def model() -> Iterator[FakeModel]:
    fake = FakeModel()
    yield fake
    fake.close()


@pytest.mark.promise_p5
def test_p5_ai_draft_in_browser_is_saved_only_on_save(
    qa_browser: Browser, qa_server_factory: Callable[..., QaServer], model: FakeModel
) -> None:
    server = qa_server_factory(ai_provider="ollama", ai_base_url=model.url)
    context = new_context(qa_browser, server)
    page = context.new_page()
    page.probe = PageProbe(page)  # type: ignore[attr-defined]
    ui_create_admin(page, server)
    api = api_as_admin(server)
    api.post("/api/unanswered", json={"query": "¿Tienen parqueo?"})
    model.text = "Sí 🚗 tenemos parqueo <b>gratis</b>"

    page.goto(f"{server.url}/#/unanswered")
    page.get_by_role("button", name="Sugerir con IA").click()
    draft = page.locator(".ai-box textarea")
    expect(draft).to_have_value(model.text)
    assert api.get("/api/answers").json() == []
    page.goto(f"{server.url}/#/search")
    page.goto(f"{server.url}/#/unanswered")
    assert api.get("/api/answers").json() == []
    assert len(api.get("/api/unanswered").json()) == 1

    page.get_by_role("button", name="Sugerir con IA").click()
    expect(draft).to_have_value(model.text)
    draft.fill("Sí, tenemos parqueo gratis 🚗")
    page.get_by_role("button", name="Revisar y guardar como respuesta").click()
    expect(page.locator("textarea[name=body]")).to_have_value("Sí, tenemos parqueo gratis 🚗")
    assert api.get("/api/answers").json() == []
    page.click("button[type=submit]")
    page.wait_for_url("**/#/unanswered")
    assert [a["body"] for a in api.get("/api/answers").json()] == ["Sí, tenemos parqueo gratis 🚗"]
    assert api.get("/api/unanswered").json() == []
    assert page.probe.errors == []  # type: ignore[attr-defined]
    context.close()


@pytest.mark.promise_p5
def test_p5_ai_failure_in_browser_shows_manual_prompt(
    qa_browser: Browser, qa_server_factory: Callable[..., QaServer], model: FakeModel
) -> None:
    model.mode = "error"
    server = qa_server_factory(ai_provider="ollama", ai_base_url=model.url)
    context = new_context(qa_browser, server)
    page = context.new_page()
    ui_create_admin(page, server)
    api = api_as_admin(server)
    api.post("/api/unanswered", json={"query": "¿Aceptan mascotas?"})
    page.goto(f"{server.url}/#/unanswered")
    page.get_by_role("button", name="Sugerir con IA").click()
    expect(page.locator(".ai-box .warning")).to_have_text(CATALOG["es"]["ai.unavailable"])
    prompt = page.locator(".ai-box textarea[readonly]").input_value()
    assert "¿Aceptan mascotas?" in prompt
    page.get_by_role("button", name="Copiar texto").click()
    assert clipboard(page) == prompt
    assert api.get("/api/answers").json() == []
    context.close()


@pytest.mark.promise_p2
def test_p2_phone_typing_finds_opening_hours(qa_browser: Browser, qa_server: QaServer) -> None:
    context = new_context(qa_browser, qa_server, "phone")
    page = context.new_page()
    ui_create_admin(page, qa_server)
    api_as_admin(qa_server).post("/api/demo/soda", json={})
    page.goto(qa_server.url)
    page.wait_for_selector(".card")  # typing before the search bar is shown would be lost
    page.locator("#search-input").press_sequentially("a que hora abren", delay=60)
    expect(page.locator(".card-title").first).to_have_text("Horario")
    assert page.evaluate("document.documentElement.scrollWidth - window.innerWidth") <= 0
    context.close()


@pytest.mark.perf
@pytest.mark.promise_p8
def test_p8_type_to_clipboard_under_2_seconds_with_1000_answers(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    api = api_as_admin(qa_server)
    api.post("/api/demo/soda", json={})
    lines = ["title,category,body,tags"] + [
        f"Respuesta generada {i},Cat {i % 9},Texto de relleno número {i} con precio y envio,x{i}"
        for i in range(1000)
    ]
    assert api.post("/api/csv/import", content="\n".join(lines).encode()).json()["imported"] == 1000
    qa_page.goto(qa_server.url)
    qa_page.wait_for_selector(".card")
    timings: list[float] = []
    for query in ("horario", "simpe", "a que ora abren", "envios"):
        qa_page.fill("#search-input", "")
        qa_page.wait_for_timeout(300)
        qa_page.evaluate("navigator.clipboard.writeText('')")
        started = time.perf_counter()
        qa_page.locator("#search-input").press_sequentially(query, delay=20)
        first = qa_page.locator(".card").first
        expect(first.locator(".card-title")).not_to_have_text("Respuesta generada 0")
        first.get_by_role("button", name="Copiar", exact=True).click()
        qa_page.wait_for_function("navigator.clipboard.readText().then(t => t.length > 0)")
        timings.append(time.perf_counter() - started)
    print(f"\nQA P8 e2e: type → clipboard {[round(t, 2) for t in timings]} s")
    assert max(timings) < 2


def test_variables_page_saves_emoji_and_rejects_bad_key_in_the_ui(
    qa_page: Page, qa_server: QaServer
) -> None:
    ui_create_admin(qa_page, qa_server)
    qa_page.goto(f"{qa_server.url}/#/business")
    qa_page.locator(".variable textarea").nth(1).fill("L-V 7am–5pm 🕖")
    qa_page.get_by_role("button", name=CATALOG["es"]["business.add"]).click()
    custom = qa_page.locator("fieldset.custom").last
    custom.locator("input").nth(0).fill("Wi-Fi")
    custom.locator("input").nth(1).fill("Wi Fi")
    custom.locator("textarea").fill("clave")
    qa_page.click("form button[type=submit]")
    qa_page.wait_for_timeout(500)  # the key field's pattern (or the server) blocks the save
    saved = {v["key"] for v in api_as_admin(qa_server).get("/api/variables").json()}
    assert "wifi" not in saved and "Wi Fi" not in saved
    custom.locator("input").nth(1).fill("wifi")
    qa_page.click("form button[type=submit]")
    expect(qa_page.locator("#toast")).to_be_visible()
    values: dict[str, Any] = {
        v["key"]: v["value"] for v in api_as_admin(qa_server).get("/api/variables").json()
    }
    assert values["hours"] == "L-V 7am–5pm 🕖"
    assert values["wifi"] == "clave"
