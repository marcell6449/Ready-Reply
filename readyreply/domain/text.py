"""Text cleaning and normalization shared by every field, search and uniqueness checks."""

import unicodedata

_FORMAT = "Cf"
_CONTROL = "Cc"
_KEPT_CONTROLS = frozenset("\n\t")
# Joiners and tag characters build emoji such as 💇‍♀️ or subdivision flags; keep them.
_KEPT_FORMAT = frozenset("‍") | frozenset(map(chr, range(0xE0020, 0xE0080)))


def _is_invisible(char: str) -> bool:
    category = unicodedata.category(char)
    if category == _CONTROL:
        return char not in _KEPT_CONTROLS
    return category == _FORMAT and char not in _KEPT_FORMAT


def clean_text(text: str) -> str:
    """NFC, Unix line breaks, and no invisible or control characters (except tab/newline)."""
    unified = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return "".join(char for char in unified if not _is_invisible(char))


def is_blank(text: str) -> bool:
    """True when nothing visible remains (spaces, joiners and other format characters only)."""
    return all(char.isspace() or unicodedata.category(char) == _FORMAT for char in text)


def _without_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(
        char
        for char in decomposed
        if not unicodedata.combining(char) and unicodedata.category(char) != _FORMAT
    )


def normalize(text: str) -> str:
    """Lowercase, strip accents and keep only letters and digits separated by single spaces."""
    plain = _without_accents(text).casefold()
    kept = "".join(char if char.isalnum() else " " for char in plain)
    return " ".join(kept.split())


def tokenize(text: str) -> list[str]:
    return normalize(text).split()
