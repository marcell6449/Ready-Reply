"""CSV export and import of answers (F10)."""

from dataclasses import dataclass

from readyreply.application.context import Actor
from readyreply.application.ports import (
    AnswerWriter,
    CsvCodec,
    CsvRow,
    UnitOfWork,
    UnitOfWorkFactory,
)
from readyreply.domain.answers import AnswerDraft
from readyreply.domain.csv_rules import (
    CSV_HEADER,
    MAX_ROWS,
    answer_to_row,
    row_to_draft,
    validate_header,
)
from readyreply.domain.errors import DomainError, InvalidInputError, PayloadTooLargeError
from readyreply.domain.permissions import Action


@dataclass(frozen=True, slots=True)
class RejectedRow:
    line: int
    code: str


@dataclass(frozen=True, slots=True)
class ImportReport:
    imported: int
    rejected: list[RejectedRow]


class ExportAnswers:
    def __init__(self, uow_factory: UnitOfWorkFactory, codec: CsvCodec) -> None:
        self._uow_factory = uow_factory
        self._codec = codec

    def execute(self, actor: Actor) -> bytes:
        actor.require(Action.TRANSFER_CSV)
        with self._uow_factory() as uow:
            answers = uow.answers.list_all(actor.business_id)
        rows = [answer_to_row(AnswerDraft(a.title, a.category, a.body, a.tags)) for a in answers]
        return self._codec.encode(CSV_HEADER, rows)


class ImportAnswers:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        codec: CsvCodec,
        create: AnswerWriter,
        max_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._codec = codec
        self._create = create
        self._max_bytes = max_bytes

    def execute(self, actor: Actor, data: bytes) -> ImportReport:
        actor.require(Action.TRANSFER_CSV)
        if len(data) > self._max_bytes:
            raise PayloadTooLargeError("csv.too_large", limit=self._max_bytes)
        header, rows = self._codec.decode(data)
        validate_header(header)
        if len(rows) > MAX_ROWS:
            raise InvalidInputError("csv.too_many_rows", limit=MAX_ROWS)
        with self._uow_factory() as uow:
            report = self._import_rows(uow, actor, rows)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
        return report

    def _import_rows(self, uow: UnitOfWork, actor: Actor, rows: list[CsvRow]) -> ImportReport:
        imported = 0
        rejected: list[RejectedRow] = []
        for line, row in rows:
            try:
                with uow.savepoint():
                    self._create.add_within(uow, actor, row_to_draft(row))
            except DomainError as error:
                rejected.append(RejectedRow(line, error.code))
            else:
                imported += 1
        return ImportReport(imported, rejected)
