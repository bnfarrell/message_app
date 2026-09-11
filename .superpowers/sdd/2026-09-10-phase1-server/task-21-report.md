# Task 21 Report: Dev-only endpoints for the phone simulator and mock PMS

## What I implemented

- `server/app/schemas/dev.py` (new): `SimGuest` and `SimEvent` Pydantic models, verbatim from the brief.
- `server/app/api/dev.py` (new): blueprint `dev.bp` at `/api/dev`, with:
  - `GET /sim/guests` — lists all guests joined to their property, flagging in-house status/room from checked-in stays, and `willFail` for numbers ending in the same `FAIL_SUFFIX` (`"0000"`) that `MockSmsAdapter.send` uses to decide whether to fail a send — so the simulator's failure indicator agrees with the actual mock SMS behavior.
  - `GET /sim/thread?phone=&propertyId=` — validates both query params are present, 404s if the property doesn't exist, then delegates to `conversations.guest_thread(db, property_id, phone)`, which is the existing internal-note-free `GuestThread` shape (never touches `internal_note`, never touches `notes`).
  - `GET /sim/events` — returns the last 100 realtime events from an in-process ring buffer fed by a `broadcast.add_listener` hook.
  - `POST /pms/check-in/<stay_id>` / `POST /pms/check-out/<stay_id>` — 404 if the stay doesn't exist, otherwise builds a `PmsEvent` via `MockPmsAdapter.event_for` and applies it via `handle_event`, returning 204.
- `server/app/__init__.py` (modified): registers the `dev` blueprint only when `not config.is_production`, right after the other blueprint registrations in `create_app` — so in production the blueprint is never constructed or registered, not merely blocked per-request.
- `server/tests/test_dev.py` (new): the four brief-verbatim tests.

### Deviation from the brief's verbatim `dev.py` snippet (hardening, not a test change)

The brief's Step 3 code for the ring buffer was a bare `deque(maxlen=100)` with `_record` doing an unguarded `_events.append(ev)`, and `sim_events` doing an unguarded `list(_events)`. The task instructions (not the brief itself) explicitly required:

- bounding + locking the ring buffer so a full buffer evicts rather than grows (copy-under-lock-then-release idiom, matching `registry.py` / `presence.py`), and
- making sure the listener can never raise (a raising listener disrupts real event delivery for every request, since `broadcast.deliver` calls listeners synchronously after releasing its own lock).

This is a genuine concurrency defect in the verbatim snippet: `_record` runs on whatever thread committed a session (could be a request thread or the background worker thread), while `sim_events` runs on an HTTP reader thread. In CPython, mutating a `deque` while another thread is mid-iteration over it (which `list(_events)` does internally) can raise `RuntimeError: deque mutated during iteration` — a single `append`/`list()` call is atomic, but there's no atomicity guarantee across the pair under concurrent access. I therefore added a `threading.Lock` (`_events_lock`) guarding both the append in `_record` and the copy-then-release read in `sim_events`, and wrapped `_record`'s body in `try/except Exception: pass` so it can never propagate an error into `broadcast.deliver`'s listener fan-out. Nothing else in the brief's code was changed — schema fields, route shapes, and PMS logic are all verbatim.

## What I tested and the results

### TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_dev.py -q` (run before any implementation existed, only `tests/test_dev.py` written):

```
.FFF                                                                     [100%]
================================== FAILURES ===================================
_________________________ test_sim_guests_and_thread __________________________
    guests = client.get("/api/dev/sim/guests").get_json()
>       sarah = [g for g in guests if g["phone"] == fx.guest_inhouse_a.phone_e164][0]
E       TypeError: string indices must be integers, not 'str'
_________________________ test_sim_events_ring_buffer _________________________
    events = client.get("/api/dev/sim/events").get_json()
>       assert any(e["type"] == "message.created" for e in events)
E       TypeError: string indices must be integers, not 'str'
___________________________ test_dev_pms_endpoints ____________________________
>       assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
E       AssertionError: assert 404 == 204
=========================== short test summary info ===========================
FAILED tests/test_dev.py::test_sim_guests_and_thread - TypeError: string indi...
FAILED tests/test_dev.py::test_sim_events_ring_buffer - TypeError: string ind...
FAILED tests/test_dev.py::test_dev_pms_endpoints - AssertionError: assert 404...
3 failed, 1 passed in 0.75s
```

