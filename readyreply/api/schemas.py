"""Request and response shapes. Content rules live in the domain; these only cap sizes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from readyreply.application.search import SearchResult
from readyreply.domain.answers import Answer, AnswerDraft
from readyreply.domain.errors import persisted_id
from readyreply.domain.unanswered import UnansweredQuestion
from readyreply.domain.users import Role, User
from readyreply.domain.variables import Variable

SHORT = 200
LONG = 10_000
TITLE_INPUT_MAX = SHORT * 2
"""Input caps only stop abuse; the domain applies the real limits (e.g. TITLE_MAX)."""
MAX_TAG_INPUTS = 100


class Credentials(BaseModel):
    username: str = Field(max_length=SHORT)
    password: str = Field(max_length=SHORT)


class MeOut(BaseModel):
    username: str
    role: Role
    csrf_token: str


class SetupStatusOut(BaseModel):
    needs_setup: bool
    csrf_token: str
    locale: str
    demo_kinds: list[str]


class VariableIO(BaseModel):
    key: str = Field(max_length=SHORT)
    label: str = Field(default="", max_length=SHORT)
    value: str = Field(default="", max_length=LONG)
    builtin: bool = False

    @classmethod
    def of(cls, variable: Variable) -> "VariableIO":
        return cls(
            **{name: getattr(variable, name) for name in ("key", "label", "value", "builtin")}
        )

    def to_domain(self) -> Variable:
        return Variable(self.key, self.label, self.value, self.builtin)


class AnswerIn(BaseModel):
    title: str = Field(max_length=TITLE_INPUT_MAX)
    category: str = Field(default="", max_length=SHORT)
    body: str = Field(max_length=LONG)
    tags: list[str] = Field(default_factory=list, max_length=MAX_TAG_INPUTS)

    def to_draft(self) -> AnswerDraft:
        return AnswerDraft(self.title, self.category, self.body, tuple(self.tags))


class AnswerOut(BaseModel):
    id: int
    title: str
    category: str
    body: str
    tags: list[str]
    updated_at: datetime

    @classmethod
    def of(cls, answer: Answer) -> "AnswerOut":
        return cls(
            id=persisted_id(answer.id),
            title=answer.title,
            category=answer.category,
            body=answer.body,
            tags=list(answer.tags),
            updated_at=answer.updated_at,
        )


class RenderedOut(BaseModel):
    text: str | None
    missing: list[str]


class SearchResultOut(BaseModel):
    answer: AnswerOut
    preview: RenderedOut

    @classmethod
    def of(cls, result: SearchResult) -> "SearchResultOut":
        preview = RenderedOut(text=result.preview.text, missing=list(result.preview.missing))
        return cls(answer=AnswerOut.of(result.answer), preview=preview)


class SynonymsIO(BaseModel):
    groups: list[list[str]] = Field(max_length=500)


class QueryIn(BaseModel):
    query: str = Field(max_length=LONG)


class UnansweredOut(BaseModel):
    id: int
    text: str
    times_searched: int
    last_seen: datetime

    @classmethod
    def of(cls, question: UnansweredQuestion) -> "UnansweredOut":
        return cls(
            id=question.id,
            text=question.sample_text,
            times_searched=question.times_searched,
            last_seen=question.last_seen,
        )


class CopiedOut(BaseModel):
    answer_id: int
    title: str
    copies: int


class StatsOut(BaseModel):
    total_answers: int
    total_copies: int
    top_copied: list[CopiedOut]
    top_unanswered: list[UnansweredOut]


class UserIn(Credentials):
    role: Role


class UserUpdateIn(BaseModel):
    role: Role
    active: bool
    new_password: str | None = Field(default=None, max_length=SHORT)


class UserOut(BaseModel):
    id: int
    username: str
    role: Role
    active: bool

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(
            id=persisted_id(user.id), username=user.username, role=user.role, active=user.active
        )


class RejectedRowOut(BaseModel):
    line: int
    code: str


class ImportReportOut(BaseModel):
    imported: int
    rejected: list[RejectedRowOut]


class DemoIn(BaseModel):
    mode: Literal["empty_only", "replace"] = "empty_only"


class DemoOut(BaseModel):
    loaded: int


class SuggestionOut(BaseModel):
    kind: Literal["draft", "manual"]
    text: str | None = None
    prompt: str | None = None
    open_url: str | None = None
    notice: str | None = None


class LanOut(BaseModel):
    url: str
