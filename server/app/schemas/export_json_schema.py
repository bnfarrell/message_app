"""Exports every API model as one JSON Schema document for the React client
(web/src/api/schema.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.schemas import (
    analytics,
    auth,
    content,
    conversations,
    dev,
    notifications,
    properties,
    users,
    work_orders,
)

MODULES = (auth, users, conversations, work_orders, content, notifications, analytics,
           properties, dev)
DEFAULT_OUT = str(Path(__file__).resolve().parents[3] / "web" / "src" / "api" / "schema.json")


def _models() -> list[type[BaseModel]]:
    seen: dict[str, type[BaseModel]] = {}
    for mod in MODULES:
        for name, obj in vars(mod).items():
            if (isinstance(obj, type) and issubclass(obj, BaseModel)
                    and obj.__module__ == mod.__name__):
                seen[name] = obj
    return [seen[k] for k in sorted(seen)]


def build() -> dict:
    _, schema = models_json_schema([(m, "serialization") for m in _models()],
                                   ref_template="#/$defs/{model}",
                                   title="Relay API")
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    return schema


def main(out: str | None = None) -> None:
    path = Path(out or DEFAULT_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
