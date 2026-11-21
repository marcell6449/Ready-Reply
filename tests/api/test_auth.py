"""F6: setup, login, sessions, CSRF, roles."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import ADMIN, STAFF, Api, run_sql


def test_new_database_needs_setup(anon: Api) -> None:  # F6-01, F11-06
    assert anon.get("/api/setup/status").json()["needs_setup"] is True
    assert anon.get("/api/auth/me").status_code == 401


def test_setup_creates_admin_and_signs_in(admin: Api) -> None:
    me = admin.get("/api/auth/me").json()
    assert (me["username"], me["role"]) == ("admin", "admin")
    assert admin.get("/api/setup/status").json()["needs_setup"] is False


def test_setup_only_once(admin: Api, anon: Api) -> None:  # F6-02
    response = Api(admin.client).setup_admin("other", "other-pass-1")
    assert (response.status_code, response.json()["code"]) == (409, "setup.already_done")


def test_setup_requires_csrf(anon: Api) -> None:
    response = anon.client.post("/api/setup", json={"username": "a1b", "password": "12345678"})
    assert (response.status_code, response.json()["code"]) == (403, "auth.csrf_failed")


def test_weak_password(anon: Api) -> None:  # F6-03
    response = anon.setup_admin("admin", "short")
    assert (response.status_code, response.json()["code"]) == (422, "auth.weak_password")


def test_password_stored_as_argon2id(admin: Api, app: FastAPI) -> None:  # F6-04
    (stored,) = run_sql(app, "SELECT password_hash FROM users")[0]
    assert stored.startswith("$argon2id$")
    assert ADMIN[1] not in stored


def test_session_cookie_flags(anon: Api) -> None:  # F6-05
    response = anon.setup_admin()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie


def test_wrong_credentials_do_not_reveal_user(admin: Api, app: FastAPI) -> None:  # F6-06
    with TestClient(app) as other:
        wrong_password = Api(other).login("admin", "nope-nope")
        unknown_user = Api(other).login("ghost", "nope-nope")
    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["code"] == "auth.invalid_credentials"


def test_login_is_throttled(admin: Api, app: FastAPI) -> None:  # F6-07
    with TestClient(app) as other:
        api = Api(other)
        codes = [api.login("admin", "bad-password").status_code for _ in range(6)]
        assert codes == [401] * 5 + [429]
        assert api.login(*ADMIN).json()["code"] == "auth.too_many_attempts"


def test_successful_login(admin: Api, app: FastAPI) -> None:
    with TestClient(app) as other:
        assert Api(other).login(" ADMIN ", ADMIN[1]).status_code == 200


def test_expired_session(admin: Api, app: FastAPI) -> None:  # F6-08, F4-09
    run_sql(app, "UPDATE sessions SET expires_at = '2000-01-01 00:00:00'")
    response = admin.get("/api/auth/me")
    assert (response.status_code, response.json()["code"]) == (401, "auth.session_expired")
    assert admin.get("/api/auth/me").json()["code"] == "auth.required"


def test_session_is_refreshed_when_old(admin: Api, app: FastAPI) -> None:
    run_sql(app, "UPDATE sessions SET expires_at = datetime('now', '+1 hour')")
    assert admin.get("/api/auth/me").status_code == 200
    (expires,) = run_sql(app, "SELECT expires_at FROM sessions")[0]
    (later,) = run_sql(app, "SELECT datetime('now', '+11 hours')")[0]
    assert str(expires) > str(later)


def test_logout_invalidates_cookie(admin: Api) -> None:  # F6-09
    old_cookie = admin.client.cookies.get("rr_session")
    assert admin.post("/api/auth/logout").status_code == 204
    admin.client.cookies.set("rr_session", old_cookie or "")
    assert admin.get("/api/auth/me").status_code == 401


def test_state_change_without_csrf_header(admin: Api) -> None:  # F6-10
    response = admin.client.put("/api/variables", json=[])
    assert (response.status_code, response.json()["code"]) == (403, "auth.csrf_failed")


def test_foreign_origin_rejected(admin: Api) -> None:  # F6-10
    response = admin.post("/api/answers", json={}, headers={"origin": "http://evil.example"})
    assert (response.status_code, response.json()["code"]) == (403, "auth.csrf_failed")


def test_same_origin_allowed(admin: Api) -> None:
    response = admin.post(
        "/api/answers",
        json={"title": "T", "body": "B"},
        headers={"origin": "http://testserver"},
    )
    assert response.status_code == 201


def test_staff_cannot_use_admin_endpoints(staff: Api) -> None:  # F6-11
    calls = [
        staff.put("/api/variables", json=[]),
        staff.post("/api/answers", json={"title": "T", "body": "B"}),
        staff.get("/api/users"),
        staff.get("/api/stats"),
        staff.get("/api/csv/export"),
        staff.post("/api/csv/import", content=b"title,category,body,tags\n"),
        staff.post("/api/demo/soda", json={}),
        staff.post("/api/ai/suggest", json={"question_id": 1}),
        staff.put("/api/synonyms", json={"groups": []}),
        staff.get("/api/system/lan"),
        staff.get("/api/system/qr.svg"),
    ]
    assert [c.status_code for c in calls] == [403] * len(calls)
    assert {c.json()["code"] for c in calls} == {"auth.forbidden"}


def test_last_admin_cannot_be_demoted(admin: Api) -> None:  # F6-12
    (me,) = admin.get("/api/users").json()
    response = admin.put(f"/api/users/{me['id']}", json={"role": "staff", "active": True})
    assert response.json()["code"] == "user.last_admin"
    assert admin.delete(f"/api/users/{me['id']}").json()["code"] == "user.last_admin"


def test_deactivated_user_is_signed_out(admin: Api, staff: Api) -> None:  # F6-13
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "staff")
    admin.put(f"/api/users/{staff_id}", json={"role": "staff", "active": False})
    assert staff.get("/api/auth/me").status_code == 401
    assert staff.login(*STAFF).status_code == 401


def test_password_reset_signs_out_and_new_password_works(admin: Api, staff: Api) -> None:
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "staff")
    changes = {"role": "staff", "active": True, "new_password": "brand-new-pass"}
    assert admin.put(f"/api/users/{staff_id}", json=changes).status_code == 200
    assert staff.get("/api/auth/me").status_code == 401
    assert staff.login("staff", "brand-new-pass").status_code == 200


def test_username_unique_ignoring_case(admin: Api) -> None:  # F6-14
    admin.post("/api/users", json={"username": "ana", "password": "12345678", "role": "staff"})
    response = admin.post(
        "/api/users", json={"username": " ANA ", "password": "12345678", "role": "staff"}
    )
    assert (response.status_code, response.json()["code"]) == (409, "user.username_taken")


def test_delete_user(admin: Api, staff: Api) -> None:
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "staff")
    assert admin.delete(f"/api/users/{staff_id}").status_code == 204
    assert staff.get("/api/auth/me").status_code == 401
    assert admin.delete("/api/users/999").json()["code"] == "user.not_found"


def test_admin_promotes_staff(admin: Api, staff: Api) -> None:
    staff_id = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "staff")
    admin.put(f"/api/users/{staff_id}", json={"role": "admin", "active": True})
    assert staff.get("/api/users").status_code == 200


def test_invalid_payload_has_code(admin: Api) -> None:
    response = admin.post("/api/answers", json={"title": 5})
    assert (response.status_code, response.json()["code"]) == (422, "request.invalid")
