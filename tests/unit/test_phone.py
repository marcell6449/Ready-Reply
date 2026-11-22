"""Business WhatsApp number given at registration."""

import pytest

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.phone import WhatsAppNumber


@pytest.mark.parametrize(
    ("raw", "digits", "shown"),
    [
        ("8888-1234", "50688881234", "+506 8888 1234"),
        ("8888 1234", "50688881234", "+506 8888 1234"),
        ("+506 8888-1234", "50688881234", "+506 8888 1234"),
        ("(506) 8888 1234", "50688881234", "+506 8888 1234"),
        ("00506 88881234", "50688881234", "+506 8888 1234"),
        ("+52 55 1234 5678", "525512345678", "+52 55 1234 5678"),
        ("+1 (415) 555-0100", "14155550100", "+1 (415) 555-0100"),
    ],
)
def test_numbers_are_normalized(raw: str, digits: str, shown: str) -> None:
    number = WhatsAppNumber.parse(raw)
    assert number.digits == digits
    assert number.display == shown


@pytest.mark.parametrize(
    "raw", ["", "123", "8888-12345678901234", "abc-defg", "88881234x", "+0 8888 1234"]
)
def test_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidInputError) as error:
        WhatsAppNumber.parse(raw)
    assert error.value.code == "setup.invalid_whatsapp"
