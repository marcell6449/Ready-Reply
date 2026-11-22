"""Any provider exposing the OpenAI-compatible chat completions API (key in .env)."""

from dataclasses import dataclass

import httpx

from readyreply.application.ports import ProviderUnavailableError
from readyreply.domain.ai import Draft, SuggestionResult
from readyreply.infrastructure.ai.http import post_json, require_text


@dataclass(frozen=True, slots=True)
class OpenAICompatibleConfig:
    base_url: str
    model: str
    api_key: str
    deadline: float


def _content(reply: object) -> object:
    try:
        return reply["choices"][0]["message"]["content"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as error:
        raise ProviderUnavailableError("unexpected reply") from error


class OpenAICompatibleProvider:
    def __init__(self, client: httpx.Client, config: OpenAICompatibleConfig) -> None:
        self._client = client
        self._config = config
        self._url = config.base_url.rstrip("/") + "/chat/completions"

    def suggest(self, prompt: str) -> SuggestionResult:
        payload = {"model": self._config.model, "messages": [{"role": "user", "content": prompt}]}
        headers = {"Authorization": f"Bearer {self._config.api_key}"}
        reply = post_json(self._client, self._url, payload, self._config.deadline, headers)
        return Draft(require_text(_content(reply)))
