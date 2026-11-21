"""HTTP hardening: security headers, same-origin check, CSRF, privacy-safe access log."""

import hmac
import logging
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from readyreply.api.errors import error_body

SESSION_COOKIE = "rr_session"
CSRF_COOKIE = "rr_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
FORBIDDEN = 403
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store",
}

access_log = logging.getLogger("readyreply.access")
Handler = Callable[[Request], Awaitable[Response]]


def tokens_match(expected: str | None, received: str | None) -> bool:
    if not expected or not received:
        return False
    return hmac.compare_digest(expected.encode(), received.encode())


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin is None:
        return True
    return urlsplit(origin).netloc == request.headers.get("host", "")


async def same_origin_guard(request: Request, call_next: Handler) -> Response:
    if request.method not in SAFE_METHODS and not _origin_allowed(request):
        return JSONResponse(error_body("auth.csrf_failed"), status_code=FORBIDDEN)
    return await call_next(request)


async def security_headers(request: Request, call_next: Handler) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


async def privacy_safe_access_log(request: Request, call_next: Handler) -> Response:
    """Logs method, path (no query string), status and duration. Never bodies or cookies."""
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    access_log.info(
        "%s %s %s %.0fms", request.method, request.url.path, response.status_code, elapsed_ms
    )
    return response


def install_http_security(app: FastAPI) -> None:
    app.middleware("http")(same_origin_guard)
    app.middleware("http")(security_headers)
    app.middleware("http")(privacy_safe_access_log)
