"""Synonym groups: "abren", "atienden" and "horario" find the same answer."""

from collections.abc import Iterable, Sequence

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.text import normalize

MIN_TERMS = 2
MAX_GROUPS = 200
MAX_TERMS_PER_GROUP = 30

SynonymGroup = tuple[str, ...]


def _clean_group(raw_terms: Iterable[str]) -> SynonymGroup:
    terms = tuple(dict.fromkeys(term for term in (normalize(raw) for raw in raw_terms) if term))
    if any(" " in term for term in terms):
        raise InvalidInputError("synonym.single_word")
    if len(terms) < MIN_TERMS:
        raise InvalidInputError("synonym.too_few_terms")
    if len(terms) > MAX_TERMS_PER_GROUP:
        raise InvalidInputError("synonym.too_many_terms", limit=MAX_TERMS_PER_GROUP)
    return terms


def validate_groups(raw_groups: Sequence[Iterable[str]]) -> list[SynonymGroup]:
    if len(raw_groups) > MAX_GROUPS:
        raise InvalidInputError("synonym.too_many_groups", limit=MAX_GROUPS)
    groups = [_clean_group(raw) for raw in raw_groups]
    seen: set[str] = set()
    for term in (term for group in groups for term in group):
        if term in seen:
            raise InvalidInputError("synonym.term_in_use", term=term)
        seen.add(term)
    return groups


class SynonymLookup:
    """Finds the other members of a term's group."""

    def __init__(self, groups: Iterable[SynonymGroup]) -> None:
        self._groups: dict[str, SynonymGroup] = {term: group for group in groups for term in group}

    def related(self, term: str) -> tuple[str, ...]:
        return tuple(other for other in self._groups.get(term, ()) if other != term)
