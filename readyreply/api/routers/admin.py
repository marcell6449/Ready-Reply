"""Users, CSV transfer and phone access (F6, F10)."""

from fastapi import APIRouter, Request, Response

from readyreply.api.deps import ActorDep, ContainerDep
from readyreply.api.schemas import (
    ImportReportOut,
    LanOut,
    RejectedRowOut,
    UserIn,
    UserOut,
    UserUpdateIn,
)
from readyreply.application.users import UserChanges
from readyreply.domain.errors import PayloadTooLargeError
from readyreply.domain.permissions import Action

router = APIRouter(prefix="/api")
CSV_FILENAME = "ready-reply-answers.csv"


@router.get("/users")
def list_users(actor: ActorDep, container: ContainerDep) -> list[UserOut]:
    return [UserOut.of(user) for user in container.admin.list_users.execute(actor)]


@router.post("/users", status_code=201)
def create_user(body: UserIn, actor: ActorDep, container: ContainerDep) -> UserOut:
    user = container.admin.create_user.execute(actor, body.username, body.password, body.role)
    return UserOut.of(user)


@router.put("/users/{user_id}")
def update_user(
    user_id: int, body: UserUpdateIn, actor: ActorDep, container: ContainerDep
) -> UserOut:
    changes = UserChanges(body.role, body.active, body.new_password or None)
    return UserOut.of(container.admin.update_user.execute(actor, user_id, changes))


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, actor: ActorDep, container: ContainerDep) -> None:
    container.admin.delete_user.execute(actor, user_id)


@router.get("/csv/export")
def export_csv(actor: ActorDep, container: ContainerDep) -> Response:
    data = container.admin.export_csv.execute(actor)
    disposition = f'attachment; filename="{CSV_FILENAME}"'
    return Response(
        data, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": disposition}
    )


async def _read_limited(request: Request, limit: int) -> bytes:
    """Stop reading as soon as the upload passes the limit (checked before parsing)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError("csv.too_large", limit=limit)
    received = bytearray()
    async for chunk in request.stream():
        received.extend(chunk)
        if len(received) > limit:
            raise PayloadTooLargeError("csv.too_large", limit=limit)
    return bytes(received)


@router.post("/csv/import")
async def import_csv(request: Request, actor: ActorDep, container: ContainerDep) -> ImportReportOut:
    actor.require(Action.TRANSFER_CSV)
    data = await _read_limited(request, container.settings.max_csv_bytes)
    report = container.admin.import_csv.execute(actor, data)
    rejected = [RejectedRowOut(line=row.line, code=row.code) for row in report.rejected]
    return ImportReportOut(imported=report.imported, rejected=rejected)


HTTP_DEFAULT_PORT = 80


@router.get("/system/lan")
def lan_address(request: Request, actor: ActorDep, container: ContainerDep) -> LanOut:
    port = request.url.port or HTTP_DEFAULT_PORT
    return LanOut(url=container.admin.phone_access.url(actor, port))


@router.get("/system/qr.svg")
def lan_qr(request: Request, actor: ActorDep, container: ContainerDep) -> Response:
    svg = container.admin.phone_access.qr(actor, request.url.port or HTTP_DEFAULT_PORT)
    return Response(svg, media_type="image/svg+xml")
