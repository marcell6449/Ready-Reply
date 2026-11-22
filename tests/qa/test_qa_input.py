"""QA: strange input and injection in every text field, through the API."""

import unicodedata
from typing import Any

import pytest

from tests.conftest import Api, answer_payload, run_sql, set_variables
from tests.support.seed import seed_business

SQLI = "'; DROP TABLE answers; --"
HTML = '<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>'
STRANGE_TEXTS = [
    "Promo 🍔🍟 2x1 👨\u200d👩\u200d👧\u200d👦",
    "\u202eRTL override عربى",
    "שלום עולם",
    "x" * 120,
    "Línea con tabulación\tadentro",
    "2026",
    SQLI,
    HTML,
    "%_%' OR '1'='1",
]


def create(api: Api, title: str, body: str = "Cuerpo", **extra: Any) -> Any:
    return api.post("/api/answers", json=answer_payload(title, body, **extra))


@pytest.mark.parametrize("title", STRANGE_TEXTS)
def test_strange_titles_are_stored_and_returned_exactly(admin: Api, title: str) -> None:
    response = create(admin, title, body=f"Cuerpo {title}")
    assert response.status_code == 201, response.text
    (stored,) = admin.get("/api/answers").json()
    assert stored["title"] == title
    assert stored["body"] == f"Cuerpo {title}"
    copied = admin.post(f"/api/answers/{stored['id']}/copy").json()
    assert copied["text"] == f"Cuerpo {title}"


def test_sql_injection_in_every_answer_field_is_plain_text(admin: Api, app: Any) -> None:
    response = create(admin, SQLI, body=SQLI, category=SQLI[:60], tags=[SQLI[:40]])
    assert response.status_code == 201
    assert run_sql(app, "SELECT count(*) FROM answers")[0][0] == 1
    assert admin.get("/api/answers").json()[0]["title"] == SQLI


@pytest.mark.parametrize("blank", ["", "   ", "\t\n", "  ", "　", "   "], ids=repr)
def test_whitespace_only_title_or_body_is_rejected(admin: Api, blank: str) -> None:
    assert create(admin, blank).json()["code"] == "answer.title_required"
    assert create(admin, "Título", body=blank).json()["code"] == "answer.body_required"


def test_emoji_only_titles_are_distinct_answers(admin: Api) -> None:
    """Two different emoji-only titles are not the same title (both normalize to "")."""
    assert create(admin, "🍔").status_code == 201
    response = create(admin, "🍕")
    assert response.status_code == 201, response.json()


def test_punctuation_title_does_not_block_an_unrelated_emoji_title(admin: Api) -> None:
    assert create(admin, "!!!").status_code == 201
    response = create(admin, "☕")
    assert response.status_code == 201, response.json()


@pytest.mark.parametrize("invisible", ["\u200b\u200c\u200d", "\u2060", "\u00ad"], ids=repr)
def test_invisible_only_title_is_rejected_as_empty(admin: Api, invisible: str) -> None:
    response = create(admin, invisible)
    assert response.status_code == 422, f"invisible title {invisible!r} was accepted"
    assert response.json()["code"] == "answer.title_required"


@pytest.mark.parametrize("trick", ["Hora\u200brio", "Hor\u2060ario", "Ho\u00adrario"])
def test_title_differing_only_by_invisible_characters_is_a_duplicate(
    admin: Api, trick: str
) -> None:
    assert create(admin, "Horario").status_code == 201
    response = create(admin, trick)
    assert response.status_code == 409, f"{trick!r} looks identical to 'Horario' but was accepted"
    assert response.json()["code"] == "answer.title_taken"


def test_composed_and_decomposed_accents_are_the_same_title(admin: Api) -> None:
    composed = unicodedata.normalize("NFC", "Menú del día")
    decomposed = unicodedata.normalize("NFD", "Menú del día")
    assert composed != decomposed
    assert create(admin, composed).status_code == 201
    assert create(admin, decomposed).json()["code"] == "answer.title_taken"


def test_decomposed_accents_do_not_count_double_against_the_title_limit(admin: Api) -> None:
    """120 visible letters typed on a keyboard that sends NFD (e.g. macOS) must be accepted."""
    visible = "é" * 120
    assert create(admin, unicodedata.normalize("NFC", visible)).status_code == 201
    response = create(admin, "Otra " + unicodedata.normalize("NFD", "é" * 115))
    assert response.status_code == 201, response.json()


