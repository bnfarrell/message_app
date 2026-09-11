# Task 13 Report: SLA sweep and snooze wake

## What I implemented

Two recurring job handlers, both matching the brief verbatim (no deviations needed — the interfaces
from Tasks 8/11/12 lined up exactly as described):

- `server/app/queue/handlers/sla.py`
  - `sweep_once(db) -> int`: finds `Conversation`s that are `open`, have a non-null `sla_due_at` in the
    past, and have not yet been notified (`sla_breach_notified_at IS NULL`). For each, sends an
    `sla.breach` notification via `notifications.notify_user_or_department` (assignee if set, else
    assigned department, else front-desk members, else admins — existing fallback logic, untouched),
    stamps `sla_breach_notified_at = now` so it won't re-fire, and queues a `conversation.updated`
    realtime event. Returns the count processed.
  - `@handler("sla.sweep")` wraps `sweep_once` for the recurring-job dispatcher.
- `server/app/queue/handlers/snooze.py`
  - `wake_once(db) -> int`: finds `snoozed` conversations whose `snoozed_until <= now`, flips them back
    to `open`, clears `snoozed_until`, queues `conversation.updated`. Returns the count processed.
  - `@handler("snooze.wake")` wraps `wake_once`.
- `server/tests/test_sla.py`: the five brief-specified tests, copied verbatim.

No changes were needed to `app/queue/handlers/__init__.py` (MODULES already lists `sla`/`snooze`) or
`app/queue/jobs.py` (RECURRING already seeded with `sla.sweep: 30`, `snooze.wake: 60`) — both were
pre-seeded by earlier tasks per the brief's note.

## What I tested and the results

Focused suite: `../.venv/Scripts/python.exe -m pytest tests/test_sla.py -q` → 5 passed.
Full suite: `../.venv/Scripts/python.exe -m pytest -q` → 139 passed (134 prior + 5 new), no warnings.
Also ran the focused suite once more with `-W error` to double-check no hidden deprecation warnings:
5 passed, clean.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_sla.py -q` (run before creating
`app/queue/handlers/sla.py` / `snooze.py`):

```
=================================== ERRORS ====================================
_____________________ ERROR collecting tests/test_sla.py ______________________
ImportError while importing test module '...\tests\test_sla.py'.
Traceback:
...
tests\test_sla.py:7: in <module>
    from app.queue.handlers.sla import sweep_once
E   ModuleNotFoundError: No module named 'app.queue.handlers.sla'
=========================== short test summary info ===========================
ERROR tests/test_sla.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.21s
```

This matches the brief's expected failure exactly (`ModuleNotFoundError: app.queue.handlers.sla`),
confirming the tests exercise code that does not yet exist.

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_sla.py -q` (after implementing
both handler modules):

```
.....                                                                    [100%]
5 passed in 0.80s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`:

```
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 5.32s
```

## Files changed

- `server/app/queue/handlers/sla.py` (new)
- `server/app/queue/handlers/snooze.py` (new)
- `server/tests/test_sla.py` (new)

## Self-review findings

- Both handler modules and the test file match the brief's code verbatim — verified line by line
  against `task-13-brief.md`.
- Confirmed idempotency is actually exercised: `test_overdue_conversation_notifies_assignee_once` ticks
  `sweep_once` three times (before due, at due, after already-notified) and asserts exactly one
  `Notification` row exists after all three ticks — this is the idempotency proof the task called out.
- Confirmed the frozen-clock-tie concern doesn't apply here: no test in this file asserts ordering
  between rows created in the same tick: each test only advances the clock and re-checks counts/ids, so
  no adjustment was needed there.
- `ruff check` on the two new handler files and the test file surfaces only pre-existing-style `E501`
  (line too long) findings inside the brief-verbatim code — per project convention these are left for
  the single Task 24 `ruff check --fix` pass, not fixed per-task.
- No orphaned imports, no unused variables. `payload: dict` is unused in both `@handler`-decorated
  wrapper functions, matching the exact style already used in `outbound.py` / `mock_delivery.py`.
- Property-scoping constraint: `sweep_once(db)` and `wake_once(db)` correctly take no `property_id`
  (by design, per the brief) and sweep across all properties; the domain call inside `sweep_once`
  (`notify_user_or_department`) is passed `c.property_id`, the specific conversation's property.
- Time source is `app.clock.now()` throughout, no direct `datetime.now()`/`datetime.utcnow()` calls.
- Realtime events only via `realtime.broadcast.queue_event`, no other event path used.

## Issues or concerns

None. No brief defects found — all five tests passed on the first implementation attempt with the
brief's code taken verbatim.
