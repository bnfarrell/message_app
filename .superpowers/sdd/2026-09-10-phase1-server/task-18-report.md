# Task 18: Analytics — Report

## What was implemented

Verbatim from the brief (no defects found requiring deviation):

- `server/app/schemas/analytics.py` — `HourBucket`, `DayBucket`, `DepartmentBucket`, `ResponseBucket`,
  `Overview`, `AgentStats` (all `CamelModel`).
- `server/app/domain/analytics.py` — `percentile(values, p)` (nearest-rank, `None` on empty input),
  `default_range(since, until)` (defaults to last 7 days ending `clock.now()`), `overview(db, property_id,
  since, until)`, `agents(db, property_id, since, until, only_user_id)`. All aggregation (hour/day
  bucketing, percentiles, means) is done in Python over narrow `select()` results — no raw SQL, no
  SQLite-only functions (no `strftime`/`julianday`). This matters for portability per the brief's own
  docstring, and I verified it holds.
- `server/app/api/analytics.py` — `GET .../analytics/overview` (requires `view_property_analytics`) and
  `GET .../analytics/agents` (property-wide for `view_property_analytics` holders, self-only for
  `view_own_stats` holders, 403 otherwise). `_parse()` handles ISO date-only and datetime query params,
  treating a date-only `to` as end-of-day (`time.max`).
