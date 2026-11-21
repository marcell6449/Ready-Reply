"""F3-02, F3-09: normalization used by search."""

import pytest

from readyreply.domain.text import normalize, tokenize


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
