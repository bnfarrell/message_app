# Task 20 Report: PMS adapter interface, MockPmsAdapter, idempotent event handling

## Fix report — review round 1

**Finding (Important):** the Stay upsert in `handle_event` (`server/app/pms/handle_event.py`) was a
plain `SELECT ...; if stay is None: db.add(Stay(...))`, unguarded by any constraint — unlike the
`pms_event` insert (backed by `UniqueConstraint(integration_key, external_id, event_type)`) and
`guests.find_or_create_by_phone` (backed by `UniqueConstraint(property_id, phone_e164)`) elsewhere
in the same function. Two events for the same reservation that differ only by `event_type` (e.g.
`reservation.created` and `stay.checked_in`) pass the per-event-type dedup check independently, so
a race between them could produce duplicate `Stay` rows for one reservation.

**What I changed:**

1. Added `UniqueConstraint("property_id", "pms_reservation_id", name="uq_stay_property_reservation")`
   to `Stay` in `server/app/models/guests.py`. Verified SQLite treats `NULL` as distinct under a
   unique constraint (inserted two rows with `pms_reservation_id=NULL` for the same property
   directly against a migrated DB — both succeeded), so stays without a reservation id are
   unaffected.
2. Added `server/alembic/versions/0002_stay_unique_reservation.py` (revision `0002`, down_revision
   `0001`), generated via `alembic revision --autogenerate` against a DB built from `0001` only, so
   it captures exactly the one schema diff. Verified `run_migrations` upgrades a fresh DB to head
   cleanly (`0001` then `0002`) and the resulting `stay` table DDL carries
   `CONSTRAINT uq_stay_property_reservation UNIQUE (property_id, pms_reservation_id)`.
3. Extracted `_find_stay(db, property_id, pms_reservation_id)` and wrapped the Stay creation in
   `db.begin_nested()` + `except IntegrityError`, recovering by re-querying via `_find_stay` and
   returning the winner — the same shape as the function's other two upserts.
4. Added `test_stay_upsert_survives_concurrent_insert_race` to `server/tests/test_pms.py`, mirroring
   `test_find_or_create_by_phone_survives_concurrent_insert_race` in `tests/test_guests_stays.py`:
   monkeypatches `app.pms.handle_event._find_stay` so the first lookup misses while a competing
   `Stay` row (same `property_id`/`pms_reservation_id`) already exists, then asserts `handle_event`
   still returns `True`, exactly one `Stay` row exists afterward, and it's the pre-existing winner
   (not a new row).

**Also fixed (Minor, cheap):**

- `server/app/pms/mock_pms.py`'s `next_events`: added `Stay.id` as a secondary sort key on both the
  arrival and departure queries (`.order_by(Stay.arrival_date, Stay.id)` /
  `.order_by(Stay.departure_date, Stay.id)`) so a same-day tie has a deterministic winner instead of
  depending on row insertion/storage order.
- `server/tests/test_pms.py`'s `test_check_in_does_not_reopen_consent_for_opted_out_sms_guest`: the
  original report claimed the test verified `sms_consent_at`/`sms_consent_source` were untouched,
  but it only asserted `sms_consent_status`. Added explicit assertions for both
  (`g.sms_consent_at == consent_at` and `g.sms_consent_source == "sms_keyword"`) so the test matches
  the claim.

**Covering tests — command and output:**

```
../.venv/Scripts/python.exe -m pytest tests/test_pms.py -q
```
```
......                                                                   [100%]
6 passed in 0.76s
```

Full suite:
```
../.venv/Scripts/python.exe -m pytest -q -W error
```
```
........................................................................ [ 33%]
........................................................................ [ 67%]
....................................................................     [100%]
212 passed in 13.29s
```

