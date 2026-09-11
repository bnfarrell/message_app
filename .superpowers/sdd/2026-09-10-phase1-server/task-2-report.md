# Task 2 Report: SQLAlchemy models, enums, and the initial Alembic migration

## What was implemented

Exactly per `task-2-brief.md`, in step order:

1. `server/tests/test_models.py` — the four model/migration tests, verbatim from the brief.
2. `server/app/db.py` — `Database`, `Base`, `UTCDateTime`, `new_id()`, `get_db()`, `run_migrations()`, `utcnow()`, verbatim from the brief.
3. `server/app/schemas/__init__.py` (empty) and `server/app/schemas/enums.py` — 17 `StrEnum` classes, verbatim from the brief.
4. Model modules, verbatim from the brief:
   - `server/app/models/core.py` — `enum_type()`, `TimestampMixin`, `Property`, `UserAccount`, `Department`, `PropertyMembership`
   - `server/app/models/guests.py` — `Guest`, `Stay`
   - `server/app/models/conversations.py` — `ResolutionCategory`, `Conversation`, `Message`, `InternalNote`
   - `server/app/models/work_orders.py` — `WorkOrder`, `WorkOrderEvent`, `DraftPrompt`
   - `server/app/models/content.py` — `QuickReply`, `DigitalAsset`
   - `server/app/models/infra.py` — `UserSession`, `Job`, `Notification`, `AuditLog`, `PmsEvent`
   - `server/app/models/__init__.py` — re-exports
5. Alembic config: `server/alembic.ini`, `server/alembic/env.py`, `server/alembic/script.py.mako`, `server/alembic/versions/.gitkeep` — verbatim from the brief.
6. Generated `server/alembic/versions/0001_init.py` via `alembic revision --autogenerate` (see below for the one fix applied).
7. `server/app/__init__.py` modified to register `app.extensions["db"] = Database(config.DATABASE_URL)` right after `SECRET_KEY` is set, exactly as the brief's diff shows.

## TDD evidence

**RED** — `cd server && source ../.venv/Scripts/activate && python -m pytest tests/test_models.py -q`:
```
ImportError while importing test module '...\tests\test_models.py'.
tests\test_models.py:7: in <module>
    from app.db import Database, run_migrations
E   ModuleNotFoundError: No module named 'app.db'
1 error in 0.89s
```
Matches the brief's expected failure exactly (before `app/db.py` existed).

**GREEN** — after writing `app/db.py`, `app/schemas/*`, `app/models/*`, and generating the migration — `python -m pytest tests/test_models.py -q`:
```
....                                                                     [100%]
4 passed, 4 warnings in 1.55s
```
(The 4 warnings are all the same alembic `DeprecationWarning` about `path_separator`, discussed under Concerns.)

## Migration generation (Step 7)

```
mkdir -p data
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic revision --autogenerate -m init --rev-id 0001
```
Output: `Generating ...\alembic\versions\0001_init.py ...  done`

**Autogenerate defect found and fixed:** the generated file used `app.db.UTCDateTime()` for every timestamp column but never imported `app.db`, which would raise `NameError` at migration-load time. I added `import app.db` alongside the existing `from alembic import op` / `import sqlalchemy as sa` imports at the top of `0001_init.py`. This is the one hand-edit made, per the brief's allowance to fix an autogenerate error; no other line was touched.

Verified every table in `EXPECTED_TABLES` (except `alembic_version`) has an `op.create_table(...)`: `job, pms_event, property, user_account, audit_log, department, guest, notification, resolution_category, user_session, digital_asset, property_membership, quick_reply, stay, conversation, internal_note, message, work_order, draft_prompt, work_order_event` — all 20 present.

```
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic upgrade head
```
→ completed with no errors (exit 0).

```
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic check
```
```
No new upgrade operations detected.
```

Cleaned up: `rm -f data/migrate-check.db data/migrate-check.db-wal data/migrate-check.db-shm`. `server/data/` is git-ignored and confirmed empty before commit.

## Full test suite (Step 9)

`python -m pytest -q`:
```
.......                                                                  [100%]
7 passed, 4 warnings in 1.54s
```
Note: the brief's Step 9 says "Expected: 6 passed" — actual collected/passed count is 7 (3 pre-existing from Task 1: `test_errors.py` ×1, `test_health.py` ×2, plus the 4 new `test_models.py` tests). All tests pass; the brief's expected count appears to be a minor miscount in the brief itself, not a defect — every test that exists passes.

## Files changed

- Created: `server/app/db.py`, `server/app/schemas/__init__.py`, `server/app/schemas/enums.py`, `server/app/models/__init__.py`, `server/app/models/core.py`, `server/app/models/guests.py`, `server/app/models/conversations.py`, `server/app/models/work_orders.py`, `server/app/models/content.py`, `server/app/models/infra.py`, `server/alembic.ini`, `server/alembic/env.py`, `server/alembic/script.py.mako`, `server/alembic/versions/.gitkeep`, `server/alembic/versions/0001_init.py`, `server/tests/test_models.py`
- Modified: `server/app/__init__.py` (added `Database` registration on `app.extensions["db"]`)

## Self-review findings

