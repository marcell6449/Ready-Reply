"""Business variables use cases (F1)."""

from collections.abc import Sequence

from readyreply.application.context import Actor
from readyreply.application.ports import UnitOfWorkFactory
from readyreply.domain.permissions import Action
from readyreply.domain.variables import Variable, validate_variable_set


class ListVariables:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> list[Variable]:
        actor.require(Action.SEARCH)
        with self._uow_factory() as uow:
            return uow.variables.list_all(actor.business_id)


class UpdateVariables:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, variables: Sequence[Variable]) -> list[Variable]:
        actor.require(Action.MANAGE_VARIABLES)
        cleaned = validate_variable_set(variables)
        with self._uow_factory() as uow:
            uow.variables.replace_all(actor.business_id, cleaned)
            uow.commit()
        return cleaned
