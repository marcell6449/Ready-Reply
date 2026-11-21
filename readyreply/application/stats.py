"""Usage statistics (F7)."""

from dataclasses import dataclass

from readyreply.application.context import Actor
from readyreply.application.ports import UnitOfWorkFactory
from readyreply.domain.permissions import Action
from readyreply.domain.unanswered import UnansweredQuestion

TOP_LIMIT = 10


@dataclass(frozen=True, slots=True)
class CopiedAnswer:
    answer_id: int
    title: str
    copies: int


@dataclass(frozen=True, slots=True)
class Stats:
    total_answers: int
    total_copies: int
    top_copied: list[CopiedAnswer]
    top_unanswered: list[UnansweredQuestion]


class GetStats:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> Stats:
        actor.require(Action.VIEW_STATS)
        with self._uow_factory() as uow:
            counts = uow.copies.counts(actor.business_id)
            titles = {a.id: a.title for a in uow.answers.list_all(actor.business_id)}
            unanswered = uow.unanswered.list_open(actor.business_id, TOP_LIMIT)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], titles.get(item[0], "")))
        top = [CopiedAnswer(aid, titles[aid], n) for aid, n in ranked if aid in titles]
        return Stats(len(titles), sum(counts.values()), top[:TOP_LIMIT], unanswered)
