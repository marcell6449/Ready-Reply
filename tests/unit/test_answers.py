"""F2-02, F2-03, F2-04, F2-07, F2-11."""

import pytest

from readyreply.domain.answers import (
    BODY_MAX,
    TITLE_MAX,
    AnswerDraft,
    copy_title,
    parse_tags,
    title_key,
)
from readyreply.domain.errors import InvalidInputError


def draft(**overrides: object) -> AnswerDraft:
    fields: dict[str, object] = {
        "title": "Horario",
        "category": "Info",
        "body": "Abrimos {hours}",
        "tags": ("horario",),
    }
    fields.update(overrides)
    return AnswerDraft(**fields)  # type: ignore[arg-type]


def test_clean_trims_fields() -> None:
    cleaned = draft(title="  Horario ", category=" Info ", body=" Abrimos \n").cleaned()
    assert (cleaned.title, cleaned.category, cleaned.body) == ("Horario", "Info", "Abrimos")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("title", "   ", "answer.title_required"),
        ("body", "", "answer.body_required"),
        ("title", "x" * (TITLE_MAX + 1), "answer.title_too_long"),
        ("body", "x" * (BODY_MAX + 1), "answer.body_too_long"),
        ("category", "x" * 61, "answer.category_too_long"),
    ],
)
def test_clean_rejects_invalid_fields(field: str, value: str, code: str) -> None:
    with pytest.raises(InvalidInputError) as error:
        draft(**{field: value}).cleaned()
    assert error.value.code == code


def test_limits_are_inclusive() -> None:
    draft(title="x" * TITLE_MAX, body="y" * BODY_MAX).cleaned()


def test_tags_normalized_and_unique() -> None:
    assert parse_tags(["Pago", " SINPE", "pago ", " ", "Envío"]) == ("pago", "sinpe", "envio")


def test_too_many_tags_rejected() -> None:
    with pytest.raises(InvalidInputError) as error:
        parse_tags([f"t{i}" for i in range(21)])
    assert error.value.code == "answer.too_many_tags"


def test_long_tag_rejected() -> None:
    with pytest.raises(InvalidInputError) as error:
        parse_tags(["x" * 41])
    assert error.value.code == "answer.tag_too_long"


def test_clean_parses_tags() -> None:
    assert draft(tags=("Pago", "pago")).cleaned().tags == ("pago",)


def test_title_key_ignores_case_accents_spaces() -> None:
    assert title_key(" HORÁRIO ") == title_key("horario") == "horario"


def test_copy_title_first_and_next() -> None:
    assert copy_title("Horario", "copia", frozenset({"horario"})) == "Horario (copia)"
    taken = frozenset({"horario", "horario copia"})
    assert copy_title("Horario", "copia", taken) == "Horario (copia 2)"
    taken = taken | {"horario copia 2"}
    assert copy_title("Horario", "copia", taken) == "Horario (copia 3)"


def test_copy_title_respects_max_length() -> None:
    title = copy_title("x" * TITLE_MAX, "copy", frozenset())
    assert len(title) <= TITLE_MAX
    assert title.endswith("(copy)")


def test_answer_with_draft_updates_fields_and_time() -> None:
    from datetime import UTC, datetime

    from readyreply.domain.answers import Answer

    created = datetime(2026, 1, 1, tzinfo=UTC)
    later = datetime(2026, 1, 2, tzinfo=UTC)
    answer = Answer(1, 1, "Horário", "", "x", (), created, created)
    updated = answer.with_draft(draft(title="Nuevo").cleaned(), later)
    assert answer.title_key == "horario"
    assert (updated.title, updated.updated_at, updated.created_at) == ("Nuevo", later, created)
