"""Repositories for users and sessions."""

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session as OrmSession

from readyreply.domain.errors import NotFoundError
from readyreply.domain.sessions import Session
from readyreply.domain.users import Role, User
from readyreply.infrastructure.db.models import SessionRow, UserRow


def _to_user(row: UserRow) -> User:
    return User(
        row.id, row.business_id, row.username, row.password_hash, Role(row.role), row.active
    )


class SqlUserRepository:
    def __init__(self, session: OrmSession) -> None:
        self._session = session

    def any_exists(self) -> bool:
        return bool(self._session.scalar(select(exists().select_from(UserRow))))

    def _row(self, business_id: int, user_id: int) -> UserRow:
        row = self._session.get(UserRow, user_id)
        if row is None or row.business_id != business_id:
            raise NotFoundError("user.not_found", id=user_id)
        return row

    def get(self, business_id: int, user_id: int) -> User:
        return _to_user(self._row(business_id, user_id))

    def find_by_username(self, business_id: int, username: str) -> User | None:
        query = select(UserRow).where(
            UserRow.business_id == business_id, UserRow.username == username
        )
        row = self._session.scalar(query)
        return _to_user(row) if row else None

    def list_all(self, business_id: int) -> list[User]:
        query = select(UserRow).where(UserRow.business_id == business_id).order_by(UserRow.username)
        return [_to_user(row) for row in self._session.scalars(query)]

    def add(self, user: User) -> User:
        row = UserRow(
            business_id=user.business_id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
            active=user.active,
        )
        self._session.add(row)
        self._session.flush()
        return _to_user(row)

    def update(self, user: User) -> None:
        if user.id is None:
            raise NotFoundError("user.not_found")
        row = self._row(user.business_id, user.id)
        row.password_hash = user.password_hash
        row.role = user.role.value
        row.active = user.active
        self._session.flush()

    def delete(self, business_id: int, user_id: int) -> None:
        self._session.delete(self._row(business_id, user_id))
        self._session.flush()


def _to_session(row: SessionRow) -> Session:
    return Session(row.token_hash, row.user_id, row.business_id, row.csrf_token, row.expires_at)


class SqlSessionRepository:
    def __init__(self, session: OrmSession) -> None:
        self._session = session

    def add(self, session: Session) -> None:
        self._session.add(
            SessionRow(
                token_hash=session.token_hash,
                user_id=session.user_id,
                business_id=session.business_id,
                csrf_token=session.csrf_token,
                expires_at=session.expires_at,
            )
        )
        self._session.flush()

    def get(self, token_hash: str) -> Session | None:
        row = self._session.get(SessionRow, token_hash)
        return _to_session(row) if row else None

    def update(self, session: Session) -> None:
        row = self._session.get(SessionRow, session.token_hash)
        if row is not None:
            row.expires_at = session.expires_at
            self._session.flush()

    def delete(self, token_hash: str) -> None:
        self._session.execute(delete(SessionRow).where(SessionRow.token_hash == token_hash))

    def delete_for_user(self, user_id: int) -> None:
        self._session.execute(delete(SessionRow).where(SessionRow.user_id == user_id))
