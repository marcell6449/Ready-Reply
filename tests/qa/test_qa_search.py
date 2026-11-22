"""QA: search robustness, relevance (P2) and speed with 1,000 answers (P8)."""

import random
import statistics
import time

import pytest

from tests.conftest import Api, answer_payload
from tests.support.seed import seed_business

SYNONYM = {"groups": [["horario", "abren", "atienden", "cierran", "hora", "abierto"]]}


@pytest.fixture
def soda(admin: Api) -> Api:
    seed_business(admin, "soda")
    return admin


def titles(api: Api, query: str) -> list[str]:
    response = api.get("/api/search", params={"q": query})
    assert response.status_code == 200, (query, response.text)
    return [result["answer"]["title"] for result in response.json()]


@pytest.mark.promise_p2
@pytest.mark.parametrize(
    "query",
    [
        "horario",
        "HORARIO",
        "Horário",
        "horario!!!",
        "¿A qué hora abren?",
        "a que ora abren",
        "A QUÉ HORA ABREN",
        "orario",
        "hroario",
        "horaio",
        "horari",
        "hor",
        "abren el domingo",
        "cierran",
        "atienden hoy",
        "Ｈｏｒａｒｉｏ",
        "horario\u200b",
    ],
)
def test_opening_hours_found_with_typos_accents_and_wording(soda: Api, query: str) -> None:
    found = titles(soda, query)
    assert found and found[0] == "Horario", (query, found)


@pytest.mark.promise_p2
@pytest.mark.parametrize(
    "query, expected",
    [
        ("sinpe", "Pago por SINPE Móvil"),
        ("simpe", "Pago por SINPE Móvil"),
        ("SINPE móvil", "Pago por SINPE Móvil"),
        ("delivery", "Envíos a domicilio"),
        ("express", "Envíos a domicilio"),
        ("envios", "Envíos a domicilio"),
        ("ubicasion", "Ubicación"),
        ("dirrecion", "Ubicación"),
        ("donde estan ubicados", "Ubicación"),
        ("tarjta", "Pago con tarjeta"),
        ("vejetariano", "Opciones vegetarianas"),
        ("cuanto cuesta", "Precios"),
        ("reservar para grupo", "Reservaciones para grupos"),
    ],
)
def test_relevance_for_common_customer_questions(soda: Api, query: str, expected: str) -> None:
    found = titles(soda, query)
    assert found and found[0] == expected, (query, found)


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        "🍔",
        "!!!",
        "¿?",
        "%",
        "_",
        "\x00",
        "' OR 1=1 --",
        "<script>",
        "a" * 200,
        "horario " * 25,
        "\u202e\u200b",
        "ñ" * 199,
        "🍔 " * 100,
    ],
)
def test_search_never_errors(soda: Api, query: str) -> None:
    response = soda.get("/api/search", params={"q": query})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_symbols_only_query_equals_empty_query(soda: Api) -> None:
    assert titles(soda, "🍔") == titles(soda, "!!!") == titles(soda, "") == titles(soda, "%")


def test_sql_wildcards_do_not_widen_results(soda: Api) -> None:
    assert titles(soda, "' OR 1=1 --") == []
    assert titles(soda, "horario%") == ["Horario"]


