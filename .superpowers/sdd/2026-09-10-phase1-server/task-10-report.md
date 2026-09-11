# Task 10 Report: Guests, stays, and consent

## What I implemented

Followed the brief verbatim, per its instruction that brief code/tests are used as-is unless a genuine defect is found. No defects were found.

- `server/app/domain/guests.py`: `normalize_phone`, `find_by_phone`, `find_or_create_by_phone`, `get`.
- `server/app/domain/stays.py`: `find_in_house_for_guest`, `find_in_house_by_phone`, `get`.
- `server/app/domain/consent.py`: `STOP_WORDS`/`START_WORDS`/`HELP_WORDS`, `classify_keyword`, `STOP_CONFIRMATION`, `opt_out`/`opt_in` (via shared `_set` helper), `assert_can_send`.
- `server/tests/test_consent.py`, `server/tests/test_guests_stays.py`: brief-verbatim test files.

`ConsentError` already existed in `app/errors.py` (status 422, code `CONSENT_OPTED_OUT`) from an earlier task, so no change was needed there.

`consent._set` calls `audit.record(db, guest.property_id, None, f"consent.{status.value}", "guest", guest.id, before=..., after=...)` — matches the existing `audit.record` signature (`property_id` optional, `actor_user_id=None` since this is a guest-initiated/system-driven consent change, not a staff action).

`assert_can_send` was built as specified and is NOT wired into any call site — per the brief and task instructions, `messages.send` (which will call it) arrives in Task 11.

## What I tested and the results

Focused tests: `../.venv/Scripts/python.exe -m pytest tests/test_consent.py tests/test_guests_stays.py -q` → `21 passed`.

Full suite: `../.venv/Scripts/python.exe -m pytest -q` → `90 passed` (69 prior + 21 new), no warnings.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_consent.py tests/test_guests_stays.py -q`

```
=================================== ERRORS ====================================
___________________ ERROR collecting tests/test_consent.py ____________________
ImportError while importing test module '...\tests\test_consent.py'.
tests\test_consent.py:3: in <module>
    from app.domain import consent
E   ImportError: cannot import name 'consent' from 'app.domain' (...\app\domain\__init__.py)
_________________ ERROR collecting tests/test_guests_stays.py _________________
ImportError while importing test module '...\tests\test_guests_stays.py'.
tests\test_guests_stays.py:1: in <module>
    from app.domain import guests, stays
E   ImportError: cannot import name 'guests' from 'app.domain' (...\app\domain\__init__.py)
=========================== short test summary info ===========================
ERROR tests/test_consent.py
ERROR tests/test_guests_stays.py
!!!!!!!!!!!!!!!!!!! Interrupted: 2 errors during collection !!!!!!!!!!!!!!!!!!!
2 errors in 0.13s
```

Expected: the brief predicted `ModuleNotFoundError`; the actual failure is `ImportError: cannot import name 'X' from 'app.domain'` because `app/domain` is a package with an (empty) `__init__.py`, so importing a missing submodule name from it raises `ImportError` rather than `ModuleNotFoundError`. This is the correct failure mode for "module doesn't exist yet" in this codebase's import style (`from app.domain import consent`) — confirmed by checking how other domain modules are imported elsewhere in the codebase. Not a brief defect, just an imprecise error-name prediction in the brief text.

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_consent.py tests/test_guests_stays.py -q`

```
.....................                                                    [100%]
21 passed in 0.85s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 80%]
..................                                                       [100%]
90 passed in 3.93s
```

No warnings in either run.

## Files changed

- `server/app/domain/guests.py` (new)
- `server/app/domain/stays.py` (new)
- `server/app/domain/consent.py` (new)
- `server/tests/test_consent.py` (new)
- `server/tests/test_guests_stays.py` (new)

## Self-review findings

