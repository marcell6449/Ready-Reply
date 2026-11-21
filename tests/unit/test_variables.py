"""F1-01..F1-07."""

import pytest

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.variables import (
    BUILTIN_KEYS,
    VALUE_MAX,
    Variable,
    builtin_variables,
    validate_variable_set,
    values_by_key,
)


def builtins(**values: str) -> list[Variable]:
    return [
        Variable(key=key, label="", value=values.get(key, ""), builtin=True) for key in BUILTIN_KEYS
    ]


def custom(key: str, label: str = "Label", value: str = "v") -> Variable:
    return Variable(key=key, label=label, value=value, builtin=False)


def code_of(variables: list[Variable]) -> str:
    with pytest.raises(InvalidInputError) as error:
        validate_variable_set(variables)
    return error.value.code


def test_builtins_are_the_six_documented_keys() -> None:
    assert BUILTIN_KEYS == ("name", "hours", "address", "sinpe", "phone", "prices")
    assert all(variable.value == "" and variable.builtin for variable in builtin_variables())


def test_valid_set_is_cleaned() -> None:
    result = validate_variable_set([*builtins(hours=" L-V 7am–5pm 🕖 "), custom("wifi", " Wi-Fi ")])
    assert values_by_key(result)["hours"] == "L-V 7am–5pm 🕖"
    assert result[-1].label == "Wi-Fi"


@pytest.mark.parametrize("key", ["Wi Fi", "1abc", "ñame", "", "a" * 41, "wifi-pass"])
def test_invalid_custom_key(key: str) -> None:
    assert code_of([*builtins(), custom(key)]) == "variable.invalid_key"


def test_duplicate_key() -> None:
    assert code_of([*builtins(), custom("wifi"), custom("wifi")]) == "variable.duplicate_key"


def test_custom_cannot_reuse_builtin_key() -> None:
    assert code_of([*builtins(), custom("sinpe")]) == "variable.duplicate_key"


def test_missing_builtin_is_protected() -> None:
    assert code_of(builtins()[1:]) == "variable.builtin_protected"


def test_unknown_builtin_rejected() -> None:
    fake = Variable(key="other", label="", value="", builtin=True)
    assert code_of([*builtins(), fake]) == "variable.builtin_protected"


def test_value_too_long() -> None:
    assert code_of(builtins(hours="x" * (VALUE_MAX + 1))) == "variable.value_too_long"


def test_custom_label_required() -> None:
    assert code_of([*builtins(), custom("wifi", "  ")]) == "variable.label_required"


def test_custom_label_too_long() -> None:
    assert code_of([*builtins(), custom("wifi", "x" * 61)]) == "variable.label_too_long"
