"""Watches folders for exported WhatsApp chats and imports each new file by itself."""

import logging
import re
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
CHAT_SUFFIXES = frozenset({".txt", ".zip"})
WHATSAPP_EXPORT_NAME = re.compile(r"whatsapp|^_chat\.txt$", re.IGNORECASE)
MAX_REMEMBERED_FILES = 10_000


class ChatImporter(Protocol):
    def execute(self, data: bytes) -> object: ...


@dataclass(frozen=True, slots=True)
class WatchedFolder:
    path: Path
    whatsapp_names_only: bool
    """Downloads holds many files: there, only take names WhatsApp gives its exports."""


def downloads_folder(setting: str) -> Path | None:
    if not setting:
        return None
    if setting == "auto":
        candidate = Path.home() / "Downloads"
        return candidate if candidate.is_dir() else None
    return Path(setting).expanduser()


class ChatFolderWatcher:
    def __init__(
        self,
        folders: Sequence[WatchedFolder],
        importer: ChatImporter,
        stable_seconds: float,
        interval_seconds: float,
    ) -> None:
        self._folders = list(folders)
        self._importer = importer
        self._stable_seconds = stable_seconds
        self._interval = interval_seconds
        self._done: set[tuple[str, int, int]] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def folders(self) -> list[str]:
        return [str(folder.path) for folder in self._folders]

    @property
    def enabled(self) -> bool:
        return self._interval > 0

    def ensure_folders(self) -> None:
        for folder in self._folders:
            if not folder.whatsapp_names_only:
                folder.path.mkdir(parents=True, exist_ok=True)

    def scan_once(self) -> int:
        imported = 0
        for path, key in self._ready_files():
            try:
                data = path.read_bytes()
            except OSError:
                continue  # still being copied or locked: try again on the next scan
            if self._importer.execute(data) is not None:
                imported += 1
            self._remember(key)
        return imported

    def _ready_files(self) -> Iterator[tuple[Path, tuple[str, int, int]]]:
        now = time.time()
        for folder in self._folders:
            for path in self._chat_files(folder):
                stat = path.stat()
                key = (str(path), stat.st_size, stat.st_mtime_ns)
                if key not in self._done and now - stat.st_mtime >= self._stable_seconds:
                    yield path, key

    @staticmethod
    def _chat_files(folder: WatchedFolder) -> Iterator[Path]:
        if not folder.path.is_dir():
            return
        for path in sorted(folder.path.iterdir()):
            named_ok = not folder.whatsapp_names_only or WHATSAPP_EXPORT_NAME.search(path.name)
            if path.is_file() and path.suffix.lower() in CHAT_SUFFIXES and named_ok:
                yield path

    def _remember(self, key: tuple[str, int, int]) -> None:
        if len(self._done) >= MAX_REMEMBERED_FILES:
            self._done.clear()  # the database still knows every imported file
        self._done.add(key)

    def start(self) -> None:
        if self.enabled and self._thread is None:
            self._thread = threading.Thread(target=self._run, name="chat-watcher", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval + 1)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.scan_once()
            except (OSError, SQLAlchemyError):
                logger.warning("Automatic chat import failed; it will retry", exc_info=True)
