"""Sample businesses stored as JSON next to this module (F9)."""

import json
from pathlib import Path
from typing import Any

from readyreply.application.demo import DemoBusiness
from readyreply.domain.answers import AnswerDraft
from readyreply.domain.errors import NotFoundError
from readyreply.domain.variables import BUILTIN_KEYS, Variable

DEMO_DIR = Path(__file__).parent
KINDS = ("soda", "salon", "hardware")


def _variables(data: dict[str, Any]) -> tuple[Variable, ...]:
    builtins = tuple(
        Variable(key, "", data["variables"].get(key, ""), True) for key in BUILTIN_KEYS
    )
    custom = tuple(
        Variable(c["key"], c["label"], c["value"], False) for c in data.get("custom", [])
    )
    return builtins + custom


def _answers(data: dict[str, Any]) -> tuple[AnswerDraft, ...]:
    return tuple(
        AnswerDraft(a["title"], a["category"], a["body"], tuple(a.get("tags", ())))
        for a in data["answers"]
    )


class JsonDemoCatalog:
    def kinds(self) -> tuple[str, ...]:
        return KINDS

    def load(self, kind: str) -> DemoBusiness:
        if kind not in KINDS:
            raise NotFoundError("demo.not_found", kind=kind)
        data = json.loads((DEMO_DIR / f"{kind}.json").read_text(encoding="utf-8"))
        synonyms = tuple(tuple(group) for group in data["synonyms"])
        return DemoBusiness(_variables(data), _answers(data), synonyms)
