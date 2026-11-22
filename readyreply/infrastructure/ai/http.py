"""HTTP helpers shared by the AI providers: one total deadline and one error type."""

import json
import time

import httpx

from readyreply.application.ports import ProviderUnavailableError


def post_json(
    client: httpx.Client,
    url: str,
    payload: object,
    deadline_seconds: float,
    headers: dict[str, str] | None = None,
) -> object:
    """POST and parse JSON, giving up when the whole reply takes longer than the deadline."""
    deadline = time.monotonic() + deadline_seconds
    try:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if time.monotonic() > deadline:
                    raise ProviderUnavailableError("deadline exceeded")
        return json.loads(body)
    except (httpx.HTTPError, ValueError) as error:
        raise ProviderUnavailableError(type(error).__name__) from error


def require_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderUnavailableError("empty reply")
    return value
