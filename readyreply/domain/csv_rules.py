"""Rules for the answers CSV format (no file handling here)."""

from collections.abc import Mapping, Sequence

from readyreply.domain.answers import AnswerDraft
from readyreply.domain.errors import InvalidInputError

CSV_HEADER = ("title", "category", "body", "tags")
TAG_SEPARATOR = "|"
MAX_ROWS = 5000
_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
_FORMULA_ESCAPE = "'"


def validate_header(header: Sequence[str]) -> None:
    if tuple(name.strip().casefold() for name in header) != CSV_HEADER:
        raise InvalidInputError("csv.invalid_header", expected=",".join(CSV_HEADER))


def escape_formula(cell: str) -> str:
    """Stop spreadsheet apps from running cells such as "=HYPERLINK(...)"."""
    return _FORMULA_ESCAPE + cell if cell.startswith(_FORMULA_STARTS) else cell


def _unescape_formula(cell: str) -> str:
    escaped = cell.startswith(_FORMULA_ESCAPE) and cell[1:2].startswith(_FORMULA_STARTS)
    return cell[1:] if escaped and cell[1:] else cell


def answer_to_row(draft: AnswerDraft) -> tuple[str, str, str, str]:
    tags = TAG_SEPARATOR.join(draft.tags)
    cells = (draft.title, draft.category, draft.body, tags)
    title, category, body, tag_cell = (escape_formula(cell) for cell in cells)
    return (title, category, body, tag_cell)


def row_to_draft(row: Mapping[str, str]) -> AnswerDraft:
    cells = {name: _unescape_formula(row.get(name) or "") for name in CSV_HEADER}
    tags = tuple(cells["tags"].split(TAG_SEPARATOR))
    return AnswerDraft(cells["title"], cells["category"], cells["body"], tags).cleaned()
