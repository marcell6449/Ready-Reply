"""Copy an answer with its variables filled in (F4, P1, P3)."""

from readyreply.application.context import Actor
from readyreply.application.ports import Clock, RepeatGuard, UnitOfWorkFactory
from readyreply.domain.permissions import Action
from readyreply.domain.sessions import COPY_REPEAT_WINDOW
from readyreply.domain.templates import RenderResult, render
from readyreply.domain.variables import values_by_key


class CopyAnswer:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, guard: RepeatGuard) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._guard = guard

    def execute(self, actor: Actor, answer_id: int) -> RenderResult:
        actor.require(Action.COPY)
        with self._uow_factory() as uow:
            answer = uow.answers.get(actor.business_id, answer_id)
            values = values_by_key(uow.variables.list_all(actor.business_id))
            result = render(answer.body, values)
            if result.text is not None and not self._is_double_click(actor, answer_id):
                uow.copies.add(actor.business_id, answer_id, actor.user_id, self._clock.now())
                uow.commit()
            return result

    def _is_double_click(self, actor: Actor, answer_id: int) -> bool:
        key = f"copy:{actor.business_id}:{actor.user_id}:{answer_id}"
        return self._guard.is_repeat(key, self._clock.now(), COPY_REPEAT_WINDOW)
