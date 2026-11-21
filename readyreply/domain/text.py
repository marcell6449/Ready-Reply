"""Text normalization shared by search, unanswered questions and uniqueness checks."""

import unicodedata


def _without_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize(text: str) -> str:
    """Lowercase, strip accents and keep only letters and digits separated by single spaces."""
    plain = _without_accents(text).casefold()
    kept = "".join(char if char.isalnum() else " " for char in plain)
    return " ".join(kept.split())


def tokenize(text: str) -> list[str]:
    return normalize(text).split()
