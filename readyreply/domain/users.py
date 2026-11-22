"""Users, roles and account rules."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from readyreply.domain.errors import ConflictError, InvalidInputError

PASSWORD_MIN = 8
PASSWORD_MAX = 128
_USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")


class Role(StrEnum):
    ADMIN = "admin"
    STAFF = "staff"


@dataclass(frozen=True, slots=True)
class User:
    id: int | None
    business_id: int
    username: str
    password_hash: str
    role: Role
    active: bool


def clean_username(raw: str) -> str:
    username = raw.strip().casefold()
    if not _USERNAME.match(username):
        raise InvalidInputError("user.invalid_username")
    return username


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise InvalidInputError("auth.weak_password", minimum=PASSWORD_MIN)
    if len(password) > PASSWORD_MAX:
        raise InvalidInputError("auth.password_too_long", limit=PASSWORD_MAX)


def ensure_an_admin_remains(users_after_change: Iterable[User]) -> None:
    if not any(user.role is Role.ADMIN and user.active for user in users_after_change):
        raise ConflictError("user.last_admin")
