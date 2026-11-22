"""Ollama: free AI that runs on the business's own computer (default provider)."""

import httpx

from readyreply.application.ports import ProviderUnavailableError
from readyreply.domain.ai import Draft, SuggestionResult
from readyreply.infrastructure.ai.http import post_json, require_text


class OllamaProvider:
    def __init__(self, client: httpx.Client, base_url: str, model: str, deadline: float) -> None:
        self._client = client
        self._url = base_url.rstrip("/") + "/api/generate"
        self._model = model
        self._deadline = deadline

    def suggest(self, prompt: str) -> SuggestionResult:
        payload = {"model": self._model, "prompt": prompt, "stream": False}
        reply = post_json(self._client, self._url, payload, self._deadline)
        if not isinstance(reply, dict):
            raise ProviderUnavailableError("unexpected reply")
        return Draft(require_text(reply.get("response")))
