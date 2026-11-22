"""Unanswered questions, statistics and AI suggestions (F5, F7, F8)."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from readyreply.api.deps import ActorDep, ContainerDep
from readyreply.api.schemas import (
    AnswerIn,
    AnswerOut,
    CopiedOut,
    QueryIn,
    StatsOut,
    SuggestionOut,
    UnansweredOut,
)
from readyreply.domain.ai import Draft

router = APIRouter(prefix="/api")


class SuggestIn(BaseModel):
    question_id: int
    locale: Literal["es", "en"] | None = None


@router.get("/unanswered")
def list_unanswered(actor: ActorDep, container: ContainerDep) -> list[UnansweredOut]:
    return [UnansweredOut.of(q) for q in container.activity.list_unanswered.execute(actor)]


@router.post("/unanswered", status_code=204)
def record_unanswered(body: QueryIn, actor: ActorDep, container: ContainerDep) -> None:
    container.activity.record_unanswered.execute(actor, body.query)


@router.post("/unanswered/{question_id}/answer", status_code=201)
def answer_question(
    question_id: int, body: AnswerIn, actor: ActorDep, container: ContainerDep
) -> AnswerOut:
    answer = container.activity.answer_question.execute(actor, question_id, body.to_draft())
    return AnswerOut.of(answer)


@router.delete("/unanswered/{question_id}", status_code=204)
def dismiss_unanswered(question_id: int, actor: ActorDep, container: ContainerDep) -> None:
    container.activity.dismiss_unanswered.execute(actor, question_id)


@router.get("/stats")
def stats(actor: ActorDep, container: ContainerDep) -> StatsOut:
    result = container.activity.stats.execute(actor)
    return StatsOut(
        total_answers=result.total_answers,
        total_copies=result.total_copies,
        top_copied=[
            CopiedOut(answer_id=c.answer_id, title=c.title, copies=c.copies)
            for c in result.top_copied
        ],
        top_unanswered=[UnansweredOut.of(q) for q in result.top_unanswered],
    )


@router.post("/ai/suggest")
def suggest(body: SuggestIn, actor: ActorDep, container: ContainerDep) -> SuggestionOut:
    outcome = container.activity.suggest.execute(actor, body.question_id, body.locale)
    if isinstance(outcome.result, Draft):
        return SuggestionOut(kind="draft", text=outcome.result.text, notice=outcome.notice)
    return SuggestionOut(
        kind="manual",
        prompt=outcome.result.prompt,
        open_url=outcome.result.open_url,
        notice=outcome.notice,
    )
