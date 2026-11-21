"""QA: simple concurrency against the real server (uvicorn, several threads, SQLite WAL)."""

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from tests.qa.conftest import ADMIN_PASSWORD, HttpUser, QaServer


def parallel(count: int, action: Callable[[int], Any]) -> list[Any]:
    with ThreadPoolExecutor(count) as pool:
        return list(pool.map(action, range(count)))


def admin_user(server: QaServer) -> HttpUser:
    user = HttpUser(server.url)
    assert user.setup().status_code == 200
    return user


def staff_users(server: QaServer, admin: HttpUser, count: int) -> list[HttpUser]:
    users = []
    for index in range(count):
        name = f"staff{index:02d}"
        admin.post("/api/users", json={"username": name, "password": "password-1", "role": "staff"})
        user = HttpUser(server.url)
        assert user.login(name, "password-1").status_code == 200
        users.append(user)
    return users


def test_parallel_first_admin_setup_creates_exactly_one_admin(qa_server: QaServer) -> None:
    def setup(index: int) -> int:
        return HttpUser(qa_server.url).setup(f"admin{index}", ADMIN_PASSWORD).status_code

    statuses = parallel(12, setup)
    assert Counter(statuses) == {200: 1, 409: 11}
    winner = statuses.index(200)
    admin = HttpUser(qa_server.url)
    assert admin.login(f"admin{winner}", ADMIN_PASSWORD).status_code == 200
    assert len(admin.get("/api/users").json()) == 1


def test_parallel_creates_of_the_same_title_make_one_answer(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    titles = ["Horario", "horario", " HORARIO ", "Horário"] * 3

    def create(index: int) -> int:
        body = {"title": titles[index], "category": "", "body": "Abrimos", "tags": []}
        return admin.post("/api/answers", json=body).status_code

    statuses = parallel(len(titles), create)
    assert Counter(statuses) == {201: 1, 409: len(titles) - 1}
    assert len(admin.get("/api/answers").json()) == 1


def test_parallel_duplicates_never_fail_with_a_server_error(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    answer = admin.post(
        "/api/answers", json={"title": "Horario", "category": "", "body": "x", "tags": []}
    ).json()
    statuses = parallel(
        8, lambda _: admin.post(f"/api/answers/{answer['id']}/duplicate").status_code
    )
    assert all(status < 500 for status in statuses), statuses
    titles = [a["title"] for a in admin.get("/api/answers").json()]
    assert len(titles) == len(set(titles)) == 1 + statuses.count(201)


def test_parallel_copies_from_twenty_users_record_twenty_events(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    answer = admin.post(
        "/api/answers", json={"title": "Horario", "category": "", "body": "x", "tags": []}
    ).json()
    users = staff_users(qa_server, admin, 20)
    statuses = parallel(
        20, lambda i: users[i].post(f"/api/answers/{answer['id']}/copy").status_code
    )
    assert statuses == [200] * 20
    assert admin.get("/api/stats").json()["top_copied"][0]["copies"] == 20


def test_parallel_double_clicks_of_one_user_record_one_copy(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    answer = admin.post(
        "/api/answers", json={"title": "Horario", "category": "", "body": "x", "tags": []}
    ).json()
    statuses = parallel(10, lambda _: admin.post(f"/api/answers/{answer['id']}/copy").status_code)
    assert statuses == [200] * 10
    assert admin.get("/api/stats").json()["top_copied"][0]["copies"] == 1


def test_parallel_unanswered_from_twenty_users_counts_twenty(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    users = staff_users(qa_server, admin, 20)
    variants = ["¿Tienen parqueo gratis?", "tienen PARQUEO gratis", "gratis parqueo tienen"]
    statuses = parallel(
        20,
        lambda i: users[i].post("/api/unanswered", json={"query": variants[i % 3]}).status_code,
    )
    assert statuses == [204] * 20
    (question,) = admin.get("/api/unanswered").json()
    assert question["times_searched"] == 20


def test_parallel_demo_replace_leaves_one_clean_library(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    statuses = parallel(
        4, lambda _: admin.post("/api/demo/salon", json={"mode": "replace"}).status_code
    )
    assert all(status < 500 for status in statuses), statuses
    titles = [a["title"] for a in admin.get("/api/answers").json()]
    assert len(titles) == len(set(titles)) >= 12


def test_parallel_csv_imports_do_not_duplicate_rows(qa_server: QaServer) -> None:
    admin = admin_user(qa_server)
    data = ("title,category,body,tags\n" + "".join(f"T{i},c,b,t\n" for i in range(60))).encode()

    def run(_: int) -> Any:
        response = admin.post("/api/csv/import", content=data, headers={"content-type": "text/csv"})
        return response.status_code, response.json()

    results = parallel(4, run)
    assert all(status == 200 for status, _ in results), results
    assert sum(body["imported"] for _, body in results) == 60
    assert len(admin.get("/api/answers").json()) == 60
