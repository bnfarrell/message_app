# Task 22 Report: Seed script and CLI

## What I implemented

Followed the brief's steps in order:

- `server/seed/__init__.py` — empty package marker.
- `server/seed/data.py` — static vocabulary (names, openers, staff replies, work order templates,
  quick replies, assets, categories), copied verbatim from the brief.
- `server/seed/seed.py` — `run(database_url, *, reset=True, now=None) -> SeedSummary`, copied from
  the brief with two functional fixes and one safety addition (all described under "Brief defects"
  below).
- `server/app/cli.py` — `flask seed` command (`--no-reset` flag), plus an upfront "what is about to
  happen" line and a login line, per the task's callout that this is what a human logs into.
- `server/app/__init__.py` — registered `seed_command` via `app.cli.add_command(seed_command)`,
  right after `register_error_handlers(app)`. Four-line, single-purpose diff.
- `server/tests/test_seed.py` — copied verbatim from the brief.

## Brief defects found and fixed

1. **Genuine defect — `summary.conversations` undercounts by 1.** The brief creates 29 conversations
   in the main `plan` loop (`convs.append(c)`), then separately creates `tom_conv` (Tom's
   failed-delivery conversation) but never appends it to `convs`. The DB ends up with the correct 30
   conversation rows (`count(Conversation, property_id==hvh.id) == 30` passes regardless, since that
   assertion queries the DB, not the list), but `SeedSummary(conversations=len(convs), ...)` would be
   29, failing the brief's own `assert summary.conversations == 30`. I confirmed this by tracing the
   code before touching it, then added `convs.append(tom_conv)` right after `tom_conv` is built. Ran
   the real seed afterward — `SeedSummary(... conversations=30 ...)` — confirming the fix, and the
   test (which exercises this exact assertion) passes.

2. **Convention fix — `datetime.now(timezone.utc)` instead of `app.clock.now()`.** The brief's
   default-`now` fallback (`now = now or datetime.now(timezone.utc)`) violates the project's global
   constraint ("time only from `app.clock.now()` — never `datetime.now()`"). `app.clock.now()` falls
   back to the identical raw call when the clock isn't frozen, so behavior for the shipped tests is
   unchanged, but this keeps the seed testable under `clock.freeze(...)` like the rest of the codebase
   and removes a raw `datetime.now()` call from a module that touches persisted timestamps. Changed to
   `from app import clock` / `now = now or clock.now()`.

3. **Safety addition — refuse `reset=True` on non-sqlite URLs.** The brief's reset logic only deletes
   files when the URL starts with `sqlite:///`; for any other URL (e.g. Postgres) `reset=True` would
   silently do nothing protective and then seed on top of whatever is already there, hitting unique
   constraint violations (or, worse on a mostly-empty prod DB, partially succeeding). I added a guard
   that raises `ValueError` for `reset=True` with a non-sqlite URL, telling the caller to pass
   `reset=False` and ensure the target is empty first. This was called out explicitly in my task
   context ("Make sure it cannot run against a non-empty production database by accident") — no test
   in the brief exercises this path since both tests use sqlite URLs, so nothing in the brief's test
   suite is affected. Verified manually (see Testing below).

No other counts, ids, or behaviors needed correction — I traced every count assertion in
`test_seed.py` against the brief's construction logic by hand before running anything (staff/HVH
membership count = 12, checked_in = 85, reserved = 10, checked_out = 8, conversations = 30, archived =
5, DraftPrompt = 2, opted_out guest = 1, redacted message = 1, active work orders = 15 with the six
`verified` ones added after the 15-count is reached so they're excluded, linked work orders ≥ 6, quick
replies ≥ 15, assets = 8, categories ≥ 10, failed message ≥ 1) and they all matched before I ran a
single test.

## TDD Evidence

**RED** — before any implementation existed:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q
```
```
ImportError while importing test module 'tests\test_seed.py'.
tests\test_seed.py:7: in <module>
    from seed.seed import run
E   ModuleNotFoundError: No module named 'seed'
1 error in 0.12s
```
This is the expected failure — the `seed` package didn't exist yet.

**GREEN** — after implementing `seed/data.py`, `seed/seed.py`, `app/cli.py`, and registering the CLI:
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q
```
```
..
2 passed in 1.25s
```

