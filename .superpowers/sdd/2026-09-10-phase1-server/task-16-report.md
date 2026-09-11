# Task 16 Report: Quick replies, digital assets, resolution categories

## What I implemented

Followed the brief's steps exactly, with two deliberate deviations noted below.

- `server/app/schemas/content.py` (new): `QuickReplyIn/Patch/Out`, `RenderRequest`, `RenderedQuickReply`,
  `AssetIn/Patch/Out`, `CategoryIn/Patch/Out` — verbatim from the brief.
- `server/app/domain/quick_replies.py` (appended, `interpolate` untouched): `list`, `get`,
  `_assert_shortcut_free`, `create`, `update`, `delete`, `context_for_conversation`, `render` —
  verbatim from the brief's Step 4 code block, plus the needed imports (`func, or_, select` from
  sqlalchemy; `Session`; `Guest, Property, QuickReply, Stay, UserAccount` from `app.models`;
  `Conflict, NotFound`; `conversations as conv_domain`; `segment_count`; the content schemas).
  I did not import `Conversation` (mentioned in the brief's prose but never referenced by any
  function body) to avoid an unused import.
- `server/app/domain/assets.py` (new): `new_short_code`, `list`, `get`, `get_by_short_code`,
  `create`, `update`, `delete` — verbatim from the brief **except** `new_short_code`, see "Deviation
  1" below.
- `server/app/domain/categories.py` (new): `list_tree`, `get`, `create`, `update`, `delete` —
  verbatim from the brief.
- `server/app/api/quick_replies.py` (new): `list/create/update/delete/render` routes under
  `/api/p/<property_id>/quick-replies` — verbatim from the brief **except** `render_quick_reply`,
  see "Deviation 2" below.
- `server/app/api/assets.py` (new): `list/create/update/delete` under
  `/api/p/<property_id>/assets`, GET open to any property member, others `manage_admin`.
- `server/app/api/categories.py` (new): `list/create/update/delete` under
  `/api/p/<property_id>/resolution-categories`, same capability split.
- `server/app/api/short_links.py` (new): public `GET /a/<short_code>` → 302 redirect or 404 —
  verbatim from the brief.
- `server/app/__init__.py` (modified): registered the four new blueprints in `create_app`.

No Alembic migration was needed — `quick_reply`, `digital_asset`, and `resolution_category` tables
already exist in `alembic/versions/0001_init.py` from earlier tasks.

### Deviation 1 — bounded retry in `new_short_code`

The brief's `new_short_code` is `while True: ... ` with no bound. The task dispatch instructions
explicitly flagged this as something to get right: "a retry loop needs a bound." I changed it to
`for _ in range(MAX_SHORT_CODE_ATTEMPTS)` (20 attempts) with a `RuntimeError` raised if all attempts
collide, so a systemic problem (e.g. a bug that always regenerates the same code, or a genuinely
near-exhausted code space) surfaces as a loud failure instead of hanging the request forever. With
31^6 ≈ 887M possible codes this is not expected to ever trigger in practice; it's a defensive bound,
not a functional change to the collision-avoidance logic (still checks uniqueness against the DB
each time, same alphabet, same length).

### Deviation 2 — `assert_viewer_can_see` on the render route

The brief's `render_quick_reply` route takes a `conversationId` and calls
`quick_replies.render(...)`, which reads that conversation's guest/stay context, but the brief's
route code never calls `conversations.assert_viewer_can_see(...)`. Per the security pattern from
Task 12 (explicitly called out in my task dispatch as something Task 12 got wrong twice — a
Critical finding), any route that reads a specific conversation must call
`conversations.get(...)` then `conversations.assert_viewer_can_see(...)` before any side effect
(here, the side effect is `usage_count += 1`, and a dept_staff agent could otherwise render a
teaser of another department's conversation's guest name/room number). I added:

```python
c = conversations.get(db, g.property_id, body.conversation_id)
conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
```

