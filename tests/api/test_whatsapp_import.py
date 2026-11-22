"""Import answers from WhatsApp chat exports: preview first, then save in one step."""

import base64
import io
import zipfile
from pathlib import Path
from typing import Any

from tests.conftest import Api, answer_payload, set_variables

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "whatsapp"
SODA_CHATS = ("android_soda.txt", "android_soda_2.txt", "ios_soda.txt")


def file_payload(name: str, data: bytes) -> dict[str, str]:
    return {"name": name, "content_base64": base64.b64encode(data).decode()}


def chat_files(*names: str) -> list[dict[str, str]]:
    return [file_payload(name, (FIXTURES / name).read_bytes()) for name in names]


def analyze(api: Api, files: list[dict[str, str]], sender: str | None = None) -> Any:
    return api.post("/api/whatsapp/analyze", json={"files": files, "business_sender": sender})


def test_preview_finds_answers_questions_and_details_without_saving(admin: Api) -> None:
    response = analyze(admin, chat_files(*SODA_CHATS))
    assert response.status_code == 200
    preview = response.json()
    assert preview["business_sender"] == "Soda La Esquina"
    assert "Soda La Esquina" in preview["senders"]
    questions = {a["question"]: a for a in preview["answers"]}
    hours = next(a for q, a in questions.items() if "abren" in q.casefold())
    assert hours["times_asked"] == 2
    assert hours["exists"] is False
    assert any("parqueo" in q["question"] for q in preview["unanswered"])
    details = {d["key"]: d for d in preview["details"]}
    assert details["sinpe"]["value"] == "8888-1234 a nombre de María Rodríguez"
    assert details["sinpe"]["current"] == ""
    assert admin.get("/api/answers").json() == []


def test_import_saves_everything_in_one_step(admin: Api) -> None:
    preview = analyze(admin, chat_files(*SODA_CHATS)).json()
    selection = {
        "answers": [
            {"title": a["question"], "category": "WhatsApp", "body": a["reply"], "tags": []}
            for a in preview["answers"]
        ],
        "questions": preview["unanswered"],
        "details": {d["key"]: d["value"] for d in preview["details"]},
    }
    result = admin.post("/api/whatsapp/import", json=selection).json()
    assert result["created"] == len(preview["answers"])
    assert result["questions"] == len(preview["unanswered"])
    assert result["details"] == 3
    variables = {v["key"]: v["value"] for v in admin.get("/api/variables").json()}
    assert variables["sinpe"] == "8888-1234 a nombre de María Rodríguez"
    parking = next(q for q in admin.get("/api/unanswered").json() if "parqueo" in q["text"])
    assert parking["times_searched"] == 2
    top = admin.get("/api/search", params={"q": "a que hora abren"}).json()[0]
    assert "6:30" in top["preview"]["text"]


def test_existing_titles_are_flagged_and_skipped(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Cuál es el número de SINPE", "x"))
    preview = analyze(admin, chat_files(*SODA_CHATS)).json()
    sinpe = next(a for a in preview["answers"] if "sinpe" in a["question"].casefold())
    assert sinpe["exists"] is True
    selection = {
        "answers": [{"title": sinpe["question"], "body": "y"}],
        "questions": [],
        "details": {},
    }
    assert admin.post("/api/whatsapp/import", json=selection).json() == {
        "created": 0,
        "skipped": 1,
        "questions": 0,
        "details": 0,
    }


def test_known_business_values_become_placeholders(admin: Api) -> None:
    set_variables(admin, sinpe="8888-1234 a nombre de María Rodríguez")
    preview = analyze(admin, chat_files(*SODA_CHATS)).json()
    sinpe = next(a for a in preview["answers"] if "sinpe" in a["question"].casefold())
    assert "{sinpe}" in sinpe["reply"]


def test_iphone_zip_export_is_accepted(admin: Api) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("_chat.txt", (FIXTURES / "ios_soda.txt").read_bytes())
        archive.writestr("__MACOSX/._chat.txt", b"\x00\x05junk")
    preview = analyze(admin, [file_payload("WhatsApp Chat - Ana.zip", buffer.getvalue())]).json()
    assert preview["business_sender"] == "Soda La Esquina"
    assert preview["answers"]


def test_choosing_another_business_sender(admin: Api) -> None:
    preview = analyze(admin, chat_files("android_soda.txt"), sender="María López").json()
    assert preview["business_sender"] == "María López"


def test_files_that_are_not_chats(admin: Api) -> None:
    bad = analyze(admin, [file_payload("foto.txt", b"\x89PNG\r\n\x1a\n\x00\x00")])
    assert (bad.status_code, bad.json()["code"]) == (422, "whatsapp.no_messages")
    empty = admin.post("/api/whatsapp/analyze", json={"files": []})
    assert (empty.status_code, empty.json()["code"]) == (422, "whatsapp.no_files")
    broken = admin.post(
        "/api/whatsapp/analyze", json={"files": [{"name": "a.txt", "content_base64": "%%%"}]}
    )
    assert broken.json()["code"] == "whatsapp.invalid_file"


def test_some_bad_files_are_skipped(admin: Api) -> None:
    files = [*chat_files("android_soda.txt"), file_payload("notas.txt", b"solo texto")]
    preview = analyze(admin, files).json()
    assert preview["skipped_files"] == 1
    assert preview["answers"]


def test_staff_cannot_import(staff: Api) -> None:
    assert analyze(staff, chat_files("android_soda.txt")).status_code == 403
    selection: dict[str, object] = {"answers": [], "questions": [], "details": {}}
    assert staff.post("/api/whatsapp/import", json=selection).status_code == 403


def test_only_business_details_can_be_set(admin: Api) -> None:
    selection = {"answers": [], "questions": [], "details": {"password": "x", "sinpe": "8888-0000"}}
    response = admin.post("/api/whatsapp/import", json=selection)
    assert (response.status_code, response.json()["code"]) == (422, "whatsapp.unknown_detail")


def test_zip_bomb_is_rejected(admin: Api) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("_chat.txt", b"a" * (60 * 1024 * 1024))
    response = analyze(admin, [file_payload("bomb.zip", buffer.getvalue())])
    assert (response.status_code, response.json()["code"]) == (413, "whatsapp.too_large")


def test_saved_details_become_variables_inside_imported_answers(admin: Api) -> None:
    preview = analyze(admin, chat_files(*SODA_CHATS)).json()
    sinpe = next(a for a in preview["answers"] if "sinpe" in a["question"].casefold())
    assert "8888-1234" in sinpe["reply"]
    selection = {
        "answers": [{"title": sinpe["question"], "body": sinpe["reply"]}],
        "questions": [],
        "details": {d["key"]: d["value"] for d in preview["details"]},
    }
    admin.post("/api/whatsapp/import", json=selection)
    (saved,) = admin.get("/api/answers").json()
    assert "{sinpe}" in saved["body"]
    copied = admin.post(f"/api/answers/{saved['id']}/copy").json()["text"]
    assert "8888-1234 a nombre de María Rodríguez" in copied
