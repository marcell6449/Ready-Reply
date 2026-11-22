"""Answer entity and its validation rules."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.text import clean_text, is_blank, normalize

TITLE_MAX = 120
BODY_MAX = 4000
CATEGORY_MAX = 60
TAG_MAX = 40
TAGS_MAX_COUNT = 20


def title_key(title: str) -> str:
    """Comparison key so "Horario" and " HORÁRIO " count as the same title.

    Titles made only of emoji or symbols keep their symbols, so "🍔" and "🍕" differ.
    """
    return normalize(title) or " ".join(clean_text(title).casefold().split())


def _require_text(value: str, limit: int, field: str) -> str:
    cleaned = clean_text(value).strip()
    if is_blank(cleaned):
        raise InvalidInputError(f"answer.{field}_required")
    if len(cleaned) > limit:
        raise InvalidInputError(f"answer.{field}_too_long", limit=limit)
    return cleaned


def _clean_category(category: str) -> str:
    cleaned = clean_text(category).strip()
    if len(cleaned) > CATEGORY_MAX:
        raise InvalidInputError("answer.category_too_long", limit=CATEGORY_MAX)
    return cleaned


def parse_tags(raw_tags: Iterable[str]) -> tuple[str, ...]:
    tags = tuple(dict.fromkeys(tag for tag in (normalize(raw) for raw in raw_tags) if tag))
    if len(tags) > TAGS_MAX_COUNT:
        raise InvalidInputError("answer.too_many_tags", limit=TAGS_MAX_COUNT)
    if any(len(tag) > TAG_MAX for tag in tags):
        raise InvalidInputError("answer.tag_too_long", limit=TAG_MAX)
    return tags


@dataclass(frozen=True, slots=True)
class AnswerDraft:
    """What a person types when creating or editing an answer."""

    title: str
    category: str
    body: str
    tags: tuple[str, ...]

    def cleaned(self) -> "AnswerDraft":
        return AnswerDraft(
            title=_require_text(self.title, TITLE_MAX, "title"),
            category=_clean_category(self.category),
            body=_require_text(self.body, BODY_MAX, "body"),
            tags=parse_tags(self.tags),
        )


@dataclass(frozen=True, slots=True)
class Answer:
    id: int | None
    business_id: int
    title: str
    category: str
    body: str
    tags: tuple[str, ...]
    created_at: datetime
    updated_at: datetime

    @property
    def title_key(self) -> str:
        return title_key(self.title)

    def with_draft(self, draft: AnswerDraft, now: datetime) -> "Answer":
        return replace(
            self,
            title=draft.title,
            category=draft.category,
            body=draft.body,
            tags=draft.tags,
            updated_at=now,
        )


def copy_title(title: str, suffix_word: str, taken_keys: frozenset[str]) -> str:
    """ "Horario" → "Horario (copia)", then "Horario (copia 2)", ... skipping taken titles."""
    number = 1
    while True:
        label = suffix_word if number == 1 else f"{suffix_word} {number}"
        suffix = f" ({label})"
        candidate = title[: TITLE_MAX - len(suffix)].rstrip() + suffix
        if title_key(candidate) not in taken_keys:
            return candidate
        number += 1