(211 baseline after Task 19's fix round + 1 new race test = 212.)

**Files changed in this round:**
- `server/app/models/guests.py` — added `UniqueConstraint` on `Stay`.
- `server/alembic/versions/0002_stay_unique_reservation.py` — new migration.
- `server/app/pms/handle_event.py` — race-safe Stay upsert via `_find_stay` +
  `db.begin_nested()`/`IntegrityError`.
- `server/app/pms/mock_pms.py` — deterministic tie-break sort key.
- `server/tests/test_pms.py` — new race test; strengthened consent assertions.

Commit: `1b93384 fix(server): close Stay upsert race with a DB constraint, deterministic mock
tie-break`

**Concerns:** none remaining. The unique constraint, migration, and race guard all verified
directly (migration applies cleanly from scratch, NULL-distinctness confirmed against a real
SQLite DB, race test exercises the actual `IntegrityError` recovery path rather than mocking it
away).

---

## What I implemented

- `server/app/pms/__init__.py` — empty package marker.
- `server/app/pms/base.py` — brief-verbatim: `NormalizedGuest`, `NormalizedStay`, `PmsEvent` dataclasses
  and the `PmsAdapter` Protocol (`fetch_in_house`, `next_events`).
- `server/app/pms/handle_event.py` — `handle_event(db, event, integration_key="mock") -> bool`,
  upserts the guest (via `guests.find_or_create_by_phone`) and stay from a normalized `PmsEvent`,
  records an audit entry and a `stay.updated` realtime event, and returns `False` for a replayed
  `(integration_key, external_id, event_type)`. **Deviates from the brief** in one respect — see
  "Issues / concerns" below: the duplicate-event insert is now race-safe via
  `db.begin_nested()` + `except IntegrityError`, matching the established codebase pattern
  (`app.domain.guests.find_or_create_by_phone`), instead of the brief's plain SELECT-then-INSERT.
- `server/app/pms/mock_pms.py` — brief-verbatim `MockPmsAdapter`: `next_events` alternates between
  checking in one `reserved` stay arriving today and checking out one `checked_in` stay departing
  today, using a persistent `self._flip` toggle (not row ordering) so the alternation is
  deterministic even when both an arrival-due-today and departure-due-today stay exist
  simultaneously (as they do in the fixture data). Also implements `fetch_in_house` and
  `event_for` (for Task 21's dev endpoints — no HTTP route added here).
- `server/app/queue/handlers/pms.py` — brief-verbatim `pms.tick` recurring handler; iterates every
  `Property`, pulls `adapter.next_events`, and calls `handle_event`. Does not re-enqueue itself —
  the worker's `schedule_next_recurrence` after each run handles that (per `RECURRING["pms.tick"]`,
  already seeded in `create_app` from an earlier task).
- `server/app/__init__.py` — added `from app.queue.handlers import pms as pms_handler` and
  `app.extensions["pms_adapter"] = pms_handler.adapter`, right after `Worker(app)` is constructed,
  per the brief's Step 5 instruction.
- `server/tests/test_pms.py` — the brief's four tests verbatim, plus one test I added per the task
  instructions (see below).

## What I tested and the results

Ran the brief's four tests plus one additional test I wrote to satisfy the task's explicit
"Two things to be careful about" instruction (an SMS-opted-out guest must not be reopened by a PMS
check-in, and must not be duplicated):

`test_check_in_does_not_reopen_consent_for_opted_out_sms_guest` — creates a `Guest` directly with
`sms_consent_status=opted_out` (simulating a prior STOP text), then runs a PMS check-in `handle_event`
for the same phone number, and asserts: (a) exactly one `Guest` row exists for that
`(property_id, phone)` afterward (no duplicate), (b) PMS profile fields (`first_name`, etc.) were
merged onto the existing guest, and (c) `sms_consent_status` is still `opted_out`. This passes
because `handle_event`'s guest-merge loop only ever touches
`first_name/last_name/email/loyalty_tier/vip/pms_profile_id` — it never writes consent fields — and
`guests.find_or_create_by_phone` finds the existing row by `(property_id, phone_e164)` rather than
creating a new one.

Full suite: 205 pre-existing + 5 new (`test_pms.py`) = 210 passed.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_pms.py -q`, run before any
`app/pms` code existed:

```
ImportError while importing test module '...\tests\test_pms.py'.
tests\test_pms.py:7: in <module>
    from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent as Ev
E   ModuleNotFoundError: No module named 'app.pms.base'
1 error in 0.19s
```

This is the expected failure — the brief predicted `ModuleNotFoundError: app.pms`; the actual
message names the more specific submodule `app.pms.base` because Python's import system reports the
first missing module encountered while resolving the dotted import, which is functionally the same
failure (the `app.pms` package did not exist).

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_pms.py -q`, after
implementing `app/pms/*` and `app/queue/handlers/pms.py`:

```
.....                                                                    [100%]
5 passed in 0.68s
```

Full suite, command: `../.venv/Scripts/python.exe -m pytest -q`:

```
........................................................................ [ 34%]
........................................................................ [ 68%]
..................................................................       [100%]
210 passed in 12.57s
```

Also ran with `-W error` to catch any new warnings — still 210 passed, no warnings.

## Files changed

- `server/app/pms/__init__.py` (new)
- `server/app/pms/base.py` (new)
- `server/app/pms/handle_event.py` (new)
- `server/app/pms/mock_pms.py` (new)
- `server/app/queue/handlers/pms.py` (new)
- `server/app/__init__.py` (modified — registers `app.extensions["pms_adapter"]`)
- `server/tests/test_pms.py` (new)

Commit: `d3d0e8b feat(server): PMS adapter interface, mock PMS driving check-ins/outs, idempotent
event handling`

## Self-review findings

- Completeness: all brief interfaces implemented (`NormalizedGuest`, `NormalizedStay`, `PmsEvent`,
  `PmsAdapter`, `MockPmsAdapter.next_events`/`fetch_in_house`/`event_for`, `handle_event`,
  `pms.tick` handler, adapter registered on the app). No HTTP route added (correctly deferred to
  Task 21). `RECURRING["pms.tick"]` seeding in `create_app` was already present from an earlier
  task and needed no change.
- Quality: followed the existing channel-seam shape (`app/channels/base.py` /
  `app/channels/mock_sms.py`) as instructed — `PmsAdapter` mirrors `ChannelAdapter`'s
  Protocol-with-attributes-and-two-methods shape.
- Discipline: touched only what the brief's Step 5 named in `app/__init__.py` (four lines added,
  nothing else). Did not reformat any brief-verbatim long lines or semicolon statements to satisfy
  ruff (project convention: single `ruff check --fix` pass at Task 24). Ran `ruff check` on the new
  files and on the whole `server` tree to confirm no *new* categories of finding were introduced
  beyond the pre-existing long-line/import-style findings that already exist across the codebase.
