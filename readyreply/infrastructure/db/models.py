"""SQLAlchemy tables. Every table carries business_id, so a multi-business SaaS needs no rework."""

from datetime import UTC, datetime
from typing import override

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Stores UTC; always returns timezone-aware datetimes (SQLite drops the zone)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


def _business_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)


class BusinessRow(Base):
    __tablename__ = "businesses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    locale: Mapped[str] = mapped_column(String(10))
    content_revision: Mapped[int] = mapped_column(Integer, default=0)
    chat_name: Mapped[str | None] = mapped_column(String(80), nullable=True, default=None)
    """How the business appears in its own WhatsApp exports (learned on the first import)."""


class VariableRow(Base):
    __tablename__ = "variables"
    __table_args__ = (UniqueConstraint("business_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    key: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(60))
    value: Mapped[str] = mapped_column(Text)
    builtin: Mapped[bool]
    position: Mapped[int]


class AnswerRow(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("business_id", "title_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    title: Mapped[str] = mapped_column(String(120))
    title_key: Mapped[str] = mapped_column(String(240))
    category: Mapped[str] = mapped_column(String(60))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime)


class SynonymGroupRow(Base):
    __tablename__ = "synonym_groups"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    terms: Mapped[list[str]] = mapped_column(JSON)


class UnansweredRow(Base):
    __tablename__ = "unanswered_questions"
    __table_args__ = (UniqueConstraint("business_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    key: Mapped[str] = mapped_column(String(400))
    sample_text: Mapped[str] = mapped_column(String(200))
    times_searched: Mapped[int]
    first_seen: Mapped[datetime] = mapped_column(UtcDateTime)
    last_seen: Mapped[datetime] = mapped_column(UtcDateTime)
    resolved_answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("answers.id", ondelete="SET NULL"), nullable=True
    )
    resolved: Mapped[bool] = mapped_column(default=False)


class UserRow(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("business_id", "username"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    username: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(10))
    active: Mapped[bool]


class CopyEventRow(Base):
    __tablename__ = "copy_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    copied_at: Mapped[datetime] = mapped_column(UtcDateTime)


class ImportedChatRow(Base):
    """A chat file already imported automatically. Its name is not kept (it names a customer)."""

    __tablename__ = "imported_chats"
    __table_args__ = (UniqueConstraint("business_id", "file_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = _business_fk()
    file_hash: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(UtcDateTime)
    answers: Mapped[int]
    questions: Mapped[int]
    details: Mapped[int]
    error: Mapped[str | None] = mapped_column(String(60), nullable=True)


class SeenChatQuestionRow(Base):
    """One-way fingerprints of customer questions already counted, so nothing counts twice."""

    __tablename__ = "seen_chat_questions"
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), primary_key=True
    )
    fingerprint: Mapped[str] = mapped_column(String(32), primary_key=True)


class SessionRow(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    business_id: Mapped[int] = _business_fk()
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
