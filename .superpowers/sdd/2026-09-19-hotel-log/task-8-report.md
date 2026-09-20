# Task 8 Report: The API blueprint

## What I implemented

Followed the brief verbatim:

1. `server/app/api/log.py` (new) — the eight routes of spec §4.1:
   `GET /`, `POST /`, `GET /mentionables`, `GET /<entry_id>`, `POST /<entry_id>/ack`,
   `POST /<entry_id>/pin`, `DELETE /<entry_id>/pin`, `GET /<entry_id>/photo`, plus the
   `_photo_from_request` helper (size check then `sniff_image_type`, mirroring
   `staff_messages.py`). `bp = Blueprint("log", __name__, url_prefix="/api/p/<property_id>/log-entries")`.
2. `server/app/__init__.py` — added `log` to the `from app.api import (...)` list and
   `app.register_blueprint(log.bp)` alongside the other registrations.
3. `server/app/domain/log.py` — appended `mentionables()` (active members + departments,
   one flat list) and `get_photo()` (404s via `get()` first, then loads the blob), and
   added `LogMentionableOut` to the schema import block.
4. `server/tests/test_log_api.py` — appended the six tests from the brief verbatim:
   `test_post_and_list_through_the_api`, `test_an_agent_cannot_pin_but_a_supervisor_can`,
   `test_photo_round_trips`, `test_a_non_image_upload_is_rejected`,
   `test_mentionables_lists_people_and_departments`, `test_no_route_can_change_an_entry_body`.

No deviation from the brief's code was needed — it matched the already-committed
domain/schema layer exactly (capabilities `view_log`/`post_log`/`pin_log_entry` already
existed in `app/auth/permissions.py`; `MAX_PHOTO_BYTES`/`sniff_image_type` already existed
in `app/domain/work_orders.py`; `ValidationFailed` already mapped to 400 in `app/errors.py`).

## What I tested and the results

- Baseline (before any change): `418 passed` — matches the brief's stated baseline.
- Full suite after implementation: **424 passed, 0 failed** (418 + 6 new = 424, exactly as predicted).
- `tests/test_isolation.py` run explicitly together with `test_log_api.py`: **32 passed**
  (7 isolation tests including `test_admin_of_a_is_not_403_on_own_property` and
  `test_non_member_gets_403_everywhere` / anonymous-401 checks, + 25 log-API tests).
- `ruff check .`: **All checks passed.**

## TDD evidence

