# Task 5 Report: Create an entry — validation, mention fan-out, ack snapshot

## What I implemented

1. `server/app/domain/users.py`
   - Added `UserStatus` to the `app.schemas.enums` import.
   - Added `active_members_of_department(db, property_id, department_id) -> list[str]`, a
     sibling to the existing `members_of_department` that additionally filters on
     `UserAccount.status == UserStatus.active`. `members_of_department` itself is untouched.

2. `server/app/domain/log.py`
   - New imports: `select`, `Session`, `clock`, `audit`, `notifications`,
     `active_members_of_department`, `ValidationFailed`, `Conversation`, `Department`,
     `LogEntry`, `LogEntryMention`, `LogEntryPhoto`, `Property`, `PropertyMembership`,
     `UserAccount`, `WorkOrder`, `queue_event`, `MentionTargetType`, `UserStatus`,
     `CreateLogEntryRequest`, `MentionRef`.
   - `_assert_member`, `_assert_department`, `_validate_refs` — cross-property validation
     helpers for mention/ack-audience refs.
   - `resolve_audience(db, property_id, refs)` — flattens `MentionRef`s to concrete,
     de-duplicated, active user ids, order-preserving for direct user refs.
   - `create(db, property_id, author_user_id, data, photo=None)` — validates department,
     mentions, ack_audience, linked work order/conversation are all in-property; validates the
     stripped body is non-empty (see below); resolves and freezes `ack_expected` (excluding the
     author) only when `requires_ack` is set, downgrading `requires_ack` to `False` if the
     resolved audience excluding the author is empty; persists the `LogEntry`, its
     `LogEntryMention` rows (in submitted order), and an optional `LogEntryPhoto`; fans out
     `log.mention` notifications to mentioned users (excluding the author, de-duplicated) and
     `log.ack_requested` notifications to anyone expected to ack who wasn't already mentioned;
     records an audit entry and queues a `log.entry.created` realtime event.

3. **Coordinator addition (folded in before commit, not a separate commit):** `CreateLogEntryRequest.body`'s Pydantic `min_length=1` does not catch a whitespace-only string. Added, in `create()`, right after the linked-conversation check and before building `expected`:
   ```python
   body = data.body.strip()
   if not body:
       raise ValidationFailed("A log entry needs a body")
   ```
   and used that local `body` (rather than a second `.strip()` call) when constructing the
   `LogEntry`. Added `test_a_whitespace_only_body_is_rejected` to `test_log_api.py`, placed
   with the other validation tests, before `test_a_cross_property_department_tag_is_rejected`.

4. `server/tests/test_log_api.py` (new) — the brief's 7 tests plus the coordinator's 8th
   (whitespace-only body). One deviation from the brief's literal text: the brief's import line
   included `LogEntry`, but no test in the file references the class directly (only instances
   returned by `create()` are used), so ruff flagged it as unused. I dropped `LogEntry` from
   the import to keep lint clean; this is the only place I diverged from the brief's exact code.

## Tests and results

- Target file: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
  → **8 passed**.
- Full suite: `cd server && ../.venv/Scripts/python.exe -m pytest -q` → **407 passed**
  (documented baseline 399 + 7 brief tests + 1 coordinator test = 407; matches).
- Lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` → **All checks passed.**

## TDD evidence

**RED** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`
(run immediately after writing the test file, before touching `log.py`/`users.py`):
```
FAILED tests/test_log_api.py::test_create_stores_shift_and_mentions_in_order
FAILED tests/test_log_api.py::test_department_mention_notifies_each_member_once_and_never_the_author
FAILED tests/test_log_api.py::test_ack_expected_snapshots_active_department_members_excluding_author
FAILED tests/test_log_api.py::test_disabled_users_are_excluded_from_the_snapshot
FAILED tests/test_log_api.py::test_an_empty_resolved_audience_downgrades_requires_ack
FAILED tests/test_log_api.py::test_a_cross_property_mention_is_rejected - Att...
FAILED tests/test_log_api.py::test_a_cross_property_department_tag_is_rejected
7 failed in 2.04s
```
Failure mode: `AttributeError: module 'app.domain.log' has no attribute 'create'` — expected,
since `create()` did not exist yet.

