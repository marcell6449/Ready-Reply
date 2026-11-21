"""F3-15."""

import pytest

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.synonyms import SynonymLookup, validate_groups


def test_groups_are_normalized_and_deduplicated() -> None:
    assert validate_groups([["Horario", "abren", "ABREN", " "]]) == [("horario", "abren")]


def test_too_few_terms() -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_groups([["horario", "Horário"]])
    assert error.value.code == "synonym.too_few_terms"


def test_term_in_two_groups() -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_groups([["horario", "abren"], ["abren", "abierto"]])
    assert error.value.code == "synonym.term_in_use"


def test_multiword_term_rejected() -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_groups([["envio", "a domicilio"]])
    assert error.value.code == "synonym.single_word"


def test_too_many_groups_rejected() -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_groups([[f"a{i}", f"b{i}"] for i in range(201)])
    assert error.value.code == "synonym.too_many_groups"


def test_lookup_returns_other_members() -> None:
    lookup = SynonymLookup([("horario", "abren", "atienden")])
    assert lookup.related("abren") == ("horario", "atienden")
    assert lookup.related("nada") == ()


def test_too_many_terms_in_group() -> None:
    with pytest.raises(InvalidInputError) as error:
        validate_groups([[f"t{i}" for i in range(31)]])
    assert error.value.code == "synonym.too_many_terms"
