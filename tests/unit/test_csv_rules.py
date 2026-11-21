"""F10-02, F10-03, F10-05, F10-09 (pure rules; file decoding lives in infrastructure)."""

import pytest

from readyreply.domain.answers import AnswerDraft
from readyreply.domain.csv_rules import (
    CSV_HEADER,
    TAG_SEPARATOR,
    answer_to_row,
    escape_formula,
    row_to_draft,
    validate_header,
)
from readyreply.domain.errors import InvalidInputError


def test_header() -> None:
    assert CSV_HEADER == ("title", "category", "body", "tags")
    validate_header(["Title ", "category", "BODY", "tags"])


@pytest.mark.parametrize("header", [[], ["title", "body"], ["titel", "category", "body", "tags"]])
def test_invalid_header(header: list[str]) -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_header(header)
    assert error.value.code == "csv.invalid_header"


@pytest.mark.parametrize("cell", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_formula_cells_escaped(cell: str) -> None:
    assert escape_formula(cell) == "'" + cell


def test_safe_cell_untouched() -> None:
    assert escape_formula("Horario") == "Horario"


def test_row_round_trip() -> None:
    draft = AnswerDraft("=Horario", "Info", 'Línea 1\n"Línea" 2, 🍔', ("pago", "sinpe"))
    row = answer_to_row(draft)
    assert row == ("'=Horario", "Info", 'Línea 1\n"Línea" 2, 🍔', "pago|sinpe")
    parsed = row_to_draft(dict(zip(CSV_HEADER, row, strict=True)))
    assert parsed.title == "=Horario"
    assert parsed.tags == ("pago", "sinpe")
    assert TAG_SEPARATOR == "|"


def test_row_validation_uses_answer_rules() -> None:
    with pytest.raises(InvalidInputError) as error:
        row_to_draft({"title": "", "category": "", "body": "x", "tags": ""})
    assert error.value.code == "answer.title_required"


def test_row_missing_cells_are_empty() -> None:
    with pytest.raises(InvalidInputError):
        row_to_draft({"title": "T"})
