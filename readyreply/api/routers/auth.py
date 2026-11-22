"""First-run setup, login and logout (F6)."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from readyreply.api.cookies import set_private_cookie
from readyreply.api.deps import ContainerDep, SessionDep, verify_pre_session_csrf
from readyreply.api.schemas import Credentials, MeOut, SetupStatusOut
from readyreply.api.security import CSRF_COOKIE, SESSION_COOKIE
from readyreply.application.auth import NewSession
from readyreply.config import Settings

router = APIRouter(prefix="/api")
PreSessionCsrf = Annotated[None, Depends(verify_pre_session_csrf)]
UNKNOWN_CLIENT = "unknown"


def _signed_in(response: Response, new: NewSession, settings: Settings) -> MeOut:
    set_private_cookie(response, SESSION_COOKIE, new.token, settings)
    return MeOut(username=new.actor.username, role=new.actor.role, csrf_token=new.csrf_token)


@router.get("/setup/status")
def setup_status(response: Response, container: ContainerDep) -> SetupStatusOut:
    csrf = secrets.token_urlsafe(32)
    set_private_cookie(response, CSRF_COOKIE, csrf, container.settings)
    return SetupStatusOut(
        needs_setup=container.auth.needs_setup.execute(),
        csrf_token=csrf,
        locale=container.settings.locale,
    )


@router.post("/setup")
def setup(
    body: Credentials, response: Response, container: ContainerDep, _: PreSessionCsrf
) -> MeOut:
    new = container.auth.setup.execute(body.username, body.password)
    return _signed_in(response, new, container.settings)


@router.post("/auth/login")
def login(
    body: Credentials,
    request: Request,
    response: Response,
    container: ContainerDep,
    _: PreSessionCsrf,
) -> MeOut:
    client = request.client.host if request.client else UNKNOWN_CLIENT
    new = container.auth.login.execute(body.username, body.password, client)
    return _signed_in(response, new, container.settings)


@router.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, container: ContainerDep, _: SessionDep) -> None:
    container.auth.logout.execute(request.cookies.get(SESSION_COOKIE, ""))
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/auth/me")
def me(session: SessionDep) -> MeOut:
    actor = session.actor
    return MeOut(username=actor.username, role=actor.role, csrf_token=session.csrf_token)
