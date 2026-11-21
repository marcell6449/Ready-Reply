"""F4-01..F4-05, F4-08, P1: template rendering."""

from readyreply.domain.templates import placeholders, render, strip_placeholders


def test_renders_known_values() -> None:
    result = render("Abrimos {hours}", {"hours": "L-V 7–5"})
    assert result.text == "Abrimos L-V 7–5"
    assert result.missing == ()


def test_empty_value_is_missing_and_blocks_text() -> None:
    result = render("SINPE: {sinpe} a nombre de {name}", {"sinpe": "  ", "name": "Soda"})
    assert result.text is None
    assert result.missing == ("sinpe",)


def test_undefined_key_is_missing() -> None:
    assert render("{undefined_key}", {}).missing == ("undefined_key",)


def test_missing_keys_are_unique_and_ordered() -> None:
    assert render("{b} {a} {b}", {}).missing == ("b", "a")


def test_double_braces_are_literal() -> None:
    assert render("{{literal}} y }}", {}).text == "{literal} y }"


def test_unclosed_brace_kept_as_written() -> None:
    assert render("Abrimos {hours", {"hours": "x"}).text == "Abrimos {hours"


def test_invalid_key_syntax_is_literal() -> None:
    assert render("{Hours} {1x} { }", {}).text == "{Hours} {1x} { }"


def test_values_are_not_expanded_twice() -> None:
    assert render("{a}", {"a": "{b}", "b": "no"}).text == "{b}"


def test_emojis_and_newlines_preserved() -> None:
    assert render("Hola 👋\n*{name}*", {"name": "Soda Tica"}).text == "Hola 👋\n*Soda Tica*"


def test_placeholders_lists_keys_in_order() -> None:
    assert placeholders("{a} {{b}} {c} {a}") == ("a", "c")


def test_strip_placeholders_for_indexing() -> None:
    assert strip_placeholders("Abrimos {hours} hoy") == "Abrimos   hoy"
