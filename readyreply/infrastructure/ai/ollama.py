"""Ollama: free AI that runs on the business's own computer (default provider)."""

import httpx

from readyreply.application.ports import ProviderUnavailableError
from readyreply.domain.ai import Draft, SuggestionResult


class OllamaProvider:
    def __init__(self, client: httpx.Client, base_url: str, model: str) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/api/generate"
        self._model = model

    def suggest(self, prompt: str) -> SuggestionResult:
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        try:
            response = self._client.post(self._url, json=payload)
            response.raise_for_status()
            text = response.json()["response"]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ProviderUnavailableError(type(error).__name__) from error
        if not isinstance(text, str) or not text.strip():
            raise ProviderUnavailableError("empty reply")
        return Draft(text)
