"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from readyreply.api.errors import register_error_handlers
from readyreply.api.request_guard import RequestGuard
from readyreply.api.routers import activity, admin, auth, content, whatsapp
from readyreply.api.security import install_http_security
from readyreply.config import Settings
from readyreply.container import Container, build_container
from readyreply.infrastructure.db.migrate import upgrade_to_latest

STATIC_DIR = Path(__file__).parent / "web" / "static"


def prepare_database(container: Container) -> None:
    upgrade_to_latest(container.settings.database_url)
    container.bootstrap.execute()


CSV_IMPORT_PATH = "/api/csv/import"
CHAT_ANALYZE_PATH = "/api/whatsapp/analyze"
BASE64_FACTOR = 2  # base64 text is 4/3 of the file size; 2 leaves room for JSON
CSV_BODY_FACTOR = 2  # the CSV route reports its own exact limit; the guard stops abuse


def _install_request_guard(app: FastAPI, settings: Settings) -> None:
    extra_hosts = frozenset(
        h.strip().lower() for h in settings.allowed_hosts.split(",") if h.strip()
    )
    app.add_middleware(
        RequestGuard,
        default_limit=settings.max_request_bytes,
        path_limits={
            CSV_IMPORT_PATH: settings.max_csv_bytes * CSV_BODY_FACTOR,
            CHAT_ANALYZE_PATH: settings.max_chat_bytes * BASE64_FACTOR,
        },
        extra_hosts=extra_hosts,
    )


def _serve_frontend(app: FastAPI) -> None:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")


def create_app(settings: Settings | None = None) -> FastAPI:
    container = build_container(settings or Settings())

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        prepare_database(container)
        container.chat_watcher.ensure_folders()
        container.chat_watcher.start()
        yield
        container.chat_watcher.stop()
        container.http_client.close()
        container.engine.dispose()

    app = FastAPI(title="Ready Reply", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.container = container
    register_error_handlers(app)
    install_http_security(app)
    _install_request_guard(app, container.settings)
    for router in (auth.router, content.router, activity.router, admin.router, whatsapp.router):
        app.include_router(router)
    _serve_frontend(app)
    return app
