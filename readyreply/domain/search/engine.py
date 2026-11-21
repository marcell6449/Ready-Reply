"""Ranks answers for a query by combining all scorers."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from readyreply.domain.search import scoring_config as config
from readyreply.domain.search.index import SearchDocument, SearchIndex
from readyreply.domain.search.scorers import Scorer
from readyreply.domain.search.tokens import Tokenizer

__all__ = ["SearchDocument", "SearchEngine", "SearchHit", "SearchIndex"]


@dataclass(frozen=True, slots=True)
class SearchHit:
    answer_id: int
    score: float


class SearchEngine:
    def __init__(self, tokenizer: Tokenizer, scorers: Sequence[Scorer]) -> None:
        self._tokenizer = tokenizer
        self._scorers = scorers

    def search(
        self, index: SearchIndex, query: str, popularity: Mapping[int, int]
    ) -> list[SearchHit]:
        tokens = self._tokenizer.content_tokens(query[: config.MAX_QUERY_CHARS])
        if tokens:
            hits = self._score(index, tokens)
        else:
            hits = [SearchHit(answer_id, 0.0) for answer_id in index.title_keys]
        return sorted(
            hits,
            key=lambda hit: (
                -hit.score,
                -popularity.get(hit.answer_id, 0),
                index.title_keys[hit.answer_id],
            ),
        )

    def _score(self, index: SearchIndex, tokens: list[str]) -> list[SearchHit]:
        totals: dict[int, float] = defaultdict(float)
        matched: dict[int, int] = defaultdict(int)
        for token in tokens:
            for answer_id, value in self._token_scores(index, token).items():
                totals[answer_id] += value
                matched[answer_id] += 1
        hits = (
            SearchHit(answer_id, total * _coverage(matched[answer_id], len(tokens)))
            for answer_id, total in totals.items()
        )
        return [hit for hit in hits if hit.score >= config.MIN_SCORE]

    def _token_scores(self, index: SearchIndex, token: str) -> dict[int, float]:
        best: dict[int, float] = {}
        for scorer in self._scorers:
            for match in scorer.matches(token, index):
                for answer_id, weight in index.postings[match.term].items():
                    best[answer_id] = max(best.get(answer_id, 0.0), match.strength * weight)
        return best


def _coverage(matched_tokens: int, total_tokens: int) -> float:
    return config.COVERAGE_BASE + config.COVERAGE_BONUS * matched_tokens / total_tokens
