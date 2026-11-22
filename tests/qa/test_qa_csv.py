"""QA: CSV import/export edge cases (F10)."""

import csv
import io
import os
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI

from tests.conftest import Api, answer_payload, run_sql

HEADER = "title,category,body,tags\n"
LIMIT = 1024 * 1024


def upload(api: Api, data: bytes) -> Any:
    return api.post("/api/csv/import", content=data, headers={"content-type": "text/csv"})


def count(app: FastAPI) -> int:
    return int(run_sql(app, "SELECT count(*) FROM answers")[0][0])


def padded_file(size: int) -> bytes:
    """A valid CSV of exactly `size` bytes: rows of ~1 KB, the last one padded to fit."""
    data = bytearray(HEADER.encode())
    index = 0
    while size - len(data) > 2100:
        data += f"Fila {index},c,{'x' * 1000},t\n".encode()
        index += 1
    last_start = f"Fila {index},c,".encode()
    pad = size - len(data) - len(last_start) - len(b",t\n")
    data += last_start + b"y" * pad + b",t\n"
    return bytes(data)


def test_file_of_exactly_the_size_limit_is_accepted(admin: Api) -> None:
    data = padded_file(LIMIT)
    assert len(data) == LIMIT
    response = upload(admin, data)
    assert response.status_code == 200, response.json()
    assert response.json()["rejected"] == []
    assert response.json()["imported"] == data.count(b"\n") - 1


def test_one_byte_over_the_limit_is_413_before_parsing(admin: Api, app: FastAPI) -> None:
    response = upload(admin, padded_file(LIMIT + 1))
    assert response.status_code == 413
    assert response.json()["code"] == "csv.too_large"
    assert count(app) == 0


def test_over_the_limit_without_content_length_is_413(admin: Api) -> None:
    def chunks() -> Iterator[bytes]:  # streamed, so no Content-Length header is sent
        data = padded_file(LIMIT + 10)
        for start in range(0, len(data), 65536):
            yield data[start : start + 65536]

    response = admin.post("/api/csv/import", content=chunks(), headers={"content-type": "text/csv"})
    assert response.status_code == 413


def rows_file(rows: int) -> bytes:
    return (HEADER + "".join(f"Respuesta {i},c,Cuerpo {i},t\n" for i in range(rows))).encode()


def test_5000_rows_are_imported(admin: Api, app: FastAPI) -> None:
    response = upload(admin, rows_file(5000))
    assert response.status_code == 200
    assert response.json()["imported"] == 5000
    assert count(app) == 5000


def test_5001_rows_are_rejected_and_nothing_is_imported(admin: Api, app: FastAPI) -> None:
    response = upload(admin, rows_file(5001))
    assert response.status_code == 422
    assert response.json()["code"] == "csv.too_many_rows"
    assert count(app) == 0


@pytest.mark.parametrize("bom", [b"", b"\xef\xbb\xbf"], ids=["no-bom", "bom"])
@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"], ids=["lf", "crlf", "cr"])
@pytest.mark.parametrize("delimiter", [",", ";"], ids=["comma", "semicolon"])
def test_bom_newlines_and_delimiters(admin: Api, bom: bytes, newline: str, delimiter: str) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator=newline)
    writer.writerow(["title", "category", "body", "tags"])
    writer.writerow(
        ["Horario ⏰", "Info; general", 'Abrimos "temprano"\ny cerramos, tarde 👋', "a|b"]
    )
    writer.writerow(["Pago", "Pagos", "SINPE", ""])
    response = upload(admin, bom + buffer.getvalue().encode())
    assert response.status_code == 200, response.json()
    assert response.json() == {"imported": 2, "rejected": []}
    answers = {a["title"]: a for a in admin.get("/api/answers").json()}
    assert answers["Horario ⏰"]["body"] == 'Abrimos "temprano"\ny cerramos, tarde 👋'
    assert answers["Horario ⏰"]["category"] == "Info; general"
    assert answers["Horario ⏰"]["tags"] == ["a", "b"]


def test_header_with_capital_letters_imports_the_rows(admin: Api, app: FastAPI) -> None:
    """Spreadsheet users often write "Title,Category,Body,Tags". The header is accepted
    (case-insensitive) so the rows must be read too, not all rejected as empty."""
    response = upload(admin, b"Title,Category,Body,Tags\nHorario,Info,Abrimos a las 8,hora\n")
    assert response.status_code == 200
    assert response.json() == {"imported": 1, "rejected": []}
    assert count(app) == 1


def test_header_with_spaces_imports_the_rows(admin: Api) -> None:
    response = upload(admin, b"title, category, body, tags\nHorario, Info, Abrimos, hora\n")
    assert response.status_code == 200
    assert response.json() == {"imported": 1, "rejected": []}


def test_wrong_header_order_is_never_mismapped(admin: Api) -> None:
    response = upload(admin, b"body,title,category,tags\nEl cuerpo,El titulo,c,t\n")
    if response.status_code == 422:
        assert response.json()["code"] == "csv.invalid_header"
        return
    (answer,) = admin.get("/api/answers").json()
    assert (answer["title"], answer["body"]) == ("El titulo", "El cuerpo")


