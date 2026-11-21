"""F1, F2: variables and answers through the API."""

from fastapi import FastAPI

from tests.conftest import Api, answer_payload, run_sql, set_variables


def test_builtin_variables_exist_on_new_database(admin: Api) -> None:  # F1-01
    variables = admin.get("/api/variables").json()
    assert [v["key"] for v in variables] == ["name", "hours", "address", "sinpe", "phone", "prices"]
    assert all(v["value"] == "" and v["builtin"] for v in variables)


def test_save_variable_with_emoji(admin: Api) -> None:  # F1-02, F1-03
    response = set_variables(admin, hours="L-V 7am–5pm 🕖", wifi="clave123")
    assert response.status_code == 200
    saved = {v["key"]: v["value"] for v in admin.get("/api/variables").json()}
    assert saved["hours"] == "L-V 7am–5pm 🕖"
    assert saved["wifi"] == "clave123"


def test_invalid_variable_rejected_and_nothing_saved(admin: Api) -> None:  # F1-04
    response = set_variables(admin, hours="x", **{"Wi Fi": "v"})
    assert (response.status_code, response.json()["code"]) == (422, "variable.invalid_key")
    assert {v["key"]: v["value"] for v in admin.get("/api/variables").json()}["hours"] == ""


def test_builtin_cannot_be_deleted(admin: Api) -> None:  # F1-06
    without_sinpe = [v for v in admin.get("/api/variables").json() if v["key"] != "sinpe"]
    response = admin.put("/api/variables", json=without_sinpe)
    assert response.json()["code"] == "variable.builtin_protected"


def test_staff_reads_but_cannot_edit_variables(staff: Api) -> None:  # F1-08
    assert staff.get("/api/variables").status_code == 200
    assert staff.put("/api/variables", json=[]).status_code == 403


def test_create_list_edit_answer(admin: Api) -> None:  # F2-01, F2-05
    created = admin.post("/api/answers", json=answer_payload(tags=["Pago", " SINPE", "pago ", " "]))
    assert created.status_code == 201
    answer = created.json()
    assert answer["tags"] == ["pago", "sinpe"]  # F2-11
    edited = admin.put(f"/api/answers/{answer['id']}", json=answer_payload(body="Nuevo texto"))
    assert edited.json()["body"] == "Nuevo texto"
    assert edited.json()["updated_at"] >= answer["updated_at"]
    assert admin.get("/api/search", params={"q": "nuevo"}).json()[0]["answer"]["id"] == answer["id"]


def test_answer_validation(admin: Api) -> None:  # F2-02, F2-03
    cases = {
        "answer.title_required": answer_payload(title="   "),
        "answer.body_required": answer_payload(body=""),
        "answer.title_too_long": answer_payload(title="x" * 121),
        "answer.body_too_long": answer_payload(body="x" * 4001),
    }
    for code, payload in cases.items():
        response = admin.post("/api/answers", json=payload)
        assert (response.status_code, response.json()["code"]) == (422, code)


def test_duplicate_title_ignores_case_accents_spaces(admin: Api) -> None:  # F2-04, F2-09
    assert admin.post("/api/answers", json=answer_payload("Horario")).status_code == 201
    for title in ("horário", " HORARIO "):
        response = admin.post("/api/answers", json=answer_payload(title))
        assert (response.status_code, response.json()["code"]) == (409, "answer.title_taken")
    assert len(admin.get("/api/answers").json()) == 1


def test_edit_to_taken_title_rejected(admin: Api) -> None:
    admin.post("/api/answers", json=answer_payload("A"))
    second = admin.post("/api/answers", json=answer_payload("B")).json()
    response = admin.put(f"/api/answers/{second['id']}", json=answer_payload("a"))
    assert response.json()["code"] == "answer.title_taken"
    assert admin.put(f"/api/answers/{second['id']}", json=answer_payload("b")).status_code == 200


def test_delete_answer_removes_it_everywhere(admin: Api) -> None:  # F2-06
    answer = admin.post("/api/answers", json=answer_payload(body="Hola")).json()
    admin.post(f"/api/answers/{answer['id']}/copy")
    assert admin.delete(f"/api/answers/{answer['id']}").status_code == 204
    assert admin.get("/api/answers").json() == []
    assert admin.get("/api/search", params={"q": "horario"}).json() == []
    assert admin.get("/api/stats").json()["top_copied"] == []


def test_duplicate_answer(admin: Api) -> None:  # F2-07
    answer = admin.post("/api/answers", json=answer_payload()).json()
    first = admin.post(f"/api/answers/{answer['id']}/duplicate").json()
    second = admin.post(f"/api/answers/{answer['id']}/duplicate").json()
    assert (first["title"], second["title"]) == ("Horario (copia)", "Horario (copia 2)")
    assert first["body"] == answer["body"]


def test_staff_cannot_change_answers(admin: Api, staff: Api) -> None:  # F2-08
    answer = admin.post("/api/answers", json=answer_payload()).json()
    calls = [
        staff.post("/api/answers", json=answer_payload("Otra")),
        staff.put(f"/api/answers/{answer['id']}", json=answer_payload()),
        staff.delete(f"/api/answers/{answer['id']}"),
        staff.post(f"/api/answers/{answer['id']}/duplicate"),
    ]
    assert [c.status_code for c in calls] == [403] * 4
    assert len(admin.get("/api/answers").json()) == 1


def test_unknown_or_foreign_answer(admin: Api, app: FastAPI) -> None:  # F2-10
    assert admin.put("/api/answers/999", json=answer_payload()).json()["code"] == "answer.not_found"
    assert admin.delete("/api/answers/999").status_code == 404
    run_sql(app, "INSERT INTO businesses (id, locale, content_revision) VALUES (2, 'es', 0)")
    run_sql(
        app,
        "INSERT INTO answers (business_id, title, title_key, category, body, tags, created_at,"
        " updated_at) VALUES (2, 'Ajena', 'ajena', '', 'secreto', '[]',"
        " '2026-01-01', '2026-01-01')",
    )
    (foreign_id,) = run_sql(app, "SELECT id FROM answers WHERE business_id = 2")[0]
    assert admin.delete(f"/api/answers/{foreign_id}").status_code == 404
    assert admin.post(f"/api/answers/{foreign_id}/copy").status_code == 404
    assert admin.get("/api/search", params={"q": "ajena"}).json() == []
    assert admin.get("/api/answers").json() == []


def test_emojis_and_newlines_kept(admin: Api) -> None:  # F2-12
    body = "Hola 👋\n*Bienvenido* a {name} 🍔"
    answer = admin.post("/api/answers", json=answer_payload(body=body)).json()
    set_variables(admin, name="Soda Tica")
    copied = admin.post(f"/api/answers/{answer['id']}/copy").json()
    assert copied["text"] == "Hola 👋\n*Bienvenido* a Soda Tica 🍔"


def test_synonyms_roundtrip_and_validation(admin: Api, staff: Api) -> None:  # F3-15
    response = admin.put("/api/synonyms", json={"groups": [["Envío", "express", "delivery"]]})
    assert response.json()["groups"] == [["envio", "express", "delivery"]]
    assert staff.get("/api/synonyms").json()["groups"] == [["envio", "express", "delivery"]]
    bad = admin.put("/api/synonyms", json={"groups": [["uno"]]})
    assert (bad.status_code, bad.json()["code"]) == (422, "synonym.too_few_terms")