**Full suite**, run once before committing:
```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```
```
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [ 99%]
..                                                                       [100%]
218 passed in 14.48s
```
216 previously-passing + 2 new = 218, no warnings, no skips.

## Manually verifying the real seed (not just the test)

Ran the seed directly against a scratch `server/data/app.db` (module form and the registered Flask
CLI command), then deleted the scratch db (it's gitignored — `server/data/` and `*.db` are already in
`.gitignore` — and nothing under `server/data/*.db` was staged or committed):

```
$ ../.venv/Scripts/python.exe -m seed.seed
SeedSummary(properties=2, users=14, guests=106, stays=106, conversations=30, messages=53, work_orders=21)

$ ../.venv/Scripts/python.exe -m flask --app app seed
Seeding sqlite:///data/app.db (reset=True)...
Seeded 2 properties, 14 users, 106 guests, 106 stays, 30 conversations, 53 messages, 21 work orders.
Log in as ava@hvh.test / Password123!
```

Also checked:
- `--no-reset` against an already-seeded db correctly fails loud (SQLite `UNIQUE constraint failed:
  property.code`) rather than silently corrupting data — expected, since `--no-reset` is for adding to
  an empty db, not idempotent re-seeding.
- `run("postgresql://x/y", reset=True)` raises the new `ValueError` guard rather than doing nothing
  protective.
- Queried the seeded db directly for `(property_id, pms_reservation_id)` duplicates across all 106
  stays: **0 duplicates** (the brief's random suffixes on `pms_reservation_id` never collided under
  seed 42; this satisfies the `Stay` unique constraint added in migration 0002).
- `ruff check` on my own additions (`app/cli.py`, the reset-guard block in `seed/seed.py`) — clean, no
  findings. Ran `ruff check` over the brief-verbatim files too; it reports the usual line-length/style
  findings already expected in plan-verbatim code — left untouched per project convention (one
  `ruff --fix` pass at Task 24).

## Files changed

