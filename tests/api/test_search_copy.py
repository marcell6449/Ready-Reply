"""F3, F4 and promises P1, P2 through the API."""

import pytest

from tests.conftest import Api, answer_payload, set_variables


@pytest.fixture
def soda(admin: Api) -> Api:
    assert admin.post("/api/demo/soda", json={}).status_code == 200
    return admin


def top_title(api: Api, query: str) -> str:
    results = api.get("/api/search", params={"q": query}).json()
    return str(results[0]["answer"]["title"]) if results else ""


@pytest.mark.promise_p2
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("horario", "Horario"),
        ("HORÁRIO", "Horario"),
        ("¿A qué hora abren?", "Horario"),
        ("a que hora abren", "Horario"),
        ("orario", "Horario"),
        ("hroario", "Horario"),
        ("sinpe", "Pago por SINPE Móvil"),
        ("simpe", "Pago por SINPE Móvil"),
        ("¿Dónde están ubicados?", "Ubicación"),
        ("hacen express?", "Envíos a domicilio"),
        ("cuanto cuesta el casado", "Precios"),
        ("tienen comida vegetariana", "Opciones vegetarianas"),
    ],
)
def test_tolerant_search(soda: Api, query: str, expected: str) -> None:
    assert top_title(soda, query) == expected


def test_prefix_while_typing(soda: Api) -> None:  # F3-06
    titles = [r["answer"]["title"] for r in soda.get("/api/search", params={"q": "hor"}).json()]
    assert "Horario" in titles


@pytest.mark.parametrize("query", ["xyzzy", "' OR 1=1 --"])
def test_no_results(soda: Api, query: str) -> None:  # F3-07, F3-10
    assert soda.get("/api/search", params={"q": query}).json() == []


def test_empty_query_lists_everything(soda: Api) -> None:  # F3-08, F3-09
    everything = soda.get("/api/search", params={"q": ""}).json()
    assert len(everything) == 13
    for query in ("   ", "🍔", "!!!", "%", "_"):
        assert len(soda.get("/api/search", params={"q": query}).json()) == 13


def test_long_query(soda: Api) -> None:  # F3-11
    response = soda.get("/api/search", params={"q": "horario " + "x" * 1500})
    assert response.status_code == 200
    assert response.json()[0]["answer"]["title"] == "Horario"


def test_new_synonym_applies_immediately(admin: Api) -> None:  # F3-12
    admin.post("/api/answers", json=answer_payload("Envíos", body="Hacemos envíos"))
    assert top_title(admin, "delivery") == ""
    admin.put("/api/synonyms", json={"groups": [["envios", "delivery", "express"]]})
    assert top_title(admin, "delivery") == "Envíos"


def test_search_preview_renders_variables(soda: Api) -> None:
    result = soda.get("/api/search", params={"q": "horario"}).json()[0]
    assert "lunes a sábado" in result["preview"]["text"]
    assert result["preview"]["missing"] == []


@pytest.mark.promise_p1
def test_variable_saved_once_fills_every_answer(admin: Api) -> None:  # P1
    ids = [
        admin.post("/api/answers", json=answer_payload(f"R{i}", f"Texto {i}: {{hours}}")).json()[
            "id"
        ]
        for i in range(3)
    ]
    set_variables(admin, hours="8 a 5")
    assert [admin.post(f"/api/answers/{i}/copy").json()["text"] for i in ids] == [
        "Texto 0: 8 a 5",
        "Texto 1: 8 a 5",
        "Texto 2: 8 a 5",
    ]
    set_variables(admin, hours="9 a 6")
    assert all("9 a 6" in admin.post(f"/api/answers/{i}/copy").json()["text"] for i in ids)


def test_missing_variable_blocks_copy(admin: Api) -> None:  # F4-02, F4-03
    answer = admin.post("/api/answers", json=answer_payload(body="SINPE {sinpe} {otra}")).json()
    copied = admin.post(f"/api/answers/{answer['id']}/copy").json()
    assert copied == {"text": None, "missing": ["sinpe", "otra"]}
    assert admin.get("/api/stats").json()["total_copies"] == 0


def test_literal_braces(admin: Api) -> None:  # F4-04, F4-05, F4-08
    set_variables(admin, hours="{name}")
    answer = admin.post("/api/answers", json=answer_payload(body="{{literal}} {hours} {sin")).json()
    assert admin.post(f"/api/answers/{answer['id']}/copy").json()["text"] == "{literal} {name} {sin"


def test_double_click_counts_once(admin: Api) -> None:  # F4-07
    answer = admin.post("/api/answers", json=answer_payload(body="Hola")).json()
    for _ in range(3):
        assert admin.post(f"/api/answers/{answer['id']}/copy").json()["text"] == "Hola"
    assert admin.get("/api/stats").json()["total_copies"] == 1


def test_staff_can_search_and_copy(soda: Api, staff: Api) -> None:
    result = staff.get("/api/search", params={"q": "sinpe"}).json()[0]
    copied = staff.post(f"/api/answers/{result['answer']['id']}/copy").json()
    assert "8888-1234" in copied["text"]
