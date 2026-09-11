### Task 23: JSON Schema export for the frontend

**Files:**
- Create: `server/app/schemas/export_json_schema.py`, `server/tests/test_schema_export.py`, `web/src/api/schema.json` (generated)

**Interfaces:**
- Produces: `export_json_schema.build() -> dict` (one JSON Schema document with every request/response model under `$defs`, keyed by class name); `python -m app.schemas.export_json_schema [out_path]` writes it (default `../web/src/api/schema.json`); the test fails when the committed file is stale. Consumed by the web plan's `npm run gen:types`.

- [ ] **Step 1: Write the failing test**

`server/tests/test_schema_export.py`:
```python
import json
from pathlib import Path

from app.schemas.export_json_schema import DEFAULT_OUT, build


def test_export_contains_the_public_models():
    schema = build()
    defs = schema["$defs"]
    for name in ("SessionOut", "ConversationSummary", "ConversationDetail", "GuestThread", "MessageOut",
                 "WorkOrderOut", "WorkOrderDetail", "WorkOrderPrefill", "QuickReplyOut", "AssetOut", "CategoryOut",
                 "NotificationOut", "Overview", "AgentStats", "StaffUserOut", "DepartmentOut", "SimGuest"):
        assert name in defs, name
    assert defs["GuestThread"]["additionalProperties"] is False
    assert "notes" not in defs["GuestThread"]["properties"]


def test_committed_schema_is_current():
    path = Path(DEFAULT_OUT)
    assert path.exists(), f"run: python -m app.schemas.export_json_schema  (writes {path})"
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed == build(), "web/src/api/schema.json is stale — re-run python -m app.schemas.export_json_schema"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_schema_export.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the exporter**

`app/schemas/export_json_schema.py`:
```python
"""Exports every API model as one JSON Schema document for the React client (web/src/api/schema.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.schemas import analytics, auth, content, conversations, dev, notifications, users, work_orders

MODULES = (auth, users, conversations, work_orders, content, notifications, analytics, dev)
DEFAULT_OUT = str(Path(__file__).resolve().parents[3] / "web" / "src" / "api" / "schema.json")


def _models() -> list[type[BaseModel]]:
    seen: dict[str, type[BaseModel]] = {}
    for mod in MODULES:
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__:
                seen[name] = obj
    return [seen[k] for k in sorted(seen)]


def build() -> dict:
    _, schema = models_json_schema([(m, "serialization") for m in _models()], ref_template="#/$defs/{model}",
                                   title="Concierge API")
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    return schema


def main(out: str | None = None) -> None:
    path = Path(out or DEFAULT_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
```

Serialization mode is used so `datetime` fields export as `format: date-time` strings and aliases are camelCase — exactly what the client receives. Request models (`LoginRequest`, `CreateWorkOrder`, …) are exported in the same pass; their camelCase aliases are what the client sends.

- [ ] **Step 4: Generate, then run the tests**

Run from `server/`: `python -m app.schemas.export_json_schema` → `wrote …/web/src/api/schema.json`.
Run: `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server web/src/api/schema.json
git commit -m "feat(server): export API models as JSON Schema for the web client"
```

---

