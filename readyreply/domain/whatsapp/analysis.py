"""Turn exported chats into suggested answers, unanswered questions and business details.

Customer names and numbers are only used to tell who wrote what; they never leave this module.
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from readyreply.domain.search.tokens import Tokenizer
from readyreply.domain.text import normalize
from readyreply.domain.whatsapp.details import DetectedDetail, detect_details
from readyreply.domain.whatsapp.parser import ChatMessage, message_fingerprint

Chat = Sequence[ChatMessage]

SIMILAR_QUESTION = 0.6  # share of the shorter question's words found in the other one
MIN_QUESTION_WORDS = 1
MAX_SUGGESTIONS = 100
MIN_PLACEHOLDER_CHARS = 4  # shorter values (e.g. "8") are too likely to match by accident
TITLE_MAX = 80
_QUESTION_STARTS = frozenset(
    {
        "que",
        "cual",
        "cuales",
        "cuanto",
        "cuanta",
        "cuantos",
        "cuantas",
        "cuando",
        "donde",
        "como",
        "tienen",
        "tiene",
        "hay",
        "hacen",
        "hace",
        "aceptan",
        "abren",
        "abre",
        "venden",
        "puedo",
        "pueden",
        "quisiera",
        "necesito",
        "precio",
        "precios",
        "info",
        "informacion",
        "what",
        "when",
        "where",
        "how",
        "which",
        "do",
        "does",
        "can",
        "is",
        "are",
    }
)
_EDGE_PUNCTUATION = "¿?¡!.,;: "


@dataclass(frozen=True, slots=True)
class SuggestedAnswer:
    question: str
    reply: str
    times_asked: int


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    question: str
    times_asked: int


@dataclass(frozen=True, slots=True)
class ChatAnalysis:
    answers: list[SuggestedAnswer]
    unanswered: list[OpenQuestion]
    details: list[DetectedDetail]
    question_fingerprints: tuple[str, ...] = ()
    """The new customer questions this analysis counted (to skip them next time)."""


@dataclass(slots=True)
class _Group:
    words: frozenset[str]
    questions: list[str]
    replies: list[str]


def senders_of(chats: Sequence[Chat]) -> list[str]:
    """Senders ordered by how many chats they appear in, then by how much they wrote."""
    chats_per_sender: Counter[str] = Counter()
    letters: Counter[str] = Counter()
    for chat in chats:
        chats_per_sender.update({message.sender for message in chat})
        for message in chat:
            letters[message.sender] += len(message.text)
    return sorted(chats_per_sender, key=lambda s: (-chats_per_sender[s], -letters[s], s))


def guess_business_sender(chats: Sequence[Chat]) -> str | None:
    senders = senders_of(chats)
    return senders[0] if senders else None


_LEADING_COURTESY = re.compile(
    r"^(?:(?:hola|holi|buenas|buenos|buen|días|dias|tardes|noches|hi|hello|y|e)\b[\s,.;:!¡¿]*)+",
    re.IGNORECASE,
)


def question_title(question: str) -> str:
    """ "Buenas, a que hora abren?" becomes "A que hora abren"."""
    first_line = question.strip(_EDGE_PUNCTUATION).split("\n")[0]
    text = _LEADING_COURTESY.sub("", first_line).strip(_EDGE_PUNCTUATION) or first_line
    return (text[:1].upper() + text[1:])[:TITLE_MAX]


def with_placeholders(reply: str, known: Mapping[str, str]) -> str:
    """Write business details as variables, so the answer stays right when they change."""
    for key, value in sorted(known.items(), key=lambda item: -len(item[1])):
        if len(value.strip()) >= MIN_PLACEHOLDER_CHARS:
            reply = re.sub(re.escape(value.strip()), "{" + key + "}", reply)
    return reply


class ChatAnalyzer:
    def __init__(self, tokenizer: Tokenizer) -> None:
        self._tokenizer = tokenizer

    def analyze(
        self,
        chats: Sequence[Chat],
        business: str,
        known: Mapping[str, str] | None = None,
        skip: frozenset[str] = frozenset(),
    ) -> ChatAnalysis:
        groups: list[_Group] = []
        counted: list[str] = []
        for chat in chats:
            for question, reply in self._exchanges(chat, business):
                fingerprint = message_fingerprint(question)
                if fingerprint not in skip:
                    counted.append(fingerprint)
                    self._add(groups, question.text, reply)
        ordered = sorted(groups, key=lambda g: -len(g.questions))[:MAX_SUGGESTIONS]
        business_texts = [m.text for chat in chats for m in chat if m.sender == business]
        return ChatAnalysis(
            answers=[_suggest(g, known or {}) for g in ordered if g.replies],
            unanswered=[_open(g) for g in ordered if not g.replies],
            details=detect_details(business_texts),
            question_fingerprints=tuple(dict.fromkeys(counted)),
        )

    def is_question(self, text: str) -> bool:
        words = self._tokenizer.content_tokens(text)
        if len(words) < MIN_QUESTION_WORDS:
            return False
        first_word = normalize(text).split(" ", 1)[0]
        return "?" in text or first_word in _QUESTION_STARTS

    def _exchanges(self, chat: Chat, business: str) -> list[tuple[ChatMessage, str]]:
        """(customer question, business reply that followed; "" if none) pairs."""
        exchanges: list[tuple[ChatMessage, list[str]]] = []
        for message in chat:
            if message.sender == business:
                if exchanges:
                    exchanges[-1][1].append(message.text)
            elif self.is_question(message.text):
                exchanges.append((message, []))
        return [(question, "\n".join(replies)) for question, replies in exchanges]

    def _add(self, groups: list[_Group], question: str, reply: str) -> None:
        words = frozenset(self._tokenizer.content_tokens(question))
        for group in groups:
            if _similarity(words, group.words) >= SIMILAR_QUESTION:
                group.questions.append(question)
                if reply:
                    group.replies.append(reply)
                return
        groups.append(_Group(words, [question], [reply] if reply else []))


def _similarity(left: frozenset[str], right: frozenset[str]) -> float:
    """Overlap: "Y el sinpe?" matches "¿Cuál es el número de SINPE?"."""
    shorter = min(len(left), len(right))
    return len(left & right) / shorter if shorter else 0.0


def _most_common(texts: list[str]) -> str:
    counts = Counter(texts)
    return max(counts, key=lambda text: (counts[text], len(text)))


def _suggest(group: _Group, known: Mapping[str, str]) -> SuggestedAnswer:
    reply = with_placeholders(_most_common(group.replies), known)
    return SuggestedAnswer(
        question_title(_most_common(group.questions)), reply, len(group.questions)
    )


def _open(group: _Group) -> OpenQuestion:
    return OpenQuestion(question_title(_most_common(group.questions)), len(group.questions))
