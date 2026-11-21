"""In-memory index: for every word, which answers contain it and in which field."""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from readyreply.domain.answers import title_key
from readyreply.domain.search.scoring_config import FIELD_WEIGHTS
from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.search.vocabulary import Vocabulary
from readyreply.domain.synonyms import SynonymGroup, SynonymLookup
from readyreply.domain.templates import strip_placeholders


@dataclass(frozen=True, slots=True)
class SearchDocument:
    answer_id: int
    title: str
    category: str
    tags: tuple[str, ...]
    body: str


def _field_texts(document: SearchDocument) -> dict[str, str]:
    return {
        "title": document.title,
        "tags": " ".join(document.tags),
        "category": document.category,
        "body": strip_placeholders(document.body),
    }


class SearchIndex:
    def __init__(
        self,
        postings: Mapping[str, Mapping[int, float]],
        title_keys: Mapping[int, str],
        synonyms: SynonymLookup,
    ) -> None:
        self.postings = postings
        self.title_keys = title_keys
        self.synonyms = synonyms
        self.vocabulary = Vocabulary(postings)

    def __len__(self) -> int:
        return len(self.title_keys)

    @classmethod
    def build(
        cls,
        documents: Sequence[SearchDocument],
        synonym_groups: Iterable[SynonymGroup],
        tokenizer: Tokenizer,
    ) -> "SearchIndex":
        postings: dict[str, dict[int, float]] = defaultdict(dict)
        for document in documents:
            for field, text in _field_texts(document).items():
                weight = FIELD_WEIGHTS[field]
                for term in tokenizer.content_tokens(text):
                    best = postings[term].get(document.answer_id, 0.0)
                    postings[term][document.answer_id] = max(best, weight)
        title_keys = {document.answer_id: title_key(document.title) for document in documents}
        return cls(postings, title_keys, SynonymLookup(synonym_groups))