- Verified `normalize_phone` against all three brief test cases by hand-tracing: `"(555) 123-4567"` → `+15551234567`; `"15551234567"` → `+15551234567`; `"+44 20 7946 0958"` → `+442079460958` (leading `+` triggers the `raw.startswith("+")` branch, which strips all non-digits including the `+` itself via `\D` and re-prepends a single `+`). All correct, tests confirm.
- Verified `classify_keyword` against all 15 parametrized cases by hand-trace before running; all matched the brief's expected values (first-word-only matching correctly excludes "stop"/"help" appearing mid-sentence).
- Verified `consent.opt_out`/`opt_in` call `audit.record` with a signature that matches `app/domain/audit.py` exactly (`property_id` optional per the task's global-constraints note, `actor_user_id=None` since no staff/user is involved).
- Verified `assert_can_send` is not called anywhere outside the new test file — grep confirms no other call sites were added, consistent with the instruction that `messages.send` (Task 11) will be the sole caller.
- Confirmed `ConsentError` pre-existed in `app/errors.py` with the correct status/code — no changes needed there.
- Confirmed `app/domain/__init__.py` is empty (no explicit re-export list), so no update was needed there for the new submodules.
- No ruff run/fixes applied to the brief-verbatim code, per project convention (single pass deferred to Task 24).
- No unrelated files touched; diff is exactly the 5 new files.

## Issues or concerns

None. No brief defects found — all specified test data and expected values were verified correct by hand and by execution.

---

## Fix round 1/5 (post-review)

The reviewer found three Important issues in the TCPA layer, all inherited from the brief/spec, not from transcription. The controller ruled on each; I applied the rulings as written. Before starting, I re-synced with `HEAD` (moved to `5760adf` since my last commit — Task 9 got a fix round, and the spec's §9.1 keyword-matching rule was amended to whole-message matching in that same commit) and confirmed the current suite was at 93 passing.

### Finding 1 — `normalize_phone` accepted junk and stored it as a phone number

`app/domain/guests.py`: the final fallthrough `return "+" + digits` turned `""` into `"+"` and a 7-digit string into `"+1234567"`, both of which would then be looked up/stored as if valid.

**Fix applied (per ruling):** kept the 10-digit → `+1` rule and the `+`-prefixed passthrough exactly as before. Changed the fallthrough (no leading `+`, digit count neither 10 nor 11-with-leading-1) to `raise ValidationFailed("Invalid phone number", details={"phone": raw})`. `ValidationFailed` is the existing `app/errors.py` class (status 400, code `VALIDATION_FAILED`) already used at the API boundary (`app/api/_util.py`) for this exact shape of error — no new exception class was added.

Added `test_normalize_phone_rejects_junk` in `tests/test_guests_stays.py`, parametrized over `""`, `"   "`, `"5551234"` (7 digits), `"123456789012345"` (15 digits, no `+`) — all assert `pytest.raises(ValidationFailed)`.

### Finding 2 — keyword matching misfired on ordinary guest replies

`app/domain/consent.py`: `classify_keyword` matched on the first word only, so "Stop by room 400 later" silently opted the guest out and "Yes, extra towels please" silently opted them in.

**Fix applied (per ruling, which itself amended spec §9.1 in commit `5760adf`):** `classify_keyword` now normalizes the *whole* message (`strip()`, `lower()`, `rstrip(".,!?")`) and compares that against the keyword sets, rather than splitting and checking only the first word.

```python
def classify_keyword(body: str) -> Keyword | None:
    normalized = body.strip().lower().rstrip(".,!?")
    if not normalized:
        return None
    if normalized in STOP_WORDS:
        return "stop"
    if normalized in START_WORDS:
        return "start"
    if normalized in HELP_WORDS:
        return "help"
    return None
```

Updated `tests/test_consent.py`'s `test_classify_keyword` parametrization for the new semantics:
- Two previously-passing brief cases now correctly expect `None` under whole-message matching, since they are no longer single-keyword messages: `" Stop please "` (was `"stop"`) and `"help me"` (was `"help"`).
- Added the four misfire-pinning cases from the ruling: `"Stop by room 400 later"` → `None`, `"Yes, extra towels please"` → `None`, `"stop."` → `"stop"`, `" STOP "` → `"stop"` (the ruling's bare `"STOP"` case was already present).
- All other original cases (`"STOP"`, `"STOPALL"`, `"UNSUBSCRIBE"`, `"CANCEL"`, `"END"`, `"QUIT"`, `"START"`, `"UNSTOP"`, `"YES"`, `"HELP"`, `"Please stop the AC noise"`, `"Can you help with towels?"`, `""`) were unaffected by the semantic change and kept as-is.

### Finding 3 — `find_or_create_by_phone` could surface `IntegrityError` on a race

`app/domain/guests.py`: SELECT-then-INSERT with nothing guarding `db.flush()`; a concurrent insert of the same `(property_id, phone_e164)` (e.g. a retried webhook) would raise `IntegrityError` at the loser instead of returning the row that won.

**Fix applied (per ruling):** wrapped the insert in `db.begin_nested()` (a SAVEPOINT, so the outer transaction stays usable) and on `IntegrityError` re-query via `find_by_phone` and return `(guest, False)`.

```python
def find_or_create_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, bool]:
    existing = find_by_phone(db, property_id, phone)
    if existing:
        return existing, False
    normalized = normalize_phone(phone)
    try:
        with db.begin_nested():
            g = Guest(property_id=property_id, phone_e164=normalized)
            db.add(g)
            db.flush()
    except IntegrityError:
        g = find_by_phone(db, property_id, normalized)
        return g, False
    return g, True
```

**Test:** added `test_find_or_create_by_phone_survives_concurrent_insert_race` in `tests/test_guests_stays.py`. True multi-threaded concurrency isn't practical against a single SQLite test session, so I simulated the loser's path deterministically: a "winning" `Guest` row is inserted and flushed for a given phone number, then `guests.find_by_phone` is monkeypatched (via `monkeypatch.setattr(guests, "find_by_phone", ...)`) to return `None` on its *first* call only (simulating the race window between our existence check and our insert) and delegate to the real function afterward. This forces `find_or_create_by_phone` down its INSERT path against a phone number that is genuinely already taken in the database, so the real `UniqueConstraint("property_id", "phone_e164")` fires a real `IntegrityError` inside the real `db.begin_nested()`/`except` block — nothing about the constraint violation or the recovery path is mocked, only the timing of the initial existence check is forced. The test asserts `created is False` and that the returned guest's id matches the pre-inserted winner's id, i.e. the exception-handling branch actually executed and returned the correct row rather than raising.

### Covering tests and results

Focused: `../.venv/Scripts/python.exe -m pytest tests/test_consent.py tests/test_guests_stays.py -q`

```
..............................                                           [100%]
30 passed in 0.91s
```

Full suite: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 70%]
..............................                                           [100%]
102 passed in 4.95s
```

(93 prior + 9 new: 4 phone-junk cases, 4 keyword misfire/edge cases net of the 2 re-pointed brief cases, 1 race test.) No warnings in either run.

### Files changed (fix round 1)

- `server/app/domain/guests.py` — guarded `normalize_phone` fallthrough; race-safe `find_or_create_by_phone`.
- `server/app/domain/consent.py` — whole-message `classify_keyword`.
- `server/tests/test_guests_stays.py` — added junk-phone and race tests.
- `server/tests/test_consent.py` — updated/added keyword-matching cases.

Commit: `f815f66` — "fix(server): guard phone normalization fallthrough, whole-message keyword match, race-safe guest create"

### Concerns

None. All three rulings were applied as written; no further brief/spec discrepancies found while making these changes. The race test uses a monkeypatch to force the timing window deterministically (true thread-level concurrency against a single SQLite test session isn't practical) — flagged here per the coordinator's instruction to say so if a fully "faithful" concurrent test isn't practical, but the constraint violation and recovery path it exercises are both real, not mocked.
