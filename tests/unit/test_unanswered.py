"""F5-02, F5-03, F5-04."""

import pytest

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.search.stopwords import STOP_WORDS
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.unanswered import QuestionKeyer, sample_text

KEYER = QuestionKeyer(Tokenizer(STOP_WORDS))


def test_same_question_same_key() -> None:
    assert KEYER.key("¿Tienen envíos a Cartago?") == KEYER.key("cartago envios") == "cartago envios"


@pytest.mark.parametrize("query", ["", "h", "ho", "  ", "🍔🍔", "a b"])
def test_too_short_rejected(query: str) -> None:
    with pytest.raises(InvalidInputError) as error:
        KEYER.key(query)
    assert error.value.code == "unanswered.too_short"


def test_minimum_accepted() -> None:
    assert KEYER.key("hor") == "hor"


def test_sample_text_trimmed_and_cut() -> None:
    assert sample_text("  hola  ") == "hola"
    assert len(sample_text("x" * 500)) == 200