- `server/seed/__init__.py` (new)
- `server/seed/data.py` (new, verbatim from brief)
- `server/seed/seed.py` (new; verbatim from brief plus the three fixes above)
- `server/app/cli.py` (new; brief's CLI plus an upfront status line and a login line)
- `server/app/__init__.py` (modified — 4-line addition registering `seed_command`)
- `server/tests/test_seed.py` (new, verbatim from brief)

## Self-review

- **Completeness**: all brief steps done — failing test captured, `data.py`, `seed.py`, `cli.py`,
  registration, full-suite run, real seed run, commit.
- **Quality**: naming and structure match the brief and existing codebase conventions (domain modules
  untouched; seed builds models directly, per the task context's guidance to avoid firing outbound
  SMS/jobs/realtime events through domain functions).
- **Discipline**: no scope creep beyond the three defect/safety fixes described above, each narrowly
  justified and none touching brief-verbatim style/formatting. Did not "improve" adjacent code.
- **Testing**: both new tests exercise real behavior (a real sqlite db via migrations, a real Flask
  test client hitting `/api/auth/login` and `/api/auth/me`), no mocks. TDD followed — RED captured
  before any implementation file existed.

## Determinism — what I took it to mean and how I verified it

Determinism here means: given the same seed (`random.Random(42)`), the *shape and content* of the
generated data — guest names, phone numbers, room assignments, message bodies, work order titles,
counts — is identical run-to-run, even though row ids (`uuid.uuid4()` defaults) differ. I verified
this exactly as the brief's own test does: ran `run()` against two separate sqlite files and compared
the full sorted set of `Guest.phone_e164` values — they matched exactly (this is also covered by the
committed test, which passed). I did not add any additional determinism checks beyond what the brief
specifies, since the brief's own assertion already covers the risk area (rng-derived data) directly.

Note: `now` defaults to `clock.now()` (real wall-clock, since nothing freezes the clock in these
tests) — this affects only *when* things happened relative to the moment `run()` was called (e.g.
`now - timedelta(minutes=rng.randint(...))`), never *what* data is produced, so it does not affect the
phone-number determinism check or any count assertion.

## Seeded login

A human can sign in with:
- Email: `ava@hvh.test`
- Password: `Password123!`

(Any of the 12 HVH staff logins work with the same password — `ava` is an agent at Harbourview Hotel,
which is what `test_seeded_users_can_log_in` checks via `/api/auth/login` + `/api/auth/me`.)

## Outbound side effects

None. The seed builds `Guest`, `Stay`, `Conversation`, `Message`, `WorkOrder`, `WorkOrderEvent`,
`QuickReply`, `DigitalAsset`, `ResolutionCategory`, `UserAccount`, `PropertyMembership`, `Department`,
`DraftPrompt`, and `Job` rows directly via the SQLAlchemy models, never through the `app.domain.*`
functions that would enqueue outbound jobs, send mock SMS, or emit realtime broadcast events. I
confirmed this by checking that `db.info["events"]` — the only channel `Database.session()` uses to
dispatch realtime events on commit (`app/db.py` / `app/realtime/broadcast.py`) — is only ever populated
by `app.realtime.broadcast` calls, which nothing in `seed.py` invokes. The three `jobs.ensure_recurring(db, job_type)`
calls at the end only insert `Job` rows (queued, not executed) for `sla.sweep`, `snooze.wake`, and
`pms.tick` — no worker is started by the seed, so nothing processes them.

## Concerns

None blocking. Two small judgment calls worth the reviewer's attention:
1. The `convs.append(tom_conv)` fix (a one-line change to brief-verbatim code) is the minimal fix I
   could find for the miscounted `summary.conversations`; an alternative would have been to leave
   `tom_conv` out of `convs` and instead compute `conversations=len(convs) + 1` in the `SeedSummary`
   construction — I chose the append because it keeps `work_orders`/`messages` bookkeeping (which
   already relies on `convs` implicitly, e.g. `card_conv = convs[3]`) untouched and makes `convs`
   actually mean "every conversation created," which is what its name promises.
2. The non-sqlite `reset=True` guard is not exercised by any test in the brief (both tests use sqlite
   URLs) — it's a defensive addition responding directly to the task context's callout, not a
   TDD-driven change. Flagging this so the reviewer can judge whether it's in scope.

---

## Fix Round 1/5 (review findings addressed)

### Finding 1 (Important) — `SeedSummary.messages` overcounted by one

Confirmed exactly as the reviewer described: the seed's own `messages` was a `nonlocal` counter
incremented on every `add_msg` call, but the showcase rewire (`db.delete(m)` for the original
`convs[0]` message, then four new `add_msg` calls) never decremented it — the counter and the real
row count diverged by exactly 1 (53 vs. 52).

**Fix — derive every `SeedSummary` field from a real row count, not an in-memory counter/list.**
Removed the `messages = 0` / `nonlocal messages` / `messages += 1` machinery entirely, and replaced
the final `SeedSummary(properties=2, users=len(staff) + 2, guests=len(guests), ...)` construction with
seven `db.scalar(select(func.count()).select_from(Model))` queries run after all mutations (including
the showcase rewire and the work-order fill loop) are complete. This removes the only actually-broken
counter and also removes the *possibility* of the same class of bug recurring for any of the other six
fields, regardless of future edits to the rewire logic. (I traced `guests`/`stays`/`work_orders` before
this fix and confirmed nothing deletes from those lists today — only `messages` was ever silently wrong
— but per the ruling I moved all seven to direct DB counts rather than leave lists that merely happen to
be safe today.)

Added regression coverage in `test_seed_matches_spec_counts`: `summary.<field> == count(<Model>)` for
all seven `SeedSummary` fields, asserted against the same `count()` helper the test already uses.

### Finding 2 (Important) — determinism claim vs. `DigitalAsset.short_code`

Confirmed: `new_short_code` (`app/domain/assets.py`) uses `secrets.choice`, not the seed's
`random.Random(42)`, so `short_code` values differ between runs — my original report's "identical
run-to-run" claim was inaccurate for that one field.

**No code change** — `secrets.choice` stays, exactly as ruled: the short code is the public
`/a/<code>` guest-facing SMS link, and making it predictable to satisfy a determinism claim would be a
real security regression, which is a far worse trade. Documented the exception in `seed/seed.py`'s
module docstring (quoted in the diff below) so a future reader — or implementer — doesn't "fix" it in
the wrong direction. Restating the corrected claim here too: determinism covers the shape and content
of the seeded data (names, counts, message bodies, phone numbers, timing), driven by `random.Random(42)`;
it does **not** cover `DigitalAsset.short_code`, which is deliberately unpredictable, or row ids
(`uuid.uuid4()`), which were already called out as varying in the original report.

### Finding 3 (Important) + promoted Minor — missing tests, and a friendlier CLI failure

Added two tests to `tests/test_seed.py`:
- `test_reset_refuses_non_sqlite_url` — `pytest.raises(ValueError, match="sqlite")` around
  `run("postgresql://x/y", reset=True)`. DB-free, one-line body.
- `test_reseeding_same_sqlite_url_is_idempotent` — runs `run(url, reset=True)` twice against the same
  sqlite file and asserts the two `SeedSummary` results are equal (dataclass `__eq__`), covering the
  CLI's everyday-refresh path.

Promoted Minor: `app/cli.py`'s `seed_command` now wraps the `run(...)` call in
`try/except ValueError as exc: raise click.ClickException(str(exc)) from exc`, so an operator who points
`flask seed` at a non-sqlite `DATABASE_URL` gets a clean `Error: ...` line instead of a raw traceback.
The library-level `run()` still raises a bare `ValueError` (correct — it's a library function, not a
CLI surface).

I could not exercise this end-to-end through the real `flask --app app seed` CLI against an actual
non-sqlite URL: `create_app()` builds `Database(config.DATABASE_URL)` (which calls SQLAlchemy
`create_engine`) before the seed command ever runs, and this environment has no `psycopg2` installed,
so app creation itself fails first with `ModuleNotFoundError: No module named 'psycopg2'` — a
pre-existing, unrelated condition. Instead I verified the `try/except` conversion directly: created a
real Flask app (sqlite, in-memory), patched `seed.seed.run` to raise the same `ValueError` the guard
raises, and invoked the command through Click's `CliRunner`:

```
exit_code: 1
output: 'Seeding sqlite:///data/app.db (reset=True)...\nError: reset=True is only supported for sqlite:/// URLs\n'
exception type: SystemExit
```

Clean one-line `Error: ...` message, no traceback, exit code 1 — confirms the wrapping works.

### Re-run: covering test, full suite, and a real seed vs. real row counts

```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q
```
```
....
4 passed in 1.87s
```

```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```
```
........................................................................ [ 32%]
........................................................................ [ 64%]
........................................................................ [ 96%]
.........                                                                [100%]
225 passed in 15.43s
```
(223 baseline at fix-round start + 2 new tests = 225.)

Ran the real seed against a scratch `server/data/app.db` and queried every model's row count directly,
comparing against the printed `SeedSummary`:

```
$ ../.venv/Scripts/python.exe -m seed.seed
SeedSummary(properties=2, users=14, guests=106, stays=106, conversations=30, messages=52, work_orders=21)

$ ../.venv/Scripts/python.exe -c "... select(func.count()).select_from(model) for each model ..."
properties: 2
users: 14
guests: 106
stays: 106
conversations: 30
messages: 52
work_orders: 21
```

All seven fields match exactly — including `messages`, now 52 (not the previously-wrong 53). Deleted
the scratch `server/data/` directory afterward; nothing under it was staged.

### Files changed (this round)

- `server/seed/seed.py` — module docstring gains the determinism/short_code exception; removed the
  `messages` counter; `SeedSummary` now built from seven `select(func.count())` queries.
- `server/app/cli.py` — wraps `run(...)` in `try/except ValueError` → `click.ClickException`.
- `server/tests/test_seed.py` — added per-field `summary.<x> == count(<Model>)` assertions, plus two
  new test functions (`test_reset_refuses_non_sqlite_url`, `test_reseeding_same_sqlite_url_is_idempotent`).

### Concerns

None. All three Important findings and the promoted Minor are addressed; no regressions; ruff shows no
new findings on any line I touched (checked `app/cli.py`, `seed/seed.py`, `tests/test_seed.py`
individually — pre-existing line-length findings are all on unchanged brief-verbatim lines, left alone
per project convention).
