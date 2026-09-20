# SDD ledger — plan: docs/superpowers/plans/2026-09-19-hotel-log.md

Spec: docs/superpowers/specs/2026-09-19-hotel-log-design.md (read; binding authority)
Branch: hotel-log, cut from main at 9281bea + spec 4798727 + plan a97086b
Workspace: .superpowers/sdd/2026-09-19-hotel-log/

## Preflight conflict scan

Cross-task pairs sharing a file or an interface:

| Producer | Consumer | Interface checked | Result |
|---|---|---|---|
| T1 | T5,T6,T7,T8 | LogEntry / LogEntryMention / LogEntryPhoto / LogEntryAck names + columns | agree |
| T1 | T2 | `Shift` enum members am/pm/overnight | agree |
| T1 | T5 | `MentionTargetType` used for LogEntryMention.type | agree |
| T2 | T5 | `shift_for(prop, at)` — T5 calls `shift_for(prop, clock.now())` | agree |
| T3 | T8 | capability strings view_log / post_log / pin_log_entry | agree, exact match |
| T3 | T12 | web `Capability` union must contain 'pin_log_entry' for `can()` | agree |
| T4 | T5 | CreateLogEntryRequest fields vs create() reads | agree (body, department_id, mentions, requires_ack, ack_audience, linked_*) |
| T4 | T6 | LogFeedQuery fields vs feed() reads | agree (shift, department_id, from_, to, mentioning_me, cursor) |
| T4 | T6 | all 22 LogEntryOut fields vs _to_out kwargs | agree, field-by-field |
| T4 | T9 | generated TS names LogEntryOut/LogFeedOut/LogMentionableOut/CreateLogEntryRequest | agree via schema export |
| T6 | T8 | feed / get_out / get signatures | agree |
| T7 | T8 | acknowledge / set_pinned signatures | agree |
| T8 | T8 | mentionables + get_photo added in step 4, called in step 3 | agree (same task) |
| T9 | T10-T13 | hook names useLogFeed/useLogEntry/useLogMentionables/useCreateLogEntry/useAckLogEntry/useSetLogPinned | agree |
| T10 | T11 | MentionInput props + tokenFor | agree |
| T10 | T12 | TOKEN_RE grammar matches tokenFor output | agree |

Per-task self-consistency:

| Task | Tests vs code it specifies | Result |
|---|---|---|
| T1 | round-trip + unique constraint vs the four models | agree |
| T2 | 13 parametrised cases vs three-way boundary compare | agree |
| T3 | role matrix vs CAPABILITIES entries | agree |
| T4 | schema-export staleness test vs new module | agree |
| T5 | 7 tests vs create() | **finding D** (below) |
| T6 | 5 tests vs feed/_to_out | **finding E** (below) |
| T7 | 4 tests vs acknowledge/set_pinned | agree |
| T8 | 6 route tests vs 8 routes; isolation-suite interaction | agree — verified admin gets 422/404, never 403, on every new rule |
| T9 | ws cases vs queryKeys | agree |
| T10-T13 | assertions specified as prose bullets, not literal code | **finding M** (below) |

### Findings and rulings

Finding D — `test_ack_expected_snapshots_active_department_members_excluding_author`
asserts only that the author is absent. Housekeeping's sole active member in the
fixture IS the author, so `ack_expected == []` and the test passes even if the
snapshot logic were broken to always return empty. That is the vacuous-test class
the review rubric treats as a defect, and the plan mandates it.
**Ruling:** amend the plan's test to add a second active housekeeping member and
assert that member IS in `ack_expected`, keeping the author-absent assertion.
Spec §3.2 is the authority and it claims a positive denominator, which the original
test never exercises. Cost if wrong: one extra fixture user in a test; no production
impact.

Finding E — T6 `_to_out` selects every `UserAccount` and every `Department` row with
no property filter. Output cannot leak (only ids present on this property's entries
are looked up), but it loads both tables in full on every feed read, and an unscoped
query in a property-isolated codebase is a standing trap for the next editor.
**Ruling:** scope both to the property — users via `PropertyMembership`, departments
via `Department.property_id`. Cost if wrong: two extra joins per feed page.

Finding M — T10-T13 specify component-test assertions as prose bullets rather than
literal code, which the plan's own "No Placeholders" rule disallows for code steps.
**Ruling:** accept as written. The React tests need a harness wrapper copied from a
neighbouring test file that the plan does not reproduce; prescribing exact code
against an unread wrapper would be worse than prescribing exact assertions. Each
bullet names the precise assertion, and the dispatch will tell implementers the
assertion count is a floor, not a menu. Cost if wrong: weaker component tests than
intended, caught at task review.


## Fixture verification (controller, before Task 5)

Read `server/tests/fixtures.py` and checked every departmental assumption the
Task 5/6/7 tests rest on:

- `dept_engineering` has TWO active members: `engineer_a` (dept_staff) and
  `supervisor_a` (supervisor is in Engineering, not unassigned). This makes
  `test_disabled_users_are_excluded_from_the_snapshot` non-vacuous for free —
  disabling engineer_a still leaves supervisor_a in `ack_expected`, so an
  always-empty bug would fail it.
- `dept_housekeeping` has exactly one active member (`housekeeper_a`), which is
  why finding D's amendment moves `agent_a2` in.
- `dept_front_desk` has `agent_a` and `agent_a2`, so the mention fan-out test's
  "notified once, author never" assertions both bite.
- `admin_a` has no department — harmless for the isolation suite.
- `manager_a`, `admin_a`, `corporate_a` are department-less; `mentioning_me` via
  department therefore returns nothing for them, which no test relies on.

No plan corrections needed. All Task 5/6/7 test expectations hold against the
real fixture.

## Authorization on record

