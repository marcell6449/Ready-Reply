"""Create answers from the business's own WhatsApp chats (exported by the owner)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from readyreply.application.context import Actor
from readyreply.application.ports import (
    AnswerWriter,
    ChatFileReader,
    Clock,
    UnitOfWork,
    UnitOfWorkFactory,
)
from readyreply.domain.answers import AnswerDraft
from readyreply.domain.errors import DomainError, InvalidInputError, PayloadTooLargeError
from readyreply.domain.permissions import Action
from readyreply.domain.unanswered import QuestionKeyer, sample_text
from readyreply.domain.variables import BUILTIN_KEYS, validate_variable_set, with_value
from readyreply.domain.whatsapp.analysis import (
    ChatAnalysis,
    ChatAnalyzer,
    senders_of,
    with_placeholders,
)
from readyreply.domain.whatsapp.parser import ChatMessage, parse_chat

MAX_FILES = 50
MAX_SENDERS_SHOWN = 15


@dataclass(frozen=True, slots=True)
class ChatPreview:
    senders: list[str]
    business_sender: str
    analysis: ChatAnalysis
    existing_title_keys: frozenset[str]
    current_values: Mapping[str, str]
    skipped_files: int


@dataclass(frozen=True, slots=True)
class ChatSelection:
    answers: Sequence[AnswerDraft]
    questions: Sequence[tuple[str, int]]
    details: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ChatImportResult:
    created: int
    skipped: int
    questions: int
    details: int


def _parse_all(texts: list[str]) -> tuple[list[list[ChatMessage]], int]:
    chats, skipped = [], 0
    for text in texts:
        try:
            chats.append(parse_chat(text))
        except InvalidInputError:
            skipped += 1
    if not chats:
        raise InvalidInputError("whatsapp.no_messages")
    return chats, skipped


class PreviewChatImport:
    """Reads the chats and proposes answers. Saves nothing."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        reader: ChatFileReader,
        analyzer: ChatAnalyzer,
        max_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._reader = reader
        self._analyzer = analyzer
        self._max_bytes = max_bytes

    def execute(self, actor: Actor, files: Sequence[bytes], business: str | None) -> ChatPreview:
        actor.require(Action.IMPORT_CHATS)
        self._check_size(files)
        texts = [text for data in files for text in self._reader.texts(data, self._max_bytes)]
        chats, skipped = _parse_all(texts)
        senders = senders_of(chats)
        chosen = business if business in senders else senders[0]
        with self._uow_factory() as uow:
            current = {v.key: v.value for v in uow.variables.list_all(actor.business_id)}
            titles = uow.answers.title_keys(actor.business_id)
        known = {key: value for key, value in current.items() if value.strip()}
        analysis = self._analyzer.analyze(chats, chosen, known)
        return ChatPreview(senders[:MAX_SENDERS_SHOWN], chosen, analysis, titles, current, skipped)

    def _check_size(self, files: Sequence[bytes]) -> None:
        if not files:
            raise InvalidInputError("whatsapp.no_files")
        if len(files) > MAX_FILES or sum(len(data) for data in files) > self._max_bytes:
            raise PayloadTooLargeError("whatsapp.too_large", limit=self._max_bytes)


class ApplyChatImport:
    """Saves what the owner kept from the preview, in one transaction."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        create: AnswerWriter,
        keyer: QuestionKeyer,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._create = create
        self._keyer = keyer
        self._clock = clock

    def execute(self, actor: Actor, selection: ChatSelection) -> ChatImportResult:
        actor.require(Action.IMPORT_CHATS)
        if not set(selection.details) <= set(BUILTIN_KEYS):
            raise InvalidInputError("whatsapp.unknown_detail")
        drafts = [
            replace(draft, body=with_placeholders(draft.body, selection.details))
            for draft in selection.answers
        ]
        with self._uow_factory() as uow:
            details = self._save_details(uow, actor, selection.details)
            created = self._save_answers(uow, actor, drafts)
            questions = self._save_questions(uow, actor, selection.questions)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
        skipped = len(selection.answers) - created
        return ChatImportResult(created, skipped, questions, details)

    def _save_details(self, uow: UnitOfWork, actor: Actor, details: Mapping[str, str]) -> int:
        variables = uow.variables.list_all(actor.business_id)
        for key, value in details.items():
            variables = with_value(variables, key, value)
        uow.variables.replace_all(actor.business_id, validate_variable_set(variables))
        return len(details)

    def _save_answers(self, uow: UnitOfWork, actor: Actor, drafts: Sequence[AnswerDraft]) -> int:
        created = 0
        for draft in drafts:
            try:
                with uow.savepoint():
                    self._create.add_within(uow, actor, draft)
            except DomainError:
                continue
            created += 1
        return created

    def _save_questions(
        self, uow: UnitOfWork, actor: Actor, questions: Sequence[tuple[str, int]]
    ) -> int:
        saved = 0
        now = self._clock.now()
        for text, times in questions:
            try:
                key = self._keyer.key(text)
            except InvalidInputError:
                continue
            uow.unanswered.record(actor.business_id, key, sample_text(text), now, max(times, 1))
            saved += 1
        return saved
