"""P8: with 1,000 answers loaded, search answers in under 200 ms."""

import random
import statistics
import time

import pytest

from tests.conftest import Api

pytestmark = [pytest.mark.perf, pytest.mark.promise_p8]
ANSWERS = 1000
LIMIT_MS = 200
WORDS = [
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
    "madera",
    "tubo",
    "clavo",
    "martillo",
    "taladro",
    "brocha",
    "cabello",
    "pestañas",
    "cejas",
    "uñas",
    "desayuno",
    "cafe",
]
QUERIES = [
    "horario",
    "¿A qué hora abren?",
    "orario",
    "precio del cemento",
    "simpe",
    "envíos",
    "cuanto cuesta",
    "pintura blanca",
    "taladro",
    "factura electronica",
    "",
    "hor",
    "tinte rubio",
    "pestañas",
    "almuerzo",
    "parqueo",
    "zzzz",
    "garantía de taladro",
]


def make_csv(rng: random.Random) -> bytes:
    lines = ["title,category,body,tags"]
    for i in range(ANSWERS):
        words = rng.sample(WORDS, 6)
        body = " ".join(rng.choices(WORDS, k=40)) + " {hours} {sinpe}"
        lines.append(
            f"{words[0].title()} {words[1]} {i},Categoría {i % 12},{body},{words[2]}|{words[3]}"
        )
    return "\n".join(lines).encode()


def test_search_under_200ms_with_1000_answers(admin: Api) -> None:
    rng = random.Random(42)
    report = admin.post("/api/csv/import", content=make_csv(rng)).json()
    assert report["imported"] == ANSWERS
    admin.post("/api/demo/hardware", json={"mode": "replace"})
    admin.post("/api/csv/import", content=make_csv(rng))
    admin.put(
        "/api/synonyms",
        json={"groups": [["horario", "abren", "hora"], ["envio", "envios", "express"]]},
    )
    assert len(admin.get("/api/answers").json()) >= ANSWERS
    timings = []
    for query in QUERIES * 3:
        started = time.perf_counter()
        response = admin.get("/api/search", params={"q": query})
        timings.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
    p95 = statistics.quantiles(timings, n=20)[-1]
    print(
        f"\nP8 search with {ANSWERS} answers: median {statistics.median(timings):.1f} ms, "
        f"p95 {p95:.1f} ms, max {max(timings):.1f} ms over {len(timings)} queries"
    )
    assert p95 < LIMIT_MS
    assert max(timings) < LIMIT_MS * 2
