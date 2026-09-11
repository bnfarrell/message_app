# Task 23 Report: JSON Schema export for the frontend

## What I implemented

Followed the brief verbatim, in TDD order:

1. `server/tests/test_schema_export.py` — the two tests from the brief, unchanged:
   - `test_export_contains_the_public_models` — asserts 17 named public models are present in `$defs`, and that `GuestThread` is `additionalProperties: false` with no `notes` field (no leak of internal notes to the guest-facing thread view).
   - `test_committed_schema_is_current` — loads the committed `web/src/api/schema.json` and asserts it equals a fresh `build()`.

2. `server/app/schemas/export_json_schema.py` — the exporter from the brief, unchanged:
   - `MODULES = (auth, users, conversations, work_orders, content, notifications, analytics, dev)`
   - `_models()` walks each module's `vars()`, keeps only `BaseModel` subclasses whose `__module__` is that module (so re-exports/imports from other modules aren't double-counted), and returns them sorted by class name — deterministic model ordering regardless of dict/import order.
   - `build()` calls `pydantic.json_schema.models_json_schema` with `(model, "serialization")` mode for every model, `ref_template="#/$defs/{model}"`, title `"Concierge API"`, and sets `$schema` if absent.
   - `main()` writes `json.dumps(build(), indent=2, sort_keys=True) + "\n"` to `DEFAULT_OUT` (`web/src/api/schema.json`, resolved via `Path(__file__).resolve().parents[3]`), creating parent dirs.

   I did not add `common` or `enums` to `MODULES`. Checked both explicitly:
   - `app/schemas/common.py` contains only `CamelModel`, the abstract base every wire model inherits — not itself a request/response wire model, so it has no reason to appear as its own top-level `$defs` entry.
   - `app/schemas/enums.py` contains only `StrEnum` subclasses, no `BaseModel` subclasses — nothing for `models_json_schema` to take directly. They are pulled into `$defs` automatically wherever a model field references one (e.g. `ConversationStatus`, `Role`, `WorkOrderStatus`, etc. — confirmed present in the output, see below).
   - No `guests.py` file exists under `app/schemas/` (I enumerated the directory: `analytics.py, auth.py, common.py, content.py, conversations.py, dev.py, enums.py, notifications.py, users.py, work_orders.py`), so nothing there was missed.

3. Generated `web/src/api/schema.json` with `python -m app.schemas.export_json_schema`.

## What I tested and the results

### TDD Evidence

**RED** — before `export_json_schema.py` existed:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q
```
```
ERROR collecting tests/test_schema_export.py
ImportError while importing test module '...\tests\test_schema_export.py'.
tests\test_schema_export.py:4: in <module>
    from app.schemas.export_json_schema import DEFAULT_OUT, build
E   ModuleNotFoundError: No module named 'app.schemas.export_json_schema'
1 error in 0.11s
```
This is exactly the failure the brief predicted (Step 2: "Expected: FAIL with `ModuleNotFoundError`") — the module didn't exist yet, so the test can't even import it. Confirms the test is wired to real, not-yet-written code.

**GREEN** — after writing `export_json_schema.py` and generating the schema file:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q
```
```
2 passed in 0.13s
```

Full suite after implementation:
```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```
```
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.......                                                                  [100%]
223 passed in 14.65s
```
No warnings, no skips. (221 previously + 2 new = 223.)

### Model count and camelCase verification

`build()` produces 68 entries under `$defs`: 37 request/response models (all classes from the 8 `MODULES`) plus 31 `StrEnum` types pulled in automatically as field-type dependencies (e.g. `Role`, `ConversationStatus`, `WorkOrderStatus`, `AssetType`, `DeliveryStatus`, ...).

Verified camelCase aliasing directly against the generated file:
```python
d['$defs']['ConversationSummary']['properties'].keys()
# ['assignedDepartmentId', 'assignedUserId', 'channelPrimary', 'guest', 'id',
#  'lastGuestMessageAt', 'lastMessagePreview', 'lastStaffMessageAt',
#  'openWorkOrderCount', 'roomNumber', 'slaDueAt', 'snoozedUntil', 'status', 'unanswered']
```
All keys are camelCase (e.g. Python field `assigned_department_id` → JSON key `assignedDepartmentId`), confirming `by_alias=True` (the default for `models_json_schema`, verified via `inspect.signature`) is in effect and the export reflects the wire contract, not Python snake_case names.

