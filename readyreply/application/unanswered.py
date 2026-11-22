"""Questions with no answer yet (F5, P4)."""

from readyreply.application.context import Actor
from readyreply.application.ports import AnswerWriter, Clock, RepeatGuard, UnitOfWorkFactory
from readyreply.domain.answers import Answer, AnswerDraft
from readyreply.domain.errors import persisted_id
from readyreply.domain.permissions import Action
from readyreply.domain.sessions import UNANSWERED_REPEAT_WINDOW
from readyreply.domain.unanswered import QuestionKeyer, UnansweredQuestion, sample_text

LIST_LIMIT = 200


class RecordUnanswered:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        keyer: QuestionKeyer,
        clock: Clock,
        guard: RepeatGuard,
    ) -> None:
        self._uow_factory = uow_factory
        self._keyer = keyer
        self._clock = clock
        self._guard = guard

    def execute(self, actor: Actor, query: str) -> None:
        actor.require(Action.RECORD_UNANSWERED)
        key = self._keyer.key(query)
        now = self._clock.now()
        guard_key = f"unanswered:{actor.business_id}:{actor.user_id}:{key}"
        if self._guard.is_repeat(guard_key, now, UNANSWERED_REPEAT_WINDOW):
            return
        with self._uow_factory() as uow:
            uow.unanswered.record(actor.business_id, key, sample_text(query), now)
            uow.commit()


class ListUnanswered:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> list[UnansweredQuestion]:
        actor.require(Action.VIEW_UNANSWERED)
        with self._uow_factory() as uow:
            return uow.unanswered.list_open(actor.business_id, LIST_LIMIT)


class DismissUnanswered:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, question_id: int) -> None:
        actor.require(Action.MANAGE_UNANSWERED)
        with self._uow_factory() as uow:
            uow.unanswered.delete(actor.business_id, question_id)
            uow.commit()


class AnswerQuestion:
    """Create an answer for an unanswered question and mark it resolved, in one transaction."""

    def __init__(self, uow_factory: UnitOfWorkFactory, create: AnswerWriter) -> None:
        self._uow_factory = uow_factory
        self._create = create

    def execute(self, actor: Actor, question_id: int, draft: AnswerDraft) -> Answer:
        actor.require(Action.MANAGE_UNANSWERED)
        with self._uow_factory() as uow:
            uow.unanswered.get_open(actor.business_id, question_id)
            answer = self._create.add_within(uow, actor, draft)
            uow.unanswered.resolve(actor.business_id, question_id, persisted_id(answer.id))
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
            return answer
