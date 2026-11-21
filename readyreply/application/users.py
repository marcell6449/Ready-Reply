"""User management by the administrator (F6)."""

from dataclasses import dataclass, replace

from readyreply.application.context import Actor
from readyreply.application.ports import PasswordHasher, UnitOfWork, UnitOfWorkFactory
from readyreply.domain.errors import ConflictError
from readyreply.domain.permissions import Action
from readyreply.domain.users import (
    Role,
    User,
    clean_username,
    ensure_an_admin_remains,
    validate_password,
)


@dataclass(frozen=True, slots=True)
class UserChanges:
    role: Role
    active: bool
    new_password: str | None


def _others_plus(
    uow: UnitOfWork, business_id: int, changed: User | None, user_id: int
) -> list[User]:
    others = [user for user in uow.users.list_all(business_id) if user.id != user_id]
    return [*others, changed] if changed else others


class ListUsers:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor) -> list[User]:
        actor.require(Action.MANAGE_USERS)
        with self._uow_factory() as uow:
            return uow.users.list_all(actor.business_id)


class CreateUser:
    def __init__(self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher

    def execute(self, actor: Actor, username: str, password: str, role: Role) -> User:
        actor.require(Action.MANAGE_USERS)
        clean = clean_username(username)
        validate_password(password)
        with self._uow_factory() as uow:
            if uow.users.find_by_username(actor.business_id, clean):
                raise ConflictError("user.username_taken")
            new = User(None, actor.business_id, clean, self._hasher.hash(password), role, True)
            user = uow.users.add(new)
            uow.commit()
            return user


class UpdateUser:
    def __init__(self, uow_factory: UnitOfWorkFactory, hasher: PasswordHasher) -> None:
        self._uow_factory = uow_factory
        self._hasher = hasher

    def execute(self, actor: Actor, user_id: int, changes: UserChanges) -> User:
        actor.require(Action.MANAGE_USERS)
        if changes.new_password is not None:
            validate_password(changes.new_password)
        with self._uow_factory() as uow:
            current = uow.users.get(actor.business_id, user_id)
            updated = replace(current, role=changes.role, active=changes.active)
            if changes.new_password is not None:
                updated = replace(updated, password_hash=self._hasher.hash(changes.new_password))
            ensure_an_admin_remains(_others_plus(uow, actor.business_id, updated, user_id))
            uow.users.update(updated)
            if not updated.active or changes.new_password is not None:
                uow.sessions.delete_for_user(user_id)
            uow.commit()
            return updated


class DeleteUser:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, actor: Actor, user_id: int) -> None:
        actor.require(Action.MANAGE_USERS)
        with self._uow_factory() as uow:
            uow.users.get(actor.business_id, user_id)
            ensure_an_admin_remains(_others_plus(uow, actor.business_id, None, user_id))
            uow.users.delete(actor.business_id, user_id)
            uow.commit()
