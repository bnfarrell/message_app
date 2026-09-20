# Task 1 Report: Models, enums and migration

## What I implemented

Exactly the four tables, two enums, and migration specified in `task-1-brief.md`, step order followed (TDD: test first, watch RED, then implement):

1. **`server/app/schemas/enums.py`** — appended `Shift` (`am`/`pm`/`overnight`) and `MentionTargetType` (`user`/`department`), both `StrEnum`.
2. **`server/app/models/log.py`** (new) — `LogEntry`, `LogEntryMention`, `LogEntryPhoto`, `LogEntryAck`, verbatim from the brief. All enum columns go through `enum_type()` from `app.models.core`.
3. **`server/app/models/__init__.py`** — imports and exports the four new names, alphabetical order preserved in `__all__`.
4. **`server/alembic/versions/0006_hotel_log.py`** (new) — creates the four tables.
5. **`server/tests/test_models.py`** — added the two tests from the brief, plus the top-of-file imports they needed (`select` from sqlalchemy, `from app import clock`; `pytest` was already imported).

### One deliberate deviation from the brief's literal migration text, and why

The brief's Step 6 code block writes migration columns in the order `id, created_at, updated_at, <business columns>` and creates indexes with bare `op.create_index(...)`. I read `0005_staff_messaging.py` first as instructed ("match its style exactly") and also checked `0001_init.py` and `0004_work_order_photo.py`: **every existing migration** in this repo places `TimestampMixin`'s columns (`id`, `created_at`, `updated_at`) *last*, after the model's own declared columns, and wraps every index creation/drop in `op.batch_alter_table(...)`, even for brand-new tables. This isn't cosmetic — it's what SQLAlchemy's declarative column ordering actually produces from `TimestampMixin` + subclass, and it's the sole style used elsewhere in the codebase. I wrote `0006` to match that real pattern instead of the brief's snippet's ordering/index-call style, keeping every table name, column name, type, constraint name, and index name from the brief exactly as specified. Functionally the two forms are identical on SQLite and Postgres; I chose consistency with the existing 5 migrations over verbatim-brief formatting since the task instructions explicitly called out matching 0005's style as a global constraint.

### One correctness fix beyond the brief (found in self-review)

The brief's Step 6 snippet has `sa.Column("data", sa.LargeBinary(), nullable=True)` for `log_entry_photo.data`. But the Step 4 model declares `data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)` — non-`Optional`, which SQLAlchemy 2.0 typing maps to `nullable=False`. The established sibling pattern (`work_order_photo.data`, `app/models/work_orders.py:87`) is explicit `nullable=False` for the same non-optional-bytes case, while `staff_message.photo_data` (which IS `Optional`) is `nullable=True`. The brief's migration text looks like a copy-paste of the `staff_message` pattern into the wrong place. I changed it to `nullable=False` to match the model's actual type contract and the established sibling table. This has no test impact (the round-trip test always supplies `data=b"abc"`), but leaving it `nullable=True` would have let the DB silently accept NULL photo bytes the ORM type promises can't happen.

## What I tested and the results

Ran the full backend suite and ruff twice: once immediately after environment repair (before the ack-uniqueness test fix), and again after applying the fix and the `nullable=False` migration correction, to make sure nothing regressed between edits.

Final state:
- `cd server && ../.venv/Scripts/python.exe -m pytest -q` → **386 passed in 48.12s**, pristine output (no warnings, no skips).
- `cd server && ../.venv/Scripts/python.exe -m ruff check .` → **All checks passed!**
- `git status --porcelain` after committing shows only pre-existing, unrelated modifications (`docs/superpowers/plans/2026-09-19-hotel-log.md`, `server/data/app.db*`, deleted `two.png`, untracked `.claude/`/`images/`) — none of which I touched or committed.

## TDD evidence

