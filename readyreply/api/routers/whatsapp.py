"""Import answers from exported WhatsApp chats: preview, then save."""

import base64
import binascii

from fastapi import APIRouter
from pydantic import BaseModel, Field

from readyreply.api.deps import ActorDep, ContainerDep
from readyreply.api.schemas import AnswerIn
from readyreply.application.chat_import import ChatPreview, ChatSelection
from readyreply.domain.answers import title_key
from readyreply.domain.errors import InvalidInputError

router = APIRouter(prefix="/api/whatsapp")
MAX_FILES_IN_REQUEST = 50


class ChatFileIn(BaseModel):
    name: str = Field(max_length=300)
    content_base64: str


class AnalyzeIn(BaseModel):
    files: list[ChatFileIn] = Field(max_length=MAX_FILES_IN_REQUEST)
    business_sender: str | None = Field(default=None, max_length=200)


class SuggestedAnswerOut(BaseModel):
    question: str
    reply: str
    times_asked: int
    exists: bool


class OpenQuestionIO(BaseModel):
    question: str = Field(max_length=2000)
    times_asked: int = Field(ge=1, le=100_000)


class DetailOut(BaseModel):
    key: str
    value: str
    current: str


class PreviewOut(BaseModel):
    senders: list[str]
    business_sender: str
    answers: list[SuggestedAnswerOut]
    unanswered: list[OpenQuestionIO]
    details: list[DetailOut]
    skipped_files: int

    @classmethod
    def of(cls, preview: ChatPreview) -> "PreviewOut":
        analysis = preview.analysis
        return cls(
            senders=preview.senders,
            business_sender=preview.business_sender,
            answers=[
                SuggestedAnswerOut(
                    question=a.question,
                    reply=a.reply,
                    times_asked=a.times_asked,
                    exists=title_key(a.question) in preview.existing_title_keys,
                )
                for a in analysis.answers
            ],
            unanswered=[
                OpenQuestionIO(question=q.question, times_asked=q.times_asked)
                for q in analysis.unanswered
            ],
            details=[
                DetailOut(key=d.key, value=d.value, current=preview.current_values.get(d.key, ""))
                for d in analysis.details
            ],
            skipped_files=preview.skipped_files,
        )


class ImportIn(BaseModel):
    answers: list[AnswerIn] = Field(default_factory=list, max_length=500)
    questions: list[OpenQuestionIO] = Field(default_factory=list, max_length=500)
    details: dict[str, str] = Field(default_factory=dict, max_length=20)


class ImportOut(BaseModel):
    created: int
    skipped: int
    questions: int
    details: int


def _decode(file: ChatFileIn) -> bytes:
    try:
        return base64.b64decode(file.content_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidInputError("whatsapp.invalid_file") from error


@router.post("/analyze")
def analyze(body: AnalyzeIn, actor: ActorDep, container: ContainerDep) -> PreviewOut:
    files = [_decode(file) for file in body.files]
    preview = container.admin.preview_chats.execute(actor, files, body.business_sender)
    return PreviewOut.of(preview)


@router.post("/import")
def import_chats(body: ImportIn, actor: ActorDep, container: ContainerDep) -> ImportOut:
    selection = ChatSelection(
        answers=[answer.to_draft() for answer in body.answers],
        questions=[(q.question, q.times_asked) for q in body.questions],
        details=body.details,
    )
    result = container.admin.apply_chats.execute(actor, selection)
    return ImportOut(
        created=result.created,
        skipped=result.skipped,
        questions=result.questions,
        details=result.details,
    )
