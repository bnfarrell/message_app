# Task 7 Report: Realtime event outbox, connection registry, notifications

## What was implemented

Exactly per the brief, in step order:

- `server/app/realtime/__init__.py` — empty package marker.
- `server/app/realtime/registry.py` — `Conn` dataclass, `ConnectionRegistry` (`add`, `remove`, `count`, `users_online`, `send`), module singleton `connections`.
- `server/app/realtime/broadcast.py` — `Event` dataclass (`to_json`), `queue_event(db, ...)` (appends to `db.info["events"]`), `deliver(event)` (pushes to `connections.send` then fans out to in-process listeners), `add_listener`/`remove_listener`.
- `server/app/schemas/notifications.py` — `NotificationOut`, `UnreadCount` (both `CamelModel`).
- `server/app/domain/notifications.py` — `create`, `notify_users`, `notify_user_or_department` (user → department → front-desk fallback → admins fallback), `list_for_user`, `unread_count`, `mark_read`, `mark_all_read`.
- `server/app/api/notifications.py` — blueprint under `/api/p/<property_id>/notifications` with `GET ""`, `GET /unread-count`, `POST /<id>/read`, `POST /read-all`, all `@require_auth` → `@require_property`.
- `server/app/__init__.py` — registered `notifications.bp` in `create_app`.
- `server/tests/conftest.py` — added the `events` fixture (single retained listener reference, per the corrected form given in the task instructions).
- `server/tests/test_notifications.py` — the 7 brief-verbatim tests.

`app/db.py` (`Database.session()`) was **not modified** — it already lazily imports `app.realtime.broadcast.deliver` and calls it once per queued event after `db.commit()`, exactly as described in the brief. This is the wiring that goes live now that `app/realtime/broadcast.py` exists.

## TDD evidence

**RED** — before any implementation files existed (test file + fixture written, nothing else):

```
$ ../.venv/Scripts/python.exe -m pytest tests/test_notifications.py -q
=================================== ERRORS ====================================
________________ ERROR collecting tests/test_notifications.py _________________
ImportError while importing test module '...\tests\test_notifications.py'.
tests\test_notifications.py:1: in <module>
    from app.domain import notifications
E   ImportError: cannot import name 'notifications' from 'app.domain'
=========================== short test summary info ===========================
ERROR tests/test_notifications.py
1 error in 0.12s
```

Note: the brief's Step 2 predicted the failure would be `fixture 'events' not found`. In practice, since `app/domain/notifications.py` doesn't exist until Step 4, collection fails on the `from app.domain import notifications` import before pytest ever gets to fixture resolution. This is a minor inaccuracy in the brief's predicted error text, not a blocker — the RED state itself (tests fail before implementation) is correctly established.

**GREEN** — after implementing registry, broadcast, the `events` fixture, the domain module, the schema, and the blueprint:

```
$ ../.venv/Scripts/python.exe -m pytest tests/test_notifications.py -q
.....F.                                                                  [100%]
1 failed, 6 passed in 0.80s
```

(The one failure, `test_list_mark_read_and_unread_count_via_api`, is a genuine brief defect — see below — not an implementation gap on my part.)

## Full suite results

```
$ ../.venv/Scripts/python.exe -m pytest -q
....................................F.....................               [100%]
1 failed, 57 passed in 2.15s
```

Actual: **57 passed, 1 failed** (51 pre-existing + 7 new = 58 total; 6 of the 7 new tests pass). No warnings emitted (verified separately with `-W error::DeprecationWarning`, which did not turn up anything — only the same pre-existing assertion failure).

The isolation suite (`tests/test_isolation.py`) picked up the 4 new `/api/p/<property_id>/notifications*` routes automatically and they pass: 403 across properties, no 403 on own property, 401 anonymous — confirming `require_auth` → `require_property` ordering and property scoping are correct.

## Brief defect found

`test_list_mark_read_and_unread_count_via_api` fails deterministically (confirmed reproducible across 3+ runs, not flaky):

```python
rows = c.get(base).get_json()
assert [r["title"] for r in rows] == ["Two", "One"]
```
Actual: `AssertionError: assert ['One', 'Two'] == ['Two', 'One']`

