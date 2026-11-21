"""Build dist/ready-reply-v1.0.0.zip: the app, the start scripts and offline wheels.

Excludes tests, secrets (.env), databases, virtual environments and caches.
Usage: python scripts/build_dist.py
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
NAME = f"ready-reply-v{VERSION}"
STAGE = ROOT / "build" / NAME
ZIP_PATH = ROOT / "dist" / f"{NAME}.zip"
FILES = [
    "start.bat",
    "start.sh",
    "requirements.txt",
    ".env.example",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
]
DOCS = [
    "docs/ARCHITECTURE.md",
    "docs/DESIGN.md",
    "docs/CRITERIA.md",
    "docs/DEMO.md",
    "docs/screenshots",
]
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc", "*.db", "*.db-*", ".env")
# Wheels for Windows (the main target) and Linux; macOS installs from PyPI on first run.
WINDOWS = ("win_amd64",)
LINUX = ("manylinux_2_28_x86_64", "manylinux2014_x86_64")
PLATFORMS = [(WINDOWS, "312"), (WINDOWS, "313"), (LINUX, "312"), (LINUX, "313")]
WINDOWS_ONLY = ["colorama==0.4.6"]  # needed by click on Windows; pip skips it on Linux
FORBIDDEN_PARTS = {".env", "tests", ".venv", "data", "__pycache__"}


def download_wheels(target: Path) -> None:
    for platforms, python in PLATFORMS:
        extra = WINDOWS_ONLY if platforms == WINDOWS else []
        platform_args = [arg for tag in platforms for arg in ("--platform", tag)]
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--quiet",
                "--only-binary=:all:",
                *platform_args,
                "--python-version",
                python,
                "--implementation",
                "cp",
                "-d",
                str(target),
                "-r",
                str(ROOT / "requirements.txt"),
                *extra,
            ],
            check=True,
        )


def stage() -> None:
    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    shutil.copytree(ROOT / "readyreply", STAGE / "readyreply", ignore=IGNORED)
    for name in FILES:
        shutil.copy2(ROOT / name, STAGE / name)
    for doc in DOCS:
        source, target = ROOT / doc, STAGE / doc
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
    download_wheels(STAGE / "wheels")


def check_contents() -> None:
    for path in STAGE.rglob("*"):
        relative = path.relative_to(STAGE)
        if FORBIDDEN_PARTS & set(relative.parts) or path.suffix == ".db":
            raise SystemExit(f"refusing to package {relative}")


def write_zip() -> None:
    ZIP_PATH.parent.mkdir(exist_ok=True)
    ZIP_PATH.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(STAGE.rglob("*")):
            info = zipfile.ZipInfo.from_file(path, Path(NAME) / path.relative_to(STAGE))
            if path.name == "start.sh":
                info.external_attr = 0o100755 << 16
            if path.is_file():
                archive.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)


def main() -> None:
    stage()
    check_contents()
    write_zip()
    size_mb = ZIP_PATH.stat().st_size / 1024 / 1024
    print(f"Built {ZIP_PATH.relative_to(ROOT)} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
