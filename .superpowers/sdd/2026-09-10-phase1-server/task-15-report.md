# Task 15 Report: Work orders API and draft-prompt dismiss

## What I implemented

1. **`server/app/api/work_orders.py`** (new) — Blueprint at `/api/p/<property_id>/work-orders`
   with routes, implemented exactly as specified in the brief's Step 3:
   - `GET ""` — list, with `status`, `type`, `dept`, `assignee`, `mine`, `includeClosed` query filters
     (via `WorkOrderListQuery`).
   - `GET "/prefill"` — requires `create_work_order` capability; 400s if `conversationId` missing.
   - `POST ""` — create; requires `create_work_order` capability; 201.
   - `GET "/<work_order_id>"` — detail (any property member).
   - `PATCH "/<work_order_id>"` — dispatches to `work_orders.assign` / `set_priority` / `transition` /
     `comment` depending on which fields are present; closing statuses (`complete`, `verified`,
     `cancelled`) require the `close_work_order` capability, checked inline (403 otherwise), consistent
     with `test_close_requires_capability_but_create_does_not`.

2. **`server/app/api/conversations.py`** — added
   `POST /<conversation_id>/draft-prompts/<prompt_id>/dismiss`, gated by `require_capability("reply")`.

3. **`server/app/__init__.py`** — registered `work_orders.bp` in `create_app`.

4. **`server/tests/test_work_orders_api.py`** (new) — the four tests from the brief, verbatim.

## Deviation from the brief's literal snippet (and why)

