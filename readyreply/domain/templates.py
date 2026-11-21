"""Answer templates: "{key}" placeholders filled with business variables."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

KEY_PATTERN = r"[a-z][a-z0-9_]{0,39}"
_TOKEN = re.compile(r"\{\{|\}\}|\{(" + KEY_PATTERN + r")\}")
_LITERALS = {"{{": "{", "}}": "}"}


@dataclass(frozen=True, slots=True)
class RenderResult:
    """`text` is None whenever a placeholder has no value, so it can never be copied."""

    text: str | None
    missing: tuple[str, ...]


def placeholders(body: str) -> tuple[str, ...]:
    keys = (match.group(1) for match in _TOKEN.finditer(body) if match.group(1))
    return tuple(dict.fromkeys(keys))


def _missing_keys(body: str, values: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(key for key in placeholders(body) if not values.get(key, "").strip())


def render(body: str, values: Mapping[str, str]) -> RenderResult:
    missing = _missing_keys(body, values)
    if missing:
        return RenderResult(text=None, missing=missing)

    def substitute(match: re.Match[str]) -> str:
        key = match.group(1)
        return values[key] if key else _LITERALS[match.group(0)]

    return RenderResult(text=_TOKEN.sub(substitute, body), missing=())


def strip_placeholders(body: str) -> str:
    """Remove placeholders so variable keys are not indexed as words."""
    return _TOKEN.sub(lambda match: " " if match.group(1) else match.group(0), body)
