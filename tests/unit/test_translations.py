"""F11-09: one translations file; Spanish and English stay in sync with the code."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "readyreply"
CATALOG = json.loads((ROOT / "web/static/i18n/translations.json").read_text(encoding="utf-8"))
JS = "\n".join(p.read_text() for p in (ROOT / "web/static/js").rglob("*.js"))
PY = "\n".join(p.read_text() for p in ROOT.rglob("*.py"))


def test_same_keys_in_every_language() -> None:
    assert set(CATALOG) == {"es", "en"}
    assert set(CATALOG["es"]) == set(CATALOG["en"])


def test_no_empty_texts() -> None:
    assert [k for loc in CATALOG.values() for k, v in loc.items() if not v.strip()] == []


def test_every_literal_key_used_in_js_exists() -> None:
    used = set(re.findall(r'\bt\("([a-z_.]+)"', JS))
    assert used - set(CATALOG["es"]) == set()


def test_dynamic_keys_exist() -> None:
    routes = re.findall(r"^\s+(\w+): \{ render:", JS, re.MULTILINE)
    expected = {f"nav.{name}" for name in routes}
    expected |= {"role.admin", "role.staff", "chats.result", "auto.imported"}
    expected |= {f"var.{key}" for key in ("name", "hours", "address", "sinpe", "phone", "prices")}
    expected |= {"setup.title", "setup.intro", "setup.submit", "login.title", "login.intro"}
    expected |= {"login.submit", "ai.unavailable"}
    assert expected - set(CATALOG["es"]) == set()


def test_every_error_code_has_a_message() -> None:
    codes = set(re.findall(r'Error\(\s*"([a-z_]+\.[a-z_]+)"', PY))
    for field in ("title", "body"):
        codes |= {f"answer.{field}_required", f"answer.{field}_too_long"}
    codes |= {"request.invalid", "network.offline"}
    missing = {code for code in codes if f"error.{code}" not in CATALOG["es"]}
    assert missing == set()


def test_no_unsafe_html_sinks_in_frontend() -> None:
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in JS, sink
