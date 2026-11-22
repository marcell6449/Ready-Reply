"""Business variables such as {hours} or {sinpe}, saved once and used in every answer."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.templates import KEY_PATTERN
from readyreply.domain.text import clean_text, is_blank

BUILTIN_KEYS = ("name", "hours", "address", "sinpe", "phone", "prices")
VALUE_MAX = 2000
LABEL_MAX = 60
_KEY = re.compile(rf"^{KEY_PATTERN}$")


@dataclass(frozen=True, slots=True)
class Variable:
    key: str
    label: str
    value: str
    builtin: bool


def builtin_variables() -> list[Variable]:
    return [Variable(key=key, label="", value="", builtin=True) for key in BUILTIN_KEYS]


def values_by_key(variables: Sequence[Variable]) -> dict[str, str]:
    return {variable.key: variable.value for variable in variables}


def _clean_value(value: str) -> str:
    cleaned = clean_text(value).strip()
    if len(cleaned) > VALUE_MAX:
        raise InvalidInputError("variable.value_too_long", limit=VALUE_MAX)
    return cleaned


def _clean_label(label: str) -> str:
    cleaned = clean_text(label).strip()
    if is_blank(cleaned):
        raise InvalidInputError("variable.label_required")
    if len(cleaned) > LABEL_MAX:
        raise InvalidInputError("variable.label_too_long", limit=LABEL_MAX)
    return cleaned


def _clean(variable: Variable) -> Variable:
    if variable.builtin:
        if variable.key not in BUILTIN_KEYS:
            raise InvalidInputError("variable.builtin_protected", key=variable.key)
        return Variable(variable.key, "", _clean_value(variable.value), builtin=True)
    if not _KEY.match(variable.key):
        raise InvalidInputError("variable.invalid_key", key=variable.key)
    return Variable(variable.key, _clean_label(variable.label), _clean_value(variable.value), False)


def _ensure_unique(variables: Sequence[Variable]) -> None:
    seen: set[str] = set()
    for variable in variables:
        if variable.key in seen:
            raise InvalidInputError("variable.duplicate_key", key=variable.key)
        seen.add(variable.key)


def validate_variable_set(variables: Sequence[Variable]) -> list[Variable]:
    """Validate the full list that replaces the business's variables."""
    cleaned = [_clean(variable) for variable in variables]
    _ensure_unique(cleaned)
    present = {variable.key for variable in cleaned if variable.builtin}
    missing = [key for key in BUILTIN_KEYS if key not in present]
    if missing:
        raise InvalidInputError("variable.builtin_protected", key=missing[0])
    return cleaned
