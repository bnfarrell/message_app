# A1 — server endpoints for the admin section

Server-only. No client changes at all; A2 and A3 consume what you build.

The user has explicitly authorized these additions beyond the spec's API table (rulings D56–D59
in `progress.md`). Spec line 385 lists only `GET departments` and the spec has no properties
endpoint anywhere — that is expected, not a contradiction for you to resolve.

Three items. Each inherits the house pattern rather than inventing one: routes under
`/api/p/<property_id>/`, `require_auth` then `require_property` (then
`require_capability("manage_admin")` on writes), Pydantic in and out, camelCase via
`model_dump(by_alias=True)`, domain functions taking `(db, property_id, ...)` and filtering
every query on `property_id`.

**Your precedent for all of it is `server/app/api/categories.py` plus
`server/app/domain/categories.py`** — resolution categories are the one aggregate that already
has exactly the shape you are adding. Read both before you start, and follow them.

---

## 1. `locale` becomes patchable on quick replies

`server/app/schemas/content.py:19` — `QuickReplyPatch` carries `shortcut`, `title`, `body`,
`category`, `department_id`, `active`. `QuickReplyIn` has `locale` (default `"en"`) and
`QuickReplyOut` returns it, but it cannot be changed after creation. Add it.

- `locale: str | None = None` on `QuickReplyPatch`. Match whatever validation `QuickReplyIn`
  applies to the same field; the column is `String(8)`.
- Check that `server/app/domain/quick_replies.py`'s `update` actually applies it — if it
  iterates the set fields generically you may need no domain change at all; if it assigns field
  by field, add it there too.
- Test: PATCH `locale`, assert it persists and that the other fields are untouched.

## 2. Departments — read-only becomes full CRUD

Today `server/app/api/departments.py` has exactly one route, `GET ""`, which calls
`users.list_departments` (`server/app/domain/users.py:21`). The `Department` model
(`server/app/models/core.py:64-72`) has `property_id`, `name`, `type` (a `DepartmentType` enum),
`escalation_minutes` (default 15) and `active`. `DepartmentOut` is at
`server/app/schemas/users.py:8`.

**Ruling D61 — put the new domain functions in `server/app/domain/users.py`, beside
`list_departments`.** Do NOT create `domain/departments.py`, and do NOT move `list_departments`
into one. The API blueprint already reaches into `users` for departments; that precedent stands,
and moving the existing function ripples into its callers for no gain. If you find a concrete
reason this is wrong, say so in your report rather than quietly doing it the other way.

Add to `server/app/api/departments.py`, mirroring `categories.py` route for route:

- `POST ""` returning 201, gated `require_capability("manage_admin")`
- `PATCH "/<department_id>"` returning 200, same gate
- `DELETE "/<department_id>"` returning 204, same gate

`GET` stays on `require_auth` then `require_property` only — exactly as it is now, and exactly
as `list_categories` is. Every member can read the department list; only admins may change it.
**Do not add a capability gate to the existing GET** — half the product reads this list to
populate department pickers, and gating it would break those screens.

New schemas in `server/app/schemas/users.py` beside `DepartmentOut`:

- `DepartmentIn`: `name` (1–100), `type` (`DepartmentType`), `escalation_minutes` (default 15,
  must be positive), `active` (default True).
- `DepartmentPatch`: every field optional.

**The delete guard is the part that matters.** Five tables carry a nullable FK to
`department.id`. Verify this list yourself with
`grep -rn 'ForeignKey("department.id")' server/app/models/` rather than trusting me:

- `PropertyMembership.department_id` (`core.py:85`)
- `QuickReply.department_id` (`content.py:17`)
- `DigitalAsset.department_id` (`content.py:38`)
- `Conversation.assigned_department_id` (`conversations.py:35`)
- `WorkOrder.department_id` (`work_orders.py:37`)

Follow `categories.delete` (`server/app/domain/categories.py:49-55`) exactly: check each
reference and raise `Conflict` with a message naming what the admin must fix first. A delete
that orphans a work order's department, or silently nulls a staff member's assignment, is the
failure mode you are preventing. Do not add `ON DELETE` cascade behaviour, and do not
soft-delete — spec line 86 says soft-delete is not used in Phase 1. Deactivating
(`active=False`) is the escape hatch for a department that is in use, and your `Conflict`
message should point the admin at it.

Tests: create; patch each field; delete a clean department; and **one test per referencing
table** proving the delete is refused while that reference exists. Do not assert anything about
seed contents — create the rows each test needs.

## 3. Property settings — a new endpoint (ruling D58)

`GET /api/p/<property_id>/settings` and `PATCH /api/p/<property_id>/settings`. New blueprint
`server/app/api/properties.py`, new domain module `server/app/domain/properties.py` (this one IS
its own aggregate, unlike departments). Register the blueprint wherever the others are
registered.

The route shape is deliberate: NOT a bare `GET /api/p/<property_id>`. Spec line 479's acceptance
criterion 9 enumerates every rule in `app.url_map` under `/api/p/<property_id>` and cross-tenant
tests each method automatically — a bare-prefix route is an awkward shape for that enumeration,
and it reads wrong beside every sibling.

The `Property` model (`server/app/models/core.py:33-45`) already carries every field you need.
**There is no migration in this work.** If you conclude you need one, stop and say so in your
report.

- `PropertySettingsOut`: `id`, `name`, `code`, `timezone`, `address`, `phone`, `sms_number`,
  `brand`, `currency`, `logo_url`, `primary_color`.
- `PropertySettingsPatch`: `name`, `timezone`, `address`, `phone`, `sms_number`, `brand`,
  `currency`, `logo_url`, `primary_color` — all optional.
- **`code` is returned but NOT patchable.** It is `unique=True` across the whole install and is
  what identifies the property; renaming it is not a settings edit.
