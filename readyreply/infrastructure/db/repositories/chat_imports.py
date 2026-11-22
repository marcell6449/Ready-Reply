"""What the automatic WhatsApp import has already processed."""

from collections.abc import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from readyreply.domain.whatsapp.imports import ImportedChat
from readyreply.infrastructure.db.models import BusinessRow, ImportedChatRow, SeenChatQuestionRow


class SqlChatImportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def file_seen(self, business_id: int, file_hash: str) -> bool:
        query = select(ImportedChatRow.id).where(
            ImportedChatRow.business_id == business_id, ImportedChatRow.file_hash == file_hash
        )
        return self._session.scalar(query) is not None

    def record_file(self, business_id: int, file_hash: str, record: ImportedChat) -> None:
        self._session.add(
            ImportedChatRow(
                business_id=business_id,
                file_hash=file_hash,
                imported_at=record.imported_at,
                answers=record.answers,
                questions=record.questions,
                details=record.details,
                error=record.error,
            )
        )
        self._session.flush()

    def recent(self, business_id: int, limit: int) -> list[ImportedChat]:
        query = (
            select(ImportedChatRow)
            .where(ImportedChatRow.business_id == business_id)
            .order_by(ImportedChatRow.imported_at.desc(), ImportedChatRow.id.desc())
            .limit(limit)
        )
        return [
            ImportedChat(row.imported_at, row.answers, row.questions, row.details, row.error)
            for row in self._session.scalars(query)
        ]

    def seen_questions(self, business_id: int, fingerprints: Iterable[str]) -> frozenset[str]:
        wanted = list(fingerprints)
        query = select(SeenChatQuestionRow.fingerprint).where(
            SeenChatQuestionRow.business_id == business_id,
            SeenChatQuestionRow.fingerprint.in_(wanted),
        )
        return frozenset(self._session.scalars(query)) if wanted else frozenset()

    def remember_questions(self, business_id: int, fingerprints: Iterable[str]) -> None:
        self._session.add_all(
            SeenChatQuestionRow(business_id=business_id, fingerprint=fingerprint)
            for fingerprint in dict.fromkeys(fingerprints)
        )
        self._session.flush()

    def chat_name(self, business_id: int) -> str | None:
        return self._session.scalar(
            select(BusinessRow.chat_name).where(BusinessRow.id == business_id)
        )

    def set_chat_name(self, business_id: int, name: str) -> None:
        self._session.execute(
            update(BusinessRow).where(BusinessRow.id == business_id).values(chat_name=name)
        )
