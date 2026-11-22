"""Import chats that appear in the watched folders, with nobody clicking anything."""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from readyreply.application.chat_import import ChatSelection, ChatWriter
from readyreply.application.context import Actor
from readyreply.application.ports import (
    BusinessResolver,
    ChatFileReader,
    Clock,
    UnitOfWork,
    UnitOfWorkFactory,
)
from readyreply.domain.answers import AnswerDraft, title_key
from readyreply.domain.errors import DomainError, InvalidInputError
from readyreply.domain.permissions import Action
from readyreply.domain.users import Role
from readyreply.domain.whatsapp.analysis import ChatAnalysis, ChatAnalyzer, guess_business_sender
from readyreply.domain.whatsapp.imports import ImportedChat
from readyreply.domain.whatsapp.parser import ChatMessage, message_fingerprint, parse_chat

SYSTEM_USER_ID = 0
SYSTEM_NAME = "auto-import"
AUTO_CATEGORY = "WhatsApp"
HISTORY_LIMIT = 20

Chats = list[list[ChatMessage]]


@dataclass(frozen=True, slots=True)
class AutoImportStatus:
    enabled: bool
    folders: list[str]
    recent: list[ImportedChat]


def _selection(analysis: ChatAnalysis, existing: frozenset[str], empty: set[str]) -> ChatSelection:
    """Everything new: answers whose title is free, all open questions, empty details only."""
    answers = [
        AnswerDraft(a.question, AUTO_CATEGORY, a.reply, ())
        for a in analysis.answers
        if title_key(a.question) not in existing
    ]
    questions = [(q.question, q.times_asked) for q in analysis.unanswered]
    details = {d.key: d.value for d in analysis.details if d.key in empty}
    return ChatSelection(answers, questions, details)


class AutoImportChats:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        reader: ChatFileReader,
        analyzer: ChatAnalyzer,
        writer: ChatWriter,
        clock: Clock,
        business: BusinessResolver,
        max_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._reader = reader
        self._analyzer = analyzer
        self._writer = writer
        self._clock = clock
        self._business = business
        self._max_bytes = max_bytes

    def execute(self, data: bytes) -> ImportedChat | None:
        """Imports one file. Returns None when this exact file was imported before."""
        actor = Actor(SYSTEM_USER_ID, self._business.current(), Role.ADMIN, SYSTEM_NAME)
        digest = hashlib.sha256(data).hexdigest()
        with self._uow_factory() as uow:
            if uow.chat_imports.file_seen(actor.business_id, digest):
                return None
            record = self._import_or_note(uow, actor, data)
            uow.chat_imports.record_file(actor.business_id, digest, record)
            uow.commit()
            return record

    def _import_or_note(self, uow: UnitOfWork, actor: Actor, data: bytes) -> ImportedChat:
        try:
            with uow.savepoint():
                return self._import(uow, actor, self._chats(data))
        except DomainError as error:
            return ImportedChat(self._clock.now(), 0, 0, 0, error.code)

    def _chats(self, data: bytes) -> Chats:
        if len(data) > self._max_bytes:
            raise InvalidInputError("whatsapp.too_large")
        return [parse_chat(text) for text in self._reader.texts(data, self._max_bytes)]

    def _import(self, uow: UnitOfWork, actor: Actor, chats: Chats) -> ImportedChat:
        actor.require(Action.IMPORT_CHATS)
        business = self._business_name(uow, actor.business_id, chats)
        variables = uow.variables.list_all(actor.business_id)
        known = {v.key: v.value for v in variables if v.value.strip()}
        everything = [m for chat in chats for m in chat]
        seen = uow.chat_imports.seen_questions(actor.business_id, _fingerprints(everything))
        analysis = self._analyzer.analyze(chats, business, known, seen)
        empty = {v.key for v in variables if not v.value.strip()}
        existing = uow.answers.title_keys(actor.business_id)
        result = self._writer.write(uow, actor, _selection(analysis, existing, empty))
        uow.chat_imports.remember_questions(actor.business_id, analysis.question_fingerprints)
        return ImportedChat(self._clock.now(), result.created, result.questions, result.details)

    def _business_name(self, uow: UnitOfWork, business_id: int, chats: Chats) -> str:
        """Learned from the first import, then reused so single chats are never misread."""
        senders = {m.sender for chat in chats for m in chat}
        known = uow.chat_imports.chat_name(business_id)
        if known in senders:
            return str(known)
        guessed = guess_business_sender(chats) or ""
        uow.chat_imports.set_chat_name(business_id, guessed)
        return guessed


def _fingerprints(messages: Sequence[ChatMessage]) -> list[str]:
    return [message_fingerprint(message) for message in messages]


class GetAutoImportStatus:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, folders: Sequence[str], enabled: bool
    ) -> None:
        self._uow_factory = uow_factory
        self._folders = list(folders)
        self._enabled = enabled

    def execute(self, actor: Actor) -> AutoImportStatus:
        actor.require(Action.IMPORT_CHATS)
        with self._uow_factory() as uow:
            recent = uow.chat_imports.recent(actor.business_id, HISTORY_LIMIT)
        return AutoImportStatus(self._enabled, self._folders, recent)
