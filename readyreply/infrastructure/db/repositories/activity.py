"""Repositories for unanswered questions and copy events."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from readyreply.domain.errors import NotFoundError
from readyreply.domain.unanswered import UnansweredQuestion
from readyreply.infrastructure.db.models import CopyEventRow, UnansweredRow

UpsertInsert = sqlite.Insert | postgresql.Insert
_UPSERT_INSERTS: dict[str, Callable[[type[UnansweredRow]], UpsertInsert]] = {
    "sqlite": sqlite.insert,
    "postgresql": postgresql.insert,
}


def _to_question(row: UnansweredRow) -> UnansweredQuestion:
    return UnansweredQuestion(
        id=row.id,
        business_id=row.business_id,
        key=row.key,
        sample_text=row.sample_text,
        times_searched=row.times_searched,
        last_seen=row.last_seen,
    )


def _searched_again(sample: str, now: datetime) -> dict[str, object]:
    """Update for a question already on file. If it was answered, it starts over at 1."""
    was_resolved = UnansweredRow.resolved
    return {
        "times_searched": case((was_resolved, 1), else_=UnansweredRow.times_searched + 1),
        "resolved_answer_id": case((was_resolved, None), else_=UnansweredRow.resolved_answer_id),
        "last_seen": now,
        "sample_text": sample,
        "resolved": False,
    }


class SqlUnansweredRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, business_id: int, key: str, sample: str, now: datetime) -> None:
        insert = _UPSERT_INSERTS[self._session.get_bind().dialect.name]
        statement = insert(UnansweredRow).values(
            business_id=business_id,
            key=key,
            sample_text=sample,
            times_searched=1,
            first_seen=now,
            last_seen=now,
            resolved=False,
        )
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["business_id", "key"], set_=_searched_again(sample, now)
            )
        )

    def list_open(self, business_id: int, limit: int) -> list[UnansweredQuestion]:
        query = (
            select(UnansweredRow)
            .where(UnansweredRow.business_id == business_id, UnansweredRow.resolved.is_(False))
            .order_by(UnansweredRow.times_searched.desc(), UnansweredRow.last_seen.desc())
            .limit(limit)
        )
        return [_to_question(row) for row in self._session.scalars(query)]

    def _open_row(self, business_id: int, question_id: int) -> UnansweredRow:
        row = self._session.get(UnansweredRow, question_id)
        if row is None or row.business_id != business_id or row.resolved:
            raise NotFoundError("unanswered.not_found", id=question_id)
        return row

    def get_open(self, business_id: int, question_id: int) -> UnansweredQuestion:
        return _to_question(self._open_row(business_id, question_id))

    def resolve(self, business_id: int, question_id: int, answer_id: int) -> None:
        row = self._open_row(business_id, question_id)
        row.resolved = True
        row.resolved_answer_id = answer_id
        self._session.flush()

    def delete(self, business_id: int, question_id: int) -> None:
        self._session.delete(self._open_row(business_id, question_id))
        self._session.flush()


class SqlCopyEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, business_id: int, answer_id: int, user_id: int, now: datetime) -> None:
        self._session.add(
            CopyEventRow(
                business_id=business_id, answer_id=answer_id, user_id=user_id, copied_at=now
            )
        )
        self._session.flush()

    def counts(self, business_id: int) -> dict[int, int]:
        query = (
            select(CopyEventRow.answer_id, func.count())
            .where(CopyEventRow.business_id == business_id)
            .group_by(CopyEventRow.answer_id)
        )
        return {answer_id: total for answer_id, total in self._session.execute(query)}
