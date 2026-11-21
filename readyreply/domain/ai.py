"""What an AI suggestion request contains, and what comes back. The AI never saves anything."""

from dataclasses import dataclass

from readyreply.domain.answers import BODY_MAX
from readyreply.domain.variables import Variable

MAX_TITLES_IN_PROMPT = 50


@dataclass(frozen=True, slots=True)
class SuggestionRequest:
    question: str
    business_name: str
    variables: tuple[Variable, ...]
    existing_titles: tuple[str, ...]
    language: str


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """Localized prompt text. `intro` may use {business} and {language}."""

    intro: str
    variables_heading: str
    titles_heading: str
    question_heading: str
    rules: str


@dataclass(frozen=True, slots=True)
class Draft:
    """Text produced by a model. Shown in an editable field, never saved automatically."""

    text: str


@dataclass(frozen=True, slots=True)
class ManualHandoff:
    """The person copies `prompt` into any AI and pastes the reply back."""

    prompt: str
    open_url: str | None


SuggestionResult = Draft | ManualHandoff


def _variable_lines(variables: tuple[Variable, ...]) -> list[str]:
    filled = (variable for variable in variables if variable.value.strip())
    return [f"- {{{v.key}}} ({v.label or v.key}): {v.value}" for v in filled]


def build_prompt(request: SuggestionRequest, template: PromptTemplate) -> str:
    titles = [f"- {title}" for title in request.existing_titles[:MAX_TITLES_IN_PROMPT]]
    intro = template.intro.replace("{business}", request.business_name)
    sections = [
        intro.replace("{language}", request.language),
        template.rules,
        template.variables_heading,
        *_variable_lines(request.variables),
        template.titles_heading,
        *titles,
        template.question_heading,
        request.question.strip(),
    ]
    return "\n".join(sections) + "\n"


def clean_draft(text: str) -> Draft:
    return Draft(text.strip()[:BODY_MAX])
