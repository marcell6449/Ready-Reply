"""Questions people searched for that had no answer."""

from dataclasses import dataclass
from datetime import datetime

from readyreply.domain.errors import InvalidInputError
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.text import clean_text

MIN_QUESTION_CHARS = 3
SAMPLE_MAX = 200


@dataclass(frozen=True, slots=True)
class UnansweredQuestion:
    id: int
    business_id: int
    key: str
    sample_text: str
    times_searched: int
    last_seen: datetime


class QuestionKeyer:
    """Same words in any order, case or accents give the same key."""

    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer

    def key(self, query: str) -> str:
        tokens = sorted(set(self._tokenizer.content_tokens(query)))
        if sum(len(token) for token in tokens) < MIN_QUESTION_CHARS:
            raise InvalidInputError("unanswered.too_short", minimum=MIN_QUESTION_CHARS)
        return " ".join(tokens)


def sample_text(query: str) -> str:
    return clean_text(query).strip()[:SAMPLE_MAX]
