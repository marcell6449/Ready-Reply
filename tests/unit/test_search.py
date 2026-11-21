"""F3-01..F3-14 and P2 at the domain level."""

import pytest

from readyreply.domain.search.engine import SearchDocument, SearchEngine, SearchIndex
from readyreply.domain.search.scorers import (
    ExactScorer,
    FuzzyScorer,
    PrefixScorer,
    SynonymScorer,
)
from readyreply.domain.search.stopwords import STOP_WORDS
from readyreply.domain.search.tokens import Tokenizer
from tests.unit.fakes import OsaDistance

pytestmark = pytest.mark.promise_p2

DOCS = [
    SearchDocument(1, "Horario", "Información", ("horario",), "Abrimos {hours}. ¡Te esperamos!"),
    SearchDocument(2, "Pago por SINPE Móvil", "Pagos", ("pago", "sinpe"), "SINPE al {sinpe}"),
    SearchDocument(3, "Ubicación", "Información", ("direccion",), "Estamos en {address}"),
    SearchDocument(4, "Envíos a domicilio", "Envíos", ("envio",), "Hacemos delivery express."),
    SearchDocument(5, "Menú del día", "Comida", ("almuerzo",), "Casado con pollo, sopa del día"),
    SearchDocument(6, "Sol y playa", "Otros", (), "Sol"),
]
SYNONYMS = [
    ("horario", "abren", "atienden", "cierran", "hora", "abierto"),
    ("ubicacion", "donde", "llegar", "direccion"),
    ("envio", "envios", "delivery", "express", "domicilio"),
]


def engine() -> SearchEngine:
    return SearchEngine(
        Tokenizer(STOP_WORDS),
        [ExactScorer(), SynonymScorer(), PrefixScorer(), FuzzyScorer(OsaDistance())],
    )


def index(docs: list[SearchDocument] = DOCS) -> SearchIndex:
    return SearchIndex.build(docs, SYNONYMS, Tokenizer(STOP_WORDS))


def ids(query: str, popularity: dict[int, int] | None = None) -> list[int]:
    return [hit.answer_id for hit in engine().search(index(), query, popularity or {})]


@pytest.mark.parametrize("query", ["horario", "HORARIO", "Horário", "  horario  "])
def test_case_and_accents(query: str) -> None:
    assert ids(query)[0] == 1


def test_question_with_stop_words_and_synonym() -> None:
    assert ids("¿A qué hora abren?")[0] == 1


@pytest.mark.parametrize("query", ["orario", "hroario", "horaio", "horarion"])
def test_one_typo(query: str) -> None:
    assert ids(query)[0] == 1


@pytest.mark.parametrize("query", ["sinpe", "simpe", "SINPE movil"])
def test_sinpe(query: str) -> None:
    assert ids(query)[0] == 2


def test_prefix_while_typing() -> None:
    assert 1 in ids("hor")


def test_no_results() -> None:
    assert ids("xyzzy") == []


@pytest.mark.parametrize("query", ["", "   ", "🍔", "!!!"])
def test_empty_query_lists_by_popularity_then_title(query: str) -> None:
    result = ids(query, {4: 9, 2: 9, 5: 1})
    assert result[:3] == [4, 2, 5]
    assert sorted(result) == [1, 2, 3, 4, 5, 6]


def test_synonym_group() -> None:
    assert ids("express")[0] == 4
    assert ids("¿Dónde están?")[0] == 3


def test_title_ranks_above_body() -> None:
    docs = [
        SearchDocument(1, "Otro", "", (), "Hablamos del pollo"),
        SearchDocument(2, "Pollo frito", "", (), "Rico"),
    ]
    hits = engine().search(index(docs), "pollo", {})
    assert [hit.answer_id for hit in hits] == [2, 1]


def test_short_words_need_exact_match() -> None:
    assert 6 not in ids("sal")


def test_injection_text_is_plain_text() -> None:
    assert ids("' OR 1=1 --") == []
    assert ids("%") == ids("")


def test_long_query_is_cut() -> None:
    assert ids("horario " + "x" * 500)[0] == 1


def test_more_matched_words_rank_higher() -> None:
    hits = ids("sopa pollo")
    assert hits[0] == 5


def test_popularity_breaks_ties() -> None:
    docs = [SearchDocument(1, "Precio A", "", (), ""), SearchDocument(2, "Precio B", "", (), "")]
    hits = engine().search(index(docs), "precio", {2: 3})
    assert [hit.answer_id for hit in hits] == [2, 1]


def test_only_stop_words_still_searches() -> None:
    docs = [SearchDocument(1, "Que", "", (), "")]
    assert [h.answer_id for h in engine().search(index(docs), "que", {})] == [1]


def test_index_reports_size() -> None:
    assert len(index()) == len(DOCS)


def test_answer_matching_more_related_terms_wins_tie() -> None:
    docs = [
        SearchDocument(1, "Pago con tarjeta", "", ("pago",), ""),
        SearchDocument(2, "Pago por SINPE", "", ("pago", "sinpe"), ""),
    ]
    groups = [("sinpe", "pago", "simpe")]
    built = SearchIndex.build(docs, groups, Tokenizer(STOP_WORDS))
    hits = engine().search(built, "simpe", {})
    assert hits[0].answer_id == 2
