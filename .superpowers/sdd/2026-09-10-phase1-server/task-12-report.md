# Task 12 Report: Conversations API — list with filters, detail, notes, assign/archive/snooze, retry

## Fix report — review round 1 (commit c64c1b6 baseline, 130 tests)

The reviewer found a Critical authorization bypass plus four Important/promoted issues. All were in
the brief's Step 5/6 code, not transcription errors on my part; the controller ruled on each and I
implemented every ruling as given.

### Finding 1 (CRITICAL): `PATCH` and `POST .../notes` skipped the viewer-scope check

`get_conversation` called `conversations.assert_viewer_can_see(...)` after `conversations.get(...)`;
`add_note` and `patch_conversation` did not, and `patch_conversation` returns the full
`conversations.detail(...)` payload including the notes array. A `dept_staff` user 403'd on `GET` could
still read a conversation's internal notes through an empty `PATCH {}`, and self-assign/reassign/
snooze/archive-attempt any conversation in the property via `PATCH`, because `require_capability`
checks a role-level capability (`assign`, `add_note`) that `dept_staff` legitimately holds — it says
nothing about whether *this* conversation belongs to them.

**Fix**: added the identical `c = conversations.get(...); conversations.assert_viewer_can_see(c, ...)`
pair to both `add_note` and `patch_conversation` in `server/app/api/conversations.py`, mirroring
`get_conversation` exactly, before either route touches the conversation.

**Tests added** (`server/tests/test_conversations_api.py`, extending
`test_dept_staff_sees_only_their_department_or_own_conversations`):
```python
assert eng.patch(f"{_base(fx)}/{diego}", json={}).status_code == 403
assert eng.post(f"{_base(fx)}/{diego}/notes", json={"body": "peeking"}).status_code == 403
```

### Finding 2 (Important): `viewer_scope` widened to the whole unassigned queue for a departmentless `dept_staff`

`Conversation.assigned_department_id == viewer_department_id` compiles to `IS NULL` when
`viewer_department_id` is `None` (a Python `None` bound parameter), and `PropertyMembership.department_id`
is nullable with nothing enforcing a value for `dept_staff`. Such a viewer would match every
conversation with no department assigned — the entire fresh-inbound queue — instead of nothing.

**Fix**: `viewer_scope` now special-cases `viewer_department_id is None` to scope by
`assigned_user_id == viewer_user_id` alone, skipping the department arm of the `OR` entirely.

**Test added**: `test_dept_staff_without_department_sees_only_own_assigned` — creates a `dept_staff`
membership with `department_id=None`, leaves a guest conversation unassigned, and asserts the
departmentless viewer's list is empty (not the unassigned queue).

### Finding 3 (Important, partial fix only, per ruling): N+1 in `list`

Per the controller's explicit ruling, I made **only** the safe half of the fix: added
`.options(selectinload(Conversation.guest), selectinload(Conversation.stay))` to the `list()` query in
`server/app/domain/conversations.py`. I did **not** touch `_last_preview` / `_open_wo_count` or the
filter SQL — that rewrite is recorded as deferred to the final review, as instructed.

### Finding 4 (promoted from Minor): `resolution_category_id` never validated against the property; archiving without one silently nulled an existing one

`patch()` validated `assigned_user_id` against `PropertyMembership` and `assigned_department_id`
against `Department.property_id`, then accepted any `resolution_category_id` from any property with no
check — same class of cross-property reference as the Critical finding, just lower blast radius.
Separately, because `ConversationPatch.resolution_category_id` defaults to `None`, archiving without
supplying one (`{"status": "archived"}`) unconditionally overwrote an already-set category with `None`.

**Fix**: added a `category_supplied = "resolution_category_id" in changes.model_fields_set` check
(Pydantic v2 tracks which fields were actually present in the request body, distinct from fields that
merely took their default). When a category *is* supplied and non-null, it's validated against
`ResolutionCategory.property_id` before being accepted (`ValidationFailed` otherwise, same shape as the
existing assignee/department checks). The archive branch and the standalone
"patch only touches the category" branch both now write `c.resolution_category_id` only when
`category_supplied` is true, so an omitted field never clobbers an existing value.

**Tests added**:
- `test_patch_rejects_resolution_category_from_another_property` — a category belonging to
  `property_b` is rejected with 400 when archiving a `property_a` conversation.
- `test_archive_without_category_preserves_an_existing_one` — archive with a category, then patch
  again with `{"status": "archived"}` and no category; asserts the category survives.

