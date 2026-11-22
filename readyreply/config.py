"""All configuration comes from RR_* environment variables or the .env file (12-factor)."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PORT = 8000
PORT_SEARCH_RANGE = 10
MEGABYTE = 1024 * 1024
LOCALES = ("es", "en")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RR_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/readyreply.db"
    host: str = "0.0.0.0"  # noqa: S104 - phones on the same Wi-Fi must reach the app
    port: int = Field(default=DEFAULT_PORT, ge=1, le=65535)
    locale: Literal["es", "en"] = "es"
    session_hours: int = Field(default=12, ge=1, le=24 * 30)
    max_csv_bytes: int = Field(default=MEGABYTE, ge=1)
    max_chat_bytes: int = Field(default=20 * MEGABYTE, ge=1)
    cookie_secure: bool = False
    allowed_hosts: str = ""
    """Extra host names (comma separated) allowed in the Host header, e.g. a DNS name."""
    max_request_bytes: int = Field(default=512 * 1024, ge=1024)
    open_browser: bool = True

    ai_provider: str = "ollama"
    """A name registered in infrastructure/ai/registry.py."""
    ai_model: str = "gemma3:4b"
    ai_base_url: str = "http://127.0.0.1:11434"
    ai_chat_url: str = ""
    ai_api_key: SecretStr | None = None
    ai_timeout_seconds: float = Field(default=60, gt=0, le=600)