User instruction, this session: execute all 14 tasks, then merge `hotel-log`
onto `main`, push to the GitHub remote (https://github.com/bnfarrell/message_app),
and verify the Railway deployment picked the change up.

This grants the three things this skill would otherwise stop for: the merge, the
push to a shared branch, and the outward-facing deploy check. Do not re-ask.
Still stop for anything destructive or security-sensitive not covered above.

## Deployment facts (controller, gathered during Task 1)

Railway project `message_app` (67835e9b-cf1e-41d9-a93d-43479374b33a), production
env, service `message_app` (faee1ebb-1efd-4808-8841-81470e68d237). It auto-deploys
from GitHub `main`: the live deployment is commit 9281bea (the staff-messaging
merge), status SUCCESS, 2026-09-19T18:19Z. So the push at the end of this plan is
what triggers the deploy to verify.

**Production runs PostgreSQL, not SQLite.** The project has a `Postgres` service
(0663e14b-ba1c-454d-af25-54e62cc09a25) and the app service has `DATABASE_URL` set.
And `docker-entrypoint.sh` runs `alembic upgrade head` on every boot, before
gunicorn.

Two consequences that bind the rest of this plan:

1. Migration 0006 executes against real Postgres on the next deploy. Reviewed its
   column types for portability: `sa.JSON()` → jsonb-compatible JSON, `sa.LargeBinary`
   → BYTEA, `sa.Enum(native_enum=False, create_constraint=True)` → VARCHAR + CHECK,
   composite indexes are engine-neutral. No SQLite-only constructs. This is the
   same portability argument that put mentions in a table instead of a JSON column
   (spec §3.1) — that decision now looks load-bearing rather than merely tidy.
2. A migration failure takes the service down at boot, not just the new feature.
   Task 1's review must confirm `downgrade()` actually reverses `upgrade()`.

Ruling: no plan change. The plan's migration is already Postgres-safe; this is
recorded so the Task 1 reviewer and the final review check it deliberately rather
than assuming SQLite is the only target.

## Scope decision: Postgres everywhere (user, this session)

User: "It should all be developed to run on postgres not sql lite." Clarified via
a direct question. Chosen option: **switch dev and tests to Postgres too** — make
Postgres the only database anywhere — **after** the hotel log ships.

Agreed sequence:
1. Finish hotel log Tasks 1-14 (tests stay on SQLite for this plan).
2. Merge `hotel-log` to main, push, verify the Railway deploy.
3. Then a separate brainstorm -> spec -> plan -> build cycle for the Postgres switch.

What that future cycle has to cover, noted now while the findings are fresh so the
spec does not have to rediscover them:
- `server/app/config.py:34` defaults `DATABASE_URL` to `sqlite:///data/app.db`.
- `server/app/db.py:49-52` branches on `url.startswith("sqlite")` for
  `check_same_thread` and (line 52) further SQLite-only setup.
- `server/tests/conftest.py` gives each test a fresh DB by `shutil.copy` of a
  migrated SQLite *file*. Postgres has no file to copy; the equivalents are
  `CREATE DATABASE ... TEMPLATE` (needs a live server, slower) or wrapping each
  test in a transaction that rolls back. This is the single biggest piece of work.
- No `docker-compose.yml` exists; local Postgres has to come from somewhere.
- `psycopg[binary]>=3.2` is already a dependency (server/pyproject.toml:28), and
  pyproject already warns that a bare `postgresql://` URL resolves to psycopg2
  rather than psycopg3 — the URL scheme needs `postgresql+psycopg://`.
- `server/tools/sqlite_to_postgres.py` exists and may be obsoleted or repurposed.
- 380 backend tests must be re-verified against the new engine.

Binding on the hotel log in the meantime: no SQLite-only constructs in any new
code. Already the case (spec §3.1), and the Task 1 reviewer is checking migration
0006 against Postgres semantics.

## Postgres hosting decision (user, this session)

Local Postgres will run as a **`postgres:16` container under Docker Desktop**,
via a new `docker-compose.yml`. User chose this over a native Windows install and
over pointing tests at the Railway Postgres.

Environment facts checked on this machine:
- Docker Desktop CLI present at
  `~/AppData/Local/Programs/DockerDesktop/resources/bin/docker`, but the daemon is
  NOT running (`npipe:////./pipe/dockerDesktopLinuxEngine` missing).
- No native Postgres: no Windows service matching *postgres*, no `psql`/`pg_ctl`/
  `initdb` on PATH, no `C:\Program Files\PostgreSQL`.
- No podman.

Prerequisite for the future cycle: the user must start Docker Desktop themselves
(a GUI app this session cannot launch). `docker info` is the check.

Still deferred until after the hotel log ships. Nothing here blocks Tasks 1-14.

## Postgres version: 18, not 16

User started Docker Desktop; daemon confirmed up (server 29.7.2, linux containers).

Checked what Railway actually runs before picking a local image, and it is
**Postgres 18**: the Postgres service's source image is
`ghcr.io/railwayapp-templates/postgres-ssl:18`, live since 2026-09-12, on a 500MB
volume at /var/lib/postgresql/data in sfo. So the compose file must pin
`postgres:18`, not the 16 I suggested before checking. Pulling that image now so
the future cycle does not start with a download.

Railway's image is the `postgres-ssl` variant and has `SSL_CERT_DAYS` set, so the
production connection expects SSL while a plain local `postgres:18` container will
not offer it. The future spec has to decide how the connection URL differs between
local and Railway rather than assuming one string works in both places.

## BLOCKER: the Python venv is orphaned — no interpreter on this machine

Task 1 ran ~14 minutes without committing. Diagnosed from the controller side
while it ran; the implementer independently reached BLOCKED at the same time,
after spawning a runaway process tree of failed interpreter launches.

Root cause, not a subagent fault:

- `.venv/pyvenv.cfg` says `home = C:\Users\bryan\AppData\Local\Microsoft\WindowsApps`
  and `version = 3.14.0`. That directory holds only the Windows Store *App
  Execution Alias* stubs — `python.exe`, `python3.exe`, `pythonw.exe` are all
  **0 bytes**.
- There is no real Python install: nothing under
  `C:\Users\bryan\AppData\Local\Programs\Python`, and a recursive search for
  `python314.dll` across the user profile and both Program Files trees returns
  nothing.
- `.venv/Scripts/python.exe` is a real 255KB PE binary but ships no
  `python314.dll` beside it, so it cannot load without the base install.
- Symptom: every invocation exits 1 (or 127) printing nothing at all, including
  `python.exe -c "print('hello')"`. Silent because the Store stub swallows output
  when run non-interactively.
- `.venv/Lib/site-packages` still has 70 package directories, so this venv worked
  at some point. `pyvenv.cfg` records it was created at
  `C:\Users\bryan.farrell\Downloads\messaging_app_nw\.venv` — a different user
  profile path from the current `C:\Users\bryan\claude_code\relay`. The venv was
  moved or copied between profiles, and the base 3.14 install it points at is gone.

Consequence: NO backend work is possible — not tests, not ruff, not alembic, not
the schema export. Tasks 1-8 and 14 are all blocked. Frontend tasks 9-13 use npm
and are unaffected.

Available remedies on this machine: `winget` is present
(`AppData\Local\Microsoft\WindowsApps\winget.exe`); `uv` is not installed.
`server/pyproject.toml` requires `>=3.12`; the dead venv was 3.14.0.

Not self-resolved: installing a language runtime is a system-wide change to the
user's machine, outside this worktree, so it goes to the user rather than a
ruling.

## Environment repaired

User chose winget + Python 3.12 (matching `Dockerfile`'s `python:3.12-slim` and
ruff's `target-version = "py312"`; the dead venv's 3.14 was ahead of production).

- `winget install Python.Python.3.12 --scope user` -> Python 3.12.10 at
  `%LOCALAPPDATA%\Programs\Python\Python312\python.exe`.
- Deleted the orphaned `.venv`, recreated it from 3.12.10 at the same path, and
  `pip install -e ".[dev]"` from `server/`. All runtime + dev imports verified.
- `../.venv/Scripts/python.exe` — the command every plan and doc names — works
  again unchanged. No doc or plan edit needed for the path.
- Full suite on the rebuilt venv: **385 passed, 1 failed in 53.40s**. The 385
  include the whole pre-existing suite, so 3.12 is good for this codebase.

Ruling: plan defect in Task 1's `test_log_entry_ack_is_unique_per_user` — MINE,
not the implementer's; it transcribed the plan exactly. After `pytest.raises`
catches the IntegrityError the session is poisoned, so `database.session()`'s
commit-on-exit raises PendingRollbackError and the test fails for a reason
unrelated to the constraint under test. Plan amended to add `db.rollback()` after
the raises block, with a comment saying why. Cost if wrong: none — the assertion
under test is unchanged; only the teardown path is fixed.

Task 1 implementer (a06108d78072c30c3) was killed mid-run for the venv blocker.
Its edits are intact and uncommitted. Resuming it rather than re-dispatching: its
context is live, and the remaining work is one test-line fix plus verify + commit.

## Migration 0006 verified on REAL Postgres 18 (controller)

Not an inspection — executed. Local `postgres:18` container `relay-pg18` on
port 55432 (image matches Railway's `postgres-ssl:18` major version).

    cd server && DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_test" \
      ../.venv/Scripts/python.exe -m alembic upgrade head

`app/config.py:13 normalise_database_url` rewrote the bare `postgresql://` to
`postgresql+psycopg://`, so the provider-style URL works verbatim — same path
Railway's DATABASE_URL takes.

Results:
- Full chain 0001..0006 applies cleanly to an empty Postgres 18 database: 29 tables,
  including all four log tables.
- `\d log_entry` confirms the types came out right, not merely that DDL succeeded:
  `shift` is `character varying(32)` with CHECK constraint `ck_enum_shift` over
  ('am','pm','overnight'); `ack_expected` is real `json`; all three indexes present
  (`ix_log_entry_property_id`, `ix_log_entry_property_created`,
  `ix_log_entry_property_pinned`); all six FKs present; the three child tables
  reference `log_entry(id)`.
- **downgrade verified empirically:** `alembic downgrade 0005` drops all four log
  tables (count 0) and leaves `alembic_version = 0005`; re-running `upgrade head`
  restores 4 tables at 0006. The round trip is clean, so a failed deploy can be
  rolled back without hand-repairing the schema.

This clears the risk flagged earlier: `docker-entrypoint.sh` runs
`alembic upgrade head` before gunicorn, so a bad 0006 would have taken the whole
service down at boot, not just the log feature. It will not.

Observation for the future Postgres cycle (NOT introduced by 0006): datetime
columns land as `timestamp without time zone` — the project's `UTCDateTime` keeps
timestamps naive in the DB and enforces UTC in the application layer. Every
existing table already behaves this way, so it is a standing project decision to
revisit deliberately, not a defect of this migration.

## Frontend toolchain pre-flight (controller)

Checked ahead of Tasks 9-13 rather than discovering a second broken environment
mid-build, after the Python venv surprise.

- node v24.16.0, npm 11.13.0, `web/node_modules` present (284 entries).
- `npm test`: **599 passed across 59 files** in 44.5s.
- `npm run lint`: clean, exit 0.
- `npm run build`: succeeds in 3.85s (366.86 kB js / 108.71 kB gzip).

Baseline is green on all three. Note npm is 11.13.0, BELOW the 11.19 threshold
where install scripts get blocked by default (flagged in docs/superpowers/RESUME.md),
so that hazard does not apply here yet.

Task 9-13 acceptance therefore means: 599 + new tests passing, lint clean, build
clean. Any regression from that baseline is attributable to this plan.

## Task 1 implementer report

Status DONE. Commit aafdd7e "feat(server): hotel log tables, enums and migration 0006".
386 passed / 0 failed, ruff clean. RED->GREEN evidence in task-1-report.md.
Applied the db.rollback() plan fix exactly; 385/1 -> 386/0 confirmed it was the
only thing needed.

Two intentional deviations from the brief, both reported rather than hidden:
1. Used the column ordering + batch_alter_table style of existing migrations
   (0001/0004/0005) instead of the brief's snippet ordering. Claimed functionally
   identical.
2. Changed `log_entry_photo.data` to `nullable=False`, claiming the brief's
   `nullable=True` contradicted the model's non-Optional `Mapped[bytes]` and the
   `work_order_photo` sibling. **This is the implementer catching a real defect in
   MY plan** — the nullable=True was a copy-paste slip from staff_message.photo_data,
   where the photo genuinely is optional. A log_entry_photo row only exists when
   there IS a photo, so NOT NULL is right.

Both handed to the task reviewer to adjudicate against the real model and sibling
table rather than on the implementer's say-so.

## Postgres re-verification against COMMITTED code

The earlier Postgres run predated the implementer's nullable change, so it was
stale. Re-ran on a brand-new database (`relay_fresh`) from the committed tree:

- `alembic upgrade head` -> `alembic_version = 0006`, full chain clean on PG18.
- `\d log_entry_photo` confirms `data | bytea | not null` — deviation 2 landed
  correctly on Postgres, matching the model.

## Task 1 review

Spec ✅. Task quality: Approved. 0 Critical, 0 Important, 2 Minor.

Reviewer adjudicated both implementer deviations against the real files rather than
the report's claims, and upheld both:
1. Migration column order + batch_alter_table style — verified 0005 does place
   id/created_at/updated_at last and does wrap index ops in batch_alter_table even
   for new tables. The implementer followed the instruction "match 0005 exactly"
   better than my brief's own snippet did.
2. `log_entry_photo.data` nullable=False — verified `WorkOrderPhoto.data` is
   `nullable=False, deferred=True` for the same non-Optional `Mapped[bytes]` shape,
   while `StaffMessage.photo_data` is `Mapped[bytes | None]` and nullable. My brief
   copied the wrong sibling. SQLAlchemy 2's annotation-driven nullability already
   made the ORM column NOT NULL, so the brief would have left the DB schema more
   permissive than the model's own contract. Confirmed real defect in my plan,
   correctly fixed.

Reviewer also independently confirmed downgrade() drops in correct reverse-FK order
with every index matched, and that no construct is dialect-specific — consistent
with my own empirical PG18 round trip.

Task 1: minor (deferred): `EXPECTED_TABLES` in server/tests/test_models.py:14-21 was
not extended with the four new table names, unlike the staff-messaging slice which
did add its three. The assertion is a subset check (`<=`), so it passes today, but
`test_migration_creates_all_tables` therefore does not actually guard that 0006
created these tables — only the round-trip test proves it transitively. Cheap fix.
Task 1: minor (deferred): 0006 passes bare strings to batch_op.create_index/
drop_index where 0005 wraps names in `batch_op.f(...)`. No functional difference —
`Base` has no naming_convention in app/db.py, so op.f() is a no-op here. Cosmetic.

Task 1: complete (commits 067eac3..aafdd7e, review clean — 386/386, ruff clean,
PG18 round trip verified)

## Note: server/data/app.db is tracked ON PURPOSE

Checked because it shows as modified and would otherwise ride along on the merge.
`.gitignore`'s own header says the dummy seed database is committed deliberately —
"the data is all fixture data" — and `git log` confirms it (01572a8 committed it
intentionally). `app.db`, `app.db-shm` and `app.db-wal` are all tracked.

So this is a project convention to respect, not a defect to fix. Implementers have
been told to leave these files alone, which keeps per-task diffs clean.

Decision deferred to Task 14: that task seeds three hotel log entries, which changes
the fixture database. Per the stated convention the regenerated seed DB SHOULD then
be committed, so main carries fixture data that includes the hotel log. Will handle
it there rather than letting incidental dev churn land in a feature commit.

## Task 2 implementer report

Status DONE. Commit 7b17c8d "feat(server): derive hotel log shift from property
timezone and boundaries". 12 new tests (8-case parametrize + 4). Full suite
398 passed / 0 failed, up from the 386 baseline. Ruff clean. No concerns raised.
Review dispatched over aafdd7e..7b17c8d.
## Task 2 review

Spec ✅. Task quality: Approved. 0 Critical, 0 Important, 0 Minor.

Reviewer reasoned about the wrap independently rather than trusting the tests: the
three-way if/elif/else defines overnight as the COMPLEMENT of am and pm rather than
as an explicit wrapping range, so there is no day-boundary comparison to get wrong.
00:00-06:59 and 23:00-23:59 both fall through to `else` by construction, for any
boundary set with am < pm < overnight.

Also confirmed the timezone tests are load-bearing, not decorative: a UTC-hardcoded
implementation would classify UTC 12:00 as `am` for both the NY and LA properties,
but the test asserts LA gives `overnight` — so the bug would fail the test. Same for
the midnight-wrap test. This was the specific vacuity risk I asked about; it is real
coverage.

Task 2: observation (not a defect, no action): out-of-order custom boundaries
(am > pm) are not validated. The spec does not require it and nothing crashes — the
partition just may not match intent. Candidate for the property-settings validation
layer, not for this plan.
Task 2: note: my brief's docstring claimed 13 tests; the real count is 12 by design.
Miscount in my plan text, harmless.

Task 2: complete (commits aafdd7e..7b17c8d, review clean — 398/398, ruff clean)

## Plan amendment before Task 4 (controller)

Two fixes to Task 4's text, made while Task 3 ran:

1. Removed a hedge that violated my own no-placeholders rule: the brief said "if
   `export_json_schema` has no `__main__` entry point, read the bottom of the file
   and invoke it the way test_schema_export.py does." Checked — it HAS a `__main__`
   block calling `main(sys.argv[1] if ...)`, which writes schema.json and prints the
   path. The documented command is exactly right, so the implementer no longer has
   to work it out.

2. Added step 4b. `test_schema_export.py::test_export_contains_the_public_models`
   asserts a tuple of model names present in `$defs`, and the staff-messaging slice
   added its two (StaffConversationOut, StaffMessageOut) when it landed. My plan
   forgot the equivalent for the log models, so the test would silently stop
   guarding them. Now requires adding LogEntryOut, LogFeedOut, LogMentionableOut.

Ruling: this is the SAME class of omission the Task 1 reviewer raised as a deferred
minor (EXPECTED_TABLES in test_models.py not extended with the four new tables).
Both are "extend the existing registry test that the previous slice extended."
Catching it in the plan for Task 4 is cheaper than catching it in review. Cost if
wrong: three extra strings in a tuple.

## Task 3 implementer report + review

Commit 9aa21bc "feat: add view_log, post_log and pin_log_entry capabilities".
Backend 399 passed (from 398), frontend 601 passed (from 599), ruff + eslint clean.

Review: Spec ✅, Task quality Approved, 0 Critical / 0 Important / 0 Minor.

Reviewer went past the diff and read permissions.py, capabilities.ts and the Role
enum directly to check the two tables element-by-element — both STAFF constants
expand to the same six roles, and pin_log_entry is {supervisor, manager, admin} on
both sides. No drift.

Non-vacuity confirmed on both sides, which was the specific risk I raised:
- Python: `has_capability` is `role in CAPABILITIES.get(capability, set())`, so a
  missing key yields an empty set and the `for role in Role` loop fails on the first
  role. The test cannot pass with the capability absent.
- TypeScript: stronger still — `CAPABILITIES` is typed `Record<Capability, Role[]>`,
  so omitting a capability from the record fails compilation, and omitting it from
  the union makes the `hasCapability` call itself not type-check.
- The TS test asserts both the true and false sides of pin_log_entry.

Reviewer searched for other capability enumerations that might now be stale and
found only UI wiring (navModel.ts, CommandPalette.tsx, routes.tsx). Note for Task 13:
`routes.tsx`'s `RequireCapability` takes a hardcoded
`'manage_admin' | 'view_property_analytics'` union. Task 13 mounts /app/log with NO
RequireCapability wrapper (view_log is STAFF, everyone has it), so that union does
not need widening. If a later task ever gates a log route, it will.

Task 3: complete (commits 7b17c8d..9aa21bc, review clean — 399 backend / 601 frontend)

## Task 4 implementer report + review

Commit 28da793 "feat(server): hotel log request and response schemas".
Backend 399 (unchanged — this task extends an existing tuple rather than adding test
functions, so flat is correct), frontend 601, build clean, ruff clean.

Review: Spec ✅, Task quality Approved, 0 Critical / 0 Important / 0 Minor.

The `from_`/`from` alias risk I flagged is CLOSED, and the reviewer re-derived it
rather than trusting the implementer: `CamelModel` sets `alias_generator=to_camel`
plus `populate_by_name=True`, and Pydantic v2 gives an explicit `Field(alias=...)`
alias_priority=2 against the generator's 1, so `to_camel` never touches the field.
Confirmed by running it: `{'from': '2026-09-01'}` and `{'from_': ...}` both parse,
and `model_dump(by_alias=True)` emits `from`. The date filter will work.

Reviewer also confirmed the generated artifacts were genuinely regenerated, not
hand-edited — `types.generated.ts` still carries the json-schema-to-typescript
banner and the tool's characteristic numeric-suffixed extracted type aliases
(Departmentid8, Id13...), which nobody writes by hand; `schema.json` shows
`"maxItems": 100` on the mention lists (list bound) versus `maxLength` on body
(char bound), i.e. the bounds are on the right targets.

Task 4: complete (commits 9aa21bc..28da793, review clean)

## Ruling: whitespace-only body — routed into Task 5 in flight

The Task 4 review surfaced a real spec gap, correctly declining to count it against
Task 4: `CreateLogEntryRequest.body` is `Field(min_length=1)`, which rejects `""` but
NOT `"   "`. Spec §4.3 requires "non-empty after strip". My plan's `create()` does
`body=data.body.strip()` with no check, so a whitespace-only post would store an
empty body — a blank entry in a handover log.

Ruling: fix it in the domain layer, not the Pydantic model, matching how this
codebase already places business-rule validation (cross-property id checks and the
empty-audience downgrade both live in domain/log.py for the same reason). Sent to
the Task 5 implementer while it is still running, with the code and a test, so it
lands in the task that owns `create()` rather than becoming a fix round later.
Expected new-test count for Task 5 goes 7 -> 8, suite 406 -> 407.
Cost if wrong: one extra guard clause and one test.

## Task 5 implementer report + review

Commit 4511383 "feat(server): create hotel log entries with mention fan-out and ack
snapshot". 407 passed (399 baseline + 7 brief + 1 controller-requested whitespace
test), ruff clean. Whitespace fix folded into the single commit.

Review: Spec ✅. Task quality Approved, with 1 Important + 2 Minor — all three test
gaps, none in the implementation.

IMPORTANT: `test_disabled_users_are_excluded_from_the_snapshot` is vacuous.
dept_engineering has two active members; the test disables engineer_a and asserts
only `engineer_a not in ack_expected`. If active filtering regressed to return []
unconditionally, the assertion still holds and the test still passes. **This traces
to my brief, not the implementer** — and it is the SAME vacuous-test pattern I
caught in preflight (finding D) for the sibling test
`test_ack_expected_snapshots_active_department_members_excluding_author` and then
failed to apply to its neighbour. Third instance now of me under-specifying a test's
positive half.

Ruling: fix the Important, and fold in both Minors despite the normal rule that
minors never enter the fix loop. Justification: both are small additions to the same
test file the Important fix already opens, and both close invariants I named
explicitly when dispatching the review — direct-mention-of-author exclusion, and the
cross-call notification dedupe. Deferring them would mean reopening the same file at
final review. Cost if wrong: two extra tests.

Reviewer verified by reading (not by test) that the cross-call dedupe is genuinely
correct: `mentioned` and `expected` are each author-filtered independently, and the
ack_requested call filters `[uid for uid in expected if uid not in set(mentioned)]`.
That is real set arithmetic across two separate notify_users invocations, not
reliance on the per-call dict.fromkeys dedupe. Sound, but untested — hence Minor 3.

Reviewer also confirmed: the dropped `LogEntry` test import is genuinely unused
(grep shows no reference), the requires_ack downgrade is computed from the resolved
author-filtered list rather than the request field, and all five cross-property
validation paths are present.

Task 5: fix round 1/5 dispatched (3 findings: 1 Important, 2 Minor-by-ruling).

## CONTROLLER PROCESS ERROR: two implementers ran in parallel

I dispatched Task 5's fix round while Task 6's implementer was still running. A fix
round IS an implementation dispatch, and the skill forbids parallel implementers
precisely because of write conflicts. Both edited `server/tests/test_log_api.py`.

Task 6's implementer noticed and reported it rather than ignoring it — correct
behaviour, and the reason this was caught immediately.

Damage assessment (checked, not assumed):
- `git show --stat c2c8914` = 2 files, exactly Task 6's own (domain/log.py,
  test_log_api.py). Grepped the commit for Task 5's fix assertions
  ("supervisor_a.id in entry.ack_expected", "notified_once"): 0 hits. Task 6's
  commit did NOT absorb Task 5's in-flight work.