**GREEN** — after implementing `active_members_of_department`, `resolve_audience`, `create`,
and (after the coordinator's note) the whitespace-body check plus its test:
```
$ ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q
........
8 passed in 1.94s

$ ../.venv/Scripts/python.exe -m pytest -q
...
407 passed in 47.05s

$ ../.venv/Scripts/python.exe -m ruff check .
All checks passed!
```

## Files changed

- `server/app/domain/log.py` (modified — implementation)
- `server/app/domain/users.py` (modified — `active_members_of_department`)
- `server/tests/test_log_api.py` (new)

Not touched: `server/data/app.db*` (per instructions, not committed), and the pre-existing
unrelated working-tree changes (`docs/superpowers/plans/2026-09-19-hotel-log.md`, deleted
`two.png`, untracked `.claude/`, `images/`) — none of these were staged or committed.

## Self-review

- Every test exercises observable behaviour through `log_domain.create()` and checks
  persisted state (`LogEntry.shift`, `.ack_expected`, `.requires_ack`), a related table
  (`LogEntryMention`, `Notification`), or a raised exception — none of them assert on
  implementation internals or restate the code. None would pass against a `create()` that,
  say, didn't strip whitespace, didn't exclude the author, didn't filter disabled users, or
  didn't validate cross-property refs — I re-checked each assertion against a mental "naive
  broken" implementation and each one would catch it.
- `test_ack_expected_snapshots_active_department_members_excluding_author` was specifically
  set up (per the brief's own comment) to avoid the vacuous case: it adds a second active
  housekeeping member (`agent_a2`) so "an active member must be expected" is a real assertion
  about a non-empty, non-trivial denominator.
- I did not add anything beyond the brief plus the coordinator's explicitly requested
  whitespace-body fix. The only textual deviation from the brief is dropping the unused
  `LogEntry` import from the test file's import line to satisfy ruff (F401) — a mechanical
  fix, not a behavioural change.
- I verified `notifications.notify_users` and `audit.record`'s existing signatures against
  their source before using them positionally/by-keyword, and confirmed the fixture facts
  (`dept_front_desk` → `agent_a`, `agent_a2`; `dept_engineering` → `engineer_a`,
  `supervisor_a`; `dept_housekeeping` → `housekeeper_a` only) against
  `server/tests/fixtures.py` before trusting the brief's claims about them.

## Concerns

None. All steps in the brief completed as specified, the coordinator's ack-validation gap is
closed, the full suite is green at the expected count, and lint is clean.

---

## Fix report: post-review test-coverage gaps (2026-09-19, second pass)

Task 5 review returned spec/quality approval but flagged three test-coverage gaps in
`server/tests/test_log_api.py`. All three traced to the brief's test text, not to
`create()`'s implementation, and no production code changed.

### 1. Important — `test_disabled_users_are_excluded_from_the_snapshot` was vacuous

The test disables `engineer_a` (one of two active `dept_engineering` members) but only
asserted the negative (`fx.engineer_a.id not in entry.ack_expected`), which would also be
true if the whole active-filtering mechanism regressed to always returning `[]`. Added the
positive half:

```python
assert fx.supervisor_a.id in entry.ack_expected, \
    "the remaining active member must still be expected"
```

**Verified it can now fail:** temporarily changed `active_members_of_department` in
`server/app/domain/users.py` to `return []` unconditionally, reran just this test:

```
$ ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py::test_disabled_users_are_excluded_from_the_snapshot -q
FAILED tests/test_log_api.py::test_disabled_users_are_excluded_from_the_snapshot
AssertionError: the remaining active member must still be expected
assert 'c3a83a61-eba7-4537-bbcf-ad0f776a5c29' in []
```
Reverted the temporary break; `git diff server/app/domain/users.py` is empty (no
content change survived).

### 2. Minor — direct-mention-of-author path was untested

`test_department_mention_notifies_each_member_once_and_never_the_author` only exercised
author-exclusion via department membership. Extended the `mentions` list to also include
`MentionRef(type=MentionTargetType.user, id=fx.agent_a.id)` (a direct self-mention), keeping
the existing assertions, which now cover both paths.

**Verified it can now fail:** temporarily changed the author filter in `create()`
(`server/app/domain/log.py`, the `mentioned = [...]` comprehension) from
`if uid != author_user_id` to `if uid != "__nonexistent__"` (i.e. author no longer excluded),
reran just this test:

```
$ ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py::test_department_mention_notifies_each_member_once_and_never_the_author -q
FAILED ...
AssertionError: author must never be notified
assert 'dfb43c2f-...' not in ['dfb43c2f-...', '2fd6b1bf-...']
```
Reverted; `git diff server/app/domain/log.py` is empty.

### 3. Minor — mentioned-and-must-ack overlap invariant was untested

Added `test_a_mentioned_user_who_must_also_ack_is_notified_once`, asserting a user who is
both directly mentioned and in the resolved ack audience receives exactly one notification
(`log.mention`), not also `log.ack_requested`.

**Verified it passes against current code, and verified it would fail without the
cross-call filter:** temporarily changed the second `notify_users` call's recipient list in
`create()` from `[uid for uid in expected if uid not in set(mentioned)]` to `expected`
(removing the de-dup-across-calls filter), reran just this test:

```
$ ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py::test_a_mentioned_user_who_must_also_ack_is_notified_once -q
FAILED ...
AssertionError: mentioned AND expected must yield exactly one notification, the mention
assert ['log.mention', 'log.ack_requested'] == ['log.mention']
```
Reverted; `git diff server/app/domain/log.py` is empty. Confirmed against unmodified code
that the test passes:
```
$ ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py::test_a_mentioned_user_who_must_also_ack_is_notified_once -q
1 passed
```

### Full suite and lint after the fix

Note: between the original Task 5 commit and this fix, Task 6 (feed) landed on the branch
(`c2c8914`), adding its own tests to `test_log_api.py` and functions to `log.py`. That moved
the baseline from 407 to 412 independently of this fix. This fix adds exactly one new test
(#3) and extends two existing tests (#1, #2) without adding new test functions for those,
so `test_log_api.py`'s own count went from 13 to 14 (confirmed by running that file alone
before and after). Full-suite run after the fix:

```
$ cd server && ../.venv/Scripts/python.exe -m pytest -q
413 passed in 53.22s

$ ../.venv/Scripts/python.exe -m ruff check .
All checks passed!
```

### Files changed (this fix)

- `server/tests/test_log_api.py` (modified — one new test, two extended assertions)
- No production code changed (`server/app/domain/log.py` and
  `server/app/domain/users.py` are byte-identical to the prior commit; verified via
  `git diff`, which is empty for both).

Commit: `2e4c5b5` "test(server): close hotel log ack/mention test-coverage gaps"
