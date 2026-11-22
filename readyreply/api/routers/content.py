"""Variables, answers, synonyms, search and copy (F1–F4)."""

from fastapi import APIRouter, Query

from readyreply.api.deps import ActorDep, ContainerDep
from readyreply.api.schemas import (
    AnswerIn,
    AnswerOut,
    RenderedOut,
    SearchResultOut,
    SynonymsIO,
    VariableIO,
)
from readyreply.domain.search.scoring_config import MAX_QUERY_CHARS

router = APIRouter(prefix="/api")


@router.get("/variables")
def list_variables(actor: ActorDep, container: ContainerDep) -> list[VariableIO]:
    return [VariableIO.of(v) for v in container.content.list_variables.execute(actor)]


@router.put("/variables")
def update_variables(
    body: list[VariableIO], actor: ActorDep, container: ContainerDep
) -> list[VariableIO]:
    saved = container.content.update_variables.execute(actor, [v.to_domain() for v in body])
    return [VariableIO.of(v) for v in saved]


@router.get("/answers")
def list_answers(actor: ActorDep, container: ContainerDep) -> list[AnswerOut]:
    return [AnswerOut.of(a) for a in container.content.list_answers.execute(actor)]


@router.post("/answers", status_code=201)
def create_answer(body: AnswerIn, actor: ActorDep, container: ContainerDep) -> AnswerOut:
    return AnswerOut.of(container.content.create_answer.execute(actor, body.to_draft()))


@router.put("/answers/{answer_id}")
def edit_answer(
    answer_id: int, body: AnswerIn, actor: ActorDep, container: ContainerDep
) -> AnswerOut:
    return AnswerOut.of(container.content.edit_answer.execute(actor, answer_id, body.to_draft()))


@router.delete("/answers/{answer_id}", status_code=204)
def delete_answer(answer_id: int, actor: ActorDep, container: ContainerDep) -> None:
    container.content.delete_answer.execute(actor, answer_id)


@router.post("/answers/{answer_id}/duplicate", status_code=201)
def duplicate_answer(answer_id: int, actor: ActorDep, container: ContainerDep) -> AnswerOut:
    return AnswerOut.of(container.content.duplicate_answer.execute(actor, answer_id))


@router.post("/answers/{answer_id}/copy")
def copy_answer(answer_id: int, actor: ActorDep, container: ContainerDep) -> RenderedOut:
    result = container.content.copy.execute(actor, answer_id)
    return RenderedOut(text=result.text, missing=list(result.missing))


@router.get("/search")
def search(
    actor: ActorDep, container: ContainerDep, q: str = Query(default="")
) -> list[SearchResultOut]:
    results = container.content.search.execute(actor, q[:MAX_QUERY_CHARS])
    return [SearchResultOut.of(result) for result in results]


@router.get("/synonyms")
def list_synonyms(actor: ActorDep, container: ContainerDep) -> SynonymsIO:
    groups = container.content.list_synonyms.execute(actor)
    return SynonymsIO(groups=[list(group) for group in groups])


@router.put("/synonyms")
def update_synonyms(body: SynonymsIO, actor: ActorDep, container: ContainerDep) -> SynonymsIO:
    groups = container.content.update_synonyms.execute(actor, body.groups)
    return SynonymsIO(groups=[list(group) for group in groups])
