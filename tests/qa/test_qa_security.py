"""QA: permissions on every endpoint, CSRF, Origin, expired/old/deactivated sessions."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import ADMIN, STAFF, Api, answer_payload, run_sql
from tests.qa.conftest import FakeClock

CSV = b"title,category,body,tags\nNueva,c,b,t\n"

# (method, path, json body) for every API route. "{a}" = an answer id, "{q}" = question id,
# "{u}" = the staff user id.
STATE_CHANGING: list[tuple[str, str, Any]] = [
    ("PUT", "/api/variables", []),
    ("POST", "/api/answers", answer_payload("Nueva")),
    ("PUT", "/api/answers/{a}", answer_payload("Editada")),
    ("DELETE", "/api/answers/{a}", None),
    ("POST", "/api/answers/{a}/duplicate", None),
    ("POST", "/api/answers/{a}/copy", None),
    ("PUT", "/api/synonyms", {"groups": [["uno", "dos"]]}),
    ("POST", "/api/unanswered", {"query": "tienen parqueo"}),
    ("POST", "/api/unanswered/{q}/answer", answer_payload("Desde pregunta")),
    ("DELETE", "/api/unanswered/{q}", None),
    ("POST", "/api/ai/suggest", {"question_id": "{q}"}),
    ("POST", "/api/users", {"username": "nuevo", "password": "password-1", "role": "staff"}),
    ("PUT", "/api/users/{u}", {"role": "admin", "active": True}),
    ("DELETE", "/api/users/{u}", None),
    ("POST", "/api/csv/import", CSV),
    ("POST", "/api/auth/logout", None),
]
READS = [
    "/api/variables",
    "/api/answers",
    "/api/search?q=horario",
    "/api/synonyms",
    "/api/unanswered",
    "/api/stats",
    "/api/users",
    "/api/csv/export",
    "/api/system/lan",
    "/api/system/qr.svg",
    "/api/auth/me",
]
ADMIN_ONLY_WRITES = {
    "/api/variables",
    "/api/answers",
    "/api/answers/{a}",
    "/api/answers/{a}/duplicate",
    "/api/synonyms",
    "/api/unanswered/{q}/answer",
    "/api/unanswered/{q}",
    "/api/ai/suggest",
    "/api/users",
    "/api/users/{u}",
    "/api/csv/import",
}
ADMIN_ONLY_READS = {
    "/api/stats",
    "/api/users",
    "/api/csv/export",
    "/api/system/lan",
    "/api/system/qr.svg",
}


def seed(admin: Api) -> dict[str, int]:
    answer = admin.post("/api/answers", json=answer_payload("Horario", "Abrimos")).json()
    admin.post("/api/unanswered", json={"query": "tienen parqueo gratis"})
    question = admin.get("/api/unanswered").json()[0]
    users = admin.get("/api/users").json()
    staff = next((u for u in users if u["username"] == STAFF[0]), None)
    return {"a": answer["id"], "q": question["id"], "u": staff["id"] if staff else 999}


def fill(path: str, ids: dict[str, int]) -> str:
    return path.format(**ids)


def send(
    client: TestClient,
    method: str,
    path: str,
    body: Any,
    ids: dict[str, int],
    headers: dict[str, str],
) -> Any:
    if isinstance(body, bytes):
        return client.request(method, fill(path, ids), content=body, headers=headers)
    if isinstance(body, dict) and body.get("question_id") == "{q}":
        body = {"question_id": ids["q"]}
    return client.request(method, fill(path, ids), json=body, headers=headers)


def snapshot(app: FastAPI) -> list[Any]:
    tables = ["answers", "variables", "synonym_groups", "users", "unanswered_questions"]
    return [run_sql(app, f"SELECT * FROM {table} ORDER BY 1") for table in tables]


def test_every_endpoint_requires_a_session(admin: Api, app: FastAPI) -> None:
    ids = seed(admin)
    before = snapshot(app)
    with TestClient(app) as anonymous:
        for path in READS:
            response = anonymous.get(fill(path, ids))
            assert response.status_code == 401, path
            assert response.json()["code"] == "auth.required"
        for method, path, body in STATE_CHANGING:
            response = send(anonymous, method, path, body, ids, {})
            assert response.status_code in (401, 403), (method, path, response.status_code)
    assert snapshot(app) == before


def test_staff_gets_403_on_every_admin_endpoint_and_nothing_changes(
    admin: Api, staff: Api, app: FastAPI
) -> None:
    ids = seed(admin)
    before = snapshot(app)
    for path in sorted(ADMIN_ONLY_READS):
        response = staff.get(path)
        assert response.status_code == 403, path
        assert response.json()["code"] == "auth.forbidden"
    for method, path, body in STATE_CHANGING:
        if path not in ADMIN_ONLY_WRITES:
            continue
        response = send(staff.client, method, path, body, ids, {"x-csrf-token": staff.csrf})
        assert response.status_code == 403, (method, path, response.status_code)
    assert snapshot(app) == before


def test_staff_can_search_copy_and_record_unanswered(admin: Api, staff: Api) -> None:
    ids = seed(admin)
    assert staff.get("/api/search", params={"q": "horario"}).status_code == 200
    assert staff.post(f"/api/answers/{ids['a']}/copy").status_code == 200
    assert staff.post("/api/unanswered", json={"query": "aceptan perros"}).status_code == 204
    assert staff.get("/api/unanswered").status_code == 200
    assert staff.get("/api/variables").status_code == 200


@pytest.mark.parametrize(
    "csrf", [None, "", "forged-token", "x" * 43], ids=["missing", "empty", "forged", "random"]
)
def test_every_state_changing_endpoint_rejects_a_bad_csrf_token(
    admin: Api, app: FastAPI, csrf: str | None
) -> None:
    ids = seed(admin)
    before = snapshot(app)
    headers = {} if csrf is None else {"x-csrf-token": csrf}
    for method, path, body in STATE_CHANGING:
        response = send(admin.client, method, path, body, ids, headers)
        assert response.status_code == 403, (method, path, response.status_code)
        assert response.json()["code"] == "auth.csrf_failed"
    assert snapshot(app) == before


def test_old_csrf_token_from_a_previous_session_is_rejected(admin: Api, app: FastAPI) -> None:
    old = admin.csrf
    admin.post("/api/auth/logout")
    assert admin.login(*ADMIN).status_code == 200
    response = admin.client.post(
        "/api/answers", json=answer_payload("X"), headers={"x-csrf-token": old}
    )
    assert response.status_code == 403
    pre_session = admin.client.cookies.get("rr_csrf")
    response = admin.client.post(
        "/api/answers", json=answer_payload("X"), headers={"x-csrf-token": pre_session or ""}
    )
    assert response.status_code == 403
    assert run_sql(app, "SELECT count(*) FROM answers")[0][0] == 0


@pytest.mark.parametrize(
    "header",
    [
        {"origin": "http://evil.example"},
        {"origin": "null"},
        {"origin": "http://testserver.evil.example"},
        {"origin": "http://evil.example@testserver.attacker"},
        {"referer": "http://evil.example/page"},
    ],
    ids=["foreign", "null", "suffix", "userinfo", "referer"],
)
def test_foreign_origin_is_rejected_even_with_a_valid_token(
    admin: Api, app: FastAPI, header: dict[str, str]
) -> None:
    ids = seed(admin)
    before = snapshot(app)
    for method, path, body in STATE_CHANGING:
        response = send(
            admin.client, method, path, body, ids, {"x-csrf-token": admin.csrf} | header
        )
        assert response.status_code == 403, (method, path)
        assert response.json()["code"] == "auth.csrf_failed"
    assert snapshot(app) == before


def test_login_and_setup_need_the_pre_session_token(anon: Api, admin: Api) -> None:
    for path in ("/api/auth/login", "/api/setup"):
        response = anon.client.post(path, json={"username": "admin", "password": ADMIN[1]})
        assert response.status_code == 403
        response = anon.client.post(
            path,
            json={"username": "admin", "password": ADMIN[1]},
            headers={"x-csrf-token": "forged"},
        )
        assert response.status_code == 403


def test_logged_out_cookie_is_dead(admin: Api) -> None:
    token = admin.client.cookies.get("rr_session")
    assert admin.post("/api/auth/logout").status_code == 204
    admin.client.cookies.set("rr_session", token or "")
    assert admin.get("/api/answers").status_code == 401
    assert admin.post("/api/answers", json=answer_payload()).status_code == 401


def test_idle_session_expires(fake_clock: FakeClock, admin: Api) -> None:
    fake_clock.advance(hours=12, minutes=1)
    response = admin.get("/api/answers")
    assert response.status_code == 401
    assert response.json()["code"] == "auth.session_expired"


def test_active_session_cookie_is_renewed_with_the_server_session(
    fake_clock: FakeClock, admin: Api
) -> None:
    """F6-08 expires only *idle* sessions. The server extends an active session, so the
    cookie (Max-Age = RR_SESSION_HOURS from login) must be extended too, or the browser
    drops it and an active user is logged out after 12 hours anyway."""
    fake_clock.advance(hours=11, minutes=56)
    response = admin.get("/api/answers")
    assert response.status_code == 200
    assert "rr_session=" in response.headers.get("set-cookie", ""), (
        "server extended the session but did not renew the cookie"
    )


def test_deactivated_user_loses_session_and_cannot_log_in(admin: Api, staff: Api) -> None:
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["role"] == "staff")
    assert staff.get("/api/answers").status_code == 200
    admin.put(f"/api/users/{staff_id}", json={"role": "staff", "active": False})
    assert staff.get("/api/answers").status_code == 401
    assert staff.post("/api/unanswered", json={"query": "parqueo gratis"}).status_code == 401
    assert staff.login(*STAFF).status_code == 401


def test_deleted_user_loses_session(admin: Api, staff: Api, app: FastAPI) -> None:
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["role"] == "staff")
    assert admin.delete(f"/api/users/{staff_id}").status_code == 204
    assert staff.get("/api/answers").status_code == 401
    assert staff.post("/api/unanswered", json={"query": "parqueo gratis"}).status_code == 401
    assert run_sql(app, "SELECT count(*) FROM sessions WHERE user_id = :u", u=staff_id)[0][0] == 0


def test_demoted_admin_loses_admin_rights_immediately(admin: Api, app: FastAPI) -> None:
    admin.post("/api/users", json={"username": "jefa", "password": "password-1", "role": "admin"})
    with TestClient(app) as other:
        boss = Api(other)
        assert boss.login("jefa", "password-1").status_code == 200
        jefa = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "jefa")
        admin.put(f"/api/users/{jefa}", json={"role": "staff", "active": True})
        assert boss.get("/api/stats").status_code == 403


def test_last_admin_cannot_remove_themselves(admin: Api) -> None:
    me = admin.get("/api/users").json()[0]
    for change in ({"role": "staff", "active": True}, {"role": "admin", "active": False}):
        assert admin.put(f"/api/users/{me['id']}", json=change).json()["code"] == "user.last_admin"
    assert admin.delete(f"/api/users/{me['id']}").json()["code"] == "user.last_admin"


def test_login_throttle_is_per_user_not_per_address(admin: Api, app: FastAPI) -> None:
    """F6-07: 5 failed logins *for one user* lock the 6th attempt, from any device."""
    for octet in range(1, 6):
        with TestClient(app, client=(f"192.168.1.{octet}", 50000)) as device:
            assert Api(device).login("admin", "wrong-pass-1").status_code == 401
    with TestClient(app, client=("192.168.1.99", 50000)) as device:
        response = Api(device).login("admin", "wrong-pass-1")
    assert response.status_code == 429, response.json()


def test_throttle_ignores_username_case_and_spaces(anon: Api, admin: Api) -> None:
    for name in ("admin", "ADMIN", " Admin ", "aDmIn", "admin "):
        assert anon.login(name, "wrong-pass-1").status_code == 401
    assert anon.login("admin", ADMIN[1]).status_code == 429


def test_cookie_flags_and_security_headers(anon: Api) -> None:
    response = anon.setup_admin()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    for header in ("content-security-policy", "x-frame-options", "x-content-type-options"):
        assert header in response.headers


def test_password_is_stored_only_as_argon2id(admin: Api, app: FastAPI) -> None:
    (stored,) = run_sql(app, "SELECT password_hash FROM users")
    assert stored[0].startswith("$argon2id$")
    assert ADMIN[1] not in stored[0]


def test_answer_ids_from_nowhere_give_404(admin: Api) -> None:
    for method, path in (
        ("PUT", "/api/answers/999999"),
        ("DELETE", "/api/answers/999999"),
        ("POST", "/api/answers/999999/copy"),
        ("POST", "/api/answers/-1/duplicate"),
    ):
        body = answer_payload("Z") if method == "PUT" else None
        response = admin.client.request(
            method, path, json=body, headers={"x-csrf-token": admin.csrf}
        )
        assert response.status_code == 404, path
        assert response.json()["code"] == "answer.not_found"
