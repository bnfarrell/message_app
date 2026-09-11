# Task 14 Report: Work orders domain — state machine, prefill, events, closed-loop prompt

## Fix round 1 (post-review)

Tree had moved to HEAD `7cec147` (Tasks 15/16 landed; suite at 168 tests) before this round.
Addressed the review's three Important findings plus the three promoted Minors. `app/api/` was
untouched, as instructed (Task 15's `assert_viewer_can_see` fix is a separate round).

**Finding 1 — `prefill_from_conversation` crashes on an empty/whitespace-only inbound body.**
Fixed at `server/app/domain/work_orders.py` (the `title = ...` line in `prefill_from_conversation`):
`last.body.strip().splitlines()[0]` now falls back to `["Guest request"]` when `splitlines()`
returns `[]` (a whitespace-only body). Added
`test_prefill_with_whitespace_only_body_falls_back_to_guest_request`, which persists a message
with `body="   "` via the `make_conversation`/`make_message` factories and asserts
`prefill_from_conversation` returns `"Guest request"` instead of raising.

**Finding 2 — ordering ties under the frozen clock, and a real production risk.**
- Tests: added `clock.advance(minutes=1)` between the two `inbound()` calls in
  `test_prefill_from_conversation`, and between the `create` block and the first `transition` call
  in `test_complete_creates_unsent_editable_draft_prompt` — the Task 7 precedent, removing the
  artificial ties the frozen clock was creating.
- Production: added a secondary sort key to `prefill_from_conversation`'s message query
  (`Message.sent_at.desc(), Message.id.desc()`, `work_orders.py` line ~117) and to `list()`'s
  work-order query (`WorkOrder.created_at.desc(), WorkOrder.id.desc()`, line ~223), so a
  `DATABASE_URL` swap can't silently change which row wins a tie.
- I did **not** add the equivalent `WorkOrderEvent.id` secondary key to `detail()`'s event query
  (line ~229), and I want to flag why, since it deviates from the finding's literal "e.g." list —
  see **Issues or concerns** below. Short version: doing so broke a currently-green, out-of-scope
  test (Task 15's `test_prefill_create_transition_and_detail_via_api`) and my own new `assign`
  test, both of which assert a specific event order for rows that share a `created_at` under the
  frozen clock. The reason is that every model's primary key here is a random UUID4
  (`app/db.py:new_id`), not a monotonic/sortable id — so `ORDER BY created_at, id` doesn't recover
  true insertion order, it substitutes a *different*, cross-run-random tiebreak (a fresh UUID4 is
  generated every test run, so which row "wins" changes from run to run). That's a worse property
  than the one being fixed, for a column (`WorkOrderEvent.created_at`, non-nullable, always clock-set)
  that doesn't have the NULL-ordering divergence risk that made `Message.sent_at` a genuine concern.
  I left `detail()`'s ordering as plain `order_by(WorkOrderEvent.created_at)` and instead removed the
  tie at its only two sources (see the test changes above and the new `assign`/`detail` tests, which
  either advance the clock or filter by event type instead of position).

**Finding 3 — untested functions.** Added three tests (not all seven, per the ruling):
- `test_dismiss_prompt_transitions_and_is_noop_once_sent` (`draft_prompts.dismiss`): a pending
  prompt moves to `dismissed` with `resolved_at`/`resolved_by_user_id` set; a second, already-`sent`
  prompt (created via the real `POST .../messages` route with `draftPromptId`) is unchanged by a
  later `dismiss()` call — status, `resolved_at`, and `resolved_by_user_id` all stay as the sender
  left them.
- `test_detail_renders_event_timeline` (`work_orders.detail`): asserts `guest_name`, `room_number`,
  the ordered event-type list, and that a transition's `comment`/`user_name` render correctly —
  this is also what exercises the `**base` splat into `WorkOrderDetail` that the reviewer had to
  hand-verify; it now has a real test.
- `test_assign_reassigns_and_notifies_new_assignee` (`work_orders.assign`): reassigns a work order
  from one user to another, asserts the new assignee, the `work_order.assigned` notification, and
  the `assigned` event's `from_value`/`to_value` (looked up by event *type*, not list position — see
  Finding 2 note above for why).

**Finding 4 — the invalid-transition test proved nothing about the row.** Added to
`test_invalid_transition_is_409_and_audited`: `assert wo.status == WorkOrderStatus.open` after the
`raises` block, and an assertion that only the `created` event exists (no spurious `status_changed`
row was written before the raise).

**Finding 5 — an unknown status filter token was a bare 500.** `work_orders.list()` now catches the
`ValueError` from `WorkOrderStatus(s)` and re-raises `ValidationFailed`. Added
`test_list_rejects_unknown_status_filter`.

**Finding 6 — the guest-facing SMS lowercased the work-order title.** Removed `.lower()` from
`draft_prompts.draft_body`; the title is now sent to the guest exactly as written.

### Covering tests and results

```
$ cd server && ../.venv/Scripts/python.exe -m pytest tests/test_work_orders.py -q
...........................                                              [100%]
27 passed in 1.15s

$ cd server && ../.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 41%]
........................................................................ [ 83%]
.............................                                            [100%]
173 passed in 7.31s
```

(173 = 168 at HEAD `7cec147` + 5 new tests: the whitespace-body prefill regression test, `assign`,
`dismiss`, `detail`, and the invalid-status-filter test. No warnings in either run.)

I also re-ran `tests/test_work_orders_api.py` (Task 15's file, not modified) alongside
`tests/test_work_orders.py` after the `detail()` decision above, to confirm no regression there:

```
$ cd server && ../.venv/Scripts/python.exe -m pytest tests/test_work_orders.py tests/test_work_orders_api.py -q
..............................                                           [100%]
30 passed in 1.47s
```

### Files changed (this round)

- `server/app/domain/work_orders.py` — empty-body fallback, two secondary sort keys, status-filter
  validation.
- `server/app/domain/draft_prompts.py` — removed `.lower()` from `draft_body`.
- `server/tests/test_work_orders.py` — clock-advances to remove two artificial ties, strengthened
  the invalid-transition test, and five new tests (whitespace-body prefill, `assign`, `dismiss`,
  `detail`, invalid-status-filter).

### Issues or concerns

The one deliberate deviation from the review's literal wording: I did not add a `WorkOrderEvent.id`
(or any) secondary sort key to `work_orders.detail()`'s event query, unlike the other two sites
Finding 2 named. Reasoning is laid out above under Finding 2 — in short, this schema's primary keys
are random UUID4s with no relationship to insertion order, so using `id` as a tiebreaker there
doesn't restore correct temporal order, it just replaces one source of nondeterminism (engine-
dependent tie resolution) with another (a tiebreak that changes every test run because the UUIDs
are freshly random each run), while breaking a currently-green, plan-mandated test's real ordering
assertion in the process. I'm flagging this for the controller rather than silently applying the
literal suggestion, since it's a case where following the letter of the ruling would reintroduce
the exact class of problem it was meant to fix. If the controller still wants a secondary key there
for defense-in-depth, the correct primitive would be a monotonic sequence column (a schema/migration
change), not the existing `id`, and I did not add one without being asked.

---

## What I implemented

Followed the brief's steps verbatim (TDD, tests first):

1. `server/tests/test_work_orders.py` — copied verbatim from the brief: transition-matrix
   parametrized test, prefill test, create tests (with/without assignee), the closed-loop
   completion test, the no-source-conversation test, the "sending the draft marks it sent"
   integration test (through the real `POST .../messages` route), the invalid-transition test,
   and the department-keyword-guess unit test.
2. `server/app/schemas/work_orders.py` — `CreateWorkOrder`, `WorkOrderPatch`, `WorkOrderOut`,
   `WorkOrderEventOut`, `WorkOrderDetail`, `WorkOrderPrefill`, `WorkOrderListQuery`. Did not
   redefine `DraftPromptOut`/`WorkOrderBrief` — those stay in `app/schemas/conversations.py`
   from Task 12, reused as-is.
3. `server/app/domain/draft_prompts.py` — `draft_body`, `create_for_completion` (returns `None`
   when there's no source conversation, when the conversation row is missing, or when a pending
   prompt already exists for that work order — idempotent), `dismiss` (domain function only; no
   route — that's Task 15's).
4. `server/app/domain/work_orders.py` — `TRANSITIONS` state machine + `assert_transition`,
   `guess_department_type` + `DEPARTMENT_KEYWORDS`, `create`, `prefill_from_conversation`,
   `transition`, `assign`, `comment`, `set_priority`, `get`, `list`, `detail`.

All four new files are exactly as specified in the brief's code blocks (Steps 1, 3, 4, 5) — no
deviation was needed; I found no defects in the brief this time.

## What I tested and the results

Focused suite: `../.venv/Scripts/python.exe -m pytest tests/test_work_orders.py -q` → 22 passed.
Full suite: `../.venv/Scripts/python.exe -m pytest -q` → 161 passed (139 pre-existing + 22 new),
0 warnings (the project's `filterwarnings = ["error::DeprecationWarning:app.*"]` stayed silent).

One thing I checked carefully because of the "frozen-clock ties" warning in my instructions:
`test_prefill_from_conversation` sends two inbound SMS webhooks back-to-back under the frozen
clock (both get the identical `sent_at`), then relies on `ORDER BY sent_at DESC` to put the
second message first. I verified empirically (ran it standalone and in the full suite, both
green) that SQLite's sort is stable enough here that insertion order is preserved as a tiebreak,
so the second-inserted row does come first under `DESC`. It is not a contract SQLite formally
guarantees, but since the brief instructs verbatim test code and the test in fact passes
reliably, I did not alter it. If this ever proves flaky, the fix would be to give
`prefill_from_conversation`'s query a secondary `Message.id.desc()` order-by (or advance the
clock in the test) — but there is no observed failure to act on.

Ruff on the four changed files: only `E501` (line length), `I001` (import sort), and one `F401`
(`Direction` imported but unused) inside the verbatim test file — all in brief-verbatim code, so
left for the Task 24 `ruff --fix` pass per project convention, not touched here.

## TDD Evidence

**RED** — command: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_work_orders.py -q`, run before any implementation files existed (only the test file had been written):

```
ERROR collecting tests/test_work_orders.py
ImportError while importing test module '...\tests\test_work_orders.py'.
Traceback:
tests\test_work_orders.py:5: in <module>
    from app.domain import work_orders
E   ImportError: cannot import name 'work_orders' from 'app.domain' (...\app\domain\__init__.py)
=========================== short test summary info ===========================
ERROR tests/test_work_orders.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.26s
```

This is exactly the expected failure mode: `app/domain/work_orders.py` did not exist yet (the
brief's expected message text is `ModuleNotFoundError`; Python surfaces the identical root cause
as `ImportError: cannot import name ... from 'app.domain'` because `app.domain` is a package —
same underlying condition, not a different failure).

**GREEN** — after writing `app/schemas/work_orders.py`, `app/domain/draft_prompts.py`, and
`app/domain/work_orders.py`:

```
$ cd server && ../.venv/Scripts/python.exe -m pytest tests/test_work_orders.py -q
......................                                                   [100%]
22 passed in 7.18s

$ cd server && ../.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 44%]
........................................................................ [ 89%]
.................                                                        [100%]
161 passed in 11.13s
```

## Files changed

- `server/app/domain/work_orders.py` (new)
- `server/app/domain/draft_prompts.py` (new)
- `server/app/schemas/work_orders.py` (new)
- `server/tests/test_work_orders.py` (new)

## Self-review findings

- Read the full diff (all four files are new, nothing else touched — `git status` confirms only
  these four untracked files).
- Confirmed `list(...)` is never called as the builtin after the `list` domain function shadows
  it in `work_orders.py` (it isn't — only comprehensions and `db.scalars(...).all()` are used
  after that point), matching the same convention already in `conversations.py`.
- Confirmed `assert_transition` genuinely rejects illegal moves (`test_transition_matrix`
  proves both directions, including that `complete -> in_progress` is allowed — a deliberate
  "reopen after complete" move — and `verified`/`cancelled` are terminal).
- Confirmed `test_invalid_transition_is_409_and_audited`'s illegal `open -> complete` attempt
  raises `TransitionError` before any mutation — `transition()` calls `assert_transition` before
  any assignment to `wo.status`, so a rejected transition leaves the row untouched.
- Confirmed idempotency: `create_for_completion` checks for an existing *pending* prompt for the
  work order before creating a new one, so `complete -> in_progress -> complete` again would not
  create a second row (not directly exercised by a brief test, but the guard is in place and the
  brief's own completion test only creates one).
- No orphan imports, no dead code introduced.
- Did not touch `app/domain/conversations.py`, `app/domain/messages.py`, or any routes — those
  are correctly out of scope for this task (routes are Task 15's).

## Issues or concerns

None. No brief defects found this time. One item worth the controller's awareness (not a defect,
just a fragility noted above): `test_prefill_from_conversation`'s ordering assertion depends on
SQLite's tie-breaking behavior under the frozen clock rather than an explicit secondary sort key;
it passed reliably in both isolated and full-suite runs.
