"""Turning text into searchable words."""

from readyreply.domain.text import tokenize


class Tokenizer:
    def __init__(self, stop_words: frozenset[str]) -> None:
        self._stop_words = stop_words

    def content_tokens(self, text: str) -> list[str]:
        """Words without stop words; if only stop words remain, keep them all."""
        tokens = tokenize(text)
        content = [token for token in tokens if token not in self._stop_words]
        return content or tokens