- Task 5's fix committed separately and cleanly as 2e4c5b5, touching only
  test_log_api.py.
- The one remaining working-tree entry, `server/app/domain/users.py`, has an EMPTY
  content diff — it is a CRLF line-ending artifact, not a change.

So: no damage this time. Luck as much as anything — the two agents happened to write
at non-overlapping moments.

Rule reasserted for the rest of this plan: exactly ONE implementer at a time,
counting fix rounds as implementers. Reviews may run in parallel with each other and
with a single implementer, since reviewers only read. Concretely, that means holding
Task 7's dispatch until Task 6's review is clean, because both touch domain/log.py
and test_log_api.py.

## Task 5 fix round 1 + Task 6 implementer report

Task 5: fix round 1/5 (3 addressed, 0 open; commit 2e4c5b5 "test(server): close
hotel log ack/mention test-coverage gaps"). 413 passed, ruff clean. Only
test_log_api.py touched; both production files byte-identical to their prior commit.
The implementer verified each new assertion by deliberately breaking the code and
confirming the test failed, then reverting: forced `active_members_of_department` to
return [], disabled the `!= author_user_id` filter, and replaced the cross-call
dedupe filter with plain `expected`. That is the right way to prove a test is not
vacuous, and it is exactly what the original tests lacked.

Task 6: commit c2c8914 "feat(server): hotel log feed with filters, cursor and pinned
block". 412 passed (407 + 5), ruff clean. DONE_WITH_CONCERNS solely for the
concurrency observation above.
Task 6: note — the implementer validated multi-page cursor walking with an ad hoc
uncommitted probe (5 entries, FEED_PAGE_SIZE monkeypatched to 2) and confirmed
correct ordering on SQLite, but the COMMITTED suite never paginates past one page.
Flagged to the reviewer to judge whether that gap is acceptable.

## Task 5 fix re-review

Scoped re-review of c2c8914..2e4c5b5: all three findings ADDRESSED, no new breakage,
no production file touched (18 insertions, test_log_api.py only). Verdict: safe.

Task 5: complete (commits 28da793..4511383 + fix 2e4c5b5, 1 Important + 2 Minor
fixed, re-review clean — 413 passing)

## Task 6 review

Spec ✅. Task quality Approved. 0 Critical, 2 Important, 4 Minor. Implementation
correct — the reviewer verified the two riskiest parts empirically with throwaway
scripts against the real models rather than reasoning from the diff:
- Cursor: built 5 rows a minute apart, took the 3rd row's cursor, got exactly the
  right 2 remaining rows in order. `<` is the correct direction for DESC,DESC, and
  `next_cursor` comes from the last row of the RETURNED page (index 49 of 51
  fetched), not the lookahead row.
- Timezone: an entry at 23:30 America/New_York (03:30 UTC next day) is correctly
  included by `from=to=<that local date>`. No aware/naive mismatch, because
  UTCDateTime binds aware values — including the tuple_() cursor elements — to
  naive UTC at bind time. That was the "green in dev, broken in prod" risk I named.
- `_to_out`: 5 batched queries per call, no N+1, property scoping present as ruled
  in preflight finding E.

IMPORTANT 1: cursor pagination past page 1 never executes in CI (3 rows vs
FEED_PAGE_SIZE 50), so the decode path was proven only by an uncommitted probe.
IMPORTANT 2: `test_mentioning_me_matches_direct_and_department_mentions` cannot
distinguish correct department scoping from an implementation that matches ANY
department mention, because the viewer belongs to the only department tested. Same
vacuity class as Task 5's Important — fourth instance of my briefs specifying a test
that cannot fail the way it is meant to.

Ruling: fix both Importants, plus Minor "the property-leak test ignores the pinned
block" folded in (one line in a test already being edited, and it closes a
property-isolation hole rather than a cosmetic one). Deferred: double _to_out
batching on pinned pages, missing id tie-break on the pinned query, and the
untested `can_ack == False after acking` branch — the last handed to Task 7, which
owns acking.