def test_short_word_with_typo_is_not_fuzzy(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Sol", "Bloqueador de sol"))
    assert titles(admin, "sal") == []
    assert titles(admin, "sol") == ["Sol"]


def test_title_match_ranks_above_body_match(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Parqueo", "Tenemos espacio"))
    admin.post("/api/answers", json=answer_payload("Ubicación", "Hay parqueo al frente"))
    assert titles(admin, "parqueo") == ["Parqueo", "Ubicación"]


def test_edit_and_delete_are_visible_in_search_immediately(admin: Api) -> None:
    answer = admin.post("/api/answers", json=answer_payload("Horario", "Abrimos")).json()
    admin.put(f"/api/answers/{answer['id']}", json=answer_payload("Parqueo gratis", "Sí"))
    assert titles(admin, "horario") == []
    assert titles(admin, "parqueo") == ["Parqueo gratis"]
    admin.delete(f"/api/answers/{answer['id']}")
    assert titles(admin, "parqueo") == []


def test_new_synonym_group_takes_effect_immediately(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Envío", "Hacemos envio a domicilio"))
    assert titles(admin, "express") == []
    admin.put("/api/synonyms", json={"groups": [["envio", "delivery", "express", "domicilio"]]})
    assert titles(admin, "express") == ["Envío"]


def test_placeholder_keys_are_not_searchable(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("Pago", "Pague al {sinpe}"))
    assert titles(admin, "sinpe") == []


# --- P8 -------------------------------------------------------------------------------

SYLLABLES = [
    "ca",
    "sa",
    "do",
    "pe",
    "ri",
    "mo",
    "la",
    "te",
    "ni",
    "bo",
    "ru",
    "ga",
    "fe",
    "lo",
    "ma",
    "chi",
    "que",
    "ven",
    "tor",
    "mal",
    "pin",
    "sol",
    "bra",
    "cri",
]
REAL = [
    "horario",
    "precio",
    "envio",
    "sinpe",
    "cemento",
    "pintura",
    "varilla",
    "corte",
    "tinte",
    "manicure",
    "casado",
    "pollo",
    "almuerzo",
    "factura",
    "garantia",
    "cotizacion",
    "domicilio",
    "reservacion",
    "parqueo",
    "tarjeta",
    "efectivo",
]


def make_library(rng: random.Random) -> bytes:
    vocabulary = REAL + ["".join(rng.choices(SYLLABLES, k=rng.randint(2, 4))) for _ in range(3000)]
    lines = ["title,category,body,tags"]
    for index in range(1000):
        title = " ".join(rng.sample(vocabulary, 3))
        body = " ".join(rng.choices(vocabulary, k=50)) + " {hours}"
        tags = "|".join(rng.sample(vocabulary, 2))
        lines.append(f"{title} {index},Categoría {index % 15},{body},{tags}")
    return "\n".join(lines).encode()


def varied_queries(rng: random.Random) -> list[str]:
    queries = [
        "horario",
        "¿A qué hora abren?",
        "orario",
        "precio del cemento",
        "simpe",
        "envíos",
        "cuanto cuesta",
        "pintura blanca",
        "factura electrónica",
        "hor",
        "",
        "zzzz",
        "garantía de taladro",
        "PARQUEO",
        "domicilo",
        "reservasion",
        "tarjeta o efectivo",
    ]
    while len(queries) < 45:
        words = rng.sample(REAL, 3)
        typo = words[0][:-1] + "x"
        queries.append(" ".join([typo, *words[1:]]))
    long_query = " ".join(rng.choices(REAL, k=40))[:200]
    queries += [
        long_query,
        long_query.upper(),
        "a que ora abren " * 12,
        "cotisacion garantia",
        "manicure pedicure uñas",
    ]
    return queries


@pytest.mark.perf
@pytest.mark.promise_p8
def test_p8_search_p95_under_200ms_with_1000_answers(admin: Api) -> None:
    rng = random.Random(2026)
    assert admin.post("/api/csv/import", content=make_library(rng)).json()["imported"] == 1000
    admin.put(
        "/api/synonyms",
        json={"groups": [["horario", "abren", "hora"], ["envio", "envios", "express", "delivery"]]},
    )
    queries = varied_queries(rng)
    assert len(queries) == 50
    admin.get("/api/search", params={"q": "warm up"})
    timings = []
    for query in queries:
        started = time.perf_counter()
        response = admin.get("/api/search", params={"q": query})
        timings.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
    p95 = statistics.quantiles(timings, n=20)[-1]
    print(
        f"\nQA P8: median {statistics.median(timings):.1f} ms, p95 {p95:.1f} ms, "
        f"max {max(timings):.1f} ms"
    )
    assert p95 < 200
