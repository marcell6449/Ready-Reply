"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from readyreply.api.errors import register_error_handlers
from readyreply.api.routers import activity, admin, auth, content
from readyreply.api.security import install_http_security
from readyreply.config import Settings
from readyreply.container import Container, build_container
from readyreply.infrastructure.db.migrate import upgrade_to_latest

STATIC_DIR = Path(__file__).parent / "web" / "static"


def prepare_database(container: Container) -> None:
    upgrade_to_latest(container.settings.database_url)
    container.bootstrap.execute()


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings or Settings())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        prepare_database(container)
        yield
        container.http_client.close()
        container.engine.dispose()

    app = FastAPI(title="Ready Reply", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.container = container
    register_error_handlers(app)
    install_http_security(app)
    for router in (auth.router, content.router, activity.router, admin.router):
        app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
