"""Fill a test business through the public API, the way an owner would type it in.

The three sample businesses (soda, salon, hardware) live in tests/fixtures/businesses and
are test data only; the product itself has no sample data.
"""

import json
from pathlib import Path
from typing import Any, Protocol

from readyreply.domain.variables import BUILTIN_KEYS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "businesses"
KINDS = ("soda", "salon", "hardware")


class Client(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...
    def post(self, url: str, **kwargs: Any) -> Any: ...
    def put(self, url: str, **kwargs: Any) -> Any: ...
    def delete(self, url: str) -> Any: ...


def business(kind: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{kind}.json").read_text(encoding="utf-8"))
    return data


def _variables(data: dict[str, Any]) -> list[dict[str, Any]]:
    builtins = [
        {"key": key, "label": "", "value": data["variables"].get(key, ""), "builtin": True}
        for key in BUILTIN_KEYS
    ]
    custom = [{**item, "builtin": False} for item in data.get("custom", [])]
    return builtins + custom


def seed_business(api: Client, kind: str = "soda") -> int:
    """Replace the library with a sample business. Returns the number of answers."""
    data = business(kind)
    for answer in api.get("/api/answers").json():
        api.delete(f"/api/answers/{answer['id']}")
    assert api.put("/api/variables", json=_variables(data)).status_code == 200
    assert api.put("/api/synonyms", json={"groups": data["synonyms"]}).status_code == 200
    for answer in data["answers"]:
        response = api.post("/api/answers", json={**answer, "tags": answer.get("tags", [])})
        assert response.status_code == 201, response.json()
    return len(data["answers"])