This is the expected failure: the `dev` blueprint didn't exist yet, so every `/api/dev/...` route 404'd (Flask's default 404 response body isn't the JSON shape the tests expect, which is why `.get_json()` returns a bare error string/None and indexing it raises `TypeError` rather than a clean assertion — still unambiguously "route not found"). `test_dev_routes_absent_in_production` passed trivially at this stage since a 404 is exactly what it asserts (not meaningful RED evidence for that test on its own, but consistent).

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_dev.py tests/test_note_leakage.py -q` (after implementing `app/schemas/dev.py`, `app/api/dev.py`, and the `create_app` registration):

```
.......                                                                  [100%]
7 passed in 0.79s
```

**Full suite** — command: `../.venv/Scripts/python.exe -m pytest -q`:

```
........................................................................ [ 33%]
........................................................................ [ 66%]
........................................................................ [100%]
216 passed in 13.49s
```

216 = the prior 212 + the 4 new tests in `test_dev.py`. Output is pristine — no warnings.

### Production-absence proof

`test_dev_routes_absent_in_production` builds the app with `Config(..., ENV="production", TESTING=True)` and asserts `GET /api/dev/sim/guests` returns 404. Because `create_app` only imports and registers the `dev` blueprint inside `if not config.is_production:`, the blueprint's URL rules are never added to `app.url_map` when `ENV="production"` — Flask's router genuinely has no matching rule, so the 404 is a real "route doesn't exist" 404, not an application-level guard that could later be bypassed or removed by a refactor. This is the strongest form of the guarantee the task calls for.

### Ring-buffer / listener safety

- `_events` is a `deque(maxlen=100)` — a full buffer evicts the oldest entry on further appends, never grows.
- Both the write path (`_record`) and the read path (`sim_events`) acquire the same `threading.Lock` before touching `_events`; the read path copies to a plain `list` under the lock and releases the lock before building `SimEvent` objects, matching the copy-under-lock-then-release idiom in `app/realtime/registry.py` (`ConnectionRegistry.send`) and `app/realtime/presence.py`.
- `_record` wraps its body in `try/except Exception: pass`, so any unexpected failure (e.g., a future change to `Event` that breaks something) cannot propagate back into `broadcast.deliver`'s listener loop and disrupt delivery to real WebSocket connections or other listeners.

## Files changed

- `server/app/schemas/dev.py` (new)
- `server/app/api/dev.py` (new)
- `server/tests/test_dev.py` (new)
- `server/app/__init__.py` (modified — added the gated blueprint registration)

## Self-review findings

- Confirmed every model/field referenced (`Guest.phone_e164`, `Guest.sms_consent_status`, `Property.sms_number`, `Property.name`, `Stay.room_number`) exists as named, and that `fixtures.py` seeds `guest_inhouse_a` with room `"412"`, matching the brief's test assertion.
- Confirmed `conversations.guest_thread` was already built in an earlier task with a strict (`extra='forbid'`) `GuestThread` schema carrying no notes field, so the dev thread endpoint cannot leak internal notes by construction — `test_note_leakage.py` (pre-existing) and the new `test_sim_guests_and_thread`'s `"notes" not in t` assertion both cover this boundary.
- Confirmed `test_isolation.py`'s static guard (no `conversations.get(` call under `app/api/`) is unaffected — `dev.py` only calls `conversations.guest_thread`, never `conversations.get`.
- Confirmed the dev routes are outside `/api/p/<property_id>`, so they're correctly excluded from the cross-property 403 walk in `test_isolation.py` — that's expected, they're unauthenticated by design, but this task file supplies their own coverage (production-absence test) which is the property that matters for them.
- Ran `ruff check` on the new/changed files: findings are all line-length (`E501`) issues inside brief-verbatim code (`app/api/dev.py` line 71, and several lines in `tests/test_dev.py`) plus one unused-import (`sqlalchemy.select`) in `test_dev.py`, also brief-verbatim. Per project convention, these are deferred to the single Task 24 `ruff check --fix` pass and were not touched.
- Diff to `app/__init__.py` is minimal and surgical: one `if` block added after the existing blueprint registrations, nothing else touched.
- No orphaned imports; no unrelated files touched.

## Issues or concerns

None. The one deviation from the brief's literal code (locking + error-swallowing in the ring buffer) is a hardening fix explicitly called for by the task instructions' "Things to be careful about" section, addresses a real CPython concurrency hazard (`deque` mutated during iteration across threads), and does not touch any test, route shape, or schema field — all four brief-verbatim tests pass unmodified.

---

## Fix Round 1 (review findings)

Coordinator review found one Important and two promoted-Minor issues; both "not yours to fix" notes (unconditional status transitions in `handle_event`, process-global `_events`) were left untouched as instructed.

### What I changed

1. **Finding 1 (Important) — `since` was ignored.** Added `_parse_since(raw)` in `server/app/api/dev.py`: absent/empty `since` returns `None` (meaning "everything"); a value that fails `datetime.fromisoformat` raises `ValidationFailed` (standard 400 error shape); a naive datetime is treated as UTC to compare against `Event.at` (always UTC-aware, from `clock.now()`). `sim_events` now takes the lock-guarded snapshot first (unchanged copy-then-release), then filters to `e.at > since` before serializing.
2. **Finding 2 (promoted Minor) — no None-guard in `_pms`.** Added `if event is None: raise NotFound("Stay not found")` right after `pms_adapter.event_for(...)`, closing the `PmsEvent | None` signature gap so a future divergence between the stay lookup and `event_for`'s own re-lookup surfaces as a clean 404, not a 500.
3. **Finding 3 (promoted Minor) — untested branches.** Added three tests to `server/tests/test_dev.py`:
   - `test_dev_pms_check_in_succeeds` — check-out then check-in the same stay, asserts it moves back to `checked_in` (exercises the check-in success path; check-in's 404 was already covered).
   - `test_sim_thread_requires_query_params_and_a_real_property` — missing `phone`, missing `propertyId`, and an unknown `propertyId` all through the live route (400, 400, 404).
   - `test_sim_events_since_filters_and_rejects_garbage` — posts an inbound message, captures `since`, advances the frozen clock, posts a second inbound message, and asserts only the second message's event passes the `since` filter; also asserts a malformed `since` value is a 400.

### A test-design issue found and fixed during this round

My first version of the `since` test asserted `bodies == ["second"]` (an exact-equality check against the full filtered event list). It passed in isolation but failed under the full suite: `_events` is a process-global ring buffer (by design, not something I'm fixing), and other test modules' events — created via their own `clock.advance()` calls within tests that also start from the same frozen `FROZEN` baseline — can carry `at` timestamps later than this test's `since` cutoff, so they leak into the filtered result. I rewrote the assertion to use a unique per-test marker embedded in the message bodies (`first-<uuid>` / `second-<uuid>`) and check membership (`second_body in bodies`, `first_body not in bodies`) rather than exact list equality, so the test is correct regardless of what else has passed through the shared buffer. Also had to URL-encode the `since` value in the test's query string (`urllib.parse.quote`) — an unescaped `+00:00` UTC offset was being decoded as a literal space by Werkzeug's query-string parsing, producing a malformed value and masking the real filtering behavior.

### Covering tests run

Command: `../.venv/Scripts/python.exe -m pytest tests/test_dev.py tests/test_note_leakage.py -q`

```
..........                                                               [100%]
10 passed in 0.94s
```

Full suite: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 32%]
........................................................................ [ 65%]
........................................................................ [ 97%]
.....                                                                    [100%]
221 passed in 15.05s
```

221 = 218 (post-Task-22 baseline) + 3 new tests. Ran twice to confirm no flakiness from the shared ring buffer; both runs identical. Output pristine, no warnings.

### Files changed (this round)

- `server/app/api/dev.py` (modified — `since` parsing/filtering, `_pms` None-guard)
- `server/tests/test_dev.py` (modified — three new tests)

### Commit

`4a4c85f` — fix(server): honor sim/events since filter, guard PMS event lookup, cover untested dev route branches
