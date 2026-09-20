# Task 7 Report: Acknowledge and pin

## Fix report (post-review, commit 82e4343)

Review of the original commit (d85d137) found production code correct but flagged two
Important test-coverage gaps, both in `server/tests/test_log_api.py`. Started from
current HEAD (2bc7b70, Task 8's API routes had landed since); confirmed baseline
424 passed before touching anything.

### Gap 1 — idempotency test proved only the row count, not "does not re-audit"

`test_acknowledging_twice_is_idempotent` asserted `len(rows) == 1` on `LogEntryAck`,
which the unique constraint on `(log_entry_id, user_id)` already guarantees on its own.
Spec §9 requires the repeat to also not re-audit and not re-fire the realtime event.

**Fix:** added two assertions after the existing row-count check:
```python
audit_rows = db.scalars(select(AuditLog).where(
    AuditLog.action == "log_entry.acknowledged",
    AuditLog.entity_id == entry.id)).all()
assert len(audit_rows) == 1, "a repeat acknowledgement must not re-audit"
updated_events = [e for e in db.info.get("events", []) if e.type == "log.entry.updated"]
assert len(updated_events) == 1, "a repeat acknowledgement must not re-fire the event"
```
I used `db.info.get("events", [])` directly (confirmed reachable: `app/db.py`'s
`Database.session()` only pops/delivers `db.info["events"]` after the `with` block's
body completes, so it's still populated mid-test) rather than skipping the event
assertion, since it was cheap to check and closes the reviewer's full ask.

**Sabotage:** moved `audit.record()` and `queue_event()` in `acknowledge()` to run
before the `existing` idempotency guard (so every repeat call would re-audit/re-fire).

Command: `../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k idempotent`

Failing output (tail):
```
E           assert len(audit_rows) == 1, "a repeat acknowledgement must not re-audit"
E           AssertionError: a repeat acknowledgement must not re-audit
E           assert 2 == 1
1 failed, 24 deselected in 1.54s
```
Reverted `app/domain/log.py` from the pre-sabotage backup; `diff` against the backup
showed no residual changes; re-ran the same test — passed.

### Gap 2 — `set_pinned`'s no-op guard (`if entry.pinned == pinned`) was never exercised

The pin test only walked True→False transitions, never called `set_pinned` with the
state already at the target, so the guard was dead code in the suite. A variant that
re-audits on a redundant call, or drops the guard and lets a second pinner silently
overwrite `pinned_by_user_id`, would have passed everything.

**Fix:** extended `test_pin_and_unpin_move_the_entry_in_and_out_of_the_pinned_block`
with a redundant pin by a different user (`manager_a`) after the initial pin by
`supervisor_a`, asserting both that the audit count stays at 1 and that
`pinned_by_user_id` is untouched:
```python
log_domain.set_pinned(db, fx.property_a.id, fx.manager_a.id, entry.id, True)
db.flush()
pin_audits = db.scalars(select(AuditLog).where(
    AuditLog.action == "log_entry.pinned", AuditLog.entity_id == entry.id)).all()
assert len(pin_audits) == 1, "a redundant pin must not re-audit"
assert entry.pinned_by_user_id == fx.supervisor_a.id, \
    "a redundant pin by someone else must not overwrite who pinned it"
```

**Sabotage:** deleted the `if entry.pinned == pinned: return entry` guard in
`set_pinned()`.

Command: `../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k pin_and_unpin`

Failing output (tail):
```
E           assert len(pin_audits) == 1, "a redundant pin must not re-audit"
E           AssertionError: a redundant pin must not re-audit
E           assert 2 == 1
1 failed, 24 deselected in 1.24s
```
(This sabotage also would have failed the `pinned_by_user_id` assertion, since removing
the guard lets `manager_a`'s call overwrite it — the audit assertion failed first.)
Reverted `app/domain/log.py` from the pre-sabotage backup; `diff` confirmed a byte-clean
revert; re-ran the same test — passed.

### Full verification after both fixes

```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```
```
424 passed in 49.37s
```
(No new test functions were added — both gaps were closed by extending existing tests —
so the count is unchanged from the 424 baseline.)

```
../.venv/Scripts/python.exe -m ruff check .
```
```
All checks passed!
```

`git diff` confirmed `server/app/domain/log.py` had zero net changes (production code
untouched, as the review said no production fix was needed); only
`server/tests/test_log_api.py` changed (22 insertions, 1 deletion).

Commit: `82e4343` — `test(server): close two hotel-log ack/pin coverage gaps`

## What I implemented

Appended two functions to `server/app/domain/log.py`, verbatim from the brief:

- `acknowledge(db, property_id, user_id, entry_id) -> LogEntry` — raises `Forbidden`
  (added to the `app.errors` import) if `user_id` is not in the entry's `ack_expected`
  snapshot; otherwise idempotently inserts a `LogEntryAck` row (no-op on a second call),
  records an audit entry, and queues a `log.entry.updated` event.
- `set_pinned(db, property_id, user_id, entry_id, pinned) -> LogEntry` — no-ops if the
  flag is already at the target value; otherwise flips `pinned`, sets/clears
  `pinned_by_user_id` and `pinned_at`, audits `log_entry.pinned`/`log_entry.unpinned`,
  and queues an update event.

`LogEntryAck` was already present in the `app.models` import from Task 6, so no import
change was needed there.

## Note on branch state

The task brief said to pull HEAD before starting because commits had landed since it was
written. There is no `origin/hotel-log` remote branch (only `origin/main` exists), so
there was nothing to pull — the local `hotel-log` branch was already the correct base.
Confirmed the baseline (414 passed) matched the brief for `test_log_api.py` (19 tests
after the 4 new ones vs. the brief's now-stale "16"), consistent with "several commits
landed since the brief was written."

## What I tested and the results

Four tests appended to `server/tests/test_log_api.py`, verbatim from the brief, plus one
extra assertion I added per the task instructions (closing the Task 6 review gap):

1. `test_acknowledging_twice_is_idempotent` — calls `acknowledge` twice, asserts only one
   `LogEntryAck` row exists. **Extra:** after acking, calls `get_out` and asserts
   `can_ack is False` and `acked_by_me is True` — covering the right-hand side of
   `can_ack`'s AND (`viewer not in acked`), which no prior test exercised.
2. `test_a_user_outside_the_audience_cannot_acknowledge` — a user not in `ack_expected`
   gets `Forbidden`.
3. `test_joining_the_department_later_does_not_change_the_denominator` — a user who joins
   the department after entry creation is not in the frozen snapshot; `ack_expected_count`
   unchanged, and their `acknowledge` call still raises `Forbidden`.
4. `test_pin_and_unpin_move_the_entry_in_and_out_of_the_pinned_block` — pin moves the
   entry into `feed().pinned` (while it stays in `feed().entries` too); unpin removes it
   from `pinned`.

Final results: **418 passed, 0 failed** (baseline 414 + 4 new). `ruff check .`: all
checks passed.

## TDD evidence

**RED:**
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "acknowledg or pin or denominator"
```
Output (tail):
```
E               AttributeError: module 'app.domain.log' has no attribute 'acknowledge'
...
E           AttributeError: module 'app.domain.log' has no attribute 'set_pinned'
=========================== short test summary info ===========================
FAILED tests/test_log_api.py::test_acknowledging_twice_is_idempotent - Attrib...
FAILED tests/test_log_api.py::test_a_user_outside_the_audience_cannot_acknowledge
FAILED tests/test_log_api.py::test_joining_the_department_later_does_not_change_the_denominator
FAILED tests/test_log_api.py::test_pin_and_unpin_move_the_entry_in_and_out_of_the_pinned_block
4 failed, 15 deselected in 1.58s
```
Expected because `acknowledge`/`set_pinned` did not exist yet — matches the brief exactly.

**GREEN:**
```
cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q
```
```
...................
19 passed in 3.04s
```
Then full suite:
```
cd server && ../.venv/Scripts/python.exe -m pytest -q
```
```
418 passed in 47.26s (after sabotage/revert cycles, re-confirmed clean)
```
`ruff check .` → `All checks passed!`

## Sabotage verification

For each test, I broke the one production behavior it guards, confirmed the test (and
only that test, or the pair sharing the same guard) failed, then reverted from a saved
copy of `log.py` and re-confirmed green.

1. **`test_acknowledging_twice_is_idempotent`** — removed the
   `existing = db.scalar(...); if existing is not None: return entry` guard so the second
   `acknowledge()` call would insert again. Result:
   `sqlalchemy.exc.IntegrityError: UNIQUE constraint failed: log_entry_ack.log_entry_id,
   log_entry_ack.user_id` — test failed as expected. Reverted; test passed again.

2. **`test_a_user_outside_the_audience_cannot_acknowledge`** and
   **`test_joining_the_department_later_does_not_change_the_denominator`** — removed the
   `if user_id not in (entry.ack_expected or []): raise Forbidden(...)` block entirely.
   Ran both together: both failed with `Failed: DID NOT RAISE Forbidden`. Reverted; both
   passed again.

3. **`test_pin_and_unpin_move_the_entry_in_and_out_of_the_pinned_block`** — replaced the
   three lines that set `entry.pinned` / `pinned_by_user_id` / `pinned_at` with a comment
   (no-op), leaving `db.flush()`. Result: `AssertionError: assert [] == ['pin me']` — test
   failed as expected. Reverted; `diff` against the saved backup showed the file was
   byte-identical to the pre-sabotage state, and the test passed again.

After all three sabotage/revert cycles, ran the full suite once more: 418 passed, ruff
clean, and `git diff` against the committed state showed no residual changes.

## Files changed

- `server/app/domain/log.py` — added `acknowledge()` and `set_pinned()`; added
  `Forbidden` to the `app.errors` import.
- `server/tests/test_log_api.py` — added the 4 tests (with one extra assertion in the
  idempotency test).

Commit: `d85d137` — `feat(server): acknowledge and pin hotel log entries`

Not committed (pre-existing/unrelated to this task, per instructions and repo hygiene):
`server/app/domain/users.py`, `server/data/app.db*`, `two.png`, `.claude/`, `images/`.

## Self-review findings

- The implementation matches the brief verbatim; no deviations.
- `acknowledge()` correctly requires no capability check — only snapshot membership —
  matching spec §5's intent that a late-joiner to a department is not owed an ack
  invitation and cannot manufacture one by acking anyway.
- `set_pinned()` is deliberately not capability-gated here; that's Task 8's route-layer
  responsibility per the task description, and this function has no capability check,
  consistent with that division.
- The idempotent double-ack path returns the entry unchanged (no re-audit, no duplicate
  event) on the second call — correct, since nothing changed.
- `set_pinned` on a no-op call (already at target state) also skips the audit/event,
  which seems right: no state change occurred.
- Closed the Task 6-review gap on `can_ack`'s right-hand side by asserting it in the
  idempotency test rather than adding a fifth test, since it naturally follows an ack
  call already in that test.

## Concerns

None. Full suite green (418/418), ruff clean, diff is minimal and traceable to the task,
and all four new tests were verified to actually catch a targeted regression via
sabotage.
