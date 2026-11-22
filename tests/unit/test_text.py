"""F3-02, F3-09: normalization used by search."""

import unicodedata

import pytest

from readyreply.domain.text import clean_text, is_blank, normalize, tokenize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Horário", "horario"),
        ("  HORARIO  ", "horario"),
        ("¿A qué hora abren?", "a que hora abren"),
        ("Ñandú", "nandu"),
        ("pago-SINPE", "pago sinpe"),
        ("🍔 hamburguesa 🍔", "hamburguesa"),
        ("!!!", ""),
        ("", ""),
        ("Precio ₡2500", "precio 2500"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_tokenize_splits_normalized_words() -> None:
    assert tokenize("¿Dónde están?") == ["donde", "estan"]


def test_tokenize_empty() -> None:
    assert tokenize("   ") == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hora\u200brio", "Horario"),
        ("Hor⁠ario", "Horario"),
        ("Ho­rario", "Horario"),
        ("a\x00b\x07c", "abc"),
        ("línea\r\nnueva\rotra", "línea\nnueva\notra"),
        (unicodedata.normalize("NFD", "é"), "é"),
        ("💇‍♀️", "💇‍♀️"),
        ("tab\tkept", "tab\tkept"),
    ],
)
def test_clean_text(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


@pytest.mark.parametrize("raw", ["", "  ", "\u200b‌‍", "⁠", "­", "\n\t"])
def test_is_blank(raw: str) -> None:
    assert is_blank(clean_text(raw))


def test_not_blank() -> None:
    assert not is_blank("🍔")


def test_normalize_drops_invisible_characters() -> None:
    assert normalize("Hora\u200brio") == "horario"
