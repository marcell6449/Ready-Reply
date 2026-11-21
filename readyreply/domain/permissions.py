"""What each role may do."""

from enum import StrEnum
from types import MappingProxyType

from readyreply.domain.errors import ForbiddenError
from readyreply.domain.users import Role


class Action(StrEnum):
    SEARCH = "search"
    COPY = "copy"
    VIEW_UNANSWERED = "view_unanswered"
    RECORD_UNANSWERED = "record_unanswered"
    MANAGE_UNANSWERED = "manage_unanswered"
    MANAGE_ANSWERS = "manage_answers"
    MANAGE_VARIABLES = "manage_variables"
    MANAGE_SYNONYMS = "manage_synonyms"
    MANAGE_USERS = "manage_users"
    VIEW_STATS = "view_stats"
    TRANSFER_CSV = "transfer_csv"
    LOAD_DEMO = "load_demo"
    USE_AI = "use_ai"
    VIEW_SYSTEM = "view_system"


_STAFF_ACTIONS = frozenset(
    {Action.SEARCH, Action.COPY, Action.VIEW_UNANSWERED, Action.RECORD_UNANSWERED}
)
_PERMISSIONS = MappingProxyType({Role.ADMIN: frozenset(Action), Role.STAFF: _STAFF_ACTIONS})


def is_allowed(role: Role, action: Action) -> bool:
    return action in _PERMISSIONS[role]


def ensure_allowed(role: Role, action: Action) -> None:
    if not is_allowed(role, action):
        raise ForbiddenError("auth.forbidden", action=action.value)