The brief's Step 3 code for `dismiss_prompt` calls `draft_prompts.dismiss(...)` directly with no
prior `conversations.get` / `assert_viewer_can_see` call. Per the task instructions ("Interfaces and
facts from earlier tasks" section, point on the Task 12 security pattern), every route that touches a
conversation must call `conversations.get(...)` then
`conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)`
immediately after, before any side effect — Task 12 shipped without this on two routes and it was a
Critical finding (a dept_staff 403'd from reading a conversation could still write to it via the
missing check). The dismiss route resolves and mutates a `DraftPrompt` scoped to a conversation, so I
added the same two lines in the same position, before calling `draft_prompts.dismiss`:

```python
@bp.post("/<conversation_id>/draft-prompts/<prompt_id>/dismiss")
@require_auth
@require_property
@require_capability("reply")
def dismiss_prompt(property_id: str, conversation_id: str, prompt_id: str):
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        draft_prompts.dismiss(db, g.property_id, conversation_id, prompt_id, g.user.id)
    return no_content()
```

This isn't a brief defect I'm flagging for the controller to rule on — it's an explicit instruction
from the task assignment itself (not the brief text), so I applied it directly rather than treating it
as an open question.

I checked whether the work-order routes have an "equivalent viewer-scoping notion" that needed the
same treatment. `app/domain/work_orders.py` has no `assert_viewer_can_see`-style function — `get`,
`list`, and `detail` filter only on `property_id`, and `CAPABILITIES` has no `view_work_orders` entry
(unlike conversations, which restricts `dept_staff` to their own assigned conversations). Work orders
are visible to any property member; `dept`/`mine`/`assignee` in `list` are opt-in filters, not a
security boundary. So there is no gap to close there — I left the GET/PATCH work-order routes as
specified in the brief.

One more small fix: my edit to `app/__init__.py` (registering the new blueprint) pushed the existing
import line past 100 columns and ruff flagged it (`I001`/`E501`). Since that line is my own code, not
brief-verbatim, I reformatted it to a parenthesized one-import-per-line block (ruff's suggested fix),
consistent with the existing multi-import style already used in `conversations.py`. I left the
brief-verbatim `work_orders.py` and the pre-existing `E501`s in `conversations.py` (the
`assert_viewer_can_see` line already exceeded 100 cols before this task, at 5 pre-existing call sites)
untouched, per the project's "one ruff pass at Task 24" convention.

## TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_work_orders_api.py -q`
(run before any implementation, only the test file existed):

```
FAILED tests/test_work_orders_api.py::test_prefill_create_transition_and_detail_via_api - KeyError: 'locationRef'
FAILED tests/test_work_orders_api.py::test_close_requires_capability_but_create_does_not - KeyError: 'id'
FAILED tests/test_work_orders_api.py::test_list_filters - KeyError: 'id'
FAILED tests/test_work_orders_api.py::test_dismiss_draft_prompt - AssertionError: assert 404 == 204
4 failed in 0.78s
```

This is the expected failure: none of the `/work-orders` routes or the dismiss route existed yet, so
every request came back as a 404 with an error-shaped body lacking the keys the tests index into (or,
for dismiss, a bare 404 instead of 204).

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_work_orders_api.py tests/test_isolation.py -q`
(after implementation):

```
........
8 passed in 1.02s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`:

```
........................................................................ [ 43%]
........................................................................ [ 87%]
.....................                                                    [100%]
165 passed in 8.38s
```

(161 before this task + 4 new = 165; no warnings.)

## Files changed

- `server/app/api/work_orders.py` (new)
- `server/tests/test_work_orders_api.py` (new)
- `server/app/api/conversations.py` (added `dismiss_prompt` route + viewer check, imports)
- `server/app/__init__.py` (registered `work_orders.bp`, reformatted the import line it touched)

## Self-review

- **Completeness**: all six routes from the brief's Interfaces line are present and exercised by the
  tests (prefill, create, list w/ filters, detail, patch/transition, dismiss). `WorkOrderPatch`'s
  `clearAssignee` field is wired through `work_orders.assign(..., clear=p.clear_assignee)` even though
  no test exercises it directly — it's brief-verbatim wiring, not something I added speculatively.
- **Quality**: routes are thin — all validation and state-machine logic stays in
  `app.domain.work_orders` / `app.domain.draft_prompts` as instructed; no re-implementation of
  `TRANSITIONS` or capability tables in the route layer.
- **Discipline**: no new abstractions, no schema changes, no routes beyond what the brief specifies.
  The one deviation (viewer-scoping check on dismiss) is a security requirement from the task
  assignment, not a speculative addition.
- **Testing**: tests are brief-verbatim end-to-end HTTP tests through the real Flask test client and
  real SQLite database (no mocks). Ran isolation suite (`test_isolation.py`) explicitly — it now
  covers the work-order routes and the dismiss route automatically (route enumeration), all pass:
  cross-property 403, own-property non-403, anonymous 401.
- Ruff: `work_orders.py` and the `conversations.py`/`test_work_orders_api.py` line-length findings are
  brief-verbatim style debt intentionally left for the Task 24 cleanup pass, per project convention.
  My own new line in `app/__init__.py` was reformatted and is now ruff-clean.

## Issues or concerns

None. No brief defects found in the executable test/implementation code itself; the one place I
diverged from the brief's literal snippet (adding the viewer-scoping check to `dismiss_prompt`) was
explicitly directed by the task assignment, not a judgment call on my part.

---

## Fix report — review round 1

Tree had moved to `54d49c8` (Task 16 landed, Task 14 fix round landed, 173 tests) before I started
this round; re-read all touched files at HEAD rather than assuming my original state.

### Findings addressed

**Finding 1 (Critical) — `GET work-orders/prefill` disclosed another department's conversation.**
`prefill_from_conversation` resolves the conversation via `conv_domain.get` only (property-scoped,
not viewer-scoped). A `dept_staff` (who holds `create_work_order`) could pass any `conversationId`
in the property and get back another department's `title`/`description`/`guestName`/`locationRef`.

**Finding 2 (Important) — `POST work-orders` had the same gap on `source_conversation_id`.** No
new content leaks back to the caller, but a `dept_staff` could link a work order to a conversation
outside their department; it then surfaces via `detail()` and `conversation.updated` events.

**Finding 3 (Important) — thin PATCH coverage.** `priority`, `clearAssignee`, and a department-only
reassignment were untested, as were 403s on the two newly-scoped work-order routes.

### The structural fix (ruling, 3 parts)

1. **Added `conversations.get_for_viewer(db, property_id, conversation_id, viewer_role,
   viewer_user_id, viewer_department_id)`** to `server/app/domain/conversations.py` — `get()` +
   `assert_viewer_can_see()` in one call, returning the conversation. No other change to
   `app/domain/` (per the ruling, that layer was out of scope).

2. **Migrated every `app/api/` call site to it** — a `grep -n "conversations\.get("`
   over `server/app` before the fix found exactly 7 direct call sites, all under `app/api/`
   (6 in `server/app/api/conversations.py`: `get_conversation`, `send_message`, `retry_message`,
   `add_note`, `patch_conversation`, `dismiss_prompt`; 1 in `server/app/api/quick_replies.py`:
   `render_quick_reply`) plus the two new gaps in `server/app/api/work_orders.py` (`prefill`,
   `create_work_order`, the latter only when `source_conversation_id` is supplied — resolved and
   checked in the route before calling `work_orders.create`, per the ruling, rather than pushing
   the viewer check into the domain function). All 9 now call `get_for_viewer`. Dropped the
   now-unused `c = ...` assignment at each site (ruff `F841`) since none of the callers used the
   returned conversation object.

3. **Added a static source-level guard test** —
   `test_no_route_resolves_a_conversation_without_a_viewer_check` in
   `server/tests/test_isolation.py`. It walks `server/app/api/*.py` and regex-matches
   `\bconversations\.get\(` (which does not match `get_for_viewer(` — the `(` must follow `get`
   immediately); any hit fails the test with the offending `file:line`. Docstring explains why a
   source check was chosen over a route walk (three different id shapes: URL segment, query
   param, request body) and what the next person would be breaking if they reintroduce a bare
   `conversations.get(` call.

### New/changed tests

- `test_prefill_and_create_reject_out_of_department_dept_staff` — assigns a conversation to
  Engineering, then asserts `housekeeper@hvh.test` (dept_staff/Housekeeping) gets 403 from both
  `GET .../prefill?conversationId=` and `POST work-orders` with that `sourceConversationId`, and
  that `engineer@hvh.test` (dept_staff/Engineering) still gets 200 from prefill.
- `test_patch_priority_department_reassignment_and_clear_assignee` — covers `PATCH` with
  `priority`, a department-only reassignment (assignee untouched), and `clearAssignee` (assignee
  cleared, status falls back from `assigned` to `open`).
- `test_no_route_resolves_a_conversation_without_a_viewer_check` (new, `test_isolation.py`).

### Ruff cleanliness of my own new lines

Fixed two of my own lines that pushed past 100 columns (not brief-verbatim, so in scope):
`server/app/api/work_orders.py`'s new `create_work_order` conversation check, reflowed to fit.
Left all pre-existing `E501`/`I001` findings in these files untouched (brief-verbatim or
pre-existing from Tasks 15/16, per the project's one-ruff-pass-at-Task-24 convention).

### Commands run and results

```
../.venv/Scripts/python.exe -m pytest tests/test_work_orders_api.py tests/test_conversations_api.py tests/test_content.py tests/test_isolation.py -q
```
```
..........................
26 passed in 2.46s
```

```
../.venv/Scripts/python.exe -m pytest -q
```
```
........................................................................ [ 40%]
........................................................................ [ 81%]
................................                                         [100%]
176 passed in 7.58s
```

(173 before this round + 3 new = 176; no warnings.)

### Files changed (this round)

- `server/app/domain/conversations.py` — added `get_for_viewer`.
- `server/app/api/conversations.py` — 6 call sites migrated to `get_for_viewer`.
- `server/app/api/quick_replies.py` — `render_quick_reply` migrated.
- `server/app/api/work_orders.py` — `prefill` and `create_work_order` now check the viewer.
- `server/tests/test_isolation.py` — added the static guard test.
- `server/tests/test_work_orders_api.py` — added the two new coverage tests.

### Concerns

None. The ruling was unambiguous and the fix matches it exactly: one domain helper, every
`app/api/` call site migrated, a source-level guard so the class of bug can't recur silently, and
the requested coverage added.
