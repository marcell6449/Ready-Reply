"""Reads server-side strings (AI prompt, copy suffix, labels) from the single translations file."""

import json
from pathlib import Path

TRANSLATIONS_FILE = (
    Path(__file__).resolve().parent.parent / "web" / "static" / "i18n" / "translations.json"
)


class TranslationTexts:
    def __init__(self, locale: str, path: Path = TRANSLATIONS_FILE) -> None:
        catalog: dict[str, dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
        self._texts = catalog[locale]

    def text(self, key: str) -> str:
        return self._texts[key]