- Completeness: all files from the brief's file list exist; all interfaces listed (`Database(url).session()`, `get_db()`, `run_migrations(url)`, `Base`, `UTCDateTime`, `new_id()`, all models, all enums) are present and match verbatim.
- Discipline (YAGNI): no code beyond what the brief specified; every changed line in `app/__init__.py` traces to the brief's exact diff.
- `git status`/`git diff` reviewed before commit — only the intended 17 files staged; `server/data/` empty, no `*.db` files committed; `.venv` untouched.
- `ruff check app tests alembic` reports pre-existing style issues (a handful of `E501` line-too-long, one `UP017` `timezone.utc` → `datetime.UTC` suggestion) that all originate from the brief's verbatim code blocks (e.g. `PropertyMembership.__table_args__` line, the test's `timezone.utc` usage). I did not alter this code since the brief mandates these exact values verbatim and Step 9's only verification criterion is pytest, not ruff — flagged below as a concern rather than silently fixed or silently ignored.

## Concerns

1. **Alembic `DeprecationWarning`** (`No path_separator found in configuration; falling back to legacy splitting...`) appears 4 times in pytest output, sourced from `alembic/config.py` when `run_migrations()` builds an `AlembicConfig` from `server/alembic.ini`. It's not filtered to an error by `pyproject.toml`'s `filterwarnings = ["error::DeprecationWarning:app.*"]` (module is `alembic.*`, not `app.*`), so all tests pass, but strictly it means pytest output isn't 100% warning-free. Root cause is the brief's exact `alembic.ini` template omitting `path_separator = os` under `[alembic]`. I left `alembic.ini` untouched since the brief says to use its exact values verbatim; flagging rather than deviating.
2. Minor ruff findings (line length, `timezone.utc` vs `datetime.UTC`) exist in brief-verbatim code, not fixed for the same verbatim-fidelity reason.
3. Brief's Step 9 said "Expected: 6 passed"; actual is 7 passed (all green) — noted above, not a functional problem.

## Commit

`22aff26` — `feat(server): SQLAlchemy models, enums, and initial Alembic migration`

---

## Fix report (review round 1)

Coordinator review found the spec compliant but requested one Important fix plus two test-strength gaps.

### 1. (Important) Silence the alembic `path_separator` DeprecationWarning

`server/alembic.ini` `[alembic]` section was missing `path_separator = os`, which caused alembic to fall back to legacy `prepend_sys_path` splitting and emit a `DeprecationWarning` on every `AlembicConfig` construction (4× in the test run, once per test calling `run_migrations`).

Change:
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
path_separator = os
file_template = %%(rev)s_%%(slug)s
```

### 2. (Test gap) `test_enum_values_are_stored_as_values_and_validated` couldn't prove value-vs-name storage

Every app `StrEnum` has `name == value` (e.g. `open = "open"`), so the existing assertion `raw == "open"` was consistent with either value-storage or name-storage — it didn't actually test what its name claimed. Added a new test, `test_enum_stores_value_not_name`, that defines a throwaway `class _T(StrEnum): a_b = "a-b"` (name and value differ), builds a one-off `Table` with a column typed `enum_type(_T)` against a local `MetaData`, creates it on the test engine, inserts `_T.a_b`, and asserts the raw stored string is `"a-b"` (the value) and not `"a_b"` (the name). No app enum was changed. The original test's assertions (including the `pytest.raises(StatementError)` for an invalid string) were kept as-is.

### 3. (Test gap) No test that `UTCDateTime` rejects naive datetimes

Added `test_utc_datetime_rejects_naive`: constructs `Property(..., created_at=datetime(2026, 1, 1))` (naive, overriding the column's `default=utcnow`), adds it, flushes, and asserts `pytest.raises(StatementError)`. Confirmed via the actual run that SQLAlchemy wraps the `UTCDateTime.process_bind_param`'s `ValueError` as a `StatementError` at flush time, so the assertion is on what the code actually raises.

### Covering tests

- `server/tests/test_models.py::test_enum_stores_value_not_name` (new)
- `server/tests/test_models.py::test_utc_datetime_rejects_naive` (new)
- All four original `test_models.py` tests (regression)

### Commands and output

`python -m pytest tests/test_models.py -q`:
```
......                                                                   [100%]
6 passed in 1.73s
```
No warnings.

`python -m pytest -q` (full suite):
```
.........                                                                [100%]
9 passed in 1.48s
```
No warnings — pristine, as required.

Also re-verified the migration is still consistent after the `alembic.ini` change:
```
DATABASE_URL=sqlite:///data/migrate-check2.db python -m alembic upgrade head
DATABASE_URL=sqlite:///data/migrate-check2.db python -m alembic check
```
→ `No new upgrade operations detected.` Scratch DB and its `-wal`/`-shm` siblings deleted afterward; `server/data/` confirmed empty.

### Files changed (this round)

- Modified: `server/alembic.ini` (added `path_separator = os`)
- Modified: `server/tests/test_models.py` (added `test_enum_stores_value_not_name`, `test_utc_datetime_rejects_naive`, and their imports)

### Commit

`71a9445` — `fix(server): silence alembic path_separator warning; strengthen enum and UTCDateTime tests`
