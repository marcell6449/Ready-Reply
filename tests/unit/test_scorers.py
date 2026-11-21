"""Scorer rules in isolation."""

from readyreply.domain.search.engine import SearchDocument, SearchIndex
from readyreply.domain.search.scorers import FuzzyScorer, PrefixScorer, allowed_edits
from readyreply.domain.search.stopwords import STOP_WORDS
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.search.vocabulary import Vocabulary
from tests.unit.fakes import OsaDistance


def index_of(*titles: str) -> SearchIndex:
    docs = [SearchDocument(i, title, "", (), "") for i, title in enumerate(titles)]
    return SearchIndex.build(docs, [], Tokenizer(STOP_WORDS))


def test_allowed_edits_by_length() -> None:
    assert [allowed_edits(n) for n in (1, 3, 4, 7, 8, 20)] == [0, 0, 1, 1, 2, 2]


def test_prefix_requires_three_chars() -> None:
    index = index_of("horario")
    assert list(PrefixScorer().matches("ho", index)) == []
    assert [m.term for m in PrefixScorer().matches("hor", index)] == ["horario"]


def test_prefix_skips_exact_term() -> None:
    assert list(PrefixScorer().matches("hora", index_of("hora"))) == []


def test_fuzzy_two_edits_for_long_words() -> None:
    index = index_of("ferreteria")
    one = list(FuzzyScorer(OsaDistance()).matches("ferretria", index))
    two = list(FuzzyScorer(OsaDistance()).matches("feretria", index))
    assert [m.term for m in one] == ["ferreteria"]
    assert two[0].strength < one[0].strength


def test_fuzzy_ignores_exact_and_far_terms() -> None:
    index = index_of("horario", "zapato")
    assert list(FuzzyScorer(OsaDistance()).matches("horario", index)) == []
    assert list(FuzzyScorer(OsaDistance()).matches("zzzzzzz", index)) == []


def test_vocabulary_lookups() -> None:
    vocabulary = Vocabulary(["casa", "casado", "cosa"])
    assert "casa" in vocabulary
    assert list(vocabulary.with_prefix("cas")) == ["casa", "casado"]
    assert sorted(vocabulary.with_length_between(4, 4)) == ["casa", "cosa"]
    assert len(vocabulary) == 3