- Testing: TDD followed — RED captured before any implementation code was written. Added one test
  beyond the brief's four because the task brief text explicitly called for testing the
  opted-out-guest-merge scenario and the brief's own `test_pms.py` listing does not cover it.

## Issues / concerns — duplicate suppression enforcement (explicitly requested detail)

**Duplicate suppression is enforced at the DB level**, not just by a SELECT. `PmsEvent` (the model,
`app/models/infra.py`) has `UniqueConstraint("integration_key", "external_id", "event_type",
name="uq_pms_event_idem")`. The brief's own `handle_event.py` code (Step 4) only does a plain
`SELECT ... ; if dup: return False` before `db.add(row)` — a check-then-insert race, exactly the
pattern flagged in the task context as "a real finding four times in this plan (Tasks 10, 11, 16,
17)". I changed this: the row insert is now wrapped in `db.begin_nested()` with `except
IntegrityError: return False`, so a concurrent replay that races past the initial SELECT still
fails safely at the DB constraint rather than raising an uncaught `IntegrityError` up through the
job worker (or an API caller once Task 21's dev endpoints exist). This is the same pattern already
used by `app.domain.guests.find_or_create_by_phone`. This is the one place I deviated from the
brief's literal code — I did not change any test assertions to make this pass; all four of the
brief's tests and all 210 project tests pass unchanged.

**A PMS guest who matches an existing SMS-opted-out guest**: `handle_event` resolves the guest via
`guests.find_or_create_by_phone(db, property_id, phone)`, which matches on the existing
`UniqueConstraint(property_id, phone_e164)` — so a guest who previously texted STOP and has
`sms_consent_status=opted_out` is found (not duplicated), and only
`first_name/last_name/email/loyalty_tier/vip/pms_profile_id` are overwritten from the PMS payload.
`sms_consent_status`, `sms_consent_at`, and `sms_consent_source` are never touched by
`handle_event`, so the guest remains opted out after the PMS check-in event. Verified by the new
`test_check_in_does_not_reopen_consent_for_opted_out_sms_guest` test.

No other concerns. `MockPmsAdapter`'s `self._flip` state lives on the adapter instance, and the
`pms.tick` handler uses one module-level adapter shared across all properties per tick — so the
flip alternates globally across properties rather than per-property. This matches the brief's
specified behavior exactly and is not exercised by any test beyond the single-property case the
brief specifies, so I left it as designed rather than inventing per-property state that wasn't
asked for.
