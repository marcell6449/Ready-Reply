"""Domain errors → HTTP responses with a translatable code."""

from collections.abc import Mapping
from types import MappingProxyType

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from readyreply.domain import errors

_STATUS_BY_ERROR = MappingProxyType(
    {
        errors.InvalidInputError: 422,
        errors.NotFoundError: 404,
        errors.ConflictError: 409,
        errors.PayloadTooLargeError: 413,
        errors.UnauthenticatedError: 401,
        errors.ForbiddenError: 403,
        errors.TooManyAttemptsError: 429,
    }
)
INVALID_REQUEST_STATUS = 422


def error_body(code: str, details: Mapping[str, object] | None = None) -> dict[str, object]:
    return {"code": code, "details": dict(details or {})}


def status_for(error: errors.DomainError) -> int:
    return _STATUS_BY_ERROR[type(error)]


async def _domain_error(_request: Request, error: Exception) -> JSONResponse:
    if not isinstance(error, errors.DomainError):
        raise error
    safe_details = {k: v for k, v in error.details.items() if isinstance(v, str | int)}
    return JSONResponse(error_body(error.code, safe_details), status_code=status_for(error))


async def _validation_error(_request: Request, _error: Exception) -> JSONResponse:
    return JSONResponse(error_body("request.invalid"), status_code=INVALID_REQUEST_STATUS)


def register_error_handlers(app: FastAPI) -> None:
    for error_type in _STATUS_BY_ERROR:
        app.add_exception_handler(error_type, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
