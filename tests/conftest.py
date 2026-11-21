"""Shared fixtures: a fresh app on a temporary SQLite database per test."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from readyreply.config import Settings
from readyreply.container import Container
from readyreply.main import create_app

ADMIN = ("admin", "admin-pass-1")
STAFF = ("staff", "staff-pass-1")


class Api:
    """A browser-like client: keeps cookies and sends the CSRF header automatically."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.csrf = ""

    def _pre_session_csrf(self) -> str:
        return str(self.client.get("/api/setup/status").json()["csrf_token"])

    def setup_admin(self, username: str = ADMIN[0], password: str = ADMIN[1]) -> Any:
        csrf = self._pre_session_csrf()
        response = self.client.post(
            "/api/setup",
            json={"username": username, "password": password},
            headers={"x-csrf-token": csrf},
        )
        self.csrf = response.json().get("csrf_token", "")
        return response

    def login(self, username: str, password: str) -> Any:
        csrf = self._pre_session_csrf()
        response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"x-csrf-token": csrf},
        )
        self.csrf = response.json().get("csrf_token", "")
        return response

    def _headers(self) -> dict[str, str]:
        return {"x-csrf-token": self.csrf}

    def get(self, url: str, **kwargs: Any) -> Any:
        return self.client.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self.client.post(url, headers=self._headers() | kwargs.pop("headers", {}), **kwargs)

    def put(self, url: str, **kwargs: Any) -> Any:
        return self.client.put(url, headers=self._headers(), **kwargs)

    def delete(self, url: str) -> Any:
        return self.client.delete(url, headers=self._headers())


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        open_browser=False,
        ai_provider="manual",
        _env_file=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anon(client: TestClient) -> Api:
    return Api(client)


@pytest.fixture
def admin(client: TestClient) -> Api:
    api = Api(client)
    assert api.setup_admin().status_code == 200
    return api


@pytest.fixture
def staff(admin: Api, app: FastAPI) -> Iterator[Api]:
    created = admin.post(
        "/api/users", json={"username": STAFF[0], "password": STAFF[1], "role": "staff"}
    )
    assert created.status_code == 201
    with TestClient(app) as staff_client:
        api = Api(staff_client)
        assert api.login(*STAFF).status_code == 200
        yield api


def container_of(app: FastAPI) -> Container:
    container: Container = app.state.container
    return container


def run_sql(app: FastAPI, sql: str, **params: object) -> list[Any]:
    with container_of(app).engine.begin() as connection:
        result = connection.execute(text(sql), params)
        return list(result) if result.returns_rows else []


def answer_payload(
    title: str = "Horario", body: str = "Abrimos {hours}", **extra: Any
) -> dict[str, Any]:
    return {"title": title, "category": "Información", "body": body, "tags": [], **extra}


def set_variables(api: Api, **values: str) -> Any:
    current = api.get("/api/variables").json()
    for variable in current:
        if variable["key"] in values:
            variable["value"] = values.pop(variable["key"])
    extra = [{"key": k, "label": k, "value": v, "builtin": False} for k, v in values.items()]
    return api.put("/api/variables", json=current + extra)
