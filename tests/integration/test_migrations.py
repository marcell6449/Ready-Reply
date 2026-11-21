"""F11-06, F11-07: Alembic migrations on a new and an existing database."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from readyreply.infrastructure.db.migrate import alembic_config, upgrade_to_latest
from readyreply.infrastructure.db.models import Base


def test_upgrade_from_empty_matches_models(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'new.db'}"
    upgrade_to_latest(url)
    engine = create_engine(url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    assert diff == []
    tables = set(inspect(engine).get_table_names())
    assert {"answers", "variables", "users", "sessions", "copy_events"} <= tables


def test_every_table_has_business_id(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'tenancy.db'}"
    upgrade_to_latest(url)
    inspector = inspect(create_engine(url))
    tenant_tables = set(inspector.get_table_names()) - {"businesses", "alembic_version"}
    for table in tenant_tables:
        assert "business_id" in {c["name"] for c in inspector.get_columns(table)}, table


def test_upgrade_is_repeatable_and_keeps_data(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    upgrade_to_latest(url)
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO businesses (id, locale, content_revision) VALUES (1, 'es', 0)")
        )
    upgrade_to_latest(url)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM businesses")).scalar() == 1


def test_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    config = alembic_config(url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    assert "answers" in inspect(create_engine(url)).get_table_names()
