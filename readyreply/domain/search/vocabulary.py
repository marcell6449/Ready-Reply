"""The set of distinct indexed words, with fast prefix and length lookups."""

from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterable, Iterator


class Vocabulary:
    def __init__(self, terms: Iterable[str]) -> None:
        self._terms = frozenset(terms)
        self._sorted = sorted(self._terms)
        self._by_length: dict[int, list[str]] = defaultdict(list)
        for term in self._sorted:
            self._by_length[len(term)].append(term)

    def __contains__(self, term: object) -> bool:
        return term in self._terms

    def __len__(self) -> int:
        return len(self._terms)

    def with_prefix(self, prefix: str) -> Iterator[str]:
        position = bisect_left(self._sorted, prefix)
        while position < len(self._sorted) and self._sorted[position].startswith(prefix):
            yield self._sorted[position]
            position += 1

    def with_length_between(self, shortest: int, longest: int) -> Iterator[str]:
        for length in range(shortest, longest + 1):
            yield from self._by_length.get(length, ())
