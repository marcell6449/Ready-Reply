"""Any provider exposing the OpenAI-compatible chat completions API (key in .env)."""

import httpx

from readyreply.application.ports import ProviderUnavailableError
from readyreply.domain.ai import Draft, SuggestionResult


class OpenAICompatibleProvider:
    def __init__(self, client: httpx.Client, base_url: str, model: str, api_key: str) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def suggest(self, prompt: str) -> SuggestionResult:
        payload = {"model": self._model, "messages": [{"role": "user", "content": prompt}]}
        try:
            response = self._client.post(self._url, json=payload, headers=self._headers)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderUnavailableError(type(error).__name__) from error
        if not isinstance(text, str) or not text.strip():
            raise ProviderUnavailableError("empty reply")
        return Draft(text)
