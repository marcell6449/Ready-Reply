"""Repositories for the business, its variables, synonyms and answers."""

from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from readyreply.domain.answers import Answer
from readyreply.domain.errors import ConflictError, NotFoundError
from readyreply.domain.synonyms import SynonymGroup
from readyreply.domain.variables import Variable
from readyreply.infrastructure.db.models import (
    AnswerRow,
    BusinessRow,
    SynonymGroupRow,
    VariableRow,
)


class SqlBusinessRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure(self, business_id: int, locale: str) -> bool:
        if self._session.get(BusinessRow, business_id) is not None:
            return False
        self._session.add(BusinessRow(id=business_id, locale=locale, content_revision=0))
        self._session.flush()
        return True

    def revision(self, business_id: int) -> int:
        query = select(BusinessRow.content_revision).where(BusinessRow.id == business_id)
        return self._session.scalar(query) or 0

    def bump_revision(self, business_id: int) -> None:
        self._session.execute(
            update(BusinessRow)
            .where(BusinessRow.id == business_id)
            .values(content_revision=BusinessRow.content_revision + 1)
        )


class SqlVariableRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, business_id: int) -> list[Variable]:
        query = (
            select(VariableRow)
            .where(VariableRow.business_id == business_id)
            .order_by(VariableRow.position)
        )
        rows = self._session.scalars(query)
        return [Variable(row.key, row.label, row.value, row.builtin) for row in rows]

    def replace_all(self, business_id: int, variables: Sequence[Variable]) -> None:
        self._session.execute(delete(VariableRow).where(VariableRow.business_id == business_id))
        self._session.add_all(
            VariableRow(
                business_id=business_id,
                key=v.key,
                label=v.label,
                value=v.value,
                builtin=v.builtin,
                position=position,
            )
            for position, v in enumerate(variables)
        )
        self._session.flush()


class SqlSynonymRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self, business_id: int) -> list[SynonymGroup]:
        query = (
            select(SynonymGroupRow)
            .where(SynonymGroupRow.business_id == business_id)
            .order_by(SynonymGroupRow.id)
        )
        return [tuple(row.terms) for row in self._session.scalars(query)]

    def replace_all(self, business_id: int, groups: Sequence[SynonymGroup]) -> None:
        self._session.execute(
            delete(SynonymGroupRow).where(SynonymGroupRow.business_id == business_id)
        )
        self._session.add_all(
            SynonymGroupRow(business_id=business_id, terms=list(group)) for group in groups
        )
        self._session.flush()


def _to_answer(row: AnswerRow) -> Answer:
    return Answer(
        id=row.id,
        business_id=row.business_id,
        title=row.title,
        category=row.category,
        body=row.body,
        tags=tuple(row.tags),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAnswerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _row(self, business_id: int, answer_id: int) -> AnswerRow:
        row = self._session.get(AnswerRow, answer_id)
        if row is None or row.business_id != business_id:
            raise NotFoundError("answer.not_found", id=answer_id)
        return row

    def get(self, business_id: int, answer_id: int) -> Answer:
        return _to_answer(self._row(business_id, answer_id))

    def list_all(self, business_id: int) -> list[Answer]:
        query = select(AnswerRow).where(AnswerRow.business_id == business_id)
        return [_to_answer(row) for row in self._session.scalars(query.order_by(AnswerRow.title))]

    def count(self, business_id: int) -> int:
        query = select(func.count()).select_from(AnswerRow)
        return self._session.scalar(query.where(AnswerRow.business_id == business_id)) or 0

    def add(self, answer: Answer) -> Answer:
        row = AnswerRow(business_id=answer.business_id, title_key=answer.title_key)
        self._copy_fields(row, answer)
        row.created_at = answer.created_at
        self._session.add(row)
        self._flush()
        return _to_answer(row)

    def update(self, answer: Answer) -> None:
        if answer.id is None:
            raise NotFoundError("answer.not_found")
        row = self._row(answer.business_id, answer.id)
        self._copy_fields(row, answer)
        row.title_key = answer.title_key
        self._flush()

    def delete(self, business_id: int, answer_id: int) -> None:
        self._session.delete(self._row(business_id, answer_id))
        self._session.flush()

    def delete_all(self, business_id: int) -> None:
        self._session.execute(delete(AnswerRow).where(AnswerRow.business_id == business_id))

    def title_keys(self, business_id: int) -> frozenset[str]:
        query = select(AnswerRow.title_key).where(AnswerRow.business_id == business_id)
        return frozenset(self._session.scalars(query))

    def title_taken(self, business_id: int, key: str, exclude_id: int | None) -> bool:
        query = select(AnswerRow.id).where(
            AnswerRow.business_id == business_id, AnswerRow.title_key == key
        )
        found = self._session.scalar(query)
        return found is not None and found != exclude_id

    @staticmethod
    def _copy_fields(row: AnswerRow, answer: Answer) -> None:
        row.title = answer.title
        row.category = answer.category
        row.body = answer.body
        row.tags = list(answer.tags)
        row.updated_at = answer.updated_at

    def _flush(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            raise ConflictError("answer.title_taken") from error
