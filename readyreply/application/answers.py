"""Answer management use cases (F2)."""

from readyreply.application.context import Actor
from readyreply.application.ports import AnswerWriter, Clock, UnitOfWork, UnitOfWorkFactory
from readyreply.domain.answers import Answer, AnswerDraft, copy_title, title_key
from readyreply.domain.errors import ConflictError
from readyreply.domain.permissions import Action


def _ensure_title_free(uow: UnitOfWork, business_id: int, title: str, exclude: int | None) -> None:
    if uow.answers.title_taken(business_id, title_key(title), exclude):
        raise ConflictError("answer.title_taken", title=title)


class ListAnswers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> list[Answer]:
        actor.require(Action.SEARCH)
        with self._uow_factory() as uow:
            return uow.answers.list_all(actor.business_id)


class CreateAnswer:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, draft: AnswerDraft) -> Answer:
        with self._uow_factory() as uow:
            answer = self.add_within(uow, actor, draft)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
            return answer

    def add_within(self, uow: UnitOfWork, actor: Actor, draft: AnswerDraft) -> Answer:
        """Create inside the caller's transaction. The caller bumps the search revision once."""
        actor.require(Action.MANAGE_ANSWERS)
        cleaned = draft.cleaned()
        _ensure_title_free(uow, actor.business_id, cleaned.title, None)
        now = self._clock.now()
        return uow.answers.add(
            Answer(
                id=None,
                business_id=actor.business_id,
                title=cleaned.title,
                category=cleaned.category,
                body=cleaned.body,
                tags=cleaned.tags,
                created_at=now,
                updated_at=now,
            )
        )


class EditAnswer:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    def execute(self, actor: Actor, answer_id: int, draft: AnswerDraft) -> Answer:
        actor.require(Action.MANAGE_ANSWERS)
        cleaned = draft.cleaned()
        with self._uow_factory() as uow:
            current = uow.answers.get(actor.business_id, answer_id)
            _ensure_title_free(uow, actor.business_id, cleaned.title, answer_id)
            updated = current.with_draft(cleaned, self._clock.now())
            uow.answers.update(updated)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
            return updated


class DeleteAnswer:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, answer_id: int) -> None:
        actor.require(Action.MANAGE_ANSWERS)
        with self._uow_factory() as uow:
            uow.answers.delete(actor.business_id, answer_id)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()


class DuplicateAnswer:
    def __init__(self, uow_factory: UnitOfWorkFactory, create: AnswerWriter, suffix: str) -> None:
        self._uow_factory = uow_factory
        self._create = create
        self._suffix = suffix

    def execute(self, actor: Actor, answer_id: int) -> Answer:
        actor.require(Action.MANAGE_ANSWERS)
        with self._uow_factory() as uow:
            original = uow.answers.get(actor.business_id, answer_id)
            taken = uow.answers.title_keys(actor.business_id)
            title = copy_title(original.title, self._suffix, taken)
            draft = AnswerDraft(title, original.category, original.body, original.tags)
            answer = self._create.add_within(uow, actor, draft)
            uow.businesses.bump_revision(actor.business_id)
            uow.commit()
            return answer
