"""Search use case with a per-business index cache (F3, P8)."""

import threading
from dataclasses import dataclass

from readyreply.application.context import Actor
from readyreply.application.ports import UnitOfWork, UnitOfWorkFactory
from readyreply.domain.answers import Answer
from readyreply.domain.permissions import Action
from readyreply.domain.search.engine import SearchDocument, SearchEngine, SearchIndex
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.templates import RenderResult, render
from readyreply.domain.variables import values_by_key

RESULT_LIMIT = 50


@dataclass(frozen=True, slots=True)
class SearchResult:
    answer: Answer
    preview: RenderResult


@dataclass(frozen=True, slots=True)
class _CachedIndex:
    revision: int
    index: SearchIndex
    answers: dict[int, Answer]


class SearchIndexCache:
    """Rebuilds a business's index only when its content revision changes."""

    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer
        self._entries: dict[int, _CachedIndex] = {}
        self._lock = threading.Lock()

    def get(self, uow: UnitOfWork, business_id: int) -> tuple[SearchIndex, dict[int, Answer]]:
        revision = uow.businesses.revision(business_id)
        with self._lock:
            cached = self._entries.get(business_id)
            if cached is None or cached.revision != revision:
                cached = self._build(uow, business_id, revision)
                self._entries[business_id] = cached
            return cached.index, cached.answers

    def _build(self, uow: UnitOfWork, business_id: int, revision: int) -> _CachedIndex:
        answers = {a.id: a for a in uow.answers.list_all(business_id) if a.id is not None}
        documents = [
            SearchDocument(answer_id, a.title, a.category, a.tags, a.body)
            for answer_id, a in answers.items()
        ]
        groups = uow.synonyms.list_all(business_id)
        return _CachedIndex(
            revision, SearchIndex.build(documents, groups, self._tokenizer), answers
        )


class SearchAnswers:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, engine: SearchEngine, cache: SearchIndexCache
    ) -> None:
        self._uow_factory = uow_factory
        self._engine = engine
        self._cache = cache

    def execute(self, actor: Actor, query: str) -> list[SearchResult]:
        actor.require(Action.SEARCH)
        with self._uow_factory() as uow:
            index, answers = self._cache.get(uow, actor.business_id)
            popularity = uow.copies.counts(actor.business_id)
            values = values_by_key(uow.variables.list_all(actor.business_id))
        hits = self._engine.search(index, query, popularity)[:RESULT_LIMIT]
        return [
            SearchResult(answers[hit.answer_id], render(answers[hit.answer_id].body, values))
            for hit in hits
        ]
