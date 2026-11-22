"""Automatic import: chats that appear in the watched folders are imported by themselves."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from readyreply.config import Settings
from readyreply.main import create_app
from tests.conftest import Api, set_variables

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "whatsapp"


class Folders:
    def __init__(self, root: Path) -> None:
        self.chats = root / "Chats de WhatsApp"
        self.downloads = root / "Downloads"
        self.downloads.mkdir()


@pytest.fixture
def folders(tmp_path: Path) -> Folders:
    return Folders(tmp_path)


@pytest.fixture
def owner(tmp_path: Path, folders: Folders) -> Iterator[Api]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'auto.db'}",
        open_browser=False,
        ai_provider="manual",
        chat_folder=str(folders.chats),
        downloads_folder=str(folders.downloads),
        auto_import_seconds=0,
        auto_import_stable_seconds=0,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        api = Api(client)
        api.setup_admin()
        yield api


def scan(api: Api) -> None:
    api.client.app.state.container.chat_watcher.scan_once()  # type: ignore[attr-defined]


def drop(folder: Path, fixture: str, name: str | None = None) -> Path:
    target = folder / (name or fixture)
    shutil.copy(FIXTURES / fixture, target)
    return target


def status(api: Api) -> dict[str, object]:
    result: dict[str, object] = api.get("/api/whatsapp/auto").json()
    return result


def test_the_chat_folder_is_created_and_watched(owner: Api, folders: Folders) -> None:
    assert folders.chats.is_dir()
    current = status(owner)
    assert current["enabled"] is False  # disabled in tests; the app enables it by default
    assert str(folders.chats) in current["folders"]  # type: ignore[operator]


def test_a_chat_dropped_in_the_folder_is_imported_by_itself(owner: Api, folders: Folders) -> None:
    for name in ("android_soda.txt", "android_soda_2.txt", "ios_soda.txt"):
        drop(folders.chats, name)
    scan(owner)
    titles = [a["title"] for a in owner.get("/api/answers").json()]
    assert any("abren" in title.casefold() for title in titles)
    variables = {v["key"]: v["value"] for v in owner.get("/api/variables").json()}
    assert variables["sinpe"] == "8888-1234 a nombre de María Rodríguez"
    parking = next(q for q in owner.get("/api/unanswered").json() if "parqueo" in q["text"])
    assert parking["times_searched"] == 2
    recent = status(owner)["recent"]
    assert len(recent) == 3  # type: ignore[arg-type]


def test_nothing_is_imported_twice(owner: Api, folders: Folders) -> None:
    drop(folders.chats, "android_soda.txt")
    scan(owner)
    scan(owner)
    drop(folders.chats, "android_soda.txt", "copia.txt")
    scan(owner)
    assert len(status(owner)["recent"]) == 1  # type: ignore[arg-type]
    parking = next(q for q in owner.get("/api/unanswered").json() if "parqueo" in q["text"])
    assert parking["times_searched"] == 1


def test_a_re_exported_chat_only_adds_its_new_questions(owner: Api, folders: Folders) -> None:
    drop(folders.chats, "android_soda.txt")
    scan(owner)
    longer = (FIXTURES / "android_soda.txt").read_text(encoding="utf-8")
    longer += "20/11/24, 8:00 a. m. - María López: ¿Venden café molido?\n"
    (folders.chats / "android_soda (2).txt").write_text(longer, encoding="utf-8")
    scan(owner)
    questions = {q["text"]: q["times_searched"] for q in owner.get("/api/unanswered").json()}
    assert questions["Venden café molido"] == 1
    assert next(v for k, v in questions.items() if "parqueo" in k) == 1


def test_files_that_are_not_chats_are_noted_once(owner: Api, folders: Folders) -> None:
    folders.chats.joinpath("lista.txt").write_text("pan, leche, huevos", encoding="utf-8")
    scan(owner)
    scan(owner)
    recent: list[dict[str, object]] = status(owner)["recent"]  # type: ignore[assignment]
    assert [record["error"] for record in recent] == ["whatsapp.no_messages"]


def test_downloads_only_takes_files_named_like_whatsapp_exports(
    owner: Api, folders: Folders
) -> None:
    drop(folders.downloads, "android_soda.txt", "notas.txt")
    drop(folders.downloads, "android_soda_2.txt", "Chat de WhatsApp con +506 7777 5555.txt")
    scan(owner)
    assert len(status(owner)["recent"]) == 1  # type: ignore[arg-type]


def test_business_details_already_set_are_not_overwritten(owner: Api, folders: Folders) -> None:
    set_variables(owner, hours="Todos los días de 7 a 7")
    drop(folders.chats, "android_soda.txt")
    scan(owner)
    variables = {v["key"]: v["value"] for v in owner.get("/api/variables").json()}
    assert variables["hours"] == "Todos los días de 7 a 7"
    assert variables["sinpe"].startswith("8888-1234")


def test_customer_names_are_not_stored(owner: Api, folders: Folders) -> None:
    drop(folders.chats, "android_soda.txt", "Chat de WhatsApp con María López.txt")
    scan(owner)
    text = str(status(owner)) + str(owner.get("/api/answers").json())
    assert "María López" not in text


def test_staff_cannot_see_the_import_status(owner: Api, folders: Folders) -> None:
    staff_user = {"username": "cajera", "password": "clave-cajera-1", "role": "staff"}
    owner.post("/api/users", json=staff_user)
    staff = Api(TestClient(owner.client.app))
    staff.login("cajera", "clave-cajera-1")
    assert staff.get("/api/whatsapp/auto").status_code == 403
