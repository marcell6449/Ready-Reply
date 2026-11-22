"""Capture a numbered screenshot tour of every Ready Reply screen into docs/tour/.

Starts the real app on a temporary database, drives Chromium like a person would,
and checks each step before taking its picture. Usage: python scripts/capture_tour.py
"""

import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
from playwright.sync_api import Page, expect, sync_playwright

from readyreply.config import Settings
from readyreply.main import create_app

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "tour"
CHROMIUM = os.environ.get("RR_E2E_CHROMIUM", "/opt/pw-browsers/chromium")
PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1366, "height": 860}
ADMIN = ("duena", "clave-segura-1")
STAFF = ("cajera", "clave-cajera-1")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_server(database: Path) -> tuple[uvicorn.Server, str]:
    port = free_port()
    settings = Settings(
        database_url=f"sqlite:///{database}",
        open_browser=False,
        ai_provider="ollama",
        ai_base_url=f"http://127.0.0.1:{free_port()}",
        ai_timeout_seconds=2,
        chat_folder=str(database.parent / "chats"),
        downloads_folder="",
        auto_import_seconds=0.5,
        auto_import_stable_seconds=0,
        _env_file=None,
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server, f"http://127.0.0.1:{port}"


class Tour:
    def __init__(self, page: Page, url: str, device: str) -> None:
        self.page = page
        self.url = url
        self.device = device

    def shot(self, name: str, *, focus: str | None = None, keep_toast: bool = False) -> None:
        if not keep_toast:
            expect(self.page.locator("#toast.visible")).to_have_count(0, timeout=4000)
        if focus:
            self.page.locator(focus).first.evaluate("el => el.scrollIntoView({block: 'center'})")
        self.page.wait_for_timeout(600)
        path = OUT / f"{name}-{self.device}.png"
        self.page.screenshot(path=str(path))
        print(f"  {path.relative_to(ROOT)}")

    def go(self, route: str) -> None:
        self.page.goto(f"{self.url}/#/{route}")
        self.page.wait_for_timeout(300)

    def search(self, query: str) -> None:
        self.page.fill("#search-input", query)
        self.page.wait_for_timeout(450)

    def sign_in(self, username: str, password: str) -> None:
        self.page.fill("input[name=username]", username)
        self.page.fill("input[name=password]", password)
        self.page.click("button[type=submit]")
        self.page.wait_for_selector("#search-input")


def admin_tour(tour: Tour) -> None:
    page = tour.page
    page.goto(tour.url)
    expect(page.locator("h1")).to_have_text("Bienvenido a Ready Reply")
    page.fill("input[name=username]", ADMIN[0])
    page.fill("input[name=password]", ADMIN[1])
    page.fill("input[name=whatsapp]", "8888-1234")
    tour.shot("01-crear-administrador")
    page.click("button[type=submit]")
    expect(page.locator(".linked")).to_contain_text("+506 8888 1234")
    tour.shot("01b-bienvenida-numero-asociado")
    import_chats(tour)
    tour.search("a que ora abren")
    expect(page.locator(".card").first).to_contain_text("6:30 a.m.")
    tour.shot("03-buscar-con-errores-de-tipeo")
    page.locator(".card").first.get_by_role("button", name="Copiar").click()
    expect(page.locator("#toast")).to_contain_text("Copiado")
    tour.shot("04-copiado-con-un-clic", keep_toast=True)
    tour.search("simpe")
    expect(page.locator(".card").first).to_contain_text("8888-1234")
    tour.shot("05-buscar-sinpe")
    missing_variable(tour)
    unanswered_flow(tour)
    admin_screens(tour)


CHATS = ROOT / "tests" / "fixtures" / "whatsapp"
CHAT_FILES = ("android_soda.txt", "android_soda_2.txt", "ios_soda.txt")


def import_chats(tour: Tour) -> None:
    page = tour.page
    tour.go("data")
    tour.shot("02-importar-desde-whatsapp")
    page.set_input_files("#chat-files", [str(CHATS / name) for name in CHAT_FILES])
    expect(page.locator(".chat-preview")).to_contain_text("Esto encontramos")
    tour.shot("02b-revisar-lo-encontrado")
    tour.shot("02c-respuestas-encontradas", focus=".chat-preview .pick-card")
    page.get_by_role("button", name="Guardar todo").click()
    expect(page.locator("#chat-preview")).to_contain_text("Respuestas creadas")
    tour.shot("02d-importacion-lista")
    automatic_import(tour)


def automatic_import(tour: Tour) -> None:
    page = tour.page
    folder = Path(page.locator("#auto-import code").first.inner_text())
    shutil.copy(CHATS / "android_english.txt", folder / "Chat de WhatsApp con John.txt")
    expect(page.locator("#toast")).to_contain_text("Se importó un chat nuevo", timeout=15000)
    page.locator("#auto-import").evaluate("el => el.scrollIntoView({block: 'start'})")
    tour.shot("02e-importacion-automatica", keep_toast=True)


def missing_variable(tour: Tour) -> None:
    page = tour.page
    tour.go("answers/new")
    page.fill("input[name=title]", "Clave del Wi-Fi")
    page.fill("textarea[name=body]", "La clave del Wi-Fi es: {wifi} 📶")
    page.fill("input[name=tags]", "wifi, internet")
    tour.shot("06-editor-de-respuesta")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/answers")
    tour.search("wifi")
    expect(page.locator(".card .warning")).to_be_visible()
    tour.shot("07-falta-un-dato-no-se-copia")


def unanswered_flow(tour: Tour) -> None:
    page = tour.page
    for question in ("tienen parqueo", "aceptan mascotas"):
        tour.search(question)
        expect(page.locator("#recorded-note")).not_to_be_empty(timeout=4000)
    tour.shot("08-pregunta-sin-respuesta")
    tour.go("unanswered")
    tour.shot("09-lista-sin-respuesta")
    page.locator(".list-row").first.get_by_role("button", name="Sugerir con IA").click()
    page.wait_for_selector(".ai-box")
    tour.shot("10-sugerencia-de-ia")
    page.locator(".ai-box textarea:not([readonly])").fill(
        "¡Claro! Las mascotas son bienvenidas en nuestra terraza 🐶. Le esperamos {hours}."
    )
    page.get_by_role("button", name="Revisar y guardar como respuesta").click()
    page.fill("input[name=title]", "Mascotas")
    tour.shot("11-revisar-antes-de-guardar")
    page.click("button[type=submit]")
    page.wait_for_url("**/#/unanswered")


def admin_screens(tour: Tour) -> None:
    page = tour.page
    tour.go("answers")
    tour.shot("12-lista-de-respuestas")
    tour.go("business")
    tour.shot("13-datos-del-negocio")
    tour.go("synonyms")
    tour.shot("14-sinonimos")
    tour.go("stats")
    tour.shot("15-estadisticas")
    tour.go("users")
    form = page.locator("form.subpanel")
    form.locator("input").nth(0).fill(STAFF[0])
    form.locator("input").nth(1).fill(STAFF[1])
    form.get_by_role("button", name="Crear usuario").click()
    expect(page.locator(".list-row").filter(has_text=STAFF[0])).to_be_visible()
    tour.shot("16-usuarios-y-roles")
    csv_import(tour)
    tour.go("phone")
    expect(page.locator("img.qr")).to_be_visible()
    tour.shot("18-abrir-en-el-celular")
    tour.go("more")
    tour.shot("19-menu-mas")


SAMPLE_CSV = (
    "title,category,body,tags\nHorario de feriados,Info,Abrimos {hours},feriado\n"
    ",Info,Fila sin título,\nPrecios,Info,Duplicado,\n"
)


def csv_import(tour: Tour) -> None:
    page = tour.page
    tour.go("data")
    with tempfile.TemporaryDirectory() as folder:
        csv_file = Path(folder) / "respuestas.csv"
        csv_file.write_text(SAMPLE_CSV, encoding="utf-8")
        page.set_input_files("#csv-file", str(csv_file))
        page.get_by_role("button", name="Importar CSV").click()
        expect(page.locator("#import-report")).to_contain_text("Fila")
    tour.shot("17-importar-csv-con-reporte", focus="#import-report")


def staff_tour(tour: Tour) -> None:
    page = tour.page
    page.click("#logout")
    tour.sign_in(*STAFF)
    tour.search("hacen envios")
    tour.shot("20-dependiente-solo-busca-y-copia")
    page.click("#lang-toggle")
    tour.search("sinpe")
    tour.shot("21-interfaz-en-ingles")


def run(device: str, viewport: dict[str, int], full: bool) -> None:
    with tempfile.TemporaryDirectory() as folder:
        server, url = start_server(Path(folder) / "tour.db")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=CHROMIUM)
            context = browser.new_context(
                viewport=viewport,
                device_scale_factor=2,
                locale="es-CR",
                color_scheme="light",
                has_touch=device == "celular",
            )
            context.grant_permissions(["clipboard-read", "clipboard-write"], origin=url)
            tour = Tour(context.new_page(), url, device)
            admin_tour(tour)
            if full:
                staff_tour(tour)
            browser.close()
        server.should_exit = True


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    print("Phone (390 px):")
    run("celular", PHONE, full=True)
    print("Desktop (1366 px):")
    run("computadora", DESKTOP, full=False)


if __name__ == "__main__":
    main()