def test_numbers_and_fullwidth_digits_in_titles(admin: Api) -> None:
    assert create(admin, "2").status_code == 201
    assert create(admin, "Promo 2x1").status_code == 201
    assert create(admin, "１２３").status_code == 201
    assert create(admin, "123").json()["code"] == "answer.title_taken"


def test_null_byte_in_an_answer_does_not_break_csv_backup(admin: Api) -> None:
    """Whatever the server accepts must survive export → import (F10-01)."""
    created = create(admin, "Horario\x00", body="Abrimos\x00 a las 8")
    if created.status_code == 422:
        return  # rejecting NUL is acceptable
    exported = admin.get("/api/csv/export").content
    for answer in admin.get("/api/answers").json():
        admin.delete(f"/api/answers/{answer['id']}")
    report = admin.post("/api/csv/import", content=exported)
    assert report.status_code == 200, report.json()
    assert report.json()["imported"] == 1


def test_very_long_inputs_never_cause_a_server_error(admin: Api) -> None:
    huge = "🍔" * 20_000
    for response in (
        create(admin, huge),
        create(admin, "T", body=huge),
        create(admin, "T", category=huge),
        create(admin, "T", tags=[huge]),
        admin.put("/api/synonyms", json={"groups": [[huge, "b"]]}),
        admin.post("/api/unanswered", json={"query": huge}),
        admin.get("/api/search", params={"q": "a" * 1999}),
    ):
        assert response.status_code < 500
    assert create(admin, "x" * 121).json()["code"] == "answer.title_too_long"
    assert create(admin, "T", body="x" * 4001).json()["code"] == "answer.body_too_long"


def test_search_accepts_a_long_pasted_query(admin: Api) -> None:
    """F3-11: queries are cut to 200 chars, so a long pasted text must still answer 200."""
    create(admin, "Horario", body="Abrimos a las 8")
    response = admin.get("/api/search", params={"q": "horario " * 300})
    assert response.status_code == 200, response.json()
    assert response.json()[0]["answer"]["title"] == "Horario"


@pytest.mark.parametrize("query", ["' OR 1=1 --", "%", "_", "\\", "\x00", '"; DELETE FROM users;'])
def test_search_injection_returns_no_error(admin: Api, query: str) -> None:
    create(admin, "Horario", body="Abrimos a las 8")
    response = admin.get("/api/search", params={"q": query})
    assert response.status_code == 200
    assert len(response.json()) <= 1


def test_variables_keep_emoji_html_and_sql_exactly(admin: Api) -> None:
    assert set_variables(admin, hours="L-V 7am–5pm 🕖", name=HTML, address=SQLI).status_code == 200
    values = {v["key"]: v["value"] for v in admin.get("/api/variables").json()}
    assert values["hours"] == "L-V 7am–5pm 🕖"
    assert values["name"] == HTML
    assert values["address"] == SQLI
    answer = create(admin, "Datos", body="{name} | {address} | {hours}").json()
    text = admin.post(f"/api/answers/{answer['id']}/copy").json()["text"]
    assert text == f"{HTML} | {SQLI} | L-V 7am–5pm 🕖"


def test_variable_value_with_placeholder_is_not_expanded_twice(admin: Api) -> None:
    set_variables(admin, hours="{sinpe}", sinpe="8888")
    answer = create(admin, "H", body="{hours} {{x}}").json()
    assert admin.post(f"/api/answers/{answer['id']}/copy").json()["text"] == "{sinpe} {x}"


@pytest.mark.parametrize(
    "key", ["wi fi", "ñame", "１abc", "a١", "wifi;drop", "<b>", "WIFI", "x" * 41, ""]
)
def test_invalid_custom_variable_keys(admin: Api, key: str) -> None:
    response = set_variables(admin, **{key: "valor"})
    assert response.status_code == 422
    assert response.json()["code"] == "variable.invalid_key"


def test_custom_variable_label_with_html_and_emoji(admin: Api) -> None:
    current = admin.get("/api/variables").json()
    extra = {"key": "wifi", "label": "🔑 " + HTML[:50], "value": "clave", "builtin": False}
    response = admin.put("/api/variables", json=[*current, extra])
    assert response.status_code == 200
    assert response.json()[-1]["label"] == ("🔑 " + HTML[:50]).strip()


