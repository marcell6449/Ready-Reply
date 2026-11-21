"""Run Alembic migrations programmatically at startup (F11-06, F11-07)."""

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_latest(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
