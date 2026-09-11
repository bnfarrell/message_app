# Task 17 Report: Users & memberships admin, guest detail

## What was implemented

- `server/app/schemas/users.py`: appended `CreateStaffRequest`, `StaffPatch`, `GuestDetail` (brief-verbatim).
- `server/app/domain/users.py`: appended `_staff_out`, `_check_department`, `create_staff`, `update_staff`,
  `remove_membership` (brief-verbatim), **with one deliberate deviation** — see "Deviation from brief" below.
- `server/app/api/users.py`: added `POST ""` (201), `PATCH /<user_id>`, `DELETE /<user_id>` (204), each
  `@require_auth @require_property @require_capability("manage_admin")`, following the exact decorator order
  used elsewhere in the codebase (assets.py, categories.py, quick_replies.py).
- `server/app/api/guests.py` (new): `GET /api/p/<property_id>/guests/<guest_id>` → `GuestDetail`
  (guest + stays ordered by arrival_date desc + conversation ids), brief-verbatim.
- `server/app/__init__.py`: registered `guests.bp`.
- `server/tests/test_users_admin.py` (new): the four brief-specified tests, verbatim.

## Deviation from brief (and why)

The brief's `create_staff` did a plain SELECT-then-INSERT on `UserAccount.email` (a unique column) with no
race protection. The task context explicitly flagged this as the same defect class that bit Tasks 10, 11,
16 and pointed at the established remedy in `app/domain/guests.py:30-43` (`db.begin_nested()` +
`except IntegrityError` + re-query). I applied that shape to the new-account branch of `create_staff`:

```python
try:
    with db.begin_nested():
        user = UserAccount(...)
        db.add(user)
        db.flush()
except IntegrityError:
    user = db.scalar(select(UserAccount).where(UserAccount.email == data.email.lower()))
```

This is the only change from the brief's literal code. Everything else — schemas, routes, the rest of
`create_staff`/`update_staff`/`remove_membership`, `guests.py` — is verbatim from the brief.

## Self-demotion / last-admin

The brief does not specify any protection against an admin removing their own membership or demoting/
disabling the last admin of a property. I implemented the straightforward thing: `remove_membership` and
`update_staff` apply unconditionally to any membership in the property, including the caller's own and
including the property's only admin. **Gap, reported per instructions rather than invented protection:**
an admin can currently lock a property out of admin access by demoting or removing themselves (or the last
admin) with no server-side guard. If this matters for Phase 1, it needs a follow-up task/decision.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_users_admin.py -q` (run before any
implementation, only the test file existed):

```
FAILED tests/test_users_admin.py::test_admin_creates_updates_and_removes_staff - assert 405 == 201
FAILED tests/test_users_admin.py::test_existing_account_gets_membership_not_duplicate - assert 405 == 201
FAILED tests/test_users_admin.py::test_non_admin_cannot_manage_users - AssertionError: assert 405 == 403
FAILED tests/test_users_admin.py::test_guest_detail - KeyError: 'guest'
4 failed in 0.73s
```

Expected and correct: `POST/PATCH/DELETE /api/p/<id>/users...` didn't exist yet (Flask returns 405 for a
matched-path/wrong-method), and `GET /api/p/<id>/guests/<id>` didn't exist yet (unmatched route → generic
404 JSON body with no `"guest"` key, hence the `KeyError`). This matches the brief's stated expectation
("FAIL with 404/405").

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_users_admin.py tests/test_isolation.py -q`

```
.........
9 passed in 1.27s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 39%]
........................................................................ [ 78%]
........................................                                 [100%]
184 passed in 8.56s
```

(180 previously + 4 new = 184; output pristine, no warnings.) Re-ran once more after commit with the same
result.

## Files changed

- `server/app/schemas/users.py` (modified)
- `server/app/domain/users.py` (modified)
- `server/app/api/users.py` (modified)
- `server/app/api/guests.py` (new)
- `server/app/__init__.py` (modified — registered `guests.bp`)
- `server/tests/test_users_admin.py` (new)

## Self-review findings

- Verified `app/api/guests.py` does not call `conversations.get(` — it queries `Conversation` directly by
  `guest_id`, so the isolation suite's static guard (`test_no_route_resolves_a_conversation_without_a_viewer_check`)
  passes and correctly stays out of scope (this route never resolves a single conversation for viewing).
