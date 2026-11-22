"""Load one of the sample businesses (F9)."""

from dataclasses import dataclass
from typing import Protocol

from readyreply.application.context import Actor
from readyreply.application.ports import AnswerWriter, UnitOfWork, UnitOfWorkFactory
from readyreply.domain.answers import AnswerDraft
from readyreply.domain.errors import ConflictError
from readyreply.domain.permissions import Action
from readyreply.domain.synonyms import validate_groups
from readyreply.domain.variables import Variable, validate_variable_set


@dataclass(frozen=True, slots=True)
class DemoBusiness:
    variables: tuple[Variable, ...]
    answers: tuple[AnswerDraft, ...]
    synonyms: tuple[tuple[str, ...], ...]


class DemoCatalog(Protocol):
    def kinds(self) -> tuple[str, ...]: ...
    def load(self, kind: str) -> DemoBusiness:
        """Raises NotFoundError for unknown kinds."""
        ...


class LoadDemo:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, catalog: DemoCatalog, create: AnswerWriter
    ) -> None:
        self._uow_factory = uow_factory
        self._catalog = catalog
        self._create = create

    def kinds(self) -> tuple[str, ...]:
        return self._catalog.kinds()

    def into_empty_library(self, actor: Actor, kind: str) -> int:
        actor.require(Action.LOAD_DEMO)
        with self._uow_factory() as uow:
            if uow.answers.count(actor.business_id):
                raise ConflictError("demo.confirm_replace")
            return self._load(uow, actor, kind)

    def replacing_library(self, actor: Actor, kind: str) -> int:
        actor.require(Action.LOAD_DEMO)
        with self._uow_factory() as uow:
            uow.answers.delete_all(actor.business_id)
            return self._load(uow, actor, kind)

    def _load(self, uow: UnitOfWork, actor: Actor, kind: str) -> int:
        demo = self._catalog.load(kind)
        uow.variables.replace_all(actor.business_id, validate_variable_set(demo.variables))
        uow.synonyms.replace_all(actor.business_id, validate_groups(demo.synonyms))
        for draft in demo.answers:
            self._create.add_within(uow, actor, draft)
        uow.businesses.bump_revision(actor.business_id)
        uow.commit()
        return len(demo.answers)
