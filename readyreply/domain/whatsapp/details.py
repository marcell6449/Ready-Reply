"""Find business details (SINPE number, hours, address) in the business's own messages."""

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

DETAIL_MAX = 200
_NUMBER = r"\d{4}[-\s]?\d{4}"
_SINPE = re.compile(
    rf"sinpe[^0-9\n]{{0,40}}(?P<number>{_NUMBER})(?P<owner>\s+a\s+nombre\s+de\s+[^.\n]+)?", re.I
)
_TIME = r"\d{1,2}(?::\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?|am|pm)"
_HOURS = re.compile(
    rf"(?P<hours>(?:de\s+)?(?:lunes|martes|miércoles|jueves|viernes|sábado|domingo)[^.\n]*?"
    rf"{_TIME}[^.\n]*?{_TIME})",
    re.I,
)
_ADDRESS = re.compile(
    r"(?:estamos|ubicados|nos encontramos|nuestra dirección es|la dirección es)\s+(?:en\s+)?"
    r"(?P<address>[^\n]{8,}?)(?:\.\s|\.$|$)",
    re.I,
)


@dataclass(frozen=True, slots=True)
class DetectedDetail:
    key: str
    value: str


def _sinpe(match: re.Match[str]) -> str:
    number = re.sub(r"\s", "-", match.group("number"))
    if len(number) == 8:
        number = f"{number[:4]}-{number[4:]}"
    owner = (match.group("owner") or "").strip()
    return f"{number} {owner}".strip()


def _most_common(found: list[str]) -> str | None:
    return Counter(found).most_common(1)[0][0][:DETAIL_MAX].strip() if found else None


def detect_details(business_texts: Iterable[str]) -> list[DetectedDetail]:
    texts = list(business_texts)
    candidates = {
        "sinpe": [_sinpe(m) for t in texts for m in _SINPE.finditer(t)],
        "hours": [m.group("hours") for t in texts for m in _HOURS.finditer(t)],
        "address": [m.group("address") for t in texts for m in _ADDRESS.finditer(t)],
    }
    details = ((key, _most_common(found)) for key, found in candidates.items())
    return [DetectedDetail(key, value) for key, value in details if value]