### Finding 5 (promoted from Minor): `retry_message` never checked the message belongs to the URL's conversation

The route validated the conversation exists in the property, then called
`messages.retry(db, g.property_id, message_id)`, which only scopes by `property_id` — a message could
be retried through any other conversation's URL in the same property.

**Fix**: before calling `messages.retry` (so nothing is mutated on a mismatch), the route now looks the
message up directly (`select(Message).where(Message.id == message_id, Message.property_id ==
g.property_id)`) and raises `NotFound` if it doesn't exist or its `conversation_id` doesn't match the
URL's `conversation_id`.

**Test added**: `test_retry_rejects_message_from_a_different_conversation` — sends a message on one
conversation, then hits `/other_conversation/messages/<mid>/retry` and asserts 404.

### Covering tests and full-suite run

Command: `../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py tests/test_note_leakage.py tests/test_isolation.py -q`
```
...................                                                      [100%]
19 passed in 1.65s
```

Command: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 53%]
..............................................................           [100%]
134 passed in 5.34s
```
134 = 130 baseline (after Task 11's fix round, commit `c64c1b6`) + 4 new test functions (one existing
test was extended in place with two more assertions, not counted as new). `grep -i warn` on the full
output returned nothing — pristine.

### Files changed (this round)

- `server/app/api/conversations.py` — viewer-scope checks in `add_note`/`patch_conversation`; ownership
  check in `retry_message`.
- `server/app/domain/conversations.py` — `viewer_scope` None-department guard; `selectinload` on
  `list()`; `resolution_category_id` cross-property validation and supplied-vs-default fix in `patch()`.
- `server/tests/test_conversations_api.py` — two new assertions in the existing dept-staff-scoping
  test, plus four new test functions.

### Disclosed deviations (this round)

None beyond what's described above — every change is a direct implementation of the controller's
ruling, with the exact mechanism specified (e.g. "add selectinload... two lines" was applied as
exactly that, no filter-SQL changes).

## Fix report — review round 2 (commit f8bdb79 baseline, 139 tests)

Round 1's fixes passed re-review cleanly. The re-reviewer then found the same viewer-scope gap
survives on two routes the original Critical finding didn't name.

### Finding: `POST .../messages` and `POST .../messages/<mid>/retry` still lacked `assert_viewer_can_see`

`get_conversation`, `add_note`, and `patch_conversation` all call
`conversations.get(...)` followed by `conversations.assert_viewer_can_see(...)` (added in round 1).
`send_message` and `retry_message` did not — a `dept_staff` holding the general `reply` capability
could send a guest-facing SMS into, or retry a message on, a conversation they get 403'd from on `GET`.
As the controller noted, four-of-six routes fixed is worse than zero-of-six: it reads as "the blueprint
is covered" while leaving an exploitable gap.

**Fix**: added the identical `c = conversations.get(...); conversations.assert_viewer_can_see(c, ...)`
pair to `send_message` and `retry_message` in `server/app/api/conversations.py`, right after
`conversations.get`, exactly matching the pattern on the other three routes. In `retry_message`, the
visibility check runs *before* the message-ownership lookup, so a 403'd viewer never learns whether a
given `message_id` exists on that conversation.

**Test**: extended the same consolidated assertion block in
`test_dept_staff_sees_only_their_department_or_own_conversations` (rather than adding two more
freestanding tests) so all four write routes plus `GET` are pinned together — the point being that the
next person adding a route to this blueprint sees the whole pattern in one place, not scattered checks
they might only partially copy:
```python
assert eng.get(f"{_base(fx)}/{diego}").status_code == 403
assert eng.patch(f"{_base(fx)}/{diego}", json={}).status_code == 403
assert eng.post(f"{_base(fx)}/{diego}/notes", json={"body": "peeking"}).status_code == 403
assert eng.post(f"{_base(fx)}/{diego}/messages", json={"body": "should not send"}).status_code == 403
assert eng.post(f"{_base(fx)}/{diego}/messages/00000000-0000-0000-0000-000000000000/retry").status_code == 403
```

**RED — confirmed before fixing.** Command:
`../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py::test_dept_staff_sees_only_their_department_or_own_conversations -q`
```
>       assert eng.post(f"{_base(fx)}/{diego}/messages", json={"body": "should not send"}).status_code == 403
E       AssertionError: assert 201 == 403
E        +  where 201 = <WrapperTestResponse streamed [201 CREATED]>.status_code
1 failed in 0.65s
```
This is exactly the finding: the message was sent (201) instead of being blocked (403) for a viewer
already 403'd on `GET` of the same conversation.

**GREEN.** Command: `../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py tests/test_isolation.py -q`
```
................                                                         [100%]
16 passed in 1.52s
```

Full suite: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 51%]
...................................................................      [100%]
139 passed in 6.44s
```
139 = 139 baseline (Task 13's SLA sweep/snooze wake landed at commit `f8bdb79`) — no new test
*functions* this round, only two more assertions appended to an existing one, so the count is
unchanged. `grep -i warn` on the full run returned nothing — pristine.

### Files changed (this round)

- `server/app/api/conversations.py` — added the `get` + `assert_viewer_can_see` pair to `send_message`
  and `retry_message`.
- `server/tests/test_conversations_api.py` — extended the existing dept-staff-scoping test with two
  more assertions (`POST .../messages`, `POST .../messages/<mid>/retry`), consolidating all four scoped
  write routes plus `GET` in one place.

### Disclosed deviations (this round)

None. All five conversation-scoped routes (`GET`, `PATCH`, `POST /notes`, `POST /messages`,
`POST /messages/<mid>/retry`) now uniformly call `conversations.get` then
`conversations.assert_viewer_can_see` as their first action inside the session.

## What I implemented

Followed the brief's steps in order, verbatim, after confirming its assumed interfaces (models,
domain modules, decorators, `_util` helpers) all already existed as described from Tasks 1-11.