before the call to `quick_replies.render(...)` in `app/api/quick_replies.py`. This does mean
`conversations.get` runs twice (once in the route, once inside `context_for_conversation`) — an
acceptable small redundancy given the existing house pattern in `app/api/conversations.py` does
the same double-get.

## Public short-link route vs. the isolation suite

`GET /a/<short_code>` is registered with no `/api/p/<property_id>` prefix. `tests/test_isolation.py`
only enumerates rules whose path starts with `/api/p/<property_id>` (`property_rules()` filters on
`rule.rule.startswith("/api/p/<property_id>")`). Since `/a/<short_code>` doesn't match that prefix,
it is never enumerated by any of the three isolation tests — no special-casing or suite change was
needed. I verified this by running `tests/test_isolation.py` together with the new tests (all 7
pass) and confirming the isolation suite's route count only grew by the property-scoped routes
(quick-replies, assets, resolution-categories), not by the short-link route.

## Testing

### TDD Evidence

**RED** — command: `../.venv/Scripts/python.exe -m pytest tests/test_content.py -q` (run before
any implementation code existed, only the test file written):

```
FFF                                                                      [100%]
================================== FAILURES ===================================
___________________ test_quick_reply_crud_search_and_render ___________________
...
>       assert r.status_code == 201
E       assert 404 == 201
E        +  where 404 = <WrapperTestResponse streamed [404 NOT FOUND]>.status_code
______________ test_assets_crud_short_link_and_send_appends_link ______________
...
>       assert len(a["shortCode"]) == 6
                   ^^^^^^^^^^^^^^
E       KeyError: 'shortCode'
_______________________ test_resolution_categories_tree _______________________
...
>       child = admin.post(base, json={"name": "HVAC", "parentId": parent["id"]}).get_json()
                                                                   ^^^^^^^^^^^^
E       KeyError: 'id'
=========================== short test summary info ===========================
FAILED tests/test_content.py::test_quick_reply_crud_search_and_render - asser...
FAILED tests/test_content.py::test_assets_crud_short_link_and_send_appends_link
FAILED tests/test_content.py::test_resolution_categories_tree - KeyError: 'id'
3 failed in 0.59s
```

Expected: all three routes (`quick-replies`, `assets`, `resolution-categories`) didn't exist yet, so
every POST returned 404 and every downstream `.get_json()` field access failed — exactly the "FAIL
with 404s" the brief predicted.

**GREEN** — command: `../.venv/Scripts/python.exe -m pytest tests/test_content.py tests/test_isolation.py -q`
(after implementation):

