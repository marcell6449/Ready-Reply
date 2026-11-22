"""F10 CSV import/export and F9 demo data."""

from collections.abc import Iterator

import pytest

from tests.conftest import Api, answer_payload

HEADER = "title,category,body,tags\r\n"


def import_csv(api: Api, data: bytes) -> object:
    return api.post("/api/csv/import", content=data, headers={"content-type": "text/csv"})


def test_round_trip(admin: Api, client: object) -> None:  # F10-01, F10-02
    tricky = [
        answer_payload("Horário ☕", 'Línea 1\nLínea "2", con coma 🍔', tags=["pago", "sinpe"]),
        answer_payload("=SUMA(A1)", "Fórmula", tags=[]),
        answer_payload("Precios; ofertas", "₡2.500 ; ₡3.000"),
    ]
    for payload in tricky:
        assert admin.post("/api/answers", json=payload).status_code == 201
    exported = admin.get("/api/csv/export")
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.content.startswith(b"\xef\xbb\xbf" + HEADER.encode())
    assert b"'=SUMA(A1)" in exported.content  # F10-03
    before = {(a["title"], a["body"], tuple(a["tags"])) for a in admin.get("/api/answers").json()}
    for answer in admin.get("/api/answers").json():
        admin.delete(f"/api/answers/{answer['id']}")
    report = import_csv(admin, exported.content).json()  # type: ignore[attr-defined]
    assert report == {"imported": 3, "rejected": []}
    after = {(a["title"], a["body"], tuple(a["tags"])) for a in admin.get("/api/answers").json()}
    assert after == before


def test_semicolon_and_no_bom(admin: Api) -> None:  # F10-04
    data = b"title;category;body;tags\nHorario;Info;Abrimos a las 8;horario|info\n"
    assert import_csv(admin, data).json()["imported"] == 1  # type: ignore[attr-defined]
    assert admin.get("/api/answers").json()[0]["tags"] == ["horario", "info"]


def test_partial_import_reports_bad_rows(admin: Api) -> None:  # F10-05, F10-06
    admin.post("/api/answers", json=answer_payload("Existente", "x"))
    rows = [
        "Uno,,texto,",
        ",,sin título,",
        "Dos,,texto,",
        "Tres,,{},".format("x" * 4001),
        "existente,,dup,",
        "Cuatro,,texto,",
        ",,,",
    ]
    report = import_csv(admin, (HEADER + "\r\n".join(rows)).encode()).json()  # type: ignore[attr-defined]
    assert report["imported"] == 3
    assert report["rejected"] == [
        {"line": 3, "code": "answer.title_required"},
        {"line": 5, "code": "answer.body_too_long"},
        {"line": 6, "code": "answer.title_taken"},
    ]


def test_too_large_rejected_before_parsing(admin: Api) -> None:  # F10-07
    data = HEADER.encode() + b"x" * (1024 * 1024)
    response = import_csv(admin, data)
    assert (response.status_code, response.json()["code"]) == (413, "csv.too_large")  # type: ignore[attr-defined]


def test_too_large_without_content_length(admin: Api) -> None:
    def chunks() -> Iterator[bytes]:
        yield HEADER.encode()
        for _ in range(20):
            yield b"x" * 65536

    response = admin.post("/api/csv/import", content=chunks())
    assert response.status_code == 413


def test_too_many_rows(admin: Api) -> None:  # F10-08
    rows = "".join(f"T{i},,b,\r\n" for i in range(5001))
    response = import_csv(admin, (HEADER + rows).encode())
    assert response.json()["code"] == "csv.too_many_rows"  # type: ignore[attr-defined]
    assert admin.get("/api/answers").json() == []


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"titel,category,body,tags\nA,,b,\n", "csv.invalid_header"),
        (b"title,body\nA,b\n", "csv.invalid_header"),
        (b"\xff\xfe\x00b\x00a\x00d", "csv.invalid_encoding"),
        (b"\x89PNG\r\n\x1a\n\x00\x00", "csv.invalid_encoding"),
        (b"", "csv.empty"),
        (b"   \n  ", "csv.empty"),
        (b'title,category,body,tags\n"unclosed,,b,\n', "csv.malformed"),
    ],
)
def test_bad_files(admin: Api, data: bytes, code: str) -> None:  # F10-09
    response = import_csv(admin, data)
    assert (response.status_code, response.json()["code"]) == (422, code)  # type: ignore[attr-defined]
