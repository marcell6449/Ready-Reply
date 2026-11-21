"""F5 unanswered questions, F7 stats, P4."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import Api, answer_payload


def record(api: Api, query: str) -> int:
    return int(api.post("/api/unanswered", json={"query": query}).status_code)


@pytest.mark.promise_p4
def test_unanswered_flow(admin: Api) -> None:  # F5-01, F5-07, P4
    assert record(admin, "¿Tienen parqueo?") == 204
    (question,) = admin.get("/api/unanswered").json()
    assert (question["text"], question["times_searched"]) == ("¿Tienen parqueo?", 1)
    created = admin.post(
        f"/api/unanswered/{question['id']}/answer",
        json=answer_payload("Parqueo", "Sí, tenemos parqueo gratis."),
    )
    assert created.status_code == 201
    assert admin.get("/api/unanswered").json() == []
    assert (
        admin.get("/api/search", params={"q": "parqueo"}).json()[0]["answer"]["title"] == "Parqueo"
    )


def test_same_question_different_form_counts_up(admin: Api, staff: Api) -> None:  # F5-02
    record(admin, "¿Tienen envíos a Cartago?")
    record(staff, "cartago ENVIOS")
    (question,) = admin.get("/api/unanswered").json()
    assert question["times_searched"] == 2


@pytest.mark.parametrize("query", ["h", "ho", "a", "🍔", "  "])
def test_short_queries_not_recorded(admin: Api, query: str) -> None:  # F5-03, F5-04
    response = admin.post("/api/unanswered", json={"query": query})
    assert (response.status_code, response.json()["code"]) == (422, "unanswered.too_short")
    assert admin.get("/api/unanswered").json() == []


def test_double_submit_counts_once(admin: Api) -> None:  # F5-05
    record(admin, "parqueo")
    record(admin, "parqueo")
    assert admin.get("/api/unanswered").json()[0]["times_searched"] == 1


def test_parallel_users_counted_atomically(admin: Api, app: FastAPI) -> None:  # F5-06
    users = [f"user{i}" for i in range(20)]
    for name in users:
        admin.post("/api/users", json={"username": name, "password": "12345678", "role": "staff"})

    def search_as(name: str) -> int:
        api = Api(TestClient(app))  # no lifespan: the app is already started
        api.login(name, "12345678")
        return record(api, "horario de feriados")

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert set(pool.map(search_as, users)) == {204}
    (question,) = admin.get("/api/unanswered").json()
    assert question["times_searched"] == 20


def test_html_in_question_returned_as_text(admin: Api) -> None:  # F5-08 (API side)
    record(admin, "<img src=x onerror=alert(1)>")
    assert admin.get("/api/unanswered").json()[0]["text"] == "<img src=x onerror=alert(1)>"


def test_staff_views_but_cannot_resolve(admin: Api, staff: Api) -> None:  # F5-09
    record(staff, "parqueo")
    (question,) = staff.get("/api/unanswered").json()
    assert staff.delete(f"/api/unanswered/{question['id']}").status_code == 403
    answer = staff.post(f"/api/unanswered/{question['id']}/answer", json=answer_payload())
    assert answer.status_code == 403


def test_dismiss_question(admin: Api) -> None:
    record(admin, "parqueo")
    (question,) = admin.get("/api/unanswered").json()
    assert admin.delete(f"/api/unanswered/{question['id']}").status_code == 204
    assert admin.delete(f"/api/unanswered/{question['id']}").status_code == 404


def test_resolved_question_reopens_when_searched_again(admin: Api) -> None:
    record(admin, "parqueo")
    (question,) = admin.get("/api/unanswered").json()
    admin.post(f"/api/unanswered/{question['id']}/answer", json=answer_payload("Parqueo", "Sí"))
    admin.client.cookies.clear()
    admin.login("admin", "admin-pass-1")
    record(admin, "parqueo nuevo")
    assert [q["text"] for q in admin.get("/api/unanswered").json()] == ["parqueo nuevo"]


def test_stats(admin: Api) -> None:  # F7-01, F7-02
    ids = {t: admin.post("/api/answers", json=answer_payload(t, "x")).json()["id"] for t in "ABC"}
    copies = {"A": 5, "B": 3, "C": 1}
    container = admin.client.app.state.container  # type: ignore[attr-defined]
    with container.engine.begin() as connection:
        for title, count in copies.items():
            for _ in range(count):
                connection.exec_driver_sql(
                    "INSERT INTO copy_events (business_id, answer_id, user_id, copied_at)"
                    " VALUES (1, ?, 1, '2026-01-01')",
                    (ids[title],),
                )
    for text, times in (("siete", 7), ("dos", 2), ("cuatro", 4)):
        for _i in range(times):
            container.activity.record_unanswered._guard = type(
                "NoGuard", (), {"is_repeat": lambda *a: False}
            )()
            record(admin, text)
    stats = admin.get("/api/stats").json()
    assert [(c["title"], c["copies"]) for c in stats["top_copied"]] == [
        ("A", 5),
        ("B", 3),
        ("C", 1),
    ]
    assert [q["times_searched"] for q in stats["top_unanswered"]] == [7, 4, 2]
    assert (stats["total_answers"], stats["total_copies"]) == (3, 9)


def test_stats_on_new_database(admin: Api) -> None:  # F7-03
    assert admin.get("/api/stats").json() == {
        "total_answers": 0,
        "total_copies": 0,
        "top_copied": [],
        "top_unanswered": [],
    }