- **The `settings` JSON blob is not exposed at all** — not in Out, not in Patch. Nothing in the
  UI needs it, and an untyped bag on a public API is a liability (CLAUDE.md section 2).
- `GET`: `require_auth` then `require_property`, no capability gate — siblings behave this way.
- `PATCH`: adds `require_capability("manage_admin")`.

Validation that must be real, not decorative:

- **`timezone` must be a valid IANA zone.** Reject anything `zoneinfo.ZoneInfo()` cannot
  construct. This field is load-bearing — it is already the intended basis for analytics
  bucketing — so a typo must 422, not persist.
- `currency`: exactly 3 letters.
- `phone` and `sms_number`: check whether this codebase already has phone normalisation or
  validation (search for it) and REUSE it. Do not write a second phone validator.
- Lengths must match the columns: name 200, address 400, phone and sms_number 32, brand 100,
  currency 3, logo_url 500, primary_color 16.

Tests: GET returns the shape; PATCH each field; `code` is rejected or ignored (pick one, say
which in your report, and test the behaviour you chose); a bad timezone 422s; a non-admin PATCH
403s; a member of property A patching property B gets 403.

## 4. A quick-reply PREVIEW endpoint (ruling D67) — the reason M9's preview was declined once

`POST /api/p/<property_id>/quick-replies/preview`.

The admin screen needs a live "Preview as ..." pane and a character/segment counter under the
body field. **The existing `POST /<id>/render` cannot serve either**, for three separate
reasons, all verified in source:

1. **It increments the usage metric.** `server/app/domain/quick_replies.py:130` does
   `r.usage_count += 1`. The admin table on the very same screen renders a "Uses · 30d" column.
   Previewing would inflate the number displayed beside it.
2. **Its capability excludes the people who use the screen.** `/render` is gated on `reply`.
   `server/app/auth/permissions.py` has `manage_admin = {admin, corporate}` but
   `reply = {agent, dept_staff, supervisor, manager, admin}` — **`corporate` is not in `reply`**.
   A corporate admin can open the admin screen and would get a 403 from its own preview pane.
3. **It requires a saved quick reply and a real conversation id.** The edit panel needs to
   preview the draft body *as the admin types it*, before Save — and a property may legitimately
   have no conversation to render against.

So add a sibling that does none of those things:

- Request: `{ body: str, conversationId: str | None }`. It previews **arbitrary body text**, not
  a stored row, so the panel can preview unsaved edits.
- Gate: `require_auth` then `require_property` then `require_capability("manage_admin")` — the
  screen's own capability, so corporate works.
- **It must not mutate anything.** No `usage_count` increment, no writes at all.
- With a `conversationId`, interpolate using the existing
  `context_for_conversation`. **Without one — or for any variable that resolves to `None` —
  fall back to the `FALLBACKS` map already at `server/app/domain/quick_replies.py:18-22`**
  (`"there"`, `"your room"`, `"the front desk"`, `"soon"`, …). Reuse `interpolate`; do not write
  a second interpolator.
- Response: the existing `RenderedQuickReply` — `{ body, segments, characters }`.
- Segments come from `segment_count` (`server/app/domain/sms.py:22-29`), which already
  implements GSM-7 vs UCS-2 with the 160/153 and 70/67 boundaries. **This is exactly why the
  counter is server-side:** that boundary logic is subtle enough that an earlier task on this
  project shipped an off-by-one in it, and a TypeScript re-implementation in the client would
  be a second copy free to drift.

Also confirm and report the authoritative variable list. `server/app/domain/quick_replies.py:15-16`
defines `VARIABLES` as **five** names — `guest_first_name`, `room_number`, `property_name`,
`agent_first_name`, `departure_date`. `docs/mockups/Admin.dc.html` draws only four "Insert:"
chips and omits `property_name`. **Ruling D68: the server's five are authoritative** — A2 will
render a chip per variable, so expose the list rather than making the client hardcode it. Either
return `VARIABLES` from an endpoint or confirm in your report that the client should read it
from a shared constant; say which and why.

Tests: a preview with no `conversationId` returns fallback-interpolated text; a preview with one
returns real guest data; **a preview does NOT change `usage_count`** (assert the before and
after value — this is the regression test that matters); a `corporate` user gets 200, not 403;
a non-admin gets 403; segments and characters match `segment_count`/`len` for a GSM-7 body and
for a body containing a non-GSM character.

---

## Verify before you commit

- The full server suite. It is at **258 passing** right now — that is the number to beat, and
  nothing in it may break.
- Confirm spec acceptance criterion 9's cross-tenant enumeration test still passes, and that it
  actually picked up your four new routes (it enumerates `app.url_map`, so it should). If your
  new routes are somehow not enumerated, that is a finding — report it.
- Whatever lint the server has wired up.

## Out of scope — do not build these

- Any client or web change whatsoever. A2 and A3 own the screens.
- Automations, blocked numbers, integrations — no models, no endpoints, and the mockup captions
  them Phase 2.
- Migrations. Both models already exist in full.
- Moving `list_departments` out of `domain/users.py`.

## Report

Write your full report to `admin-A1-report.md`. Per item: what you added, which files, the
validation you chose and why, the delete-guard behaviour, and a "Found but not fixed" section.

Return in your final message ONLY: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT /
BLOCKED), commit shas, a one-line test summary, and your concerns. Keep it short — that text
lands in the controller's context.

If any instruction above is wrong — a test that cannot fail, a field that does not exist, a
validator that already exists elsewhere — **say so and do the correct thing instead.** Three
implementers on this project have caught defects in brief text, and it has been the single
highest-value thing they did. Never make production code less correct in order to make a test
deterministic. Do not dispatch subagents.
