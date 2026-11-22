"""ASGI guard that runs before the app reads a request.

- Rejects Host headers that are not this computer or the local network, which blocks
  DNS-rebinding attacks from web pages the owner visits.
- Reads at most `limit` bytes of the body, so nobody on the Wi-Fi can exhaust memory
  with a huge request, even before logging in.
"""

import ipaddress
import json
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

BAD_HOST_STATUS = 421
TOO_LARGE_STATUS = 413
_METHODS_WITH_BODY = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _hostname(host_header: str) -> str:
    if host_header.startswith("["):
        return host_header[1 : host_header.find("]")]
    return host_header.rsplit(":", 1)[0] if host_header.count(":") == 1 else host_header


def is_local_host(host_header: str, extra_hosts: frozenset[str]) -> bool:
    """IP addresses, localhost, single-label PC names, *.local, and configured names."""
    host = _hostname(host_header).lower().rstrip(".")
    if not host:
        return False
    if host == "localhost" or host in extra_hosts or host.endswith(".local"):
        return True
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return "." not in host
    return True


async def _reject(send: Send, status: int, code: str) -> None:
    body = json.dumps({"code": code, "details": {}}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive: Receive, limit: int) -> bytes | None:
    """The whole body, or None as soon as it passes `limit`."""
    body = bytearray()
    while True:
        message = await receive()
        body.extend(message.get("body", b""))
        if len(body) > limit:
            return None
        if not message.get("more_body", False):
            return bytes(body)


def _replay(body: bytes, receive: Receive) -> Receive:
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if sent:
            return await receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return replay


class RequestGuard:
    def __init__(
        self,
        app: ASGIApp,
        default_limit: int,
        path_limits: Mapping[str, int],
        extra_hosts: frozenset[str],
    ) -> None:
        self._app = app
        self._default_limit = default_limit
        self._path_limits = path_limits
        self._extra_hosts = extra_hosts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        if not is_local_host(headers.get(b"host", b"").decode("latin-1"), self._extra_hosts):
            await _reject(send, BAD_HOST_STATUS, "request.bad_host")
            return
        if scope["method"] in _METHODS_WITH_BODY:
            limit = self._path_limits.get(scope["path"], self._default_limit)
            body = await _read_body(receive, limit)
            if body is None:
                await _reject(send, TOO_LARGE_STATUS, "request.too_large")
                return
            receive = _replay(body, receive)
        await self._app(scope, receive, send)
