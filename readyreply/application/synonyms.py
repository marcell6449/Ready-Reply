"""Synonym groups use cases (F3)."""

from collections.abc import Sequence

from readyreply.application.context import Actor
from readyreply.application.ports import UnitOfWorkFactory
from readyreply.domain.permissions import Action
from readyreply.domain.synonyms import SynonymGroup, validate_groups


class ListSynonyms:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> list[SynonymGroup]:
        actor.require(Action.SEARCH)
        with self._uow_factory() as uow:
            return uow.synonyms.list_all(actor.business_id)


class UpdateSynonyms:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, groups: Sequence[Sequence[str]]) -> list[SynonymGroup]:
        actor.require(Action.MANAGE_SYNONYMS)
        cleaned = validate_groups(groups)
        with self._uow_factory() as uow:
            uow.synonyms.replace_all(actor.business_id, cleaned)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
        return cleaned