@pytest.mark.parametrize(
    "data, code",
    [
        (b"title,category,body,tags,extra\nA,c,b,t,x\n", "csv.invalid_header"),
        (b"title,category,body\nA,c,b\n", "csv.invalid_header"),
        (b"titulo,categoria,cuerpo,etiquetas\nA,c,b,t\n", "csv.invalid_header"),
        (os.urandom(2048) + b"\xff\xfe", "csv.invalid_encoding"),
        ("title,category,body,tags\nÑandú,c,b,t\n".encode("latin-1"), "csv.invalid_encoding"),
        ("title,category,body,tags\nA,c,b,t\n".encode("utf-16"), "csv.invalid_encoding"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 100, "csv.invalid_encoding"),
        (b"", "csv.empty"),
        (b"\xef\xbb\xbf  \r\n\r\n", "csv.empty"),
        (b'title,category,body,tags\n"never closed,c,b,t\n', "csv.malformed"),
    ],
    ids=[
        "extra-column",
        "missing-column",
        "spanish-header",
        "random-bytes",
        "latin1",
        "utf16",
        "png",
        "empty",
        "blank-bom",
        "unterminated-quote",
    ],
)
def test_bad_files_are_rejected_and_import_nothing(
    admin: Api, app: FastAPI, data: bytes, code: str
) -> None:
    response = upload(admin, data)
    assert response.status_code == 422
    assert response.json()["code"] == code
    assert count(app) == 0


def test_valid_and_invalid_rows_report_line_numbers(admin: Api) -> None:
    data = HEADER + 'A,c,b,t\n,c,b,t\nB,c,"multi\nline",t\nC,c,' + "x" * 4001 + ",t\nD,c,b,t\n"
    report = upload(admin, data.encode()).json()
    assert report["imported"] == 3
    codes = [row["code"] for row in report["rejected"]]
    assert codes == ["answer.title_required", "answer.body_too_long"]


def test_injection_in_cells_is_stored_as_text(admin: Api) -> None:
    payload = "<img src=x onerror=alert(1)>"
    data = (HEADER + f'"\'); DROP TABLE answers;--",c,"{payload}",t\n').encode()
    assert upload(admin, data).json()["imported"] == 1
    (answer,) = admin.get("/api/answers").json()
    assert answer["title"] == "'); DROP TABLE answers;--"
    assert answer["body"] == payload


@pytest.mark.parametrize("start", ["=", "+", "-", "@"])
def test_formula_cells_are_neutralized_on_export(admin: Api, start: str) -> None:
    admin.post(
        "/api/answers",
        json=answer_payload(
            f'{start}HYPERLINK("http://x")', body=f"{start}1+1", category=f"{start}cmd"
        ),
    )
    exported = admin.get("/api/csv/export").content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(exported)))
    assert rows[0] == ["title", "category", "body", "tags"]
    for cell in rows[1][:3]:
        assert cell.startswith("'"), cell


def test_export_is_utf8_with_bom_and_pipe_tags(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Pago", tags=["SINPE", "Pago"]))
    response = admin.get("/api/csv/export")
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[1][3] == "sinpe|pago"


def test_round_trip_keeps_every_strange_answer(admin: Api) -> None:
    titles = [
        "Ñandú 🦤",
        'Precio, "especial"',
        "Línea\tcon tab",
        "@Instagram",
        "-10% hoy",
        "+506 2222",
        "=Fórmula",
        "'Comillas simples'",
    ]
    for index, title in enumerate(titles):
        body = f"*Hola* 👋\n_{title}_\r\nfin {index}"
        assert admin.post("/api/answers", json=answer_payload(title, body)).status_code == 201
    before = sorted((a["title"], a["body"]) for a in admin.get("/api/answers").json())
    exported = admin.get("/api/csv/export").content
    for answer in admin.get("/api/answers").json():
        admin.delete(f"/api/answers/{answer['id']}")
    report = upload(admin, exported).json()
    assert report["rejected"] == []
    after = sorted((a["title"], a["body"]) for a in admin.get("/api/answers").json())
    assert after == before


def test_duplicate_title_inside_one_file_is_reported(admin: Api) -> None:
    data = (HEADER + "Horario,c,b,t\nHORÁRIO,c,b,t\n").encode()
    report = upload(admin, data).json()
    assert report == {"imported": 1, "rejected": [{"line": 3, "code": "answer.title_taken"}]}


def test_round_trip_keeps_a_title_that_starts_with_apostrophe_and_equals(admin: Api) -> None:
    """F10-01: a title the user typed as "'=50% off" must come back unchanged after import."""
    title = "'=50% descuento"
    admin.post("/api/answers", json=answer_payload(title, "Promo"))
    exported = admin.get("/api/csv/export").content
    for answer in admin.get("/api/answers").json():
        admin.delete(f"/api/answers/{answer['id']}")
    assert upload(admin, exported).json()["imported"] == 1
    assert admin.get("/api/answers").json()[0]["title"] == title
