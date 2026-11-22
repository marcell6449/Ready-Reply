"""Repository behaviour on a real SQLite database: isolation, cascades, atomic upsert."""

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from readyreply.domain.answers import Answer
from readyreply.domain.errors import NotFoundError
from readyreply.domain.sessions import Session
from readyreply.domain.users import Role, User
from readyreply.domain.variables import Variable
from readyreply.infrastructure.db.engine import make_engine, make_session_factory
from readyreply.infrastructure.db.migrate import upgrade_to_latest
from readyreply.infrastructure.db.unit_of_work import SqlUnitOfWork

NOW = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
MINE, OTHER = 1, 2


Factory = Callable[[], SqlUnitOfWork]


@pytest.fixture
def uow_factory(tmp_path: Path) -> Iterator[Factory]:
    url = f"sqlite:///{tmp_path / 'repo.db'}"
    upgrade_to_latest(url)
    engine = make_engine(url)
    sessions = make_session_factory(engine)

    def factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(sessions)

    with factory() as uow:
        for business_id in (MINE, OTHER):
            uow.businesses.ensure(business_id, "es")
        uow.commit()
    yield factory
    engine.dispose()


def answer(business_id: int, title: str) -> Answer:
    return Answer(None, business_id, title, "", "body", (), NOW, NOW)


def test_every_repository_is_isolated_by_business(uow_factory: Factory) -> None:
    with uow_factory() as uow:
        theirs = uow.answers.add(answer(OTHER, "Ajena"))
        uow.variables.replace_all(OTHER, [Variable("hours", "", "8-5", True)])
        uow.synonyms.replace_all(OTHER, [("a", "b")])
        uow.unanswered.record(OTHER, "parqueo", "parqueo", NOW)
        user = uow.users.add(User(None, OTHER, "otro", "h", Role.ADMIN, True))
        assert theirs.id is not None and user.id is not None
        uow.copies.add(OTHER, theirs.id, user.id, NOW)
        uow.commit()
    with uow_factory() as uow:
        assert uow.answers.list_all(MINE) == []
        assert uow.answers.count(MINE) == 0
        assert uow.answers.title_keys(MINE) == frozenset()
        assert not uow.answers.title_taken(MINE, "ajena", None)
        assert uow.variables.list_all(MINE) == []
        assert uow.synonyms.list_all(MINE) == []
        assert uow.unanswered.list_open(MINE, 10) == []
        assert uow.users.list_all(MINE) == []
        assert uow.users.find_by_username(MINE, "otro") is None
        assert uow.copies.counts(MINE) == {}
        with pytest.raises(NotFoundError):
            uow.answers.get(MINE, theirs.id)
        with pytest.raises(NotFoundError):
            uow.users.get(MINE, user.id)


def test_deleting_an_answer_removes_its_copy_events(uow_factory: Factory) -> None:
    with uow_factory() as uow:
        saved = uow.answers.add(answer(MINE, "A"))
        user = uow.users.add(User(None, MINE, "ana", "h", Role.ADMIN, True))
        uow.copies.add(MINE, saved.id or 0, user.id or 0, NOW)
        uow.commit()
    with uow_factory() as uow:
        uow.answers.delete(MINE, saved.id or 0)
        uow.commit()
    with uow_factory() as uow:
        assert uow.copies.counts(MINE) == {}


def test_deleting_a_user_removes_their_sessions(uow_factory: Factory) -> None:
    with uow_factory() as uow:
        user = uow.users.add(User(None, MINE, "ana", "h", Role.ADMIN, True))
        uow.sessions.add(Session("t", user.id or 0, MINE, "c", NOW))
        uow.commit()
    with uow_factory() as uow:
        uow.users.delete(MINE, user.id or 0)
        uow.commit()
    with uow_factory() as uow:
        assert uow.sessions.get("t") is None


def test_parallel_upserts_count_every_search(uow_factory: Factory) -> None:
    def record() -> None:
        with uow_factory() as uow:
            uow.unanswered.record(MINE, "envios cartago", "envíos a Cartago", NOW)
            uow.commit()

    threads = [threading.Thread(target=record) for _ in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with uow_factory() as uow:
        (question,) = uow.unanswered.list_open(MINE, 10)
    assert question.times_searched == 25


def test_r24_resolved_question_searched_again_starts_from_one(uow_factory: Factory) -> None:
    with uow_factory() as uow:
        for _ in range(7):
            uow.unanswered.record(MINE, "parqueo", "parqueo", NOW)
        saved = uow.answers.add(answer(MINE, "Parqueo"))
        (question,) = uow.unanswered.list_open(MINE, 10)
        uow.unanswered.resolve(MINE, question.id, saved.id or 0)
        uow.commit()
    with uow_factory() as uow:
        uow.unanswered.record(MINE, "parqueo", "parqueo otra vez", NOW)
        uow.commit()
    with uow_factory() as uow:
        (reopened,) = uow.unanswered.list_open(MINE, 10)
    assert (reopened.times_searched, reopened.sample_text) == (1, "parqueo otra vez")
