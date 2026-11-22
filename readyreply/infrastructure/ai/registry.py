"""Provider registry. To add a provider: write a class with `suggest()` and add one line here."""

from collections.abc import Callable
from types import MappingProxyType

import httpx

from readyreply.application.ports import SuggestionProvider
from readyreply.config import Settings
from readyreply.infrastructure.ai.manual_prompt import ManualPromptProvider
from readyreply.infrastructure.ai.ollama import OllamaProvider
from readyreply.infrastructure.ai.openai_compatible import (
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)

ProviderFactory = Callable[[Settings, httpx.Client], SuggestionProvider]


def _ollama(settings: Settings, client: httpx.Client) -> SuggestionProvider:
    return OllamaProvider(
        client, settings.ai_base_url, settings.ai_model, settings.ai_timeout_seconds
    )


def _openai_compatible(settings: Settings, client: httpx.Client) -> SuggestionProvider:
    api_key = settings.ai_api_key.get_secret_value() if settings.ai_api_key else ""
    config = OpenAICompatibleConfig(
        settings.ai_base_url, settings.ai_model, api_key, settings.ai_timeout_seconds
    )
    return OpenAICompatibleProvider(client, config)


def _manual(settings: Settings, _client: httpx.Client) -> SuggestionProvider:
    return ManualPromptProvider(settings.ai_chat_url)


PROVIDERS: MappingProxyType[str, ProviderFactory] = MappingProxyType(
    {"ollama": _ollama, "openai_compatible": _openai_compatible, "manual": _manual}
)


def build_provider(settings: Settings, client: httpx.Client) -> SuggestionProvider:
    factory = PROVIDERS.get(settings.ai_provider)
    if factory is None:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(
            f"Unknown RR_AI_PROVIDER '{settings.ai_provider}'. Use one of: {available}"
        )
    return factory(settings, client)