1. **`server/app/schemas/conversations.py`** — appended `NoteOut`, `WorkOrderBrief`, `DraftPromptOut`,
   `ConversationDetail`, `GuestThreadMessage`, `GuestThread`, `ConversationPatch`, `CreateNoteRequest`,
   `ListQuery`, plus the new enum imports (`DraftPromptStatus`, `Priority`, `WorkOrderStatus`,
   `WorkOrderType`). All copied verbatim from the brief.

2. **`server/app/domain/notes.py`** (new) — `create` (extracts `@first_name` mentions, notifies
   mentioned users via `notifications.create`, audit-logs, touches the conversation) and `list_for`
   (returns `NoteOut` rows joined to author name). Copied verbatim from the brief.

3. **`server/app/domain/conversations.py`** — appended `viewer_scope`, `list`, `_last_preview`,
   `_open_wo_count`, `_summary`, `assert_viewer_can_see`, `detail`, `guest_thread`, `patch`, plus the
   private helpers `_open_wo_exists`, `_resolved_condition`, `_unanswered_expr`, and `OPEN_WO`. Copied
   verbatim from the brief, including the plan ruling that "resolved" requires the conversation to have
   been *answered* (an ignored guest never silently drops off the queue).
   Import additions: `datetime.timedelta`; `and_, case, exists, func, or_` from sqlalchemy;
   `Forbidden, ValidationFailed` from `app.errors`; `Department, DraftPrompt, Message,
   PropertyMembership, WorkOrder` from `app.models`; the new schema classes; `DraftPromptStatus, Role,
   WorkOrderStatus` from `app.schemas.enums`; `from app.domain import audit, notifications`.
   I deliberately did **not** import `InternalNote`, `UserAccount`, or `Direction` into this file — the
   brief's prose lists them as "extra imports" to add, but none of the appended code actually
   references them (notes live entirely behind `notes_domain.list_for`; `guest_thread` passes
   `m.direction` through without naming the `Direction` class). Adding unused imports would just be a
   pristine-diff violation for no behavioral benefit, so I only imported what the code uses.

4. **`server/app/api/conversations.py`** — replaced with the brief's blueprint: `GET ""`,
   `GET "/<id>"`, `POST "/<id>/messages"` (unchanged from Task 11), `POST
   "/<id>/messages/<mid>/retry"`, `POST "/<id>/notes"`, `PATCH "/<id>"`. Copied verbatim, except I
   dropped `NoteOut` from the schema import list since the route never references the class directly
   (it forwards the domain object straight to `ok()`). Did not add the
   `draft-prompts/<pid>/dismiss` route — per your instruction, that lands in Task 15 with
   `draft_prompts` machinery, and the brief's own step-6 code block omits it too.

## What I tested and the results

**TDD Evidence**

RED — command: `../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py tests/test_note_leakage.py -q`

