# Task 19 Report: WebSocket endpoint, presence, typing

## What I implemented

- `server/app/realtime/presence.py` — `Entry` dataclass, `PresenceStore` (`update`,
  `clear_user`, `sweep`, `snapshot`, `touch`), module singleton `store`, and
  `broadcast_presence(property_id, conversation_ids)`. Implemented verbatim per the brief
  (Step 3 body plus the `touch` method specified separately in the brief).
- `server/app/realtime/ws.py` — `sock = Sock()`, the `/ws` route (`ws_route`) that
  authenticates via the `sid` cookie, enforces property membership on `subscribe`, handles
  `presence` and `heartbeat` frames, and cleans up on disconnect; `start_sweeper(app)` which
  runs `presence.store.sweep` on a 5s daemon thread and fans out presence updates for any
  conversations that changed. Implemented verbatim per the brief (Step 4).
- `server/app/__init__.py` — after the existing worker-start block (which computes
  `under_reloader`), added:
  ```python
  from app.realtime.ws import sock, start_sweeper

  sock.init_app(app)
  if config.START_WORKER and (under_reloader or not app.debug):
      start_sweeper(app)
  ```
  exactly as given in the brief.
- `server/tests/test_presence.py`, `server/tests/test_ws.py` — brief's tests verbatim, plus
  one test I added beyond the brief: `test_disconnect_clears_presence` (see "Disconnect
  cleanup" below).

No other files were touched. `app/realtime/registry.py` and `app/realtime/broadcast.py` were
read for the concurrency idiom (lock held only for the snapshot/mutation, released before I/O)
and not modified.

## What I tested and the results

- Focused: `../.venv/Scripts/python.exe -m pytest tests/test_presence.py tests/test_ws.py -q`
  → 10/10 passing (5 presence + 5 ws, including the disconnect test I added).
- Ran `tests/test_ws.py` three times in a row to check for timing flakiness around the real
  dev-server threads: 4/4 passing each time (before I added the disconnect test), consistent
  ~2.6-2.7s each run.
- Full suite: `../.venv/Scripts/python.exe -m pytest -q` → 203 passed (193 baseline + 9 brief
  tests + 1 test I added), 0 warnings, no hangs.
- `ruff check` on the new/changed files: my own edit to `app/__init__.py` is clean. The
  brief-verbatim files (`presence.py`, `ws.py`, `test_presence.py`, `test_ws.py`) have pre-existing
  line-length findings (E501) and one unused import (`timedelta` in `test_presence.py`, from the
  brief's own text) and one E702 (`a.close(); b.close()`, also brief-verbatim). Per project
  convention, these are left for the single Task 24 `ruff check --fix` pass, not fixed here.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_presence.py tests/test_ws.py -q`
(run before creating `presence.py`/`ws.py`, with the brief's tests already written verbatim):
```
=================================== ERRORS ====================================
___________________ ERROR collecting tests/test_presence.py ___________________
ImportError while importing test module '...\tests\test_presence.py'.
Traceback:
tests\test_presence.py:4: in <module>
    from app.realtime.presence import PresenceStore
E   ModuleNotFoundError: No module named 'app.realtime.presence'
=========================== short test summary info ===========================
ERROR tests/test_presence.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.13s
```
Expected failure per the brief's Step 2 (`ModuleNotFoundError`) — matches exactly.

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_presence.py tests/test_ws.py -q`
(after implementing `presence.py`, `ws.py`, and the `app/__init__.py` wiring):
```
.........                                                                [100%]
9 passed in 2.68s
```
Then, after adding `test_disconnect_clears_presence`:
```
.....                                                                    [100%]
5 passed in 3.20s
```
(test_ws.py alone, 5/5).

Full suite after all changes:
```
../.venv/Scripts/python.exe -m pytest -q
........................................................................ [ 35%]
........................................................................ [ 70%]
...........................................................              [100%]
203 passed in 12.10s
```

## Files changed

- Created: `server/app/realtime/presence.py`
- Created: `server/app/realtime/ws.py`
- Created: `server/tests/test_presence.py`
- Created: `server/tests/test_ws.py`
- Modified: `server/app/__init__.py`

## Sweeper testing — no real 5-second wait

`presence.py`'s `sweep(now, ttl_seconds=10)` takes `now` explicitly, and
`test_sweep_expires_stale_entries` in `test_presence.py` calls `clock.freeze`/`clock.advance`
and then `s.sweep(clock.now())` directly — the same pattern the queue worker's `tick()` is
tested with. **No test sleeps, and no test waits on the real `start_sweeper` background
thread.** `start_sweeper` itself is exercised only implicitly: it's wired into `create_app`,
but every test's `Config` sets `START_WORKER=False` (see `tests/conftest.py`), so the daemon
thread it spawns never actually starts during the test run — consistent with how the existing
`Worker` is handled in tests. I did not write a dedicated test for `start_sweeper`'s thread
loop itself (the brief doesn't ask for one either); its only real logic — looking up each
changed conversation's `property_id` and calling `broadcast_presence` — is a straightforward,
low-risk composition of already-tested `PresenceStore.sweep` and `broadcast_presence`.

## Tenant boundary — WS subscribe membership check

In `ws_route`, on a `subscribe` frame the code queries
`PropertyMembership` for `(user_id, property_id)` before adding the connection to the registry:
```python
ok = db.scalar(select(PropertyMembership.id).where(
    PropertyMembership.user_id == user["id"],
    PropertyMembership.property_id == pid))
if not ok:
    ws.close(4403, "no membership")
    return
```
If there's no matching membership row, the socket is closed with code 4403 and the connection
is never registered for that property — so a client can never receive events or presence
fan-out for a property it doesn't belong to. Covered by
`test_subscribe_to_other_property_is_refused` (agent logged into property A tries to subscribe
to property B and gets `ConnectionClosed`).

## Disconnect cleanup

The task brief itself doesn't include a test that asserts presence clears when a client
disconnects (only `PresenceStore.clear_user` is unit-tested directly, and the ws tests just
call `.close()` without checking its effect on presence). Per the orchestrator's explicit
instruction to test the disconnect path rather than only connect/subscribe, I added
`test_disconnect_clears_presence` to `tests/test_ws.py` (beyond the brief's verbatim tests,
additive only): agent A sets presence to "viewing" on a conversation, agent B (subscribed to
the same property) observes the `presence.update`; agent A then closes its socket, and agent B
receives a second `presence.update` for the same conversation with an empty `users` list. This
exercises the `finally` block in `ws_route`:
```python
finally:
    connections.remove(ws)
    if property_id:
        presence.broadcast_presence(property_id, presence.store.clear_user(user["id"]))
```
Passing, confirming the wiring (not just the store's `clear_user` in isolation) actually clears
and re-broadcasts presence on disconnect.

## Self-review findings

- Completeness: all interfaces in the brief (`PresenceStore.update/clear_user/sweep/snapshot`,
  the `touch` addition, `presence.store`/`presence.broadcast_presence`, `ws.sock`/`/ws` route,
  `ws.start_sweeper`) are present and match the brief's frame shapes exactly (camelCase on the
  wire: `propertyId`, `conversationId`, `presence.update`, `subscribed`).
  I added one test beyond the brief (disconnect cleanup, described above); no production code
  beyond the brief's text was added.
- Quality: followed the existing registry/broadcast concurrency idiom — `PresenceStore`
  mutates/reads under `self._lock` and releases it before any I/O (`snapshot`/`update` never
  call `deliver` while holding the lock; `broadcast_presence` calls `store.snapshot` per
  conversation, and each `snapshot` call takes/releases the lock independently, matching the
  "copy-then-unlock" pattern used in `registry.send`/`broadcast.deliver`).
- Discipline: no rewriting of `registry.py`/`broadcast.py`; no speculative features; the
  `app/__init__.py` change is the minimal wiring block from the brief, placed after the worker
  block so `under_reloader` is already defined.
- Testing: tests exercise real behavior — a real `werkzeug` dev server thread and real
  `simple_websocket` clients for `test_ws.py` (no mocking of the socket layer), and a plain
  `PresenceStore` instance with the real `app.clock` freeze/advance for `test_presence.py`.
  TDD was followed: RED captured before any implementation file existed, then GREEN.
  Full-suite output is pristine (203 passed, 0 warnings).

## Issues or concerns

- Minor asymmetry (not a functional defect, verbatim from the brief): the sweeper's start
  condition is `config.START_WORKER and (under_reloader or not app.debug)`, which differs from
  the worker's own `config.START_WORKER and (under_reloader or config.is_production)`. This
  only affects real (non-test) process startup — in every test `Config`, `START_WORKER=False`,
  so neither guard ever fires during tests, and the difference doesn't change any test outcome.
  Flagging it since the brief explicitly said to reuse "the same guard," and the boolean
  expression itself is not identical, only the `under_reloader` variable is reused as
  instructed. I implemented it exactly as written in the brief since it isn't a genuine defect
  (no test depends on it) and isn't mine to redesign.
- No other concerns. No hangs observed in 3 repeated runs of `test_ws.py` plus one full-suite
  run; no test sleeps.

## Status: DONE

---

## Fix Report — Review Round 1

Addressed all three Important findings and the three promoted Minors from the controller's
round-1 review. Nothing about the concurrency core (lock ordering, snapshot-then-release
pattern, the membership gate, the `finally`-block disconnect cleanup) was changed — those
were confirmed correct and left intact.

### Finding 1 — sweeper start guard mismatch (`app/__init__.py:81`)

Changed `if config.START_WORKER and (under_reloader or not app.debug):` back to
`if config.START_WORKER and (under_reloader or config.is_production):`, matching the worker's
guard exactly in form, per the ruling ("make `:77` identical in form to `:68`").

### Finding 2 — `conversationId` not validated against the subscribed property (`app/realtime/ws.py`)

Two changes in `ws_route`:

1. On a `presence` frame, when `conversationId` is not null, look up
   `Conversation.property_id` for that id and `continue` (silently ignore the frame) unless it
   equals the socket's subscribed `property_id`. A null `conversationId` (meaning "I've left
   all conversations") still passes straight through, since it only clears the user's own
   entry and needs no ownership check.
2. On `subscribe`, when it replaces an *different* existing `property_id` (previously any
   truthy `property_id` unconditionally re-registered the connection), first remove the old
   registry entry **and** clear the user's presence in the old property, fanning out the
   change there, before switching to the new property. Re-subscribing to the *same* property
   is now a no-op on presence (it was previously an unconditional but harmless remove+re-add).

Also promoted `Conversation` from a function-local import inside `start_sweeper` to a
top-level import, since it's now needed at module scope for the new lookup — removing the
now-redundant local import in `start_sweeper`.

Reworked the two existing tests that used opaque, non-existent conversation ids (`"c-412"`,
`"c-777"`) to use real conversations created via `tests.factories.make_conversation`, since a
fake id now gets silently dropped by the new ownership check:
- `test_presence_is_fanned_out_to_the_property` and `test_disconnect_clears_presence` now
  create a real property-A conversation via `make_conversation(db, fx)` and use its id.

Added a new test proving the cross-property refusal itself:
- `test_presence_for_foreign_conversation_is_refused` (`server/tests/test_ws.py`) — two
  agents subscribed to property A; one sends a `presence` frame for a conversation belonging
  to **property B** (`make_conversation(db, fx, guest=fx.guest_b)`), then immediately sends a
  second, legitimate presence frame for a property-A conversation on the *same* connection.
  Because a single reader thread processes frames from one connection in order, the second
  frame's broadcast landing proves the first was already handled by the time it's observed.
  The test then asserts directly against `app.realtime.presence.store.snapshot(foreign_conv_id)
  == []` — the foreign conversation's presence set was never touched.

### Finding 3 — unsynchronized `ws.send` in `ConnectionRegistry.send` (`app/realtime/registry.py`)

Added a per-`Conn` lock, held only around the `c.ws.send(text)` call:
```python
@dataclass
class Conn:
    ws: Any
    property_id: str
    user_id: str
    send_lock: threading.Lock = field(default_factory=threading.Lock)
```
```python
for c in targets:
    try:
        with c.send_lock:
            c.ws.send(text)
        delivered += 1
    except Exception:
        self.remove(c.ws)
```
This lock is per-connection (not the registry's own `_lock`), acquired only in this one place
and never while another lock is held, so it cannot introduce a new ordering hazard — matching
the ruling exactly. No other change to `registry.py`; its snapshot-then-release design and
`remove` idempotency are untouched.

### Minors

- `ws.py` read loop: added `if not isinstance(frame, dict): continue` right after the
  `json.loads` try/except, so a valid-JSON non-object frame (`5`, `[]`, `"hi"`) is ignored the
  same way malformed JSON already was, instead of `frame.get(...)` raising and killing the
  connection.
- `ws.py` auth block: wrapped the `db.get(UserAccount, s.user_id)` result in `if u is not
  None:` before building the `user` dict, so a session whose user row was deleted falls
  through to the existing `if user is None: ws.close(4401, ...)` path instead of raising on
  `u.id`.
- `tests/test_presence.py`: `test_sweep_expires_stale_entries` now takes `app` as a parameter
  purely so that fixture's `clock.reset()` teardown runs after this test's `clock.freeze`/
  `clock.advance`, instead of leaving the process-global clock frozen at `FROZEN + 11s` for
  whatever test runs next in the same process.

### Covering tests and results

Command: `../.venv/Scripts/python.exe -m pytest tests/test_ws.py tests/test_presence.py -q`
```
...........                                                              [100%]
11 passed in 3.78s
```
(5 presence tests + 6 ws tests, including the new cross-property refusal test.)

Ran `tests/test_ws.py` alone three times in a row to re-check for timing flakiness after
adding the per-`Conn` send lock and the extra conversation-ownership DB lookups on the
`presence` path:
```
......                                                                   [100%]
6 passed in 3.82s
......                                                                   [100%]
6 passed in 3.88s
......                                                                   [100%]
6 passed in 3.77s
```

Full suite: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 34%]
........................................................................ [ 68%]
...................................................................      [100%]
211 passed in 13.16s
```
(210 baseline at task-19 fix-round start + 1 new test = 211.) 0 warnings, no hangs, no test
sleeps.

`ruff check` on all changed files: no new findings from my edits. The only remaining findings
are pre-existing line-length/semicolon items in lines that are either brief-verbatim or
unchanged by this round (confirmed by diffing before/after); one new `a.close(); b.close()`
one-liner I initially wrote in the new cross-property test was split into two statements to
avoid introducing a fresh E702 of my own.

### Files changed (this round)

- `server/app/__init__.py` — sweeper guard now matches the worker's guard in form.
- `server/app/realtime/registry.py` — per-`Conn` `send_lock` added; held only around
  `ws.send`.
- `server/app/realtime/ws.py` — conversationId ownership check on `presence`; clear+refan
  presence on the old property when `subscribe` swaps properties; ignore non-dict frames;
  ignore a deleted-user session instead of raising; `Conversation` import moved to module
  scope.
- `server/tests/test_ws.py` — reworked two tests to use real conversations;
  added `test_presence_for_foreign_conversation_is_refused`.
- `server/tests/test_presence.py` — `test_sweep_expires_stale_entries` now depends on `app`
  for clock teardown.

### Concerns

None remaining from this round. All three Important findings and all three Minors were
fixed and are covered by passing tests; the concurrency core the reviewer confirmed correct
was not touched.