Task 6: fix round 1/5 dispatched, commit 068aed0 landed.

## Merge path checked early

`git log main..HEAD` = 11 commits, `git log HEAD..main` = 0. main has not moved since
this branch was cut, so the final merge is a fast-forward with no conflict surface.

## Task 6 fix round 1 + re-review

Task 6: fix round 1/5 (3 addressed, 0 open; commit 068aed0 "test(server): cover
cursor pagination, department scoping and pinned isolation"). 414 passed, ruff clean.
Only test_log_api.py touched.

Implementer sabotage-verified all three, reverting each:
1. cursor index off-by-one (rows[FEED_PAGE_SIZE] vs rows[FEED_PAGE_SIZE - 1]) ->
   pagination test failed, skipping "note 2".
2. department EXISTS arm broadened to match any department mention ->
   mentioning_me test failed, "other dept" leaked into the set.
3. property_id filter removed from the pinned query -> property-leak test failed,
   property B's pinned entry appeared in property A's pinned block.

Re-review: all three ADDRESSED, no production file in the diff, no new breakage.
Specifically confirmed the monkeypatch targets `log_domain.FEED_PAGE_SIZE` — the
namespace `feed()` resolves at runtime — and not `app.schemas.log`'s copy. Patching
the wrong module's constant would have made the test quietly exercise a single page
again and re-open the very gap it was written to close.

Task 6: complete (commits 4511383..c2c8914 + fix 068aed0, 2 Important + 1 Minor
fixed, re-review clean — 414 passing)

## Controller housekeeping

Committed 6fdc803: my own Task 4 plan amendment, written earlier and left
uncommitted, which is what the task agents kept reporting as unexplained
working-tree churn. `server/app/domain/users.py` remains "modified" with an EMPTY
content diff — a CRLF artifact only, not a change; leaving it alone.

## Task 7 implementer report + review

Commit d85d137 "feat(server): acknowledge and pin hotel log entries". 418 passed
(414 + 4), ruff clean. Sabotage-verified all four tests unprompted-by-review, because
the dispatch demanded it up front: idempotency guard removed -> IntegrityError;
Forbidden check removed (twice) -> DID NOT RAISE; set_pinned neutered -> [] vs
['pin me']. Also closed Task 6's carried-forward gap (can_ack False / acked_by_me
True after acking). No vacuous-test finding this round — moving the requirement into
the dispatch prevented the defect instead of catching it.

Review: Spec ✅. Task quality **Needs fixes** — 2 Important, 0 Critical, 0 Minor.
Production code confirmed correct; both findings are coverage gaps.

IMPORTANT 1: `test_acknowledging_twice_is_idempotent` asserts only that the
LogEntryAck row count stays 1. It never checks AuditLog or the queued events. Spec §9
lists "does not duplicate, does not re-audit" as the requirement. A bug that moved
`audit.record()`/`queue_event()` ABOVE the `existing` guard would re-audit and
re-fire on every repeat call while the DB unique constraint still kept the row count
at 1 — and all four tests would pass. The codebase already has the pattern for
asserting this (test_work_order_photos.py:75-76, test_send.py:129-130).

IMPORTANT 2: `set_pinned`'s no-op guard (`if entry.pinned == pinned: return entry`)
is never exercised — the test only calls it on transitions False->True->False, never
with the state already at the target. Sabotage 3 targeted the state-changing lines,
not this guard. The reviewer judged (rather than merely noting) that skipping
audit/event on a true no-op is correct behaviour, consistent with acknowledge()'s
idempotency, but that it must be proven: a variant that re-audits on a redundant
call, or that drops the guard and lets a second pinner silently overwrite
`pinned_by_user_id`, passes every current test.

Reviewer also independently confirmed the event-safety property I asked about:
`queue_event` only appends to `db.info["events"]`, with delivery in
`Database.session()` after commit, so nothing is ever broadcast for a change that
could still roll back.

HOLDING the fix round: Task 8's implementer is live and edits the same
`server/tests/test_log_api.py`. Dispatching now would repeat the parallel-implementer
conflict I hit between Task 5's fix and Task 6. Fix goes out once Task 8 reports.

