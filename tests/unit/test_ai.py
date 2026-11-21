"""F8-03, F8-07: what the AI prompt may contain."""

from readyreply.domain.ai import (
    MAX_TITLES_IN_PROMPT,
    Draft,
    PromptTemplate,
    SuggestionRequest,
    build_prompt,
    clean_draft,
)
from readyreply.domain.answers import BODY_MAX
from readyreply.domain.variables import Variable

TEMPLATE = PromptTemplate(
    intro="Business: {business}. Language: {language}.",
    variables_heading="Variables:",
    titles_heading="Existing answers:",
    question_heading="Question:",
    rules="Use {key} placeholders.",
)


def request(**overrides: object) -> SuggestionRequest:
    fields: dict[str, object] = {
        "question": "¿Tienen parqueo?",
        "business_name": "Soda Tica",
        "variables": (
            Variable("hours", "Horario", "L-V 7-5", builtin=True),
            Variable("sinpe", "SINPE", "", builtin=True),
        ),
        "existing_titles": ("Horario",),
        "language": "Spanish",
    }
    fields.update(overrides)
    return SuggestionRequest(**fields)  # type: ignore[arg-type]


def test_prompt_contains_only_allowed_data() -> None:
    prompt = build_prompt(request(), TEMPLATE)
    assert "Business: Soda Tica. Language: Spanish." in prompt
    assert "{hours} (Horario): L-V 7-5" in prompt
    assert "{sinpe}" not in prompt
    assert "- Horario" in prompt
    assert prompt.rstrip().endswith("¿Tienen parqueo?")
    assert "Use {key} placeholders." in prompt


def test_prompt_limits_titles() -> None:
    titles = tuple(f"T{i}" for i in range(MAX_TITLES_IN_PROMPT + 10))
    prompt = build_prompt(request(existing_titles=titles), TEMPLATE)
    assert f"T{MAX_TITLES_IN_PROMPT - 1}" in prompt
    assert f"T{MAX_TITLES_IN_PROMPT}\n" not in prompt


def test_clean_draft() -> None:
    assert clean_draft("  hola \n") == Draft("hola")
    assert len(clean_draft("x" * (BODY_MAX + 50)).text) == BODY_MAX