**RED** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "api or pin or photo or mentionables or immutab or body"` (run before creating `app/api/log.py` or touching `app/__init__.py`/`app/domain/log.py`):

```
FAILED tests/test_log_api.py::test_post_and_list_through_the_api - assert 404...
FAILED tests/test_log_api.py::test_an_agent_cannot_pin_but_a_supervisor_can
FAILED tests/test_log_api.py::test_photo_round_trips - AssertionError: {'erro...
FAILED tests/test_log_api.py::test_a_non_image_upload_is_rejected - Assertion...
FAILED tests/test_log_api.py::test_mentionables_lists_people_and_departments
FAILED tests/test_log_api.py::test_no_route_can_change_an_entry_body - KeyErr...
6 failed, 19 passed in 3.81s
```
Expected because the blueprint wasn't registered yet — the 404s (and the KeyError/TypeError
that follow from missing `"id"`/list bodies on a 404 page) are exactly what a missing route
table produces.

**GREEN** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py tests/test_isolation.py -q` (after writing `app/api/log.py`, registering the blueprint, and appending the two domain functions):

```
................................                                         [100%]
32 passed in 5.05s
```

Then full suite: `cd server && ../.venv/Scripts/python.exe -m pytest -q` → `424 passed in 48.74s`,
and `../.venv/Scripts/python.exe -m ruff check .` → `All checks passed!`

## Sabotage verification

For each new test, I made one production-code change, confirmed the test (and only that
test, run in isolation) failed for the right reason, then reverted and re-ran to confirm green.

1. **`test_post_and_list_through_the_api`** — changed `create_entry`'s success status from
   `201` to `200`. Failure: `assert 200 == 201`. Reverted; passes.
2. **`test_an_agent_cannot_pin_but_a_supervisor_can`** — changed `pin_entry`'s
   `@require_capability("pin_log_entry")` to `@require_capability("view_log")` (an agent
   capability). Failure: agent's pin attempt returned 200 instead of the expected 403 —
   `assert 200 == 403`. Reverted; passes. (This also stands in as evidence the isolation
   suite's admin clause is meaningful for these new routes: see item 6 below.)
3. **`test_photo_round_trips`** — made `_photo_from_request` return `None` unconditionally
   (photo silently dropped). Failure: `photoUrl` was `None` — `assert url` → `assert None`.
   Reverted; passes.
4. **`test_a_non_image_upload_is_rejected`** — changed
   `content_type = sniff_image_type(body)` to `sniff_image_type(body) or "image/png"`,
   defeating the allow-list. Failure: the GIF upload succeeded with 201 instead of 400 —
   `assert 201 == 400`. Reverted; passes.
5. **`test_mentionables_lists_people_and_departments`** — changed
   `mentionables()`'s `return people + departments` to `return people` (dropping
   departments). Failure: `kinds == {'user'}` vs expected `{'user', 'department'}`.
   Reverted; passes.
6. **`test_no_route_can_change_an_entry_body`** — temporarily added a stray
   `@bp.patch("/<entry_id>")` route returning 200. Failure:
   `assert 200 == 405` on the PATCH assertion. Reverted; passes.

**Extra check on the isolation-suite/admin interaction** (called out explicitly by the
task brief as the thing most likely to bite): temporarily removed `Role.admin` from the
`pin_log_entry` capability set in `app/auth/permissions.py` (a file I did not otherwise
touch) and re-ran `tests/test_isolation.py`. `test_admin_of_a_is_not_403_on_own_property`
failed with:
```
admin blocked on own property: [('POST', '/api/p/<property_id>/log-entries/<entry_id>/pin'),
('DELETE', '/api/p/<property_id>/log-entries/<entry_id>/pin')]
```
confirming the isolation suite genuinely exercises my new pin/unpin routes' admin
carve-out, not just pre-existing ones. Reverted; `test_isolation.py` passes 7/7 again.

After every sabotage/revert cycle I re-ran the affected test (and, at the end, the full
suite + ruff) to confirm no sabotage code was left behind — final state: 424 passed, ruff
clean, `git diff` shows only the intended additions.

## Files changed

- `server/app/api/log.py` (new)
- `server/app/__init__.py` (import + blueprint registration)
- `server/app/domain/log.py` (added `mentionables()`, `get_photo()`, `LogMentionableOut` import)
- `server/tests/test_log_api.py` (appended the six brief tests)

Not committed (pre-existing, unrelated to this task, per CLAUDE.md's DB rule and the
brief's file list): `server/app/domain/users.py` (shows modified in `git status` but
`git diff` is empty — line-ending/mode noise only, not a content change), `server/data/app.db*`,
`two.png`, `.claude/`, `images/`.

Commit: `2bc7b70 feat(server): hotel log API routes`

## Self-review findings

- Route order matches the brief's note: `/mentionables` declared before `/<entry_id>` for
  readability (Flask's routing would disambiguate either way).
- `get_entry_photo` uses `log.get_photo`, which calls `get()` first — so a nonexistent
  entry_id 404s before any photo-table query, and a real entry with no photo 404s with
  "No photo on this log entry" rather than a raw missing-row error.
- All eight routes use `require_auth` → `require_property` → `require_capability` in that
  order, matching the sibling blueprint and satisfying the isolation suite's 401/403
  ordering expectations (auth checked before membership checked before capability).
- No route mutates `LogEntry.body` — verified both by the immutability test and by reading
  the route table: only `create`, `acknowledge`, and `set_pinned` are called, none of which
  touch `body`.
- Diff is minimal: only 4 files changed, no unrelated formatting or refactors, imports
  alphabetized consistently with the existing file's style (`LogMentionableOut` inserted
  alphabetically between `LogFeedQuery` and `LogMentionOut`).

## Concerns

None. Full suite is green (424/424), ruff is clean, the isolation suite passes and was
verified to genuinely guard the new routes (both via direct route sabotage and via the
admin-capability sabotage on `permissions.py`), and the diff is scoped exactly to the
brief's file list.

---

## Addendum: fix for the two review findings (2026-09-19, post-review)

Coordinator review of Task 8 confirmed the spec, routes, decorator order, isolation, and
immutability, and judged the original seven sabotages accurate and non-redundant. It found
two defects, both originating in the brief's `Response(...)` snippet rather than in how I
followed it — the brief's `get_entry_photo` never carried the two extra headers the sibling
route sets, and never had the sibling's Content-Length guard. Branch had moved
(`82e4343` landed after my `2bc7b70`); starting baseline for this fix was **424 passed**
(confirmed by running the full suite before touching anything).

### Fixes applied to `server/app/api/log.py`

1. **`get_entry_photo`** now sets all three headers, matching
   `app/api/staff_messages.py:94` exactly:
   ```python
   return Response(body, mimetype=content_type, headers={
       "Content-Disposition": "inline",
       "X-Content-Type-Options": "nosniff",
       "Cache-Control": "private, max-age=86400",
   })
   ```
2. **`create_entry`** now calls a new `_reject_oversized_request()` as its first statement,
   before `parse_body`, mirroring `staff_messages.py:54`. Added a module-level
   `MULTIPART_OVERHEAD_BYTES = 4096` constant (own copy, per the existing
   `staff_messages.py`/`work_orders.py` convention of not sharing it).

### Tests

- Extended `test_photo_round_trips` (rather than writing a separate test) to assert all
  three response headers: `X-Content-Type-Options`, `Content-Disposition`,
  `Cache-Control`.
- Added `test_an_oversized_body_is_refused_before_it_is_parsed`, modeled on
  `test_work_order_photos.py`'s test of the same name: posts a multipart body with no
  `photo` part, only a `junk` field padded past `MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES`,
  and asserts `400` / `{"photo": "file_too_large"}`.

  **On the "distinguish from the byte check" reasoning, corrected during sabotage
  verification:** I initially wrote (copying the `work_orders` test's stated rationale)
  that if the guard did not fire, the 400 would instead name the unknown `junk` field
  (`CreateLogEntryRequest` has `extra="forbid"`). Sabotaging the guard showed this is
  **not** what actually happens in this codebase: Werkzeug 3.1's `Request.max_form_memory_size`
  defaults to 500 KB per non-file form field, so an oversized `junk` field is rejected by
  Werkzeug itself with a bare `413 REQUEST_ENTITY_TOO_LARGE` before pydantic ever sees it —
  confirmed via
  `../.venv/Scripts/python.exe -c "from werkzeug.wrappers import Request; print(Request.max_form_memory_size)"`
  → `500000`. I rewrote the test's docstring to state this accurately instead of leaving
  the borrowed-but-wrong rationale in place. The assertion itself (`400` /
  `{"photo": "file_too_large"}`) still correctly requires the guard to be present and to
  fire before either Werkzeug's or pydantic's own limits would otherwise produce a
  different, off-brand error.
  I did not attempt a test of an oversized `Content-Length` header with an
  actually-small body (i.e. a lying client) — the Flask/Werkzeug test client computes
  `Content-Length` from the real encoded body it sends, and overriding it separately
  looked like it would either be a no-op or exercise test-client internals rather than
  the route. The `junk`-field approach exercises the same code path (`request.content_length`
  read before `parse_body`) with a real oversized request, which is what actually matters.

### Sabotage verification (new fixes)

1. **Headers** — removed `"X-Content-Type-Options": "nosniff"` from the headers dict.
   `test_photo_round_trips` failed: `werkzeug.exceptions.BadRequestKeyError: 400 Bad
   Request` when the test tried `got.headers["X-Content-Type-Options"]` (the header was
   simply absent). Reverted; test passes again.
2. **Size guard** — replaced the `_reject_oversized_request()` call in `create_entry`
   with `pass`. `test_an_oversized_body_is_refused_before_it_is_parsed` failed:
   ```
   AssertionError: {'error': {'code': 'REQUEST_ENTITY_TOO_LARGE', 'message': 'The data
   value transmitted exceeds the capacity limit.'}}
   assert 413 == 400
   ```
   (Werkzeug's own field-size limit fired instead, producing the wrong status and an
   error shape this API never intends to leak.) Reverted; test passes again.

### Verification after revert

- `cd server && ../.venv/Scripts/python.exe -m pytest -q` → **425 passed** (424 baseline +
  1 new test; the header assertions extended an existing test rather than adding one).
- `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_isolation.py -q` →
  **7 passed**.
- `cd server && ../.venv/Scripts/python.exe -m ruff check .` → **All checks passed.**
- `git diff server/app/api/log.py` reviewed: only the two fixes, no stray sabotage code
  left behind.

### Files changed (this addendum)

- `server/app/api/log.py` — added `MULTIPART_OVERHEAD_BYTES`, `_reject_oversized_request()`,
  call site in `create_entry`, and the two extra headers in `get_entry_photo`.
- `server/tests/test_log_api.py` — extended `test_photo_round_trips`, added
  `test_an_oversized_body_is_refused_before_it_is_parsed`, added the two new imports
  (`MULTIPART_OVERHEAD_BYTES` from `app.api.log`, `MAX_PHOTO_BYTES` from
  `app.domain.work_orders`).

Commit: `46c6600 fix(server): harden hotel log photo route`

### Concerns

None. Both findings are fixed, verified by sabotage, and the one place my test's stated
rationale turned out to be wrong (the "guard vs pydantic" distinguishing story) was
caught during the sabotage step itself and corrected in the docstring rather than left
inaccurate.
