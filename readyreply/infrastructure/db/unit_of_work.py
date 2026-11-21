"""SQLAlchemy implementation of the UnitOfWork port."""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from readyreply.application.ports import (
    AnswerRepository,
    BusinessRepository,
    CopyEventRepository,
    SessionRepository,
    SynonymRepository,
    UnansweredRepository,
    UserRepository,
    VariableRepository,
)
from readyreply.infrastructure.db.repositories.accounts import (
    SqlSessionRepository,
    SqlUserRepository,
)
from readyreply.infrastructure.db.repositories.activity import (
    SqlCopyEventRepository,
    SqlUnansweredRepository,
)
from readyreply.infrastructure.db.repositories.content import (
    SqlAnswerRepository,
    SqlBusinessRepository,
    SqlSynonymRepository,
    SqlVariableRepository,
)


class SqlUnitOfWork:
    businesses: BusinessRepository
    answers: AnswerRepository
    variables: VariableRepository
    synonyms: SynonymRepository
    unanswered: UnansweredRepository
    copies: CopyEventRepository
    users: UserRepository
    sessions: SessionRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.businesses = SqlBusinessRepository(self._session)
        self.answers = SqlAnswerRepository(self._session)
        self.variables = SqlVariableRepository(self._session)
        self.synonyms = SqlSynonymRepository(self._session)
        self.unanswered = SqlUnansweredRepository(self._session)
        self.copies = SqlCopyEventRepository(self._session)
        self.users = SqlUserRepository(self._session)
        self.sessions = SqlSessionRepository(self._session)
        return self

    def commit(self) -> None:
        self._session.commit()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._session.rollback()
        self._session.close()