## Task 7 fix round 1 + re-review

Fix commit 82e4343 "test(server): close two hotel-log ack/pin coverage gaps".
424 passed, ruff clean, only test_log_api.py touched (22 insertions, 1 deletion) —
no production change was needed.

Sabotage-verified both, reverting each:
1. moved audit.record()/queue_event() above the idempotency guard -> new assertion
   failed (assert 2 == 1).
2. deleted the `if entry.pinned == pinned` no-op guard -> new assertion failed
   (assert 2 == 1).

Re-review: both ADDRESSED. Finding 2 carries BOTH required assertions — audit count
stays 1 AND `pinned_by_user_id` still holds the original pinner, the second being
the one that catches a dropped guard letting a later pinner silently steal
attribution. Re-reviewer also confirmed the event assertion is real rather than
vacuous: `db.info["events"]` is observable mid-test because delivery happens only
after the session's `with` block completes.

Task 7: complete (commits 5dc88ec..d85d137 + fix 82e4343, 2 Important fixed,
re-review clean — 424 passing)

## Task 8 implementer report + review

Commit 2bc7b70 "feat(server): hotel log API routes". 424 passed (418 + 6),
test_isolation.py 7/7, ruff clean. Seven sabotages, all reverted — including one I
did not ask for: stripping Role.admin from pin_log_entry to prove the isolation
suite's admin clause genuinely covers the NEW pin/unpin routes rather than passing
by default.

Review: Spec ✅ on all eight routes. Task quality **Needs fixes** — 1 Important,
1 Minor. Reviewer independently confirmed decorator order is correct on all eight
(auth -> property -> capability, so g.membership is set before any capability read),
photo isolation 404s before any blob read, the MAX_PHOTO_BYTES boundary is exact,
the 405 immutability assertion is meaningful rather than vacuous, and /mentionables
cannot be swallowed by the id converter.

IMPORTANT (mine): `get_entry_photo` sets only Cache-Control. The sibling it was told
to mirror (api/staff_messages.py:94) sets three headers. The missing
`X-Content-Type-Options: nosniff` matters on a route serving user-uploaded bytes
whose content type the uploader influences — it is what stops a polyglot file that
is both a valid image and valid HTML/JS from being rendered as markup. **No test
could have caught this**: test_photo_round_trips asserts status and bytes, never
headers. This is the reviewer answering the question I posed — find a plausible bug
none of the six tests would catch.

MINOR, ruled IN rather than deferred (mine): no `request.content_length` pre-check,
and no MAX_CONTENT_LENGTH configured app-wide (verified by grep). Werkzeug therefore
buffers an arbitrarily large upload in full before the truncated read runs — the
truncated read protects the database, not the process. Same function, and a
resource-exhaustion vector rather than cosmetics, so worth the round.

Plan corrected at e93ba30 so neither defect propagates. Note: my first attempt
imported MULTIPART_OVERHEAD_BYTES from the domain layer; it is actually defined
per-api-module (staff_messages.py:47, work_orders.py:22), so the plan now defines it
locally per convention.

Task 8: fix round 1/5 dispatched.

## Task 8 fix round 1 + re-review — BACKEND COMPLETE

Fix commit 46c6600 "fix(server): harden hotel log photo route". 425 passed
(424 + 1), isolation 7/7, ruff clean.

Re-review: both findings ADDRESSED.
- All three headers present on get_entry_photo and asserted by the test — the old
  test checked only status and bytes, which is exactly why the gap was invisible.
- The size guard is genuinely the FIRST statement in create_entry, before
  parse_body. Position matters: after parse_body the buffering has already happened
  and the guard would be decorative.

On the implementer's docstring correction — it borrowed the sibling test's rationale
("an unguarded oversized upload yields a confusing pydantic 400"), then its own
sabotage run disproved it for this codebase: Werkzeug 3.1's max_form_memory_size
(500KB/field) raises its own 413 first. It corrected the docstring rather than leave
a plausible-but-false explanation next to passing code. Re-reviewer confirms the
corrected docstring is accurate, and — the question I actually asked — that the
guard still earns its place: it produces this endpoint's own 400/VALIDATION_FAILED
shape instead of Werkzeug's bare 413, so it is error-shaping, not dead code. Good
outcome; the alternative was shipping a guard nobody could justify.

Re-reviewer also confirmed the substituted oversized-field test exercises the same
path as the infeasible "lying Content-Length" test would have.

Task 8: complete (commits d85d137..2bc7b70 + fix 46c6600, 1 Important + 1 Minor
fixed, re-review clean — 425 passing, isolation 7/7)

**BACKEND COMPLETE: Tasks 1-8 all done and reviewed. 425 tests, isolation 7/7,
ruff clean, migration verified on real Postgres 18 with a clean downgrade.**

Pattern worth recording for the final review and for future plans: across all eight
backend tasks, EVERY Important finding traced to my plan text, not to an
implementer. Four vacuous tests, a wrong status code (422 vs 400), a nullable=True
copied from the wrong sibling, two missing registry-test steps, and a missing
nosniff header. The implementers transcribed faithfully throughout. The single
highest-leverage change was moving the sabotage requirement into the dispatch
prompt from Task 7 onward — after that, no further vacuous tests were written.

## Task 9 implementer report + review

Commit 325cfcb "feat(web): hotel log query hooks and realtime invalidation".
web 603 (from 601), server 426 (from 425), lint + build clean.

Review: Spec ✅ on all six hooks, four query keys, two realtime cases and the
backend validator. Task quality **Needs fixes** — 1 Important, 2 Minor.