`test_note_leakage.py` failed at collection:
```
ImportError while importing test module 'tests/test_note_leakage.py'.
tests\test_note_leakage.py:7: in <module>
    from app.schemas.conversations import GuestThread
E   ImportError: cannot import name 'GuestThread' from 'app.schemas.conversations'
```
This aborted the whole run (collection error), so I ran `test_conversations_api.py` alone to see its
failures, all as expected — 404s on the not-yet-existing `GET`/`PATCH` routes and a `KeyError:
'messages'`/`AttributeError: 'NoneType'` from assertions on payload shapes that didn't exist yet:
```
8 failed in 1.00s
FAILED test_list_sorts_oldest_unanswered_first_and_shows_context
FAILED test_filters_mine_unassigned_overdue_resolved_archived
FAILED test_dept_staff_sees_only_their_department_or_own_conversations
FAILED test_detail_includes_messages_notes_and_stay
FAILED test_note_mention_notifies_mentioned_user
FAILED test_snooze_hides_and_wakes         (404 != 200 on PATCH)
FAILED test_retry_failed_message_via_api   (KeyError: 'messages')
FAILED test_archive_requires_capability    (404 != 403 on PATCH)
```
This matches the brief's predicted RED exactly ("FAIL — 404/405 on the new routes, ImportError for
GuestThread").

GREEN — command: `../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py tests/test_note_leakage.py -q`
```
...........                                                              [100%]
11 passed in 1.16s
```

Then the isolation suite (routes auto-enumerated, catches missing `@require_property`):
`../.venv/Scripts/python.exe -m pytest tests/test_conversations_api.py tests/test_note_leakage.py tests/test_isolation.py -q`
```
...............                                                          [100%]
15 passed in 1.28s
```

Then the full suite: `../.venv/Scripts/python.exe -m pytest -q`
```
........................................................................ [ 56%]
.......................................................                  [100%]
127 passed in 4.30s
```
127 = 116 (Tasks 1-11) + 11 new. Grep for "warn" in the output returned nothing — pristine, 0
warnings.

## Files changed

- `server/app/schemas/conversations.py` (modified — added detail/note/guest-thread/patch shapes)
- `server/app/domain/notes.py` (new)
- `server/app/domain/conversations.py` (modified — added `list`, `detail`, `patch`, `guest_thread`,
  `viewer_scope`, `assert_viewer_can_see`, private helpers)
- `server/app/api/conversations.py` (modified — full blueprint: list/detail/messages/retry/notes/patch)
- `server/tests/test_conversations_api.py` (new)
- `server/tests/test_note_leakage.py` (new)

## Self-review findings

- **Completeness**: every route and domain function in the brief's Interfaces line is implemented
  except the Task-15 `draft-prompts/dismiss` route, which was explicitly out of scope. All six new
  tests plus the three note-leakage tests plus the existing isolation suite pass.
- **Quality**: code matches brief verbatim for logic; the only deviations are import-list trimming
  (dropped unused `InternalNote`, `UserAccount`, `Direction` in `domain/conversations.py` and unused
  `NoteOut` in `api/conversations.py`) — a strict subset of the brief's suggested imports, not a
  behavior change, and it keeps the diff free of unused-import lint noise.
- **Discipline**: no speculative code added; `notes.py` and the appended `conversations.py` functions
  do exactly what the interfaces specify and nothing more. Did not touch `find_or_create_for_guest`,
  `get`, `sla_minutes`, `auto_resolve_hours`, or any pre-existing code beyond the required import-line
  edit.
  Did not implement the `draft-prompts/dismiss` route per your explicit instruction.
- **Testing**: tests exercise the real HTTP surface through the Flask test client and real SQLAlchemy
  queries (SQLite), no mocks. TDD was followed — RED captured before any implementation code was
  written. Test output is pristine (no warnings) at both the focused and full-suite level.
- I traced through the trickiest test by hand before running anything — `test_filters_mine_...`'s
  resolved/archived sequencing — to confirm the plan-ruled "resolved requires answered" semantics
  actually produce the exact set memberships the test asserts at each step (mine/unassigned/overdue/
  resolved/archived), and they did on the first run.

## Issues or concerns

None. No brief defects found — every plan-verbatim test passed as written, and the "resolved only if
answered" ruling from the plan was implemented exactly as specified in `_resolved_condition`. The
`draft-prompts/dismiss` route is intentionally absent per instructions (Task 15 concern).