Verified `GuestThread` strictness:
```python
d['$defs']['GuestThread']['additionalProperties']  # False
d['$defs']['GuestThread']['properties'].keys()      # ['messages', 'phone', 'propertyName']
```
No `notes` field present, `additionalProperties: false` present — `extra="forbid"` from `CamelModel` survives into the exported schema.

### Determinism

Model discovery is made deterministic in two ways:
1. `_models()` collects into a dict keyed by class name, then returns `[seen[k] for k in sorted(seen)]` — so the list passed to `models_json_schema` has a fixed order regardless of `vars()` iteration order or module import order.
2. `main()` writes with `json.dumps(..., sort_keys=True)`, so key order in the file itself is canonical.

Verified by generating the schema three times in independent process invocations (once to the real output path, twice more to scratch paths) and comparing byte-for-byte:
```
../.venv/Scripts/python.exe -m app.schemas.export_json_schema <scratch>/gen1.json
../.venv/Scripts/python.exe -m app.schemas.export_json_schema <scratch>/gen2.json
cmp <scratch>/gen1.json <scratch>/gen2.json && echo "IDENTICAL across two runs"
cmp <scratch>/gen1.json ../web/src/api/schema.json && echo "MATCHES COMMITTED FILE"
```
Output: `IDENTICAL across two runs`, `MATCHES COMMITTED FILE` — confirmed byte-identical across three separate process runs.

### Staleness test can genuinely fail

The committed `web/src/api/schema.json` was temporarily backed up, then mutated (injected a spurious `extraField` into `GuestThread.properties`) to simulate drift:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q
```
```
.F                                                                       [100%]
FAILED tests/test_schema_export.py::test_committed_schema_is_current - AssertionError: web/src/api/schema.json is stale ... re-run python -m app.schemas.export_json_schema
1 failed, 1 passed in 0.19s
```
This proves the test is a real diff against the committed bytes, not a build()-vs-build() tautology. The file was then restored from the backup and re-verified:
```
2 passed in 0.13s
```
and the full suite re-run clean (223 passed) before committing.

## Files changed

- `server/app/schemas/export_json_schema.py` (new) — the exporter, verbatim from the brief.
- `server/tests/test_schema_export.py` (new) — the two tests, verbatim from the brief.
- `web/src/api/schema.json` (new, generated) — 68 `$defs`, committed as generated by `python -m app.schemas.export_json_schema`.

`.gitignore` was checked (`web/dist/` is ignored, but not `web/` itself or `web/src/**`), so no changes were needed there — the generated file is committable as-is.

## Self-review

- **Completeness:** Both brief tests pass; the exporter covers every schema module with concrete request/response models. `common.py` (base class only) and `enums.py` (enums only, pulled in transitively) were checked and correctly excluded from `MODULES` — they contain no models that need direct top-level export.
- **Quality:** Code matches the brief's verbatim listing exactly; no unrequested embellishment.
- **Discipline:** Followed the brief's file structure and interface exactly (`build() -> dict`, `DEFAULT_OUT`, `main(out=None)`, CLI entry point). No speculative flexibility added.
- **Testing:** Both tests exercise real behavior (actual `build()` output, actual file on disk), not mocks. TDD followed: RED captured before writing the implementation. Test output is pristine — 223/223, no warnings.
- Ran `git status` and `git add -A -n` before staging to confirm only the three intended paths were added (no stray temp/backup files, no `.venv`, no `server/data/*.db`).

## Issues or concerns

None. No brief defects found in this task — the given test code and exporter code worked as specified with no modification needed.

## Commit

`3da90d6 feat(server): export API models as JSON Schema for the web client` — 3 files changed (`server/app/schemas/export_json_schema.py`, `server/tests/test_schema_export.py`, `web/src/api/schema.json`), 3743 insertions. Working tree clean after commit.
