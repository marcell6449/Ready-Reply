"""Alembic environment. The database URL comes from the caller's config (RR_DATABASE_URL)."""

from alembic import context
from sqlalchemy import Connection

from readyreply.infrastructure.db.engine import make_engine
from readyreply.infrastructure.db.models import Base


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    url = context.config.get_main_option("sqlalchemy.url")
    if url is None:
        raise RuntimeError("sqlalchemy.url is not configured")
    with make_engine(url).connect() as connection:
        _run(connection)


run_online()
