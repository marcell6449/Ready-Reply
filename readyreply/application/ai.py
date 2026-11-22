"""AI suggestions for unanswered questions (F8, P5). Nothing here ever saves an answer."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace

from readyreply.application.context import Actor
from readyreply.application.ports import (
    ProviderUnavailableError,
    SuggestionProvider,
    UnitOfWorkFactory,
)
from readyreply.domain.ai import (
    Draft,
    PromptTemplate,
    SuggestionRequest,
    SuggestionResult,
    build_prompt,
    clean_draft,
)
from readyreply.domain.permissions import Action
from readyreply.domain.variables import Variable

logger = logging.getLogger(__name__)
UNAVAILABLE_NOTICE = "ai.unavailable"


@dataclass(frozen=True, slots=True)
class SuggestionOutcome:
    result: SuggestionResult
    notice: str | None


@dataclass(frozen=True, slots=True)
class PromptSettings:
    template: PromptTemplate
    language: str
    builtin_labels: Mapping[str, str]


class SuggestAnswer:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        provider: SuggestionProvider,
        fallback: SuggestionProvider,
        settings_by_locale: Mapping[str, PromptSettings],
        default_locale: str,
    ) -> None:
        self._uow_factory = uow_factory
        self._provider = provider
        self._fallback = fallback
        self._settings_by_locale = settings_by_locale
        self._default_locale = default_locale

    def execute(self, actor: Actor, question_id: int, locale: str | None) -> SuggestionOutcome:
        actor.require(Action.USE_AI)
        settings = self._settings_by_locale[locale or self._default_locale]
        request = self._request(actor, question_id, settings)
        prompt = build_prompt(request, settings.template)
        try:
            result = self._provider.suggest(prompt)
        except ProviderUnavailableError:
            logger.info("AI provider unavailable; using the manual prompt")
            return SuggestionOutcome(self._fallback.suggest(prompt), UNAVAILABLE_NOTICE)
        if isinstance(result, Draft):
            result = clean_draft(result.text)
        return SuggestionOutcome(result, None)

    def _request(
        self, actor: Actor, question_id: int, settings: PromptSettings
    ) -> SuggestionRequest:
        with self._uow_factory() as uow:
            question = uow.unanswered.get_open(actor.business_id, question_id)
            stored = uow.variables.list_all(actor.business_id)
            variables = tuple(_labelled(v, settings.builtin_labels) for v in stored)
            titles = tuple(answer.title for answer in uow.answers.list_all(actor.business_id))
        names = [variable.value for variable in variables if variable.key == "name"]
        return SuggestionRequest(
            question=question.sample_text,
            business_name=names[0] if names else "",
            variables=variables,
            existing_titles=titles,
            language=settings.language,
        )


def _labelled(variable: Variable, builtin_labels: Mapping[str, str]) -> Variable:
    if variable.label:
        return variable
    return replace(variable, label=builtin_labels.get(variable.key, ""))
