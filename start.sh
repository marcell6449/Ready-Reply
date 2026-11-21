#!/usr/bin/env bash
# Ready Reply for Linux and macOS: run ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

find_python() {
  for candidate in python3.13 python3.12 python3.14 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
      "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

if ! PYTHON="$(find_python)"; then
  echo "Ready Reply needs Python 3.12 or newer: https://www.python.org/downloads/"
  exit 1
fi

STAMP=".venv/.installed-$(cksum requirements.txt | cut -d' ' -f1)"
if [ ! -f "$STAMP" ]; then
  echo "Installing Ready Reply (first run only)..."
  "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet --no-index --find-links wheels -r requirements.txt \
    || .venv/bin/python -m pip install --quiet -r requirements.txt
  touch "$STAMP"
fi

[ -f .env ] || cp .env.example .env
exec .venv/bin/python -m readyreply