IMPORTANT (mine, from the plan's Step 5 snippet): the multipart branch of
`useCreateLogEntry` enumerates fields by hand and omits `linkedWorkOrderId` and
`linkedConversationId`, while the JSON branch spreads `rest` wholesale and sends
them. An entry that both links a work order and attaches a photo persists with no
link, silently. This is exactly the divergence I asked the reviewer to hunt for when
dispatching — the split invites it and no test catches it. Nothing exercises it
today because the composer lands in Task 11, which is why catching it now matters.
Plan corrected.

MINOR: `types.ts:14` alphabetization regression — LogEntryOut/LogFeedOut/
LogMentionableOut sort BEFORE LoginRequest ("Log"+E/F/M < "Log"+i) but were appended
after. Worth fixing rather than waving through: this project has a dedicated commit
from the same day for exactly this drift (8acbf4a "fix(web): correct alphabetical
ordering in types.ts exports").
MINOR: no negative test for malformed JSON in the multipart validator. The reviewer
verified the behaviour independently with a standalone pydantic repro — a
JSONDecodeError is a ValueError subclass, so pydantic wraps it into a clean
ValidationError and parse_body returns 400, never a 500. Correct, but untested.

Reviewer also confirmed the uninstructed `types.ts` change was genuinely required
(the barrel is hand-maintained; git log shows codegen has never touched it) and used
the established pattern rather than inventing one. And it verified the two things
that would have been expensive to get wrong: `logFeedAll` IS a genuine array-prefix
of `logFeed`, so TanStack's partial-match invalidation catches filtered views; and
the ack/pin `setQueryData` writes use the identical key shape `useLogEntry` reads.

HOLDING the fix round — Task 10's implementer is live. Dispatch once it reports.

## Task 10 implementer report + review

Commit 9e54a71 "feat(web): mention picker that records ids rather than names".
609 passed (603 + 6: the brief's 3 verbatim plus 3 added for keyboard nav, Escape
and de-dup, because the dispatch said the brief's list was a floor). Lint + build
clean. Sabotage: recording displayName instead of id failed 4 of 6 tests.

Review: Spec ✅ on the full exported contract Tasks 11/12 depend on. Task quality
**Needs fixes** — 1 Important, 2 Minor advisories.

IMPORTANT — and notably the FIRST finding this run that is a real implementation
bug rather than a defect in my plan text. `pick()` computes the replacement range
from a stale `query.start` combined with the LIVE caret position. `query` is only
recomputed in `handleChange`, which fires on value changes — moving the caret with
ArrowLeft/Home/a click fires no onChange, so `query` goes stale while
`ref.current.selectionStart` moves. Reviewer's concrete repro: type "@Ana" (caret 4,
query.start 0), press ArrowLeft twice (caret 2), click "Ana Marquez" in the
still-open listbox -> text becomes `@[Ana Marquez](user:u1)na`, with a stray "na"
from the un-replaced tail. All six tests pick immediately after typing with the
caret still at the end of the query, so none reach this path. Fix: slice using the
query's own recorded extent, or invalidate the query on caret movement.

MINOR (advisory, carry to Task 12): `TOKEN_RE` carries the `g` flag. Nothing in this
diff calls .test()/.exec() on the shared module-level instance so there is no bug
yet, but if Task 12 uses .exec()/.test() in a loop rather than split()/matchAll(),
`lastIndex` persists across calls and silently yields false negatives on alternate
invocations. Task 12's review must check this specifically.

MINOR (advisory, carry to Task 11): nothing prunes `mentions` when a user backspaces
through a token's visible text. A deleted mention can still fire a log.mention
notification per §6. Out of Task 10's contracted scope — the brief never asked —
but somebody must own it before submission is wired. Assigning to Task 11.

Reviewer confirmed the two correspondence risks I raised are non-issues, by hand-
tracing rather than assertion: TOKEN_RE's `[^\]]+` correctly captures display names
with spaces, hyphens and apostrophes ("Ana Maria-Bonilla", "O'Brien"), and
`[0-9a-f-]{36}` exactly matches this codebase's `str(uuid.uuid4())` id format. Also
confirmed `noUncheckedIndexedAccess: true` is real in web/tsconfig.json:12 and the
`OPTIONS[1]!` idiom matches existing suite usage.

HOLDING Task 10's fix — Task 9's fix implementer is live on overlapping frontend
files. Dispatch when it reports.

## Task 10 fix round 1 + re-review

Fix commit a341f44 "fix(web): stop MentionInput desyncing the caret from a stale
query". 611 passed (610 + 1), lint + build clean.

Implementer chose the extent-based slice over the onSelect/refresh alternative and
justified it: no new event wiring, and it avoids the listbox-closing footgun the
review itself flagged with that route. Reproduced the exact corrupted string
`@[Ana Marquez](user:u1)na` in RED before fixing.

Re-review: ADDRESSED. Re-reviewer did its own arithmetic trace rather than trusting
the formula — `"@Ana"` gives queryEnd 4 (no stray tail) and `"note @Ana"` gives
queryEnd 9 with leading text preserved, so the `+ 1` correctly accounts for the `@`.
Confirmed the test uses an exact-value assertion (`toBe(tokenFor(...))`) rather than
a `toContain`, which would have passed on the corrupted output too. The TOKEN_RE
doc comment is present and names the `g`-flag/lastIndex hazard with the safe
alternatives. Mention-pruning correctly left for Task 11. Five pre-existing tests
unmodified.

Task 10: complete (commits 22cfb83..9e54a71 + fix a341f44, 1 Important fixed,
re-review clean — 611 passing)

## Task 9 fix round 1 + re-review — and a latent production 500 found and fixed

Fix commit 53ec9bf "fix(web,server): review fixes for hotel log data layer".
web 610, server 427, lint + build + ruff clean. All three findings ADDRESSED.

**The Minor test I asked for as an afterthought uncovered a real production bug.**
Writing a negative test for malformed JSON in a multipart `mentions` field revealed
that pydantic embeds the raised exception OBJECT in `ValidationError.errors()`'s
`ctx` when a mode="before" validator raises — and `jsonify()` cannot serialize it.
A 400 became an unhandled 500. Fixed with `include_context=False` in
`app/api/_util.py::parse_body`, alongside the existing `include_input=False`.

This was a KNOWN deferred risk: docs/superpowers/RESUME.md's open items already said
"`_pydantic_error` may hit non-serializable values in a validation `ctx`". It sat
theoretical since Phase 1. The hotel log's multipart path made it reachable and a
throwaway negative test proved it real.

The re-reviewer did not take any of this on trust — it independently reverted the
one-line fix and reproduced `TypeError: Object of type JSONDecodeError is not JSON
serializable`, then restored. It also:
- Confirmed nothing is lost: grepped web/src for readers of the error payload;
  `fieldErrors.ts` reads only `loc` and `msg`, `ctx` appears solely in test
  fixtures. Dropping ctx breaks nothing.
- Confirmed the FormData test genuinely inspects `init.body` rather than asserting
  the mutation resolved, by removing the two `form.set` lines and watching it fail
  with `expected null to be 'wo-1'`.
- Ruled on the two unfixed sibling sites by GREPPING rather than reasoning: the
  validator added in this diff is the ONLY custom validator in the entire schemas
  package. pydantic only stuffs a raw exception into ctx when a field/model
  validator raises, so `parse_query` cannot hit it today; and test_errors.py
  documents that `_pydantic_error` is only reached by a ValidationError escaping a
  view, which cannot happen for a model always parsed through parse_body. Both
  genuinely unreachable.

CARRY TO FINAL REVIEW / USER: leaving `parse_query` and `app/errors.py:89`
unhardened is correct today but is consistency debt — the next validator added
anywhere in the schemas package, or any route bypassing parse_body, reintroduces the
identical crash. Recommend a tracked follow-up rather than a silent gap.

Task 9: complete (commits 46c6600..325cfcb + fix 53ec9bf, 1 Important + 2 Minor
fixed, re-review clean — web 610 / server 427)

## Ruling: log day-grouping follows the viewer's timezone, not the property's

Found while verifying Task 13's assumptions before dispatch. The brief said "day
grouping uses the property timezone. Read how board/ formats dates and reuse that
helper." Both halves were wrong:
- There is NO day-grouping helper anywhere. web/src/lib/time.ts has relativeTime,
  formatClock, formatCountdown, formatDuration — none group by day.
- The property timezone is not plumbed into ANY display component. formatClock
  calls `toLocaleTimeString([])` with no zone argument, so every timestamp already
  in this product renders in the viewer's local zone.

Ruling: group by the VIEWER's local day, adding a small `dayKey(iso)` to
web/src/lib/time.ts. This departs from spec §7's wording, deliberately.

Reasoning: making this one screen group by property time would put it at odds with
every other timestamp in the product, and would require new plumbing to get
property settings into the feed — for a discrepancy that only appears when staff
view the log from outside the hotel's timezone, which is rare given they are
physically on-site.

What is NOT affected: the shift badge is computed server-side from the property
timezone and frozen on the row (spec §3.3), so shift labelling stays authoritative
no matter who is looking. Only the visual day heading follows the viewer.

Cost if wrong: a hotel whose staff routinely work remotely across timezones would
see entries grouped under their own day rather than the hotel's. Reversible — the
fix is to plumb property.timezone into the feed and pass it to dayKey.

## Task 11 implementer report + review

First attempt (ae78d814) STALLED — watchdog killed it after 600s with no progress,
right after it confirmed the baseline. Verified it had written nothing (git log
unchanged, no new files in features/log/, clean tree) and re-dispatched fresh with
an added instruction to work incrementally and prefer BLOCKED over stalling.

Commit cf76a3d "feat(web): hotel log composer". 617 passed (611 + 6: the brief's 5
plus the carried-forward pruning test), lint + build clean, 6 sabotage cycles.

Review: Spec ✅. Task quality **Approved**. 0 Critical, 0 Important, 2 Minor.

The carried-forward mention-pruning defect is properly closed, and better than I
asked: `pruneMentions` uses `text.matchAll(TOKEN_RE)` — the g-flag-safe form —
AND it is applied to `ackAudience` as well as `mentions`, closing the subtler
version of the bug I only hinted at. Reviewer confirmed matchAll clones the regex
and never writes back to the source's lastIndex, and grepped to confirm TOKEN_RE
has no .test()/.exec() call site anywhere.

Reviewer also confirmed the reset is complete and success-driven, including
clearing the file input's DOM value via a ref (React state alone cannot clear a
file input) — the exact gap staff messaging shipped.

SIXTH plan defect, found by the implementer: my brief pointed at
`web/src/api/hooks/properties.ts` for the departments hook. `useDepartments`
actually lives in `web/src/api/hooks/users.ts`. It grepped every consumer to
confirm before deviating, and disclosed it. Same root cause as the others — a
pointer I wrote from memory instead of checking.

Task 11: minor (deferred): unchecking the ack toggle WITHOUT submitting has no
direct test — the clearing behaviour is only exercised through the full
success-reset path. Code path read and believed correct.
Task 11: minor (deferred): multi-mention partial pruning untested — no case with
two mentions where one token is deleted and the other survives. pruneMentions is a
per-item Set filter so likely correct by inspection, but the most convincing case
is unexercised.

Reviewer ran the independent bug hunt I asked for — double-submit races, Enter-key
interaction between the autocomplete and the surrounding form, stale errors across
retries, empty ackAudience with requiresAck true (server already forces
requires_ack=false per §3.2), mention/department-tag overlap — and reported plainly
that it could not find a genuine functional bug rather than inventing one.

Task 11: complete (commits 72cb788..cf76a3d, review clean — 617 passing)

## Task 12 implementer report + review

Commit b106c44 "feat(web): hotel log entry card and acknowledgement bar".
632 passed (617 + 15: 6 AckBar + 9 LogEntryCard), lint + build clean.
Four sabotages: XSS via dangerouslySetInnerHTML, the pin capability gate, the
g-flag hazard via a single TOKEN_RE.exec(), plus an unrequested canAck-trust check.

Review: Spec ✅. Task quality **Approved**. 0 Critical, 0 Important, 2 Minor.

The g-flag hazard is genuinely closed, and the reviewer proved it by tracing rather
than trusting: `renderBody` uses `body.matchAll(TOKEN_RE)`, which clones the regex
and never touches the shared instance's lastIndex. It then verified the mandated
two-entry test WOULD fail against an .exec()-based implementation — a single-shot
exec leaves lastIndex set after the first card, so the second card starts searching
from a stale offset and misses, producing exactly the "renders on first paint, raw
token text later" symptom. That test only exists because the dispatch required
rendering two entries in one pass; a single-render test cannot catch this.

It also hand-traced the three split shapes I asked about, all correct with no
off-by-one: no mentions (whole string as one text node), body that is only a
mention (no leading or trailing empty node), and two adjacent mentions (no empty
node between them, distinct keys).

Confirmed AckBar trusts the server-computed `canAck`/`ackedByMe` rather than
recomputing from ack_expected — which matters because a client recomputation would
drift from the frozen-snapshot semantics of §3.2.

Judgement calls upheld: the native `<progress>` element is the right choice since
board/ genuinely has no progress-bar precedent, so inventing a bespoke Tailwind bar
would have been the actual violation of "don't invent a visual language".

Task 12: minor (deferred): footer work-order/conversation links have no test. Hrefs
independently verified correct against routes.tsx; implementation right, just not
locked down.
Task 12: minor (deferred): the shift badge and department badge both use Badge's
default `neutral` tone, so they are visually indistinguishable in the header row.
Cosmetic, no spec requirement — worth raising with the user as a design question
rather than fixing blind.

Task 12: complete (commits 76fb5ff..b106c44, review clean — 632 passing)

## Task 14 run-the-app facts (controller, gathered ahead of dispatch)

From start.bat, so its implementer does not have to reverse-engineer them:

- API: `.venv\Scripts\python.exe server\dev_start.py` -> http://127.0.0.1:5200.
  It migrates, seeds if the DB is empty, and runs the job worker and SLA sweep.
- Web: `cd web && npm run dev` -> http://127.0.0.1:5173, proxying /api, /ws and /a
  to the API. **The API alone serves no pages** — GET / is a 404 by design — so
  starting only one half looks like "nothing happens".
- Seeded logins: `ava@hvh.test` / `Password123!` (agent, lands in Inbox) and
  `alex@hvh.test` / `Password123!` (admin). Both from the seed, not the test fixture.

## Pre-existing trap worth surfacing to the user (NOT fixing — unrelated to this plan)

The root `package.json` scripts invoke bare `python`:
  "server": "cd server && python run.py"
  "seed":   "cd server && python -m seed.seed"
  "test:server", "schema" — same.

Bare `python` on this machine is the 0-byte Windows Store alias stub that exits
silently, which is exactly the failure that cost ~14 minutes at Task 1. So every
one of those npm scripts is currently broken here, and fails in the most confusing
way possible: no output, no error.

`start.bat` is unaffected — it correctly uses `.venv\Scripts\python.exe` and even
checks the venv exists first.

Not fixing: unrelated to the hotel log, and CLAUDE.md §Environment now documents
the correct invocation. Raising it with the user instead, since we just wrote the
opposite convention into CLAUDE.md and the mismatch is now visible.

## Task 13 implementer report + review — ALL BUILD TASKS COMPLETE

Commit d557733 "feat(web): assemble the hotel log page". 643 passed (632 + 11:
7 LogPage, 3 dayKey, 1 navModel), lint + build clean, 8 sabotage cycles.

Review: Spec ✅. Task quality **Approved**. 0 Critical, 0 Important, 1 Minor.

The thing I most wanted checked came back clean: the implementer modified two
PRE-EXISTING tests (AppShell.test.tsx, CommandPalette.test.tsx) that hardcoded the
nav list for a no-capability role. The reviewer confirmed both keep their exact
`toEqual([...])` assertions and merely insert 'Log' at the right position — neither
was loosened to `toContain`, and no count check was dropped. A weakened assertion
there would have silently stopped guarding the nav model for every role.

`dayKey` is correctly local-day based (getFullYear/getMonth/getDate, not UTC getters
or an ISO slice), so the viewer-local grouping ruling is implemented as ruled rather
than as a UTC approximation that happens to pass in a UTC test environment. The
sabotage swapping to UTC getters broke 2 of 3 tests.

Filters were verified to reach the actual outgoing request — the tests assert the
mocked fetch URL contains `shift=overnight` / `mentioningMe=true` against a real
QueryClient, not react-internal state with a mocked hook.

Reviewer noted one harmless inaccuracy in the implementer's report: it credited
"MessagesPage's pattern" for the loading/error states, but that pattern actually
lives in NotificationsPage. The code is right; only the attribution was off.

Task 13: minor (deferred): the page's filter <select> is labelled "Department" and
LogComposer's tag field is ALSO labelled "Department", both rendering on the page at
once. `getByLabelText('Department')` is now ambiguous, and a screen-reader user
hears two identically-named controls. Accessibility/testability nit, not functional.

Task 13: complete (commits 3a0d163..d557733, review clean — 643 passing)

**ALL 13 BUILD TASKS COMPLETE AND REVIEWED. Task 14 (seed + browser verification)
in flight. Server 427, web 643, isolation 7/7, lint/build/ruff clean.**

## Pre-merge state check (controller, while Task 14 runs)

Branch: 30 commits on `hotel-log`, merge-base `a97086b`. The spec and plan commits
are already on main (they were committed before the branch was cut), so the branch
carries implementation only. Fast-forward merge, no conflict surface.

Deferred minors for the final review to triage: 7
  T1 EXPECTED_TABLES not extended with the four new tables
  T1 migration passes bare strings where 0005 wraps in batch_op.f() (no-op here)
  T11 unchecking the ack toggle without submitting is untested
  T11 multi-mention partial pruning untested
  T12 footer work-order/conversation links untested (hrefs verified by inspection)
  T12 shift and department badges share Badge's default neutral tone (cosmetic)
  T13 duplicate "Department" label on filter and composer (a11y/testability)

Plus one cross-cutting item that is NOT a task minor: `parse_query` and
`app/errors.py:89` still call `errors()` without `include_context=False`. Confirmed
unreachable today (the only custom validator in the schemas package is the one added
in Task 9), but the next validator anywhere reintroduces the identical 500.

Rulings recorded: 12.

**Working-tree items that pre-date this work and must NOT ride along on the merge:**
- `server/app/domain/users.py` — modified with an EMPTY content diff (CRLF artifact).
- `two.png` — deleted before this session started.
- `.claude/` (2.0K) and `images/` (1.7M) — untracked. `images/` holds the Kipsu
  reference screenshots this whole feature was derived from; whether to commit them
  is the user's call and unrelated to this plan.
- `server/seed/seed.py` and `server/tests/test_seed.py` are currently modified —
  that is Task 14 in flight, and will be its commit.

At merge time: merge the branch only. Do not `git add -A`.

## Task 14 — seed + full-stack verification: 8 of 8 acceptance criteria PASS

Commit 99e7e89 "feat(server): seed hotel log entries for development".
Server 427 passed, ruff clean; web 643 unaffected.

**All eight of spec §10's acceptance criteria verified LIVE** against a real running
server and a Playwright-driven browser — the only end-to-end exercise in this whole
plan, and the only place a real integration failure could have surfaced.

Notes on how two were proven, recorded so the evidence is not overstated:
- AC2 (realtime) was demonstrated with two browser tabs on the SAME account,
  because the harness shares one cookie jar and no incognito-context tool was
  available. Still a genuine two-socket test of a property-scoped broadcast, but it
  is not literally "another user's session".
- The reseeded `server/data/app.db*` was deliberately NOT committed, matching the
  brief's own `git add` list.

**Defect found by verification, being fixed before merge:** `log.mention` and
`log.ack_requested` notification bodies pass `entry.body[:140]` raw, so recipients
see internal markup — "AM CHECKLIST … @[Hana Keeper](user:3f2a…) please check 327".
Cosmetic in that nothing breaks, but it is user-facing, hits EVERY mention
notification, and notifications are often the only part of an entry somebody reads.

Ruling: fix it now rather than deferring to the final review's fix wave, so the
whole-branch review reads corrected code. The fix collapses tokens to display names
for the notification body only — the stored body keeps its tokens, since the web
client renders them from the ids (§6.1). Truncation must happen AFTER substitution:
slicing first can cut a token in half and leave "@[Hana Kee". Cost if wrong: a
regex and two tests, no schema or contract change.

This is the payoff for insisting on real browser verification rather than trusting
643 green unit tests. No unit test would ever have caught it — every one of them
asserts on ids and structure, not on what a human reads.

## Task 14 review — ALL 14 TASKS COMPLETE

Commits 99e7e89 (seed) + aae1814 (notification fix). Review: Spec ✅, Task quality
**Approved**, 0 Critical, 0 Important, 2 Minor.

Both things I asked it to check hardest came back genuine, not nominal:

- **Shift values are real.** The seed bypasses `create()` entirely and calls
  `shift_for(hvh, <explicit local time>)` with hand-picked historical timestamps
  (07:30 / 15:30 / 02:00 yesterday). So the am/pm/overnight spread is actually
  derived, not three entries all stamped with whatever shift the seed run happened
  to fall in — the exact trap I warned about, which the implementer anticipated.
- **The overnight entry's audience is genuinely non-empty**: `ack_expected` holds
  the three real active Housekeeping members (2 dept_staff + 1 supervisor), so the
  §3.2 empty-audience downgrade never fired and the UI shows a real outstanding
  list on first load.

Regex agreement confirmed character-for-character between the new backend
`_MENTION_TOKEN` and the frontend `TOKEN_RE` — identical on every matching
construct; the only difference is capturing vs non-capturing groups, which affects
extraction, not matching.

**CORRECTION to my own earlier ledger entry.** I recorded Task 14's framing that the
two-tab realtime check was "a genuine two-socket test of a property-scoped
broadcast". The reviewer is right that this overreaches: two tabs on ONE account on
ONE property demonstrate same-property realtime delivery, and nothing more. Proving
*scoping* would require a second property's session receiving nothing. AC2 as
written in the brief ("a post from one appears in the other with no refresh") IS
met — but the scoping claim was not demonstrated and I should not have repeated it.
Property isolation is separately proven by test_isolation.py and AC8, so nothing is
actually unverified; only my wording was wrong.

Task 14: minor (deferred): the cross-reference comment on `_MENTION_TOKEN` says
"including the 36-char UUID id group", implying the backend captures it; it is
non-capturing by design. Wording only.
Task 14: minor (deferred): task-14-report.md repeats the AC2 overstatement above.

Task 14: complete (commits d557733..aae1814, review clean — 429 server / 643 web)

## Controller-run verification before the final review

Ran both suites myself rather than trusting the reports:
  server: 429 passed in 56.27s, `ruff check .` -> All checks passed!
  web:    643 passed across 65 files, eslint clean, build clean (379.38 kB)

## Push scope — corrected

`origin/main` is at **9281bea** (the staff-messaging merge), which is also what
Railway currently runs. Local `main` is at a97086b, TWO commits ahead and unpushed:
  4798727 docs: hotel log (posts) design spec
  a97086b docs: hotel log implementation plan (14 tasks)

Those were committed to main before the branch was cut, so they never went out.

So the push will carry **35 commits**, not the 33 on the branch: the 2 unpushed doc
commits plus the 33 implementation commits. Worth stating precisely — I have been
saying "33" to the user, which undercounts what actually reaches GitHub.

Remote confirmed: origin = https://github.com/bnfarrell/message_app.git, main
tracks origin/main.

## Railway deploy path confirmed (pre-push)

Service `message_app` source: repo `bnfarrell/message_app`, branch `main` — so a
push to main auto-deploys. No manual trigger needed.

Live URL: https://messageapp-production-361b.up.railway.app
Current deployment: 8278a983, SUCCESS, 2026-09-19T18:18Z, commit 9281bea.
Region sfo, 1 replica (correct — presence, the WS registry and the job worker are
all in-process, so a second replica would split presence and double-process jobs).

**One thing to verify in the deploy logs rather than assume.** The service config
reports `builder: RAILPACK`, but `railway.json` declares
`"builder": "DOCKERFILE"`. railway.json should take precedence at build time, and
it must — the Dockerfile's `docker-entrypoint.sh` is what runs
`alembic upgrade head`. If RAILPACK won instead, migrations would never run and
migration 0006 would not apply, leaving the app querying tables that do not exist.

Evidence it currently works the right way: staff messaging's migration 0005 is live
and the app functions, which it could not do without the entrypoint running. So the
Dockerfile IS being used.

**Post-push check:** confirm `==> alembic upgrade head` appears in the deploy logs
before `==> gunicorn on :$PORT`. That single line is the proof that 0006 applied to
production Postgres 18. Do not declare the deploy healthy on build success alone.

## FINAL WHOLE-BRANCH REVIEW (opus, 33 commits, 3504 hand-written lines)

Verdict: **FIX FIRST — three items**, then ship. One fix wave dispatched.

1. IMPORTANT, a real bug: `LogEntryCard.tsx:70` links a GUEST conversation id to
   `/app/messages/:id`, which resolves to MessagesPage and reads the param as a
   StaffConversation id. `linked_conversation_id` is FK to `conversation` (guest).
   Every sibling in the repo uses `/app/inbox/` — WorkOrderDetailPage.tsx:107 is
   the direct analogue. "View conversation" currently goes nowhere useful, and
   spec §1.2 puts linking a guest conversation explicitly in scope.
2. `EXPECTED_TABLES` — add the four log tables.
3. `include_context=False` on `_util.py:42` (parse_query) and `errors.py:89`.

### Where the ledger overstated — my error, and it is where the bug hid

I recorded T12's deferred minor as "hrefs independently verified correct against
routes.tsx". They were not. `/app/messages/:id` DOES exist in routes.tsx, which is
presumably what was checked — but verifying that a route RESOLVES is not verifying
it resolves to the RIGHT thing. The reviewer's framing is worth keeping: "verified
against routes.tsx" should mean "traced the id from its FK to the component that
consumes the param". One overstated verification claim in 1,255 ledger lines, and
the single real bug was behind it.

### Non-blocking findings to carry forward (NOT fixed in this branch)

- **Cursor pagination is server-only.** `useLogFeed` is a plain useQuery that never
  sends `cursor`; LogPage renders no "Load more"; `nextCursor` is dead payload. So
  entries past the newest 50 are unreachable from the UI, and LogPage exposes no
  date filter as a second route to history. At a busy property that is a few weeks
  before the logbook silently truncates. The inbox already solves this with
  useInfiniteQuery (api/hooks/conversations.ts:27) — the log invented a weaker
  parallel approach. Largest gap in the feature; fix in week one.
- **`LogEntryOut.mentions` is computed and never read.** The card renders the
  display name out of the body token instead, so spec §6.1's "the id is
  authoritative" guarantee is not actually realised: a hand-typed
  `@[Jane](user:0000…)` renders as a styled mention with no mention row and no
  notification. Either wire the renderer to `entry.mentions` or stop computing them.
- **Semantic split on "day".** Server interprets from/to in the PROPERTY timezone;
  client groups by the VIEWER's local day. Dormant only because LogPage sends no
  date filter. Whoever adds one will produce a UI where the "Thursday" heading and
  `from=2026-09-18` select different entries. Footnote belongs on the ruling.
- **`outstanding` is shown to every viewer**; spec §7 scopes it to supervisors.
  Within-property staff only, so mild, but an unrecorded divergence.
- `useLogEntry` has no consumers — dead frontend code (keep the route, §4.1).
- `entity_type="log_entry"` unmapped in NotificationsPage.linkFor, so the two
  highest-volume notifications are unclickable. Consistent with `staff_conversation`
  having the same gap, so not a new divergence.

### Verified clean by the reviewer, not assumed

- Realtime complete: all three mutations (create/acknowledge/set_pinned) broadcast,
  all after their guard clauses, all post-commit. No mutation skips an event.
- No authz bypass; `/mentionables` is STRICTER than its sibling `/staff-directory`,
  which carries no capability at all.
- **Cursor portability on PG18** — it compiled `tuple_(created_at, id) < (...)`
  against the postgresql dialect and inspected `_bind_processors` to confirm the
  UTCDateTime processor is attached to the tuple's datetime element. This was the
  single thing most likely to pass in SQLite and be wrong in production; it is not.
- Photo route: headers byte-identical to the sibling, SVG rejected, session cookie
  httponly+SameSite=Lax so a cross-site <img> carries no credentials.

### Ruling audit: none overturned, two footnoted

- Day-grouping ruling: right call, but I only moved HALF the day semantics — the
  server still uses property time for from/to. Recorded above.
- Mentions-as-a-table: right permanently, but my recorded justification (SQLite/
  Postgres portability) has a shelf life — it evaporates after the Postgres-
  everywhere cycle. The durable reason is the one I underweighted: a flat uuid
  array cannot distinguish a person from a department.

Production risk: **low**. 0006 is four create_tables with no ALTER, no data
migration, no backfill — no state a populated production DB can be in makes it fail
where an empty one succeeds. Seed does not run at boot.

## MERGED AND PUSHED

Fix-wave re-review: **SHIP**. All three ADDRESSED. The footer test asserts the
actual href (`toHaveAttribute('href', '/app/inbox/<id>')`), not mere link presence,
so it genuinely fails against the old route — the specific risk I flagged. No
sabotage left behind, exactly the 5 expected files, no scope creep, no breakage.

Merge: `git checkout main && git merge --no-ff hotel-log` -> **d2c9881**
"Merge branch 'hotel-log'". Used --no-ff deliberately to preserve branch structure
and keep the merge message, matching the staff-messaging precedent.

One snag: the merge was initially blocked by the `server/app/domain/users.py`
CRLF artifact. Confirmed `git diff --numstat` returned 0 changed lines before
discarding it with `git checkout --` — a line-ending-only change, no content lost.

**Verified the MERGED result before pushing**, not just the branch:
  server: 429 passed, ruff clean
  web:    645 passed across 65 files, eslint clean, build clean

Push: `9281bea..d2c9881 main -> main`. 0 unpushed. GitHub now has all 37 commits
(2 unpushed doc commits + 33 branch commits + the fix wave + the merge commit).

Railway: at the moment of pushing, the latest deployment was 663daadb — a
**redeploy of the OLD commit 9281bea**, created 00:46:54Z, SUCCESS. So the webhook
for d2c9881 had not yet produced a build. Watching for a new deployment whose
meta.commitHash is d2c9881, then checking its logs for
`==> alembic upgrade head` BEFORE `==> gunicorn on :$PORT` — that line is the proof
migration 0006 reached production Postgres 18. Build success alone is not proof.

## ROOT CAUSE: Railway's GitHub connection is broken, not the webhook

Symptoms: pushes to main produce no build; manual "Redeploy" re-runs the OLD
commit (9281bea) every time.

Why Redeploy could never work: Railway's Redeploy reuses the existing BUILD
ARTIFACT. It does not fetch new code. Every redeploy re-runs whatever commit was
last built. Deployment history confirms it — 663daadb and 57a37afb are both
`reason: "redeploy"` on commitHash 9281bea.

Diagnosis, in order:
1. GitHub has the code: `git ls-remote origin main` = d2c9881 (then 274b645).
   The push is not in question.
2. `gh api repos/bnfarrell/message_app/hooks` returns EMPTY — but that is expected
   and NOT the bug: Railway connects through a GitHub App installation, which does
   not create repo-level webhooks.
3. User confirmed the repo IS in the GitHub App's repository-access list.
4. **`project.deploymentTriggers` is an EMPTY list.** The service has a GitHub
   source configured (repo + branch) but NO deployment trigger — the separate
   object that actually listens for pushes and starts a build. That is the missing
   piece.
5. Attempting `deploymentTriggerCreate` fails with:
   **"Cannot create deployment trigger for bnfarrell/message_app because no one in
   the project has access to it"**
6. `query { githubRepos }` fails with **"Not Authorized"**.

Conclusion: Railway cannot see the repository. The GitHub App installation exists
on GitHub's side, but Railway's own account-level GitHub link is broken or absent,
so it can neither enumerate repos nor create a trigger. Not fixable from the API or
CLI with the current token — it needs the account's GitHub connection re-authorized
in the Railway dashboard.

This also explains why the service kept redeploying an old artifact rather than
erroring: nothing was broken at runtime, it simply never learned there was a new
commit.

Separate finding, unrelated: the CLI now warns that Config as Code
(railway.json / railway.toml) is deprecated in favour of .railway/railway.ts, with
existing files working until 2026-12-01. `railway config migrate` does the
conversion. Worth scheduling; not urgent, and NOT related to this failure.
