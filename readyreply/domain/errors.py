"""Business errors. Each carries a stable `code` that the frontend translates."""


class DomainError(Exception):
    def __init__(self, code: str, **details: object) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


class InvalidInputError(DomainError):
    """The request breaks a business rule about its content."""


class NotFoundError(DomainError):
    """The requested item does not exist for this business."""


class ConflictError(DomainError):
    """The request conflicts with the current state."""


class PayloadTooLargeError(DomainError):
    """An upload exceeds the configured size."""


class UnauthenticatedError(DomainError):
    """No valid session, or wrong credentials."""


class ForbiddenError(DomainError):
    """The user's role does not allow the action."""


class TooManyAttemptsError(DomainError):
    """Too many failed logins in a short time."""


class NotPersistedError(RuntimeError):
    """An entity that should come from the database has no id: a programming error."""


def persisted_id(entity_id: int | None) -> int:
    if entity_id is None:
        raise NotPersistedError("entity has no id")
    return entity_id
