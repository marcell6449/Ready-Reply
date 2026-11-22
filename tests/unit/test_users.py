"""F6-03, F6-12, F6-14 and role permissions (F1-08, F2-08, F5-09, F6-11, F7-04...)."""

import pytest

from readyreply.domain.errors import ConflictError, ForbiddenError, InvalidInputError
from readyreply.domain.permissions import Action, ensure_allowed, is_allowed
from readyreply.domain.users import (
    Role,
    User,
    clean_username,
    ensure_an_admin_remains,
    validate_password,
)


def user(user_id: int, role: Role, active: bool = True) -> User:
    return User(
        id=user_id,
        business_id=1,
        username=f"u{user_id}",
        password_hash="h",
        role=role,
        active=active,
    )


@pytest.mark.parametrize("raw", ["  Ana ", "ANA", "ana"])
def test_username_normalized(raw: str) -> None:
    assert clean_username(raw) == "ana"


@pytest.mark.parametrize("raw", ["", "ab", "a" * 33, "ana maria", "ana<script>"])
def test_invalid_usernames(raw: str) -> None:
    with pytest.raises(InvalidInputError) as error:
        clean_username(raw)
    assert error.value.code == "user.invalid_username"


def test_password_rules() -> None:
    validate_password("12345678")
    for bad, code in [("1234567", "auth.weak_password"), ("x" * 129, "auth.password_too_long")]:
        with pytest.raises(InvalidInputError) as error:
            validate_password(bad)
        assert error.value.code == code


def test_admin_can_do_everything() -> None:
    assert all(is_allowed(Role.ADMIN, action) for action in Action)


@pytest.mark.parametrize(
    "action", [Action.SEARCH, Action.COPY, Action.VIEW_UNANSWERED, Action.RECORD_UNANSWERED]
)
def test_staff_allowed(action: Action) -> None:
    ensure_allowed(Role.STAFF, action)


@pytest.mark.parametrize(
    "action",
    [
        a
        for a in Action
        if a not in {Action.SEARCH, Action.COPY, Action.VIEW_UNANSWERED, Action.RECORD_UNANSWERED}
    ],
)
def test_staff_forbidden(action: Action) -> None:
    with pytest.raises(ForbiddenError) as error:
        ensure_allowed(Role.STAFF, action)
    assert error.value.code == "auth.forbidden"


def test_last_admin_must_remain() -> None:
    ensure_an_admin_remains([user(1, Role.ADMIN), user(2, Role.STAFF)])
    for users in ([user(1, Role.STAFF)], [user(1, Role.ADMIN, active=False), user(2, Role.STAFF)]):
        with pytest.raises(ConflictError) as error:
            ensure_an_admin_remains(users)
        assert error.value.code == "user.last_admin"
