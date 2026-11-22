"""First-run setup, login, logout and session resolution (F6)."""

import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from readyreply.application.context import Actor
from readyreply.application.ports import (
    BusinessResolver,
    Clock,
    LoginFailureLog,
    PasswordHasher,
    TokenService,
    UnitOfWork,
    UnitOfWorkFactory,
)
from readyreply.domain.errors import (
    ConflictError,
    TooManyAttemptsError,
    UnauthenticatedError,
    persisted_id,
)
from readyreply.domain.sessions import ADDRESS_MAX_FAILURES, Session, is_login_locked
from readyreply.domain.users import Role, User, clean_username, validate_password


@dataclass(frozen=True, slots=True)
class NewSession:
    token: str
    csrf_token: str
    actor: Actor


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    actor: Actor
    csrf_token: str
    renewed_until: datetime | None = None
    """Set when this request extended the session, so the cookie must be renewed too."""


def actor_for(user: User) -> Actor:
    return Actor(persisted_id(user.id), user.business_id, user.role, user.username)


class SessionStarter:
    def __init__(self, tokens: TokenService, clock: Clock, ttl: timedelta) -> None:
        self._tokens = tokens
        self._clock = clock
        self._ttl = ttl

    def start(self, uow: UnitOfWork, user: User) -> NewSession:
        actor = actor_for(user)
        token = self._tokens.new_token()
        csrf_token = self._tokens.new_token()
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


@dataclass(frozen=True, slots=True)
class SetupStatus:
    needs_setup: bool
    csrf_token: str
    """A token for the pre-session double-submit check (login and setup)."""


class GetSetupStatus:
    def __init__(self, uow_factory: UnitOfWorkFactory, tokens: TokenService) -> None:
        self._uow_factory = uow_factory
        self._tokens = tokens

    def execute(self) -> SetupStatus:
        with self._uow_factory() as uow:
            needs_setup = not uow.users.any_exists()
        return SetupStatus(needs_setup, self._tokens.new_token())


class SetupFirstAdmin:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        starter: SessionStarter,
        business: BusinessResolver,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._starter = starter
        self._business = business
        self._lock = threading.Lock()

    def execute(self, username: str, password: str) -> NewSession:
        clean = clean_username(username)
        validate_password(password)
        with self._lock, self._uow_factory() as uow:
            if uow.users.any_exists():
                raise ConflictError("setup.already_done")
            password_hash = self._hasher.hash(password)
            admin = User(None, self._business.current(), clean, password_hash, Role.ADMIN, True)
            new_session = self._starter.start(uow, uow.users.add(admin))
            uow.commit()
            return new_session


@dataclass(frozen=True, slots=True)
class _ThrottleKeys:
    user: str
    address: str


class Login:
    """Same work for every outcome (one hash check), throttled per user and per address."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        hasher: PasswordHasher,
        failures: LoginFailureLog,
        starter: SessionStarter,
        clock: Clock,
        business: BusinessResolver,
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._failures = failures
        self._starter = starter
        self._clock = clock
        self._business = business
        self._decoy_hash = hasher.hash(secrets.token_urlsafe(16))
        self._lock = threading.Lock()

    def execute(self, username: str, password: str, client: str) -> NewSession:
        name = username.strip().casefold()
        keys = _ThrottleKeys(user=f"user:{name}", address=f"address:{client}")
        with self._lock:
            self._ensure_not_locked(keys)
            with self._uow_factory() as uow:
                user = self._authenticate(uow, name, password, keys)
                uow.sessions.delete_expired(self._clock.now())
                new_session = self._starter.start(uow, user)
                uow.commit()
        self._failures.clear(keys.user)
        return new_session

    def _ensure_not_locked(self, keys: _ThrottleKeys) -> None:
        now = self._clock.now()
        user_locked = is_login_locked(self._failures.recent(keys.user), now)
        address_failures = self._failures.recent(keys.address)
        if user_locked or is_login_locked(address_failures, now, ADDRESS_MAX_FAILURES):
            raise TooManyAttemptsError("auth.too_many_attempts")

    def _authenticate(self, uow: UnitOfWork, name: str, password: str, keys: _ThrottleKeys) -> User:
        user = uow.users.find_by_username(self._business.current(), name)
        stored_hash = user.password_hash if user else self._decoy_hash
        password_ok = self._hasher.verify(stored_hash, password)
        if user is not None and user.active and password_ok:
            return user
        now = self._clock.now()
        self._failures.record(keys.user, now)
        self._failures.record(keys.address, now)
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
            renewed_until = self._refresh(uow, session)
            return AuthenticatedSession(actor_for(user), session.csrf_token, renewed_until)

    def _refresh(self, uow: UnitOfWork, session: Session) -> datetime | None:
        refreshed = session.refreshed(self._clock.now(), self._ttl)
        if refreshed is None:
            return None
        uow.sessions.update(refreshed)
        uow.commit()
        return refreshed.expires_at