- Verified property isolation: `create_staff`, `update_staff`, `remove_membership` all filter
  `PropertyMembership` by `property_id`, and `_check_department` validates the department belongs to the
  same property — an admin of property A cannot attach/detach a membership or department in property B.
  `tests/test_isolation.py`'s route walk (which now also covers the three new `users` routes and the new
  `guests` route) passed with no failures.
- Verified password hygiene: `StaffUserOut` never carries `password_hash`; `update_staff`'s audit `after`
  payload carries only `"password_reset": bool(data.password)`, never the password or hash.
- Confirmed decorator order (`require_auth` → `require_property` → `require_capability`) matches the
  existing convention in `assets.py`/`categories.py`/`quick_replies.py`.
- No unused imports introduced (`UserStatus` mentioned in the brief's prose import list was not actually
  referenced by the verbatim code, so it was not imported, to avoid an avoidable new ruff F401 finding).
- Ran `ruff` mentally against style — did not run the tool per project convention (one pass at Task 24); no
  reformatting of brief-verbatim code was done.

## Issues or concerns

- **Self-demotion / last-admin gap**, described above — no protection exists; flagged rather than built
  speculatively, per task instructions.
- One deliberate deviation from the brief's literal code (the `IntegrityError` race-guard in `create_staff`),
  explained above; behavior-preserving for all single-request test paths, all specified tests pass unchanged.

No other concerns.

---

## Fix Report — Review Round 1 (tests only)

The reviewer confirmed no implementation defects (race guard verified line-by-line against
`guests.find_or_create_by_phone`, password hygiene clean end to end, cross-property membership writes
blocked at two layers, `remove_membership` leaves no stale-membership window, last-admin gap ACCEPTED for
Phase 1). Two Important findings, both test-coverage gaps. Per the ruling, this round changes tests only —
no implementation code touched.

### What was changed

Appended to `server/tests/test_users_admin.py`:

1. **`test_non_admin_cannot_update_staff`** and **`test_non_admin_cannot_remove_membership`** — Finding 2's
   route-level gap: only `POST /users` had a same-property wrong-role 403 test; `PATCH` and `DELETE` had
   none (the isolation suite only proves cross-*property* 403, not same-property wrong-*role* 403). Both
   now assert a `manager` (no `manage_admin` capability) gets 403 from `PATCH` and `DELETE`.

2. **`test_create_staff_conflict_when_already_member`** — covers `create_staff`'s `Conflict` (409) branch
   when the target account is already a member of the property (admin@hvh.test re-adding agent@hvh.test to
   property A, where the membership already exists).

3. **`test_create_staff_requires_password_for_new_account`** — covers the `ValidationFailed` (400) branch
   when a brand-new email is posted with no password.

4. **`test_create_staff_rejects_cross_property_department`** — covers `_check_department`'s
   `ValidationFailed` (400) branch specifically for the cross-property vector (property A admin passing a
   real department id that belongs to property B), not just an arbitrary unknown id — this is the exact
   privilege-escalation shape the task's context repeatedly warns about.

5. **`test_create_staff_survives_concurrent_account_insert_race`** — Finding 1's dead-code gap: modeled
   directly on `test_find_or_create_by_phone_survives_concurrent_insert_race`
   (`tests/test_guests_stays.py:31-59`). Since `create_staff`'s initial lookup is an inline `db.scalar(...)`
   call rather than a standalone function like `guests.find_by_phone`, monkeypatching targets the session's
   bound `scalar` method itself (test-only change, no implementation touched): the first call is forced to
   return `None` even though a winning `UserAccount` with the same email already exists, so the `try` block
   attempts the INSERT, the unique constraint on `user_account.email` raises `IntegrityError`, and the
   `except` branch must re-query and return the winner. The test asserts all three things the ruling asked
   for: the branch actually ran (`calls["n"] >= 2`), the returned account is the pre-existing winner
   (`out.id == winner_id`), and no duplicate account was created (`len(dupes) == 1`).

### Covering tests run

Command: `../.venv/Scripts/python.exe -m pytest tests/test_users_admin.py tests/test_isolation.py -q`

```
...............
15 passed in 1.96s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 37%]
........................................................................ [ 74%]
.................................................                        [100%]
193 passed in 9.31s
```

(187 at the point this round started, per the coordinator's note that Task 18 had landed in the interim, +
6 new tests = 193; output pristine, no warnings.)

### Commit

`8b08845` — test(server): task 17 review round 1 — cover the create_staff race guard, wrong-role 403s on
PATCH/DELETE users, and create_staff's Conflict/ValidationFailed branches. Tests-only; no implementation
files changed. `server` only staged (no `.db` or `.venv` files).
