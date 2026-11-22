"""Cookie settings shared by login and session renewal."""

from fastapi import Response

from readyreply.config import Settings

SECONDS_PER_HOUR = 3600


def set_private_cookie(response: Response, name: str, value: str, settings: Settings) -> None:
    response.set_cookie(
        name,
        value,
        max_age=settings.session_hours * SECONDS_PER_HOUR,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
        path="/",
    )
