"""Ways a query word can match an indexed word. Add a class to add a strategy."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from readyreply.domain.search import scoring_config as config
from readyreply.domain.search.index import SearchIndex


@dataclass(frozen=True, slots=True)
class TermMatch:
    term: str
    strength: float


class Scorer(Protocol):
    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]: ...


class EditDistance(Protocol):
    def distance(self, left: str, right: str, limit: int) -> int | None: ...


def allowed_edits(length: int) -> int:
    if length >= config.FUZZY_TWO_EDITS_MIN_CHARS:
        return config.FUZZY_EDITS_LONG
    if length >= config.FUZZY_ONE_EDIT_MIN_CHARS:
        return config.FUZZY_EDITS_SHORT
    return 0


class ExactScorer:
    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]:
        if token in index.vocabulary:
            yield TermMatch(token, config.EXACT_STRENGTH)


class SynonymScorer:
    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]:
        for term in index.synonyms.related(token):
            if term in index.vocabulary:
                yield TermMatch(term, config.SYNONYM_STRENGTH)


class PrefixScorer:
    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]:
        if len(token) < config.PREFIX_MIN_CHARS:
            return
        for term in index.vocabulary.with_prefix(token):
            if term != token:
                yield TermMatch(term, config.PREFIX_STRENGTH)


class FuzzyScorer:
    def __init__(self, edit_distance: EditDistance) -> None:
        self._edit_distance = edit_distance

    def matches(self, token: str, index: SearchIndex) -> Iterator[TermMatch]:
        limit = allowed_edits(len(token))
        if limit == 0:
            return
        for term in index.vocabulary.with_length_between(len(token) - limit, len(token) + limit):
            edits = self._edit_distance.distance(token, term, limit)
            if edits:
                penalty = (edits - 1) * config.FUZZY_PENALTY_PER_EXTRA_EDIT
                yield TermMatch(term, config.FUZZY_STRENGTH_ONE_EDIT - penalty)
