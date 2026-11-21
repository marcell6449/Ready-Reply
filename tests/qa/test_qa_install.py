"""QA: the release zip, ./start.sh in a clean folder, ports, restarts and the README backup."""

import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from tests.qa.conftest import ADMIN_PASSWORD, HttpUser, free_port

pytestmark = [pytest.mark.promise_p7]
ROOT = Path(__file__).resolve().parents[2]
ZIP = ROOT / "dist" / "ready-reply-v1.0.0.zip"
PREFIX = "ready-reply-v1.0.0/"


def clean_env(port: int) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("RR_", "VIRTUAL_ENV"))}
    venv_bin = str(ROOT / ".venv" / "bin")
    env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if p != venv_bin)
    env.update({"RR_OPEN_BROWSER": "false", "RR_PORT": str(port)})
    return env


@dataclass
class Running:
    process: subprocess.Popen[bytes]
    url: str
    started_in: float

    def stop(self, sig: int = signal.SIGTERM) -> None:
        if self.process.poll() is None:
            os.killpg(self.process.pid, sig)
            self.process.wait(timeout=30)


def start(folder: Path, port: int, timeout: float = 240) -> Running:
    log = (folder / f"start-{port}.log").open("wb")
    began = time.monotonic()
    process = subprocess.Popen(
        ["./start.sh"],
        cwd=folder,
        env=clean_env(port),
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = began + timeout
    while time.monotonic() < deadline:
        for candidate in range(port, port + 11):
            try:
                if httpx.get(f"http://127.0.0.1:{candidate}/", timeout=1).status_code == 200:
                    url = f"http://127.0.0.1:{candidate}"
                    return Running(process, url, time.monotonic() - began)
            except httpx.HTTPError:
                continue
        if process.poll() is not None:
            break
        time.sleep(0.2)
    os.killpg(process.pid, signal.SIGKILL)
    raise AssertionError((folder / f"start-{port}.log").read_text(errors="replace"))


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    if not ZIP.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_dist.py")], check=True)
    target = tmp_path_factory.mktemp("qa-install")
    with zipfile.ZipFile(ZIP) as archive:
        archive.extractall(target)
    folder = target / "ready-reply-v1.0.0"
    for info in zipfile.ZipFile(ZIP).infolist():  # zipfile does not restore the exec bit
        mode = (info.external_attr >> 16) & 0o777
        if mode:
            (target / info.filename).chmod(mode)
    yield folder


def test_release_zip_matches_the_source_and_build_script(installed: Path) -> None:
    with zipfile.ZipFile(ZIP) as archive:
        names = set(archive.namelist())
        stale = [
            name
            for name in names
            if name.startswith(PREFIX + "readyreply/")
            and not name.endswith("/")
            and (ROOT / name.removeprefix(PREFIX)).read_bytes() != archive.read(name)
        ]
    expected_docs = ["docs/ARCHITECTURE.md", "docs/DESIGN.md", "docs/CRITERIA.md", "docs/DEMO.md"]
    missing = [doc for doc in expected_docs if PREFIX + doc not in names]
    assert stale == [] and missing == [], f"stale: {stale}; missing: {missing}"


def test_zip_has_no_secrets_tests_or_data(installed: Path) -> None:
    with zipfile.ZipFile(ZIP) as archive:
        names = archive.namelist()
    for forbidden in ("/.env", "/tests/", "/.venv/", "/data/", "__pycache__", ".db"):
        assert not [n for n in names if forbidden in n and not n.endswith(".env.example")]
    assert (installed / "start.sh").stat().st_mode & 0o111


def test_start_sh_installs_offline_migrates_and_restarts_fast(installed: Path) -> None:
    """F11-01, F11-02, F11-06 and P7(d): clean folder, bundled wheels, first-run setup."""
    first = start(installed, free_port())
    try:
        assert (installed / ".venv").is_dir()
        assert (installed / ".env").is_file()
        assert (installed / "data" / "readyreply.db").is_file()
        status = httpx.get(f"{first.url}/api/setup/status").json()
        assert status["needs_setup"] is True
        admin = HttpUser(first.url)
        assert admin.setup().status_code == 200
        assert admin.post("/api/demo/soda", json={}).status_code == 200
        results = admin.get("/api/search", params={"q": "a que ora abren"}).json()
        assert results[0]["answer"]["title"] == "Horario"
    finally:
        first.stop()
    log = (installed / f"start-{first.url.rsplit(':', 1)[1]}.log").read_text()
    assert "Installing Ready Reply" in log
    second = start(installed, free_port(), timeout=30)
    try:
        assert second.started_in < 10
        admin = HttpUser(second.url)
        assert admin.login("admin", ADMIN_PASSWORD).status_code == 200
        assert len(admin.get("/api/answers").json()) >= 12
    finally:
        second.stop()


def test_busy_port_moves_to_the_next_one(installed: Path) -> None:
    """F11-03."""
    port = free_port()
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", port))
        blocker.listen()
        running = start(installed, port, timeout=60)
        try:
            assert running.url != f"http://127.0.0.1:{port}"
            log = (installed / f"start-{port}.log").read_text()
            assert running.url in log
        finally:
            running.stop()


def test_readme_backup_after_closing_the_window_keeps_all_data(
    installed: Path, tmp_path: Path
) -> None:
    """README: "close the window to stop the program" and "to back up, copy
    data/readyreply.db while the program is closed". Closing the terminal sends SIGHUP."""
    running = start(installed, free_port(), timeout=60)
    try:
        admin = HttpUser(running.url)
        status = admin.get("/api/setup/status").json()
        response = admin.setup() if status["needs_setup"] else admin.login("admin", ADMIN_PASSWORD)
        assert response.status_code == 200
        title = f"Respaldo {time.time_ns()}"
        body = {"title": title, "category": "", "body": "x", "tags": []}
        assert admin.post("/api/answers", json=body).status_code == 201
    finally:
        running.stop(signal.SIGHUP)
    backup = tmp_path / "backup.db"
    shutil.copy(installed / "data" / "readyreply.db", backup)
    with sqlite3.connect(backup) as connection:
        found = connection.execute("SELECT count(*) FROM answers WHERE title = ?", (title,))
        assert found.fetchone()[0] == 1, "the copied readyreply.db lost the last answer"


def test_env_example_lists_every_setting() -> None:
    """README: "every option is an RR_* environment variable. See .env.example"."""
    from readyreply.config import Settings

    documented = (ROOT / ".env.example").read_text(encoding="utf-8")
    missing = [
        f"RR_{name.upper()}"
        for name in Settings.model_fields
        if f"RR_{name.upper()}=" not in documented
    ]
    assert missing == []