def test_synonyms_with_injection_are_stored_as_words(admin: Api) -> None:
    groups = [["drop", "table", "answers"], ["script", "alert"]]
    response = admin.put("/api/synonyms", json={"groups": [[SQLI, "x"], groups[1]]})
    # The SQL text contains spaces once normalized, so it is rejected as not a single word.
    assert response.json()["code"] == "synonym.single_word"
    response = admin.put("/api/synonyms", json={"groups": [["<script>", "alert()"]]})
    assert response.status_code == 200
    assert response.json()["groups"] == [["script", "alert"]]


def test_emoji_only_synonym_group_is_rejected(admin: Api) -> None:
    response = admin.put("/api/synonyms", json={"groups": [["🍔", "🍕"]]})
    assert response.json()["code"] == "synonym.too_few_terms"


@pytest.mark.parametrize(
    "username",
    [SQLI, "<script>", "аdmin", "ana\u200b", "ana ana", "😀😀😀", "ab", "a" * 33, "\x00ana"],
    ids=repr,
)
def test_strange_usernames_are_rejected(admin: Api, username: str) -> None:
    response = admin.post(
        "/api/users", json={"username": username, "password": "password-1", "role": "staff"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "user.invalid_username"


def test_login_with_injection_is_just_a_wrong_login(anon: Api, admin: Api) -> None:
    for username in (SQLI, "admin' --", "admin\x00", "%"):
        response = anon.login(username, "whatever-123")
        assert response.status_code == 401
        assert response.json()["code"] == "auth.invalid_credentials"


@pytest.mark.parametrize("question", [HTML, SQLI, "¿Tienen 🅿️ parqueo?", "\u202eparqueo gratis"])
def test_unanswered_question_text_is_stored_literally(admin: Api, question: str) -> None:
    assert admin.post("/api/unanswered", json={"query": question}).status_code == 204
    (listed,) = admin.get("/api/unanswered").json()
    assert listed["text"] == question


def test_stop_words_only_query_behaves_like_an_empty_query(admin: Api) -> None:
    """F3-03 says stop words are ignored; a greeting alone must not hide every answer."""
    seed_business(admin, "soda")
    everything = [r["answer"]["id"] for r in admin.get("/api/search", params={"q": ""}).json()]
    for query in ("hola buenas", "de la", "que"):
        found = [r["answer"]["id"] for r in admin.get("/api/search", params={"q": query}).json()]
        assert found == everything, f"{query!r} returned {len(found)} of {len(everything)}"


def test_every_error_code_returned_for_bad_input_has_a_message_in_both_languages(
    admin: Api,
) -> None:
    import json
    from pathlib import Path

    catalog = json.loads(
        (
            Path(__file__).resolve().parents[2] / "readyreply/web/static/i18n/translations.json"
        ).read_text("utf-8")
    )
    responses = [
        create(admin, ""),
        create(admin, "T", body=""),
        create(admin, "x" * 121),
        create(admin, "T", category="c" * 61),
        create(admin, "T", tags=[f"t{i}" for i in range(21)]),
        create(admin, "T", tags=["t" * 41]),
        create(admin, "T", body="b" * 4001),
        admin.put("/api/variables", json=[]),
        set_variables(admin, **{"1x": "v"}),
        admin.put(
            "/api/variables",
            json=[
                *admin.get("/api/variables").json(),
                {"key": "k", "label": "", "value": "", "builtin": False},
            ],
        ),
        admin.put("/api/synonyms", json={"groups": [["a b", "c"]]}),
        admin.put("/api/synonyms", json={"groups": [["uno"]]}),
        admin.post(
            "/api/users", json={"username": "ok_user", "password": "corta", "role": "staff"}
        ),
        admin.post(
            "/api/users", json={"username": "ok_user", "password": "p" * 129, "role": "staff"}
        ),
        admin.post("/api/unanswered", json={"query": "ab"}),
        admin.post("/api/csv/import", content=b"x,y\n1,2\n"),
        admin.post("/api/csv/import", content=b'title,category,body,tags\n"a,b\n'),
        admin.post("/api/answers", json={"title": 5}),
        admin.delete("/api/unanswered/99999"),
    ]
    codes = {r.json()["code"] for r in responses}
    assert len(codes) >= 15
    for locale in ("es", "en"):
        assert [c for c in codes if f"error.{c}" not in catalog[locale]] == [], locale