**RED** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_models.py -q -k log_entry`

This was first attempted before the models/enums existed, as prescribed. That attempt (and several subsequent ones) hit a pre-existing, unrelated environment failure: `.venv/pyvenv.cfg`'s `home` pointed at a dead Windows Store Python alias stub left over from a different, stale project path, so every invocation of `../.venv/Scripts/python.exe` — even `python -c "print('hello')"` — silently self-relaunched into a runaway process tree (observed up to ~1900 `python.exe` processes) instead of executing. I killed the process trees each time (`taskkill /F /IM python.exe /T`, then `Stop-Process -Name python,pythonw -Force`) and confirmed the box was quiescent before continuing. This was environment corruption, not a code or test defect — the coordinator independently diagnosed and fixed the same root cause (dead venv, missing base Python 3.14) by installing Python 3.12.10 and recreating `.venv`.

After the fix, I re-verified RED cleanly by temporarily reverting `app/models/__init__.py` and `app/schemas/enums.py` to their pre-task versions (`git show HEAD~1:...`) with `app/models/log.py` removed, then running:

```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_models.py -q -k log_entry
```

Output:
```
FAILED tests/test_models.py::test_log_entry_round_trips_with_mentions_photo_and_ack
FAILED tests/test_models.py::test_log_entry_ack_is_unique_per_user - ImportEr...
2 failed, 7 deselected in 2.62s
```
with
```
E       ImportError: cannot import name 'LogEntry' from 'app.models' (...)
```
— exactly the failure the brief predicted, for the predicted reason (the models don't exist yet). I then restored all three files to the committed state (verified `git status --porcelain` on them showed no diff) before re-running the real suite.

**GREEN** — `cd server && ../.venv/Scripts/python.exe -m pytest -q` → `386 passed in 48.12s`.

## The ack-uniqueness test fix (per coordinator instruction)

`test_log_entry_ack_is_unique_per_user`, as written in the brief, leaves the session poisoned after `pytest.raises(IntegrityError): db.flush()` — the `database.session()` context manager's commit-on-exit then raises `PendingRollbackError`, unrelated to the constraint under test. Added `db.rollback()` immediately after the `with pytest.raises(...)` block, at the coordinator's direction and with the exact comment/placement given. Verified this was the only change needed: full suite went from 385 passed / 1 failed to 386 passed / 0 failed with no other edits.

## Files changed

- `server/app/models/log.py` (new)
- `server/alembic/versions/0006_hotel_log.py` (new)
- `server/app/models/__init__.py` (modified — import + `__all__`)
- `server/app/schemas/enums.py` (modified — `Shift`, `MentionTargetType`)
- `server/tests/test_models.py` (modified — imports + two new tests + the `db.rollback()` fix)

Commit: `aafdd7e` — `feat(server): hotel log tables, enums and migration 0006`. Only these five files are staged/committed; `server/data/app.db*` and other pre-existing unrelated working-tree changes were explicitly excluded.

## Self-review findings

- **Completeness against brief**: all four models, both enums, the `__init__.py` export, and the migration match the brief's specified names, types, constraints, and indexes. The two deviations (migration column/index style, `data` nullability) are both documented above with rationale.
- **Naming**: table names, index names (`ix_log_entry_property_created`, `ix_log_mention_property_target`, etc.), and constraint names (`uq_log_mention_entry_target`, `uq_log_ack_entry_user`) match the brief and the `ck_enum_<lowercasename>` convention from `enum_type()` (`ck_enum_shift`, `ck_enum_mentiontargettype`).
- **YAGNI**: no fields, routes, or domain logic beyond what the brief specifies. `LogEntry.body` has no update path (by design, per the model's docstring) — nothing in this task adds one.
- **Test quality**: the round-trip test verifies actual persisted state (re-fetches in a fresh session, checks `shift`, `pinned` default, `ack_expected` frozen-list round-trip, mention ordering by `position`, and deferred `photo.data` bytes) rather than merely restating the code under test. The uniqueness test verifies the DB-level constraint fires (`IntegrityError` on the second `LogEntryAck` for the same `(log_entry_id, user_id)`), not just ORM-level behavior.

## Concerns

1. **Migration portability (asked explicitly by the coordinator)**: `0006_hotel_log.py` uses only constructs already proven against production PostgreSQL 18 by migrations 0001–0005 — `sa.Enum(..., native_enum=False, create_constraint=True)` (VARCHAR + CHECK, not a native PG enum type), `app.db.UTCDateTime()`, `sa.JSON()`, `sa.LargeBinary()`, `sa.Text()`, `sa.Boolean()`, and `op.batch_alter_table(...)` for index creation/drop (a no-op-equivalent plain ALTER on Postgres, a table rebuild only on SQLite — the same trade-off every prior migration already makes). No dialect-specific types, no raw SQL, no `IF NOT EXISTS`/`IF EXISTS` guards. I have no portability concerns with this migration.
2. **`downgrade()` genuinely reverses `upgrade()`**: table drops are in strict reverse-dependency order (`log_entry_ack`, `log_entry_photo`, `log_entry_mention` — all three FK-reference `log_entry` — then `log_entry` last), and every index created in `upgrade()` is dropped by name in `downgrade()` before its table drop (redundant on both SQLite and Postgres, since `DROP TABLE` removes its own indexes, but matches the explicit symmetric style already used in `0001_init.py`'s downgrade). I traced every `create_index`/`drop_index` pair by name and confirmed they match exactly. I'm confident this downgrade is correct and complete.
3. **Unrelated files in the working tree**: `docs/superpowers/plans/2026-09-19-hotel-log.md`, `server/data/app.db*`, and `two.png` show as modified/deleted in `git status` but were not touched by me and were not included in this commit, per instruction.
4. No other open concerns. All three of this task's verification gates (RED, GREEN, ruff) are satisfied against the current committed state.