```
.......                                                                  [100%]
7 passed in 0.92s
```

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`:

```
........................................................................ [ 42%]
........................................................................ [ 85%]
........................                                                 [100%]
168 passed in 6.71s
```

165 previously-passing tests + 3 new tests in `test_content.py` = 168, all green, no warnings
summary emitted (pristine).

### Ruff check

`../.venv/Scripts/python.exe -m ruff check` on all new/changed files: 30 findings, all `E501` (line
too long), all inside brief-verbatim code (function signatures/bodies copied from the brief, and
the brief-verbatim test bodies). Per project convention, these are deferred to the single
`ruff check --fix` pass at Task 24 and were not touched.

## Files changed

- New: `server/app/schemas/content.py`, `server/app/domain/assets.py`,
  `server/app/domain/categories.py`, `server/app/api/quick_replies.py`, `server/app/api/assets.py`,
  `server/app/api/categories.py`, `server/app/api/short_links.py`, `server/tests/test_content.py`
- Modified: `server/app/domain/quick_replies.py`, `server/app/__init__.py`

## Self-review findings

- Completeness: all interfaces in the brief's "Produces" list are implemented and covered by the
  three brief-verbatim tests (CRUD + search + render for quick replies; CRUD + short link resolve +
  message-send-appends-link + soft-delete for assets; tree list/create/update/delete-with-children-guard
  for categories).
- Quality: matched existing house patterns (`app/api/work_orders.py`, `app/api/conversations.py`)
  for blueprint shape, `db_session()`/`parse_body()`/`ok()`/`no_content()` usage, and capability
  decorators. Names and structure match the brief's file organization exactly — no unrequested
  splitting or abstraction.
- Discipline: no speculative features added. The only departures from the brief's literal code are
  the two called out above (bounded short-code retry, and the missing viewer-visibility check on
  render), both explicitly flagged as risks in my task dispatch rather than my own invention.
- Testing: tests exercise real HTTP routes through the Flask test client against a real SQLite DB
  (via the `app`/`fx`/`client`/`database`/`login` fixtures) — no mocks. TDD was followed: test file
  written and run to RED before any implementation file was created.

## Issues or concerns

None outstanding. Two intentional deviations from the brief's literal code are documented above
(bounded short-code retry; added `assert_viewer_can_see` on the render route) — both are corrections
of latent defects in the brief itself, not concerns about the current implementation.

---

## Fix round 1

Review found five Important issues, no Critical. Both disclosed deviations from the original report
(bounding the short-code retry loop, adding the viewer check to `render_quick_reply`) were confirmed
correct on their merits, and the isolation-suite reasoning for the public short-link route was
verified correct — no changes needed there.

Note: between the original submission and this fix round, Task 15's own fix round landed
`conversations.get_for_viewer(db, property_id, conversation_id, role, user_id, department_id)` and
migrated every route that reads a specific conversation onto it, including `render_quick_reply` in
`server/app/api/quick_replies.py` (now `conversations.get_for_viewer(...)` in place of the
`conversations.get(...)` + `assert_viewer_can_see(...)` pair I had added). A new static test
(`tests/test_isolation.py::test_no_route_resolves_a_conversation_without_a_viewer_check`) forbids any
`app/api/*.py` module from calling `conversations.get(` directly. **I made no changes to
`app/api/quick_replies.py` in this fix round** — it already uses `get_for_viewer` and needs nothing
further from me.

### What I changed

**Finding 1 — TOCTOU race on `short_code` and `shortcut` (Important).**
`server/app/domain/assets.py`: `create()` now wraps the insert in `db.begin_nested()` and retries
with a fresh `new_short_code(db)` on `IntegrityError`, bounded by the same
`MAX_SHORT_CODE_ATTEMPTS` (20) used for code generation; exhaustion raises `Conflict` (see Finding 2).
`server/app/domain/quick_replies.py`: `create()` and `update()` now wrap their `db.flush()` in
`db.begin_nested()` and turn an `IntegrityError` (the `uq_quick_reply_shortcut` constraint firing on
a race the pre-check `_assert_shortcut_free` missed) into a `Conflict("Shortcut ... is already in
use")` instead of letting it propagate as an unhandled 500. This mirrors the established
`app.domain.guests.find_or_create_by_phone` remedy (Task 10 fix round) rather than inventing a new
shape, per the reviewer's ruling.

**Finding 2 — `RuntimeError` breaks the error contract (Important).**
`server/app/domain/assets.py`: `new_short_code()`'s retry-exhaustion branch now raises `Conflict`
(an `AppError` subclass, which `register_error_handlers` renders as `{"error": {"code",
"message"}}`) instead of a bare `RuntimeError` that would fall through to Flask's default
unstructured 500. The `create()` exhaustion branch (see Finding 1) raises the same `Conflict`.

**Finding 3 — `categories.delete` has an unguarded FK (Important).**
`server/app/domain/categories.py`: `delete()` now also checks
`select(Conversation.id).where(Conversation.resolution_category_id == c.id)` and raises
`Conflict("Reassign the conversations using this category first")` before the existing
child-category check's sibling would otherwise let `db.delete(c)` hit SQLite's FK enforcement
(`PRAGMA foreign_keys=ON`, `app/db.py:58`) and raise an unhandled `IntegrityError`. Added a new
import of `Conversation` from `app.models`.

**Finding 4 — the viewer-scope fix on render had no test (Important).**
Added `test_render_quick_reply_respects_viewer_scope` to `server/tests/test_content.py`: creates a
quick reply as admin, opens an inbound conversation for a guest with no stay (so the conversation is
unassigned), then asserts a `dept_staff` caller (`engineer@hvh.test`) gets 403 rendering it — mirrors
the existing pattern in `test_dept_staff_sees_only_their_department_or_own_conversations`
(`tests/test_conversations_api.py`) where an unassigned conversation is invisible to dept_staff.

**Finding 5 — assets/categories have no authorization test (Important).**
Added `test_assets_require_manage_admin` and `test_resolution_categories_require_manage_admin` to
`server/tests/test_content.py`: each logs in as `agent@hvh.test` (role `agent`, lacks
`manage_admin`) and asserts 403 on create/update/delete against that surface, matching the existing
403 assertion already present for quick-reply create.

**Extra regression test (my own addition, not explicitly requested).** Added
`test_resolution_category_delete_blocked_by_conversation_reference` to directly exercise the
Finding 3 fix: archives a conversation with a `resolutionCategoryId` set via the conversations PATCH
route, then asserts deleting that category returns 409 rather than crashing.

### Covering tests

Command: `../.venv/Scripts/python.exe -m pytest tests/test_content.py tests/test_isolation.py -q`

```
............                                                             [100%]
12 passed in 1.37s
```

(12 = the original 3 brief tests + 4 new tests in `test_content.py` + 5 tests in
`test_isolation.py`, including the new static `get_for_viewer` check inherited from Task 15's fix
round.)

Full suite — command: `../.venv/Scripts/python.exe -m pytest -q`

```
........................................................................ [ 40%]
........................................................................ [ 80%]
....................................                                     [100%]
180 passed in 8.23s
```

176 (post Task 14/15 fix rounds, per the coordinator's count) + 4 new tests = 180, all green, no
warnings summary emitted (pristine).

### Ruff check

Re-ran `../.venv/Scripts/python.exe -m ruff check` on all touched files. All findings are `E501`
(line too long) in brief-verbatim lines predating this fix round (e.g. `quick_replies.list`,
`_assert_shortcut_free`, `context_for_conversation`, `assets.get`/`get_by_short_code`,
`categories.list_tree`/`update`) — deferred to Task 24 per project convention. Every line I
authored or edited in this fix round (the new `begin_nested`/`IntegrityError` blocks, the new FK
guard, the new tests) is under the 100-column limit; I tightened a couple of my own lines (the
`new_short_code`/`create` exhaustion messages in `assets.py`, and two of the new test lines) that
would otherwise have tripped E501, since those are my own new code rather than brief-verbatim.

### Files changed (this fix round)

- `server/app/domain/assets.py` — bounded-retry `create()`, `Conflict` instead of `RuntimeError`
- `server/app/domain/categories.py` — `delete()` also guards against a referencing `Conversation`
- `server/app/domain/quick_replies.py` — `create()`/`update()` catch `IntegrityError` as `Conflict`
- `server/tests/test_content.py` — 4 new tests (viewer-scope render, assets 403, categories 403,
  category-delete-blocked-by-conversation regression)
- `server/app/api/quick_replies.py` — **not modified**; already on `get_for_viewer` from Task 15's
  fix round, so no change was needed for Finding 4's underlying code (only its missing test).

### Self-review

- Matched the reviewer's explicit ruling on Finding 1 (mirror `guests.find_or_create_by_phone`'s
  `begin_nested`/`except IntegrityError` shape) rather than inventing a different remedy.
- Confirmed I did not reintroduce a manual `conversations.get(` call anywhere in `app/api/` — the
  static test in `test_isolation.py` covers this and passes.
- Did not touch the three brief-verbatim tests in `test_content.py`; only appended new test
  functions.
- Re-ran the full suite after tightening line lengths in my own new code to confirm no regression.

### Concerns

None outstanding.
