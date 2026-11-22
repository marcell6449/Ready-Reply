"""The business's WhatsApp number, entered once at registration."""

from dataclasses import dataclass

from readyreply.domain.errors import InvalidInputError

DEFAULT_COUNTRY_CODE = "506"  # Costa Rica
LOCAL_NUMBER_DIGITS = 8  # Costa Rican numbers have 8 digits: 8888-1234
MIN_DIGITS = 8
MAX_DIGITS = 15  # longest international (E.164) number
INTERNATIONAL_PREFIX = "00"
_ALLOWED = frozenset("0123456789 +-().")


def _digits_of(text: str) -> str:
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith(INTERNATIONAL_PREFIX):
        digits = digits.removeprefix(INTERNATIONAL_PREFIX)
    if len(digits) == LOCAL_NUMBER_DIGITS:
        digits = DEFAULT_COUNTRY_CODE + digits
    return digits


def _display(text: str, digits: str) -> str:
    local = digits.removeprefix(DEFAULT_COUNTRY_CODE)
    if digits.startswith(DEFAULT_COUNTRY_CODE) and len(local) == LOCAL_NUMBER_DIGITS:
        return f"+{DEFAULT_COUNTRY_CODE} {local[:4]} {local[4:]}"
    return " ".join(text.split()) if text.startswith("+") else f"+{digits}"


@dataclass(frozen=True, slots=True)
class WhatsAppNumber:
    digits: str
    """Country code and number, digits only (what wa.me links use)."""
    display: str
    """How the number is shown to customers, e.g. "+506 8888 1234"."""

    @classmethod
    def parse(cls, raw: str) -> "WhatsAppNumber":
        text = raw.strip()
        if not text or not set(text) <= _ALLOWED:
            raise InvalidInputError("setup.invalid_whatsapp")
        digits = _digits_of(text)
        if not MIN_DIGITS <= len(digits) <= MAX_DIGITS or digits.startswith("0"):
            raise InvalidInputError("setup.invalid_whatsapp")
        return cls(digits, _display(text, digits))
