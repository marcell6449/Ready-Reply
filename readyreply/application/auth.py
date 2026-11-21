"""First-run setup, login, logout and session resolution (F6)."""

import secrets
import threading
from dataclasses import dataclass
from datetime import timedelta

from readyreply.application.context import Actor
from readyreply.application.ports import (
    Clock,
    LoginFailureLog,
    PasswordHasher,
    TokenService,
    UnitOfWork,
    UnitOfWorkFactory,
)
from readyreply.domain.errors import ConflictError, TooManyAttemptsError, UnauthenticatedError
from readyreply.domain.sessions import Session, is_login_locked
from readyreply.domain.users import Role, User, clean_username, validate_password

BUSINESS_ID = 1


@dataclass(frozen=True, slots=True)
class NewSession:
    token: str
    csrf_token: str
    actor: Actor


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    actor: Actor
    csrf_token: str


def actor_for(user: User) -> Actor:
    if user.id is None:
        raise UnauthenticatedError("auth.required")
    return Actor(user.id, user.business_id, user.role, user.username)


class SessionStarter:
    def __init__(self, tokens: TokenService, clock: Clock, ttl: timedelta) -> None:
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    def start(self, uow: UnitOfWork, user: User) -> NewSession:
        actor = actor_for(user)
        token = self._tokens.new_token()
        csrf_token = secrets.token_urlsafe(32)
        expires_at = self._clock.now() + self._ttl
        session = Session(
            token_hash=self._tokens.hash_token(token),
            user_id=actor.user_id,
            business_id=actor.business_id,
            csrf_token=csrf_token,
            expires_at=expires_at,
        )
        uow.sessions.add(session)
        return NewSession(token, csrf_token, actor)


class NeedsSetup:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self) -> bool:
        with self._uow_factory() as uow:
            return not uow.users.any_exists()


class SetupFirstAdmin:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher, starter: SessionStarter
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._starter = starter
        self._lock = threading.Lock()

    def execute(self, username: str, password: str) -> NewSession:
        clean = clean_username(username)
        validate_password(password)
        with self._lock, self._uow_factory() as uow:
            if uow.users.any_exists():
                raise ConflictError("setup.already_done")
            admin = User(None, BUSINESS_ID, clean, self._hasher.hash(password), Role.ADMIN, True)
            new_session = self._starter.start(uow, uow.users.add(admin))
            uow.commit()
            return new_session


class Login:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        failures: LoginFailureLog,
        starter: SessionStarter,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._failures = failures
        self._starter = starter
        self._clock = clock

    def execute(self, username: str, password: str, client: str) -> NewSession:
        throttle_key = f"{client}:{username.strip().casefold()}"
        if is_login_locked(self._failures.recent(throttle_key), self._clock.now()):
            raise TooManyAttemptsError("auth.too_many_attempts")
        with self._uow_factory() as uow:
            user = self._authenticate(uow, username, password, throttle_key)
            new_session = self._starter.start(uow, user)
            uow.commit()
        self._failures.clear(throttle_key)
        return new_session

    def _authenticate(self, uow: UnitOfWork, username: str, password: str, key: str) -> User:
        user = uow.users.find_by_username(BUSINESS_ID, username.strip().casefold())
        if user is None:
            self._hasher.verify(self._hasher.hash("timing-equalizer"), password)
        elif user.active and self._hasher.verify(user.password_hash, password):
            return user
        self._failures.record(key, self._clock.now())
        raise UnauthenticatedError("auth.invalid_credentials")


class Logout:
    def __init__(self, uow_factory: UnitOfWorkFactory, tokens: TokenService) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens

    def execute(self, token: str) -> None:
        with self._uow_factory() as uow:
            uow.sessions.delete(self._tokens.hash_token(token))
            uow.commit()


class ResolveSession:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, tokens: TokenService, clock: Clock, ttl: timedelta
    ) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    def execute(self, token: str) -> AuthenticatedSession:
        now = self._clock.now()
        with self._uow_factory() as uow:
            session = uow.sessions.get(self._tokens.hash_token(token))
            if session is None:
                raise UnauthenticatedError("auth.required")
            if session.is_expired(now):
                uow.sessions.delete(session.token_hash)
                uow.commit()
                raise UnauthenticatedError("auth.session_expired")
            user = uow.users.get(session.business_id, session.user_id)
            if not user.active:
                raise UnauthenticatedError("auth.required")
            self._refresh(uow, session)
            return AuthenticatedSession(actor_for(user), session.csrf_token)

    def _refresh(self, uow: UnitOfWork, session: Session) -> None:
        refreshed = session.refreshed(self._clock.now(), self._ttl)
        if refreshed is not None:
            uow.sessions.update(refreshed)
            uow.commit()
