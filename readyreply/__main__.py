"""`python -m readyreply`: start the server, print the addresses and open the browser."""

import logging
import socket
import threading
import webbrowser
from pathlib import Path

import uvicorn

from readyreply.config import PORT_SEARCH_RANGE, Settings
from readyreply.infrastructure.network.lan import lan_ip
from readyreply.main import create_app

BROWSER_DELAY_SECONDS = 1.5


def free_port(host: str, first: int) -> int:
    for port in range(first, first + PORT_SEARCH_RANGE + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit(f"No free port between {first} and {first + PORT_SEARCH_RANGE} on {host}")


def _ensure_data_dir(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        Path(database_url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings()
    _ensure_data_dir(settings.database_url)
    port = free_port(settings.host, settings.port)
    local_url = f"http://127.0.0.1:{port}/"
    print(f"\n  Ready Reply is running.\n  On this computer: {local_url}", flush=True)
    print(f"  On your phone (same Wi-Fi): http://{lan_ip()}:{port}/\n", flush=True)
    if settings.open_browser:
        threading.Timer(BROWSER_DELAY_SECONDS, webbrowser.open, args=(local_url,)).start()
    uvicorn.run(
        create_app(settings), host=settings.host, port=port, log_level="warning", access_log=False
    )


if __name__ == "__main__":
    main()