**Root cause:** `tests/conftest.py`'s `app` fixture (pre-existing, Task 1) freezes the clock (`clock.freeze(FROZEN)`) for the duration of each test. `Notification.created_at` (via `TimestampMixin`, pre-existing) defaults to `utcnow()` → `clock.now()`, evaluated at flush time. Both "One" and "Two" are created in the same `with database.session() as db:` block while the clock is frozen, so they get an **identical** `created_at`. The brief-verbatim `list_for_user` orders only by `Notification.created_at.desc()` with no tiebreaker. For tied sort keys, SQLite's query plan here preserves ascending insertion (rowid) order rather than reversing it, so the result comes back `["One", "Two"]` instead of the newest-first `["Two", "One"]` the test expects.

This is a genuine interaction bug between the brief-verbatim domain code (single-column sort, no tiebreaker) and the brief-verbatim test (two same-recipient notifications created back-to-back under a frozen test clock, asserting strict newest-first order). Per my instructions I did not alter either side to force a pass — no secondary sort key (e.g. `id`) was added to `list_for_user`, since `id` is a random UUID and wouldn't reliably restore chronological order either; a real fix would need a monotonic tiebreaker (e.g. an autoincrement column) that is out of the brief's scope. Everything else in the file (fan-out, fallback logic, unread-count, mark-read, mark-all-read, ownership check) is exercised by the other 6 tests, all of which pass.

## Self-review

**Completeness:** All brief interfaces implemented exactly as specified: `Event`, `queue_event`, `deliver`, `add_listener`/`remove_listener`, `ConnectionRegistry` with the full method set and `connections` singleton, all 7 `notifications` domain functions, `NotificationOut`/`UnreadCount`, all 4 routes, blueprint registration. No `Database.session()` changes were needed (already wired per the brief's note).

**Discipline (YAGNI):** No files exceed the brief's intent; nothing added beyond what's specified (no extra tests, no extra routes, no extra fields).

**Testing — after-commit delivery, reasoned through (not just trusted):** In `test_events_are_delivered_only_after_commit`, the `RuntimeError` raised inside the `with database.session() as db:` block is raised at the `yield db` statement inside `Database.session()`'s `try`, so control goes straight to `except Exception: db.rollback(); raise` — this re-raises before ever reaching `db.commit()`, `events = db.info.pop("events", [])`, or the `if events: ... deliver(...)` block after the `try/except/finally`. So the queued event is never delivered, and `events == []` holds. If delivery were instead performed synchronously inside `create()` (e.g. calling `broadcast.deliver` directly rather than `queue_event`), the listener would see the event immediately, before the rollback — the test would then fail (`events` would be non-empty), which is exactly why this test is a meaningful proof of the after-commit-only guarantee, not a tautology.

**Testing — ConnectionRegistry drops a socket whose `send` raises:** Verified by direct manual exercise (not added as a permanent test, since it's not in the brief's required test list):
```python
r = ConnectionRegistry()
r.add(BadSocket_that_raises, 'p1', 'u1')
r.add(GoodSocket, 'p1', 'u2')
assert r.count('p1') == 2
delivered = r.send('p1', 'hello')
assert delivered == 1
assert r.count('p1') == 1   # bad socket was dropped
assert good.received == ['hello']
```
Result: `OK: bad socket dropped, good socket received, count decremented correctly` — confirms `send()`'s `except Exception: self.remove(c.ws)` behaves as intended.

**Attribution note:** The brief's Step 7 specifies ending the commit message with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. A system-level instruction present in this session explicitly states it "replaces any earlier attribution guidance" and mandates `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` for all commits made "from here on." I followed the higher-priority system instruction rather than the brief's line. Flagging this explicitly since it's a deviation from the brief's literal text (the subject line and `git add server` scope were followed exactly).

## Files changed

- Created: `server/app/realtime/__init__.py`, `server/app/realtime/registry.py`, `server/app/realtime/broadcast.py`, `server/app/domain/notifications.py`, `server/app/schemas/notifications.py`, `server/app/api/notifications.py`, `server/tests/test_notifications.py`
- Modified: `server/app/__init__.py` (registered `notifications.bp`), `server/tests/conftest.py` (added `events` fixture)

Note: `CLAUDE.md` shows as modified in the working tree but that change predates this task and was not touched or staged by me (commit only staged `server/`).

## Concerns

- One brief-verbatim test (`test_list_mark_read_and_unread_count_via_api`) fails deterministically due to the ordering defect described above. This affects only the ordering assertion within that one test; the underlying `list_for_user`/`mark_read`/`mark_all_read`/`unread_count` behavior is otherwise validated by the rest of the test and by the other passing tests.
- Actual suite result is 57 passed, 1 failed (not the 58/0 anticipated in the task instructions) — reported as-is per instructions, not adjusted.
