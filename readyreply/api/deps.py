"""Request dependencies: the container, the current user and CSRF verification."""

from typing import Annotated

from fastapi import Depends, Request

from readyreply.api.security import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SAFE_METHODS,
    SESSION_COOKIE,
    tokens_match,
)
from readyreply.application.auth import AuthenticatedSession
from readyreply.application.context import Actor
from readyreply.container import Container
from readyreply.domain.errors import ForbiddenError, UnauthenticatedError


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def current_session(request: Request, container: ContainerDep) -> AuthenticatedSession:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise UnauthenticatedError("auth.required")
    session = container.auth.resolve.execute(token)
    if request.method not in SAFE_METHODS and not tokens_match(
        session.csrf_token, request.headers.get(CSRF_HEADER)
    ):
        raise ForbiddenError("auth.csrf_failed")
    return session


SessionDep = Annotated[AuthenticatedSession, Depends(current_session)]


def current_actor(session: SessionDep) -> Actor:
    return session.actor


ActorDep = Annotated[Actor, Depends(current_actor)]


def verify_pre_session_csrf(request: Request) -> None:
    """Double-submit check for login and setup, which happen before a session exists."""
    if not tokens_match(request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
        raise ForbiddenError("auth.csrf_failed")