- `server/app/__init__.py` — registered `analytics.bp` (added to the import tuple and the
  `register_blueprint` calls, alphabetically placed in the import list to match existing style; blueprint
  registration itself appended after `hooks.bp` per the brief's "Register `analytics.bp`" instruction).
- `server/tests/test_analytics.py` — the three tests from the brief, copied verbatim.

## What was tested and results

Focused: `../.venv/Scripts/python.exe -m pytest tests/test_analytics.py tests/test_isolation.py -q`
→ `8 passed in 0.92s` (3 new analytics tests + 5 isolation tests, including the cross-property 403 walk
and the "admin not blocked on own property" walk, both of which now cover the two new analytics routes
automatically).

Full suite: `../.venv/Scripts/python.exe -m pytest -q` → `187 passed in 9.98s` (184 prior + 3 new), no
warnings section in the output (pristine).

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_analytics.py -q`, run before any
implementation files existed:

```
ImportError while importing test module '...\tests\test_analytics.py'.
E   ImportError: cannot import name 'analytics' from 'app.domain' (...\app\domain\__init__.py)
=========================== short test summary info ===========================
ERROR tests/test_analytics.py
1 error in 0.31s
```

This is the expected failure: `app/domain/analytics.py` did not exist yet, so the module-level import in
the test file fails at collection. (The brief predicted `ModuleNotFoundError`; pytest's actual wording is
`ImportError: cannot import name 'analytics' from 'app.domain'` — same underlying cause, an equivalent
signal, not a discrepancy worth treating as a brief defect.)

**GREEN** — after writing `app/schemas/analytics.py`, `app/domain/analytics.py`, `app/api/analytics.py`,
and registering the blueprint, command: `../.venv/Scripts/python.exe -m pytest tests/test_analytics.py
tests/test_isolation.py -q` → `8 passed in 0.92s`, then full suite `../.venv/Scripts/python.exe -m pytest
-q` → `187 passed in 9.98s`. All three new tests passed on the first implementation attempt, with no
adjustment needed — I traced the fixture data (`tests/fixtures.py`, no pre-existing conversations/messages/
work orders) and the reply/SLA domain logic (`app/domain/messages.py`: `sla_due_at` cleared and
`first_response_seconds` set on first staff reply; `app/queue/handlers/sla.py`: `sweep_once` marks
`sla_breach_notified_at`) by hand before running, to confirm the brief's asserted numbers (120s first
response, 1 SLA breach, 1200s mean time to resolve) were correct before trusting the green run.

## Files changed

- `server/app/schemas/analytics.py` (new)
- `server/app/domain/analytics.py` (new)
- `server/app/api/analytics.py` (new)
- `server/tests/test_analytics.py` (new)
- `server/app/__init__.py` (modified: import + register `analytics.bp`)

## Self-review findings

- Completeness: both interfaces from the brief (`overview`, `agents`, `percentile`) implemented exactly;
  both routes registered; capability gating matches `app/auth/permissions.py` (`view_property_analytics`
  vs `view_own_stats`) without re-deriving it.
- Division by zero: verified explicitly — `percentile([])` → `None`; `sla_breach_rate` → `0.0` when no
  conversations; `mean_time_to_resolve_seconds` → `None` when no closed work orders in range;
  `first_response_p50/p90` → `None` when no conversation has answered yet; `ResponseBucket.share` → `0.0`
  when `frs` is empty. All covered by the empty-agents-response path in
  `test_agent_sees_only_own_stats_and_no_overview` and by construction in the aggregate functions.
- Frozen-clock/bucketing: the brief's own test advances the clock between the two inbound messages'
  conversation-scoped side effects (reply, work order transitions), and both inbound messages land in the
  same hour bucket by design (test doesn't exercise cross-hour/cross-day bucketing) — this is the brief's
  test as given; I did not need to add clock advances since `inbound_by_hour`/`inbound_by_day` correctness
  is structural (`Counter` over `.hour`/`.date().isoformat()`), not something the given fixtures could get
  vacuously right only by chance.
- Reused `app.domain.conversations` semantics: overview/agents do not re-derive "resolved" or "unanswered"
  — they only use `first_response_seconds`, `sla_breach_notified_at`, and raw counts, none of which
  require the `_resolved_condition`/`_unanswered_expr` helpers, so no divergence risk here.
- SQL portability: confirmed — no raw SQL strings, no `func.strftime`, no `julianday`, no dialect-specific
  constructs anywhere in `app/domain/analytics.py`. All bucketing/percentile/mean logic runs in Python
  over plain `SELECT` results, so it is not SQLite-specific and will behave identically under
  PostgreSQL.
- Ruff: ran `ruff check` on the four new files for visibility only, per project convention (plan-verbatim
  code is not reformatted mid-task). Findings are all `E501` line-too-long in the brief's own verbatim
  code (domain/schemas/api/test files) — left untouched, deferred to the Task 24 `ruff check --fix` pass
  as instructed.
- No orphaned imports/dead code introduced; `__init__.py` change is a two-line, surgical addition matching
  the existing pattern exactly (single alphabetical insertion in the import tuple, one
  `register_blueprint` call appended in the existing order).

## Issues or concerns

None. No brief defects found — the three specified tests passed against the brief's code exactly as
written, on the first implementation attempt, with no code changes needed. `quick_reply_share` is `None`
in `AgentStats` for Phase 1 as the brief's inline comment specifies (no `quick_reply_id` column exists yet
on `Message`).

---

## Fix report — review round 1 (tests only, no implementation changes)

The review confirmed **no implementation defects**: every asserted number was hand-traced against the
fixture, property scoping was verified query by query, the division-by-zero guards are structurally
sound, and SQL portability holds. It found three test-coverage gaps. Per the ruling, `app/domain/analytics.py`,
`app/schemas/analytics.py`, and `app/api/analytics.py` were **not touched** this round — only
`server/tests/test_analytics.py` changed.

### Finding 1 (Important) — bucketing assertion was vacuous

`test_overview_and_agents` only asserted `sum(inboundByHour) == 2` and `len == 24`; both inbound messages
were created at the same frozen instant, so the test could not distinguish correct bucketing from an
implementation that dumped everything into one bucket.

**Fix:** inserted `clock.advance(hours=13)` between the two `inbound()` calls, crossing both an hour
boundary and midnight (12:00 → 01:00 next day). Replaced the vacuous sum-only assertion with:
- `hour_counts = {b["hour"]: b["count"] for b in o["inboundByHour"]}` plus explicit checks that
  `hour_counts[start.hour] == 1`, `hour_counts[second_hour.hour] == 1`, and `start.hour != second_hour.hour`
  (guards against the two landing in the same bucket by coincidence).
- `day_counts` built the same way from `inboundByDay` (previously unasserted at all), checked against
  `{start.date().isoformat(): 1, second_hour.date().isoformat(): 1}` with an explicit `start.date() !=
  second_hour.date()` guard.

Advancing the clock 13 hours before Diego's message shifts *his* conversation's timeline (its
`sla_due_at`) but not Sarah's, since Sarah's inbound message, staff reply, and work order all keep their
original relative timing (`clock.advance(minutes=2)` / `clock.advance(minutes=20)` are unaffected — they
are relative to whatever the clock currently is). I re-derived every downstream number by hand rather than
guessing:
- Sarah's first reply is now 13h2m after her inbound message → `firstResponseP50/P90Seconds` changed from
  `120` to `13*3600+120 = 46920` (both overview and per-agent). Verified this is correct, not a hack,
  by tracing `app/domain/messages.py:send()` — `first_response_seconds = now - last_guest_message_at`, and
  `last_guest_message_at` is Sarah's, set before the 13h advance.
- `meanTimeToResolveSeconds` stayed `1200` — the work order's `created_at`/`completed_at` are both after
  the 13h shift, so their 20-minute difference is untouched.
- `slaBreaches` stayed `1` — Diego's `sla_due_at` is now `13h + 15min` after `start`, and the sweep runs
  `13h + 22min` after `start`, so he is still overdue by 7 minutes when swept.

### Finding 2 (Important) — coverage didn't match the breadth shipped

Added to `test_overview_and_agents`:
- `slaBreachRate` — asserted `== 0.5` (1 breach / 2 conversations), not just the raw `slaBreaches` count.
- `firstResponseDistribution` — asserted all 5 buckets (`len(dist) == len(analytics.BUCKETS)`), located the
  one bucket the 46920s value falls into via `analytics.BUCKETS` itself (not a hardcoded/transcribed label
  string, to avoid coupling the test to the exact unicode dash in the bucket labels), and asserted
  `count == 1, share == 1.0` for that bucket and `count == 0, share == 0.0` for every other bucket.
- Per-agent `firstResponseP90Seconds` (was previously only P50), `slaBreaches` (asserted `== 0` — Sarah's
  conversation, the one Ava handled, was never breached), and `quickReplyShare` (asserted `is None`, per
  the brief's Phase 1 note).

Added a new test, `test_empty_window_returns_zeros_not_500`, calling the real HTTP routes
(`GET .../analytics/overview` and `GET .../analytics/agents`) against the default 7-day window on a
property with zero conversations/messages/work orders (the base fixture creates none). Asserts `200` (not
`500`) and that every count is `0`, every average is `None`, `slaBreachRate == 0.0`, `inboundByDay == []`,
`inboundByHour` has 24 zero-count buckets, every `firstResponseDistribution` bucket is `count=0, share=0.0`,
`workOrdersByDepartment == []`, and every returned agent row has all-zero/`None` stats. This is the
"level that matters" check the dispatch named as the likeliest 500 source — previously only
`percentile([])` was unit-tested in isolation, never a full `overview()`/`agents()` call with zero rows in
range.

### Finding 3 — cross-property number-isolation test

Added `test_overview_excludes_other_property_data`: seeds one inbound conversation in property A and,
separately, one inbound conversation plus a work order in property B (via `fx.guest_b`, `fx.admin_b`,
`fx.property_b`), then calls `analytics.overview()` directly for both properties and asserts property A's
`conversations`/`inbound_messages`/`work_orders_created` reflect only its own row (not B's), and vice
versa. This pins the per-query `property_id` filters (previously only verified by inspection) rather than
relying on `test_isolation.py`'s route-level 403 walk, which proves unreachability, not that scoped counts
never blend across properties.

One test-authoring wrinkle hit and fixed: the first version of this test called `analytics.overview()`
immediately after seeding, with no explicit `since`/`until`. `default_range()`'s `until` defaults to
`clock.now()` and the seeded conversation's `created_at` is also `clock.now()` at that same frozen
instant, so the query's `created_at < until` (strict) excluded the very row just created — an off-by-one
against a frozen clock, not an implementation bug (the same query with a real, advancing clock would never
see `created_at == until` exactly). Fixed by adding `clock.advance(minutes=1)` between seeding and the
`analytics.overview()` calls, matching the pattern already used elsewhere in this test file to keep frozen
timestamps from colliding.

### Covering tests and output

Command: `../.venv/Scripts/python.exe -m pytest tests/test_analytics.py tests/test_isolation.py -q`

```
..........
10 passed in 1.18s
```

(5 analytics tests — the 2 original plus 3 new/expanded — and 5 isolation tests, both walks still passing
for the two analytics routes.)

Full suite: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 35%]
........................................................................ [ 70%]
.............................................................            [100%]
205 passed in 12.15s
```

(203 prior + 2 net-new test functions; `test_overview_and_agents` was expanded in place rather than
duplicated.) Output is pristine — no warnings section.

`ruff check tests/test_analytics.py` was run for visibility: 14 findings, all pre-existing-pattern `E501`
(line-too-long) plus one `F841` (`diego` assigned but never used) that was already present in the original
committed file (confirmed via `git show c734e1e:server/tests/test_analytics.py | ruff check --stdin-filename ... -`,
which reports the same `F841` and 10 pre-existing `E501`s). The 4 additional `E501`s come from my new
assertion lines; left as-is per the project's stated one-shot `ruff check --fix` pass at Task 24, and
because none of them are correctness issues.

### Files changed this round

- `server/tests/test_analytics.py` (modified: expanded `test_overview_and_agents`, added
  `test_empty_window_returns_zeros_not_500` and `test_overview_excludes_other_property_data`)

No changes to `server/app/domain/analytics.py`, `server/app/schemas/analytics.py`,
`server/app/api/analytics.py`, or `server/app/__init__.py` this round.
