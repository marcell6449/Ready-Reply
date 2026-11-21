"""No model: the person copies the prompt into any AI they like and pastes the reply back."""

from readyreply.domain.ai import ManualHandoff, SuggestionResult


class ManualPromptProvider:
    def __init__(self, open_url: str | None) -> None:
        self._open_url = open_url or None

    def suggest(self, prompt: str) -> SuggestionResult:
        return ManualHandoff(prompt=prompt, open_url=self._open_url)
