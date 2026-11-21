"""Who is calling a use case."""

from dataclasses import dataclass

from readyreply.domain.permissions import Action, ensure_allowed
from readyreply.domain.users import Role


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: int
    business_id: int
    role: Role
    username: str

    def require(self, action: Action) -> None:
        ensure_allowed(self.role, action)
