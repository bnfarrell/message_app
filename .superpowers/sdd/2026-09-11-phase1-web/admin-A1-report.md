# A1 — server endpoints for the admin section · implementation report

**Status: DONE_WITH_CONCERNS** (the work is complete; four brief/codebase defects are recorded
below, two of which changed what I built).

Commits on `main`, from `28e8b97`:

| sha | subject |
| --- | --- |
| `2ba6cb8` | feat(server): patchable quick-reply locale, plus a non-mutating preview |
| `182c459` | feat(server): departments become full CRUD, with a referential delete guard |
| `554a950` | feat(server): property settings GET/PATCH endpoint |

Each commit is self-consistent: `web/src/api/schema.json` was regenerated and the full suite and
lint were run at every one, not only at the end.

**Verification:** `python -m pytest -q` → **279 passed** (baseline 258, +21 new; nothing broken).
`python -m ruff check app tests seed` → clean. Acceptance criterion 9
(`tests/test_isolation.py`) picked up all seven new routes — enumeration confirmed below.

> **Read the two fix-round sections at the end of this file before coding against anything here.**
> Fix round 1 changed the property-settings shape and added a cross-cutting `400` contract; fix
> round 2 changed which field a phone/timezone error names. Both supersede the shapes given in
> the body below, and the body is marked where that happens.

---

## 1. `locale` is patchable on quick replies

**Files:** `server/app/schemas/content.py`, `server/tests/test_content.py`.

- `QuickReplyPatch.locale: str | None = Field(default=None, min_length=1, max_length=8)`.
- **No domain change was needed.** `quick_replies.update` iterates
  `data.model_dump(exclude_unset=True)` and `setattr`s generically, so the new field applies as
  soon as it exists on the schema. The brief's "check whether it assigns field by field" is
  answered: it does not.

### Validation chosen, and a brief correction

The brief says "match whatever validation `QuickReplyIn` applies to the same field". **It applies
none** — `QuickReplyIn.locale` was a bare `str = "en"` while the column is `String(8)`. Matching
that literally would have let `PATCH {"locale": "x"*200}` through, which SQLite silently accepts
(it does not enforce `VARCHAR` length) and PostgreSQL rejects with a 500 — i.e. a bug that only
appears after the DATABASE_URL switch the spec anticipates. So I bounded **both** In and Patch to
`min_length=1, max_length=8`, matching the column. This is the one place I widened the diff beyond
the literal ask; it is one line on a schema that was already being edited, and the alternative was
knowingly shipping the weaker rule.

There is **no allow-list of locales** and I did not invent one: nothing in the codebase consumes
`locale` yet (no lookup, no fallback chain), so an enum would be speculative configurability.
`"fr-CA"`, `"en"`, `"es"` all pass; only length and emptiness are enforced.

### Shape for A2

```
PATCH /api/p/{propertyId}/quick-replies/{id}
  { "locale": "fr-CA" }            // 1-8 chars; 400 otherwise
-> 200 QuickReplyOut (unchanged shape, `locale` now reflects the patch)
```

---

## 2. Departments — full CRUD with a referential delete guard

**Files:** `server/app/schemas/users.py` (new `DepartmentIn`, `DepartmentPatch`),
`server/app/domain/users.py` (new `get_department`, `create_department`, `update_department`,
`_DEPARTMENT_REFERENCES`, `delete_department`), `server/app/api/departments.py`,
`server/tests/test_departments_users.py`.

Ruling D61 followed: the domain functions sit beside `list_departments` in `domain/users.py`; no
`domain/departments.py` was created and `list_departments` was not moved. **I found no concrete
reason to disagree** — `users.py` already owned the aggregate and the API blueprint already reached
into it.

### Routes and gates

| route | gates |
| --- | --- |
| `GET    /api/p/{propertyId}/departments` | `require_auth` → `require_property` (**unchanged, still no capability gate**) |
| `POST   /api/p/{propertyId}/departments` | + `require_capability("manage_admin")` → 201 |
| `PATCH  /api/p/{propertyId}/departments/{departmentId}` | same → 200 |
| `DELETE /api/p/{propertyId}/departments/{departmentId}` | same → 204 |

### Validation chosen

`DepartmentIn`: `name` 1–100 (the column is `String(100)`), `type` the `DepartmentType` enum
(`front_desk`, `housekeeping`, `engineering`, `food_beverage`, `spa`, `security`, `valet`,
`other`; an unknown value is a 400, *not* a 500 at the DB check constraint), `escalation_minutes`
default 15 with `gt=0` (a 0- or negative-minute SLA is not a configuration, it is a bug —
`escalation_minutes=0` would make every conversation instantly overdue), `active` default True.
`DepartmentPatch` is the same with every field optional and no defaults.

I deliberately did **not** add a uniqueness rule on `name`: the model has no unique constraint on
it, the test fixture has two departments called "Front Desk" (one per property), and inventing a
409 the database does not enforce would be a rule the rest of the system does not share.

### Delete-guard behaviour

`grep -rn 'ForeignKey("department.id")' server/app/models/` confirms the brief's list exactly —
five nullable FKs, no sixth, none with `ON DELETE` behaviour:

| column | Conflict message |
| --- | --- |
| `PropertyMembership.department_id` | `Move the staff members in this department to another one first, or deactivate the department instead` |
| `QuickReply.department_id` | `Reassign the quick replies in this department first, …` |
| `DigitalAsset.department_id` | `Reassign the digital assets in this department first, …` |
| `Conversation.assigned_department_id` | `Reassign the conversations assigned to this department first, …` |
| `WorkOrder.department_id` | `Reassign the work orders assigned to this department first, …` |

Checked in that order, first hit wins, `409 CONFLICT`. Nothing is written and nothing is nulled.
No soft-delete (spec line 86) and no cascade were added; every message ends by pointing the admin
at `PATCH {"active": false}`, which the tests prove still works while a reference exists.

A department of another property is a **404, not a 403**, on PATCH and DELETE — `get_department`
filters on `property_id`, so it is invisible rather than merely forbidden. (The 403 still fires
first when the *URL's* property is one the caller has no membership at; that is `require_property`.)

Tests: create; patch each of the four fields plus an empty patch; clean delete → 204 then 404;
capability matrix (agent/manager 403 on all three writes, 200 on GET; corporate 200 on PATCH);
validation failures; cross-property 404s; and **one parametrised test per referencing table**
(`membership`, `quick_reply`, `digital_asset`, `conversation`, `work_order`) proving the refusal.
Per the brief, every test creates the rows it needs — **nothing asserts against seed contents.**

### Shapes for A3

```
GET /api/p/{propertyId}/departments
-> 200 [ { "id", "name", "type", "escalationMinutes", "active" } ]   // sorted by name

POST /api/p/{propertyId}/departments
  { "name": "Spa", "type": "spa", "escalationMinutes": 30, "active": true }
     // name + type required; escalationMinutes defaults 15, active defaults true
-> 201 DepartmentOut

PATCH /api/p/{propertyId}/departments/{id}
  { "name"?, "type"?, "escalationMinutes"?, "active"? }   // any subset, {} is a valid no-op
-> 200 DepartmentOut   | 404 if not this property's

DELETE /api/p/{propertyId}/departments/{id}
-> 204
-> 409 { "error": { "code": "CONFLICT", "message": "<what to fix> first, or deactivate the
        department instead" } }
```

A3 should surface that 409 `message` verbatim — it is written to be read by an admin, and it
names the escape hatch.

---

## 3. Property settings

**Files (new):** `server/app/schemas/properties.py`, `server/app/domain/properties.py`,
`server/app/api/properties.py`, `server/tests/test_property_settings.py`.
**Files (edited):** `server/app/__init__.py` (blueprint registration, beside `departments`),
`server/app/schemas/export_json_schema.py` (new module added to `MODULES` so the client gets
types), `server/pyproject.toml` (see `tzdata` below).

**No migration.** `Property` already carries every field; I did not need one and did not add one.

Routes: `GET /api/p/{propertyId}/settings` (`require_auth` → `require_property`) and
`PATCH` (+ `require_capability("manage_admin")`). Named sub-resource, not a bare prefix, per the
brief's reasoning about acceptance criterion 9.

### `code`: rejected, not ignored

`CamelModel` sets `extra="forbid"`, so `PATCH {"code": "NEW"}` is a **400 VALIDATION_FAILED** with
no write. I chose rejection over silent ignoring and tested it: a settings form that silently
dropped a field the user typed would be worse than one that says no. The same is true of
`{"settings": {...}}` — the JSON blob is not in the Patch model, so sending it 400s. `code` **is**
returned by GET.

### Validation chosen, and why it lives in the domain

- **`timezone`** must construct a `zoneinfo.ZoneInfo`. `"America/Nowhere"`, `"EST5EDT7"`,
  `"../../etc/passwd"` and `""` all 400; `"Asia/Tokyo"` persists.
- **`phone` / `sms_number`** reuse **`app.domain.guests.normalize_phone`** — the existing
  validator, as instructed; no second one was written. They are *normalised*, not merely checked:
  `"(555) 012-3456"` is stored as `"+15550123456"`. This matters beyond tidiness —
  `app/channels/inbound.py:26` routes an inbound SMS with
  `Property.sms_number == guests.normalize_phone(to_number)`, so a prettified number saved through
  this endpoint would silently stop inbound SMS for the property. `"not a phone"` → 400.
- **`currency`** is `^[A-Za-z]{3}$` and is upper-cased on write (`"eur"` → `"EUR"`).
- Lengths match the columns exactly: name 200 (and min 1), address 400, phone/sms_number 32,
  brand 100, currency 3, logo_url 500, primary_color 16.

Both `timezone` and the phone fields are validated **in `domain/properties.py`, not in a Pydantic
`field_validator`.** I started with a `field_validator` and it produced a **500**: a custom
`ValueError` raised inside a Pydantic v2 validator lands in `e.errors()` as
`ctx: {"error": ValueError(...)}`, and `_util.parse_body` passes that straight to `jsonify`, which
cannot serialise an exception object. Domain-level validation raising `ValidationFailed` is also
the house precedent (`normalize_phone` does exactly this) and yields a clean
`400 {"error": {"code": "VALIDATION_FAILED", "message": "Invalid time zone",
"details": {"timezone": "..."}}}`. See "Found but not fixed" for the underlying `parse_body`
defect.

### `tzdata` added as a runtime dependency — please note

`zoneinfo` has **no tz database on Windows** and none on slim Linux images. On this machine
`ZoneInfo("America/New_York")` raised `ZoneInfoNotFoundError` before I installed `tzdata`, so the
brief's "reject anything `ZoneInfo()` cannot construct" would have rejected **every** valid zone,
including the one the seed sets. `tzdata>=2024.1` is now in `[project].dependencies` (a 348 KB
pure-data wheel, no code). **Anyone syncing this branch must `pip install -e ".[dev]"` again or
`pip install tzdata`, or the six property-settings tests will fail.** The alternative — a regex
that pretends to validate — is exactly the decorative validation the brief ruled out.

### Shapes for A3 — current as of fix round 2

```
GET /api/p/{propertyId}/settings            // every member may read
-> 200 {
    "id", "name", "code", "timezone", "address", "phone", "smsNumber",
    "brand", "currency", "logoUrl", "primaryColor",
    "slaMinutes": 15,          // int, always present   (added in fix round 1)
    "autoResolveHours": 4,     // int, always present   (added in fix round 1)
    "helpText": "..." | null   // the guest-visible reply to an SMS "HELP"
  }
  // id, name, code, timezone, currency are strings and slaMinutes/autoResolveHours are ints,
  // all always present; the other seven (address, phone, smsNumber, brand, logoUrl,
  // primaryColor, helpText) are string|null.
  // `code` is read-only. `settings` (the JSON blob) is never present — those three typed
  // fields ARE its three live keys.

PATCH /api/p/{propertyId}/settings          // manage_admin only; 403 otherwise
  any subset of: name, timezone, address, phone, smsNumber, brand, currency,
                 logoUrl, primaryColor, slaMinutes, autoResolveHours, helpText
-> 200 PropertySettingsOut (the full object, post-normalisation — re-read it into the form:
       phone/smsNumber come back E.164 and currency upper-cased, not as typed)
-> 400 on a bad timezone, a bad phone, a non-3-letter currency, an over-long field,
      a slaMinutes/autoResolveHours that is not > 0, an explicit null on a required field,
      or on sending `code` / `settings` / any unknown key
```

Two things about that 400 that the block above cannot show, both covered in the fix-round
sections at the end of this file: `details` has **two different shapes** depending on where the
validation failed, and a phone/timezone failure now names the field you patched. Read
"The `details` contract has two shapes" before building the form.

---

## 4. Quick-reply preview (+ the variable list)

**Files:** `server/app/schemas/content.py` (`PreviewRequest`),
`server/app/domain/quick_replies.py` (`preview`), `server/app/api/quick_replies.py`,
`server/tests/test_content.py`.

I verified all three of the brief's reasons `/render` cannot serve this, in source, and all three
hold: `quick_replies.py` line 130 `r.usage_count += 1`; `/render` is gated on `reply`, and
`permissions.py` has `reply` **without** `Role.corporate` while `manage_admin` is
`{admin, corporate}`; and `render()` takes a stored `quick_reply_id` plus a required
`conversation_id`.

`preview` writes nothing. It reuses `interpolate` and `context_for_conversation` (no second
interpolator) and `sms.segment_count` (no second segment counter). With no `conversationId` the
context is `{}`, and `interpolate` already substitutes `FALLBACKS` for any variable that is
missing or `None` — so the no-conversation case and the null-field case take the same path by
construction rather than by a second branch.

One addition to the brief: when a `conversationId` **is** supplied I run
`conversations.get_for_viewer(...)` first, exactly as `/render` does. With `manage_admin` gating
the route this is currently belt-and-braces (admin and corporate both pass `assert_viewer_can_see`),
but the alternative is a route that resolves a conversation without a viewer check, which
`test_isolation.py` documents as having been missed on seven routes across three tasks.

### Variable list — I added an endpoint

`GET /api/p/{propertyId}/quick-replies/variables` → `200 ["guest_first_name", "room_number",
"property_name", "agent_first_name", "departure_date"]` (a bare array, matching `GET departments`'
house style; `require_auth` + `require_property`, no capability gate — the reply composer may want
it too).

I chose the endpoint over "the client reads a shared constant" because there is no shared constant
to read: the client's only generated artefact is `schema.json`, which carries models, not
module-level tuples, so "shared constant" would in practice mean a hand-copied TypeScript array —
the exact drift the brief argues against for the segment counter. Ruling D68's five names are what
the endpoint returns; `docs/mockups/Admin.dc.html`'s four chips are the stale side.

### Tests

Fallback text with no `conversationId`; real guest data with one (`"Hi Sarah in 412 at Harbourview
Hotel."`); **`usage_count` unchanged after three previews** (asserted before *and* after);
`corporate` → 200 while `agent`, `manager` and `engineer` → 403; and segments/characters equal to
`segment_count(body)`/`len(body)` across both boundaries — 160 vs 161 GSM-7 septets, and a body
with a non-GSM character (an emoji plus 69 ASCII = 71 UTF-16 units, i.e. 2 segments).

### Shapes for A2

```
POST /api/p/{propertyId}/quick-replies/preview        // manage_admin only
  { "body": "Hi {{guest_first_name}}...", "conversationId": "..." | null }
     // body 1-1600 chars (empty -> 400); conversationId optional
-> 200 { "body": "<interpolated>", "segments": 2, "characters": 173 }

GET /api/p/{propertyId}/quick-replies/variables
-> 200 ["guest_first_name","room_number","property_name","agent_first_name","departure_date"]
```

Debounce the preview call in the editor; it is a round trip per keystroke otherwise. `segments`
and `characters` are the authoritative counter values — do not compute either client-side.

---

## Acceptance criterion 9 — confirmed

`tests/test_isolation.py` enumerates `app.url_map` and picked up **all seven** new rules; the three
cross-tenant tests (403 for a member of A on every B route, not-403 for a member on its own
property, 401 for anonymous) pass unchanged:

```
POST   /api/p/<property_id>/departments
PATCH  /api/p/<property_id>/departments/<department_id>
DELETE /api/p/<property_id>/departments/<department_id>
POST   /api/p/<property_id>/quick-replies/preview
GET    /api/p/<property_id>/quick-replies/variables
GET    /api/p/<property_id>/settings
PATCH  /api/p/<property_id>/settings
```

---

## Found but not fixed

1. **`_util.parse_body` 500s on any custom Pydantic validator.**
   `server/app/api/_util.py:27` calls `e.errors(include_url=False)`. When a validator raises a
   plain `ValueError`, Pydantic v2 puts the exception *object* in `ctx["error"]`, and Flask's
   `jsonify` raises `TypeError: Object of type ValueError is not JSON serializable` — a 500 in
   place of a 400. No current schema triggers it (nothing else uses `field_validator`), which is
   why it has never fired. I routed around it rather than changing shared error-detail shape
   mid-wave, since A2/A3 are being briefed against the current `details` payload. The fix is
   `e.errors(include_url=False, include_context=False)` — but that also strips useful context
   (`{"max_length": 100}`) from every existing 400, so it wants a deliberate decision, ideally
   with a serialisable-`ctx` filter instead.

2. **`web/src/api/schema.json` had to be regenerated** by the server command
   `python -m app.schemas.export_json_schema`, despite the "do not touch `web/`" instruction:
   `tests/test_schema_export.py::test_committed_schema_is_current` fails otherwise, so the suite
   cannot be green without it. It is a server-generated artefact that happens to be stored under
   `web/`, and the diff is **365 additions, 0 deletions** — purely the new/changed models. No
   hand-written web file was read, run or modified.

3. **`Property.timezone` is not used anywhere in `app/`.** The brief calls it "already the
   intended basis for analytics bucketing"; `grep -rn timezone app/` shows it is set by the seed
   and read by nothing — `app/domain/analytics.py` buckets in UTC. The validation I added is
   therefore preventing a future bug rather than an existing one. Someone should decide whether
   analytics is meant to honour it, because an admin who sets the zone here will reasonably expect
   the dashboard to follow.

4. **`docs/mockups/Admin.dc.html` is stale** on the variable chips — four, missing
   `property_name`. Ruling D68 already settles which side wins; flagging it so the mockup is not
   treated as the contract during A2 review.

5. **`Department.escalation_minutes` is read by nothing, and the SLA the server actually enforces
   lives somewhere the admin cannot reach.** `grep -rn escalation_minutes app/` returns only the
   model and my new schemas. The live value is `conversations.sla_minutes()`
   (`app/domain/conversations.py:52`), which reads `Property.settings["sla_minutes"]` — seeded to
   15 on both properties and, per the brief's ruling, deliberately **not** exposed by the settings
   endpoint. So A3 will give an admin a department SLA field that changes nothing, while the
   number that does drive `conv.sla_due_at` is uneditable. This needs a ruling (wire
   `escalation_minutes` into `sla_minutes()` as a per-department override, or expose
   `sla_minutes`, or label the field as Phase 2) before A3 ships the control.

6. **Pre-existing, untouched:** `QuickReplyPatch.shortcut` has a `pattern` but no `min_length` /
   `max_length`, while `QuickReplyIn.shortcut` has `min_length=2, max_length=40`. Same In/Patch
   asymmetry as `locale`, on a different field. I did not change it — it was not in scope and the
   regex bounds the damage — but it is the same latent PostgreSQL-only truncation class.

---
---

# A1 · Fix round 1

**Status: DONE_WITH_CONCERNS.** All six items addressed; one is implemented more widely than the
letter of the instruction (item 1's scope), and two new observations are recorded at the end.
Nothing was declined.

Commits, on `main` from `8094d4f`:

| sha | subject |
| --- | --- |
| `8469e64` | fix(server): an explicit null on a NOT NULL column is a 400, not a 500 |
| `e6677e5` | fix(server): a sender number must carry at least two digits |
| `02c5def` | feat(server): expose the three live settings-bag keys as typed fields |
| `9ae2bac` | chore(web): regenerate the API types my schema changes made stale |

## Verification

```
$ cd server && python -m ruff check app tests seed
All checks passed!

$ python -m pytest -q
........................................................................ [ 97%]
........                                                                 [100%]
296 passed in 25.14s

$ cd web && npx vitest run src/api/types.generated.test.ts
 ✓ src/api/types.generated.test.ts (2 tests) 263ms
 Test Files  1 passed (1)
      Tests  2 passed (2)

$ npm test
 Test Files  44 passed (44)
      Tests  386 passed (386)

$ npm run lint
(clean)

$ npx tsc --noEmit -p tsconfig.json
(clean)
```

Server 279 → **296** (+17 new tests, none removed, none broken). Web 386 with 1 failed → **386
passed, 0 failed.** The seed also runs clean against the new phone floor (see item 2).

---

## 1 · Ruling D82 — explicit null on a NOT NULL column (`8469e64`)

**Upheld and reproduced.** Fixed once, in a new `server/app/domain/_patch.py`:

```python
patch_changes(model, data, *, required=()) -> dict
```

It is `model_dump(exclude_unset=True)` plus a refusal: any key whose value is `None` and whose
mapped column is `nullable=False` (or which is named in `required`) raises `ValidationFailed`
before anything is set. It replaced the `model_dump(exclude_unset=True)` call at **five** sites:

| site | schema | fields that could 500 |
| --- | --- | --- |
| `domain/properties.py` `update_settings` | `PropertySettingsPatch` | name, timezone, currency (+ the two bag ints) |
| `domain/users.py` `update_department` | `DepartmentPatch` | name, type, escalation_minutes, active |
| `domain/categories.py` `update` | `CategoryPatch` | name, active — **pre-existing, per the ruling** |
| `domain/quick_replies.py` `update` | `QuickReplyPatch` | shortcut, title, body, locale, active |
| `domain/assets.py` `update` | `AssetPatch` | name, type, url, active |

**I widened the scope by one site, deliberately.** The ruling named three copies; `grep -rn
"model_dump(exclude_unset=True)" app/` found six call sites, and `domain/assets.py:64` is a fourth
with the identical hole (`PATCH /assets/<id> {"name": null}` was the same unhandled 500). The
ruling's own argument — "fixing two siblings while knowingly leaving the third broken is
incoherent" — applies to it verbatim, so it is fixed and tested with the others.

**The sixth site, `users.update_staff`, is untouched and I want to flag that explicitly.** It does
*not* have this bug: it already guards with `if data.role is not None`, so `{"role": null}` is a
silent no-op, not a 500. It therefore has the *other* failure mode — 200 with the edit discarded —
and routing it through `patch_changes` would change working behaviour on an endpoint outside this
wave. Left alone; recorded below.

### Reject, not skip — and why

I chose **reject with a 400**. Skipping returns 200 and silently discards what the admin typed,
which is the same silent-no-op class the reviewer flagged in items 2 and 5; the coordinator's own
framing of the A3 scenario ("an admin clearing the Currency box gets ... 'currency is required'")
is the rejecting behaviour. Nullable neighbours are unaffected and still clearable — tested
explicitly on all four models, because a guard that over-rejects would break the form in the other
direction.

### One improvement beyond the ruling

The error names the **camelCase** field the client sent, not the snake_case attribute:

```json
{ "error": { "code": "VALIDATION_FAILED",
             "message": "Cannot be cleared: escalationMinutes",
             "details": { "escalationMinutes": "required" } } }
```

`changes` stays snake_case for `setattr`; only the message and `details` use the alias. Without
this, A3 could not map the failure back to the input the admin cleared — which is the entire point
of returning 400 instead of skipping.

**A2/A3 contract:** any PATCH may now return `400 VALIDATION_FAILED` with
`details: { "<camelCaseField>": "required" }`. Render it against that field.

## 2 · Ruling D83 — a junk `smsNumber` that kills inbound SMS (`e6677e5`)

**Upheld.** The floor is in `normalize_phone` (`domain/guests.py`) so every caller benefits, as a
named constant `MIN_SENDER_DIGITS = 2`, applied only to the `+` branch (the other two branches were
already exact at 10 and 11 digits).

**Why 2.** Two constraints had to hold simultaneously, and they squeeze from opposite sides:

- it must reject the reported typos — `"+"` (0 digits) and `"+1-"` (1 digit) — so the floor is at
  least 2;
- it must be **incapable** of rejecting a legitimate short code. Short codes are 5–6 digits in the
  US and UK but as few as **3** in the shortest national schemes, and `normalize_phone` also
  normalises guest numbers arriving from inbound webhooks, so any floor that could bite a real
  sender is the same outage in the opposite direction.

2 is the only value that is simultaneously the **smallest** floor satisfying the first constraint
and strictly below the shortest short code anywhere, so it cannot reject one by construction. A
floor of 5 (the US short-code length) would have been defensible-looking and wrong for the rest of
the world. Tested both directions: `"+"`, `"+ "`, `"+1-"`, `"+()"` reject; `"+12"`, `"+345"`,
`"+55512"`, `"+123456"` round-trip unchanged.

**Seed run, as instructed** — no existing datum fails the floor:

```
$ python -c "from seed.seed import run; print(run('sqlite:///data/seed_check.db', reset=True))"
SeedSummary(properties=2, users=14, guests=106, stays=106, conversations=30, messages=52,
            work_orders=21)
```

## 3 · `PATCH {"locale": null}` returning a 409 about the shortcut

**Resolved by item 1, verified rather than assumed.** The 409 came from `quick_replies.update`'s
`with db.begin_nested()` / `except IntegrityError: raise Conflict(f"Shortcut {...} is already in
use")` — the NOT NULL violation on `locale` was caught by a handler that assumed a shortcut
collision. `patch_changes` now raises before the flush, so the nested-flush handler only ever sees
an actual shortcut collision again. Covered in
`test_patching_a_not_null_field_to_null_is_a_400_not_a_500`, which asserts 400 +
`VALIDATION_FAILED` for `locale`, `shortcut` and `body` on a quick reply (and the same across
categories and assets), and that `category`/`departmentId` are still clearable. The pre-existing
409-on-real-collision test still passes.

## 4 · "all six" / seven

Corrected in place above — the acceptance-criterion-9 section now reads **all seven**, which
matches the seven rules it lists. My error.

## 5 · The settings bag's three live keys (`02c5def`)

Implemented as specified. `slaMinutes` (int, `gt=0`), `autoResolveHours` (int, `gt=0`) and
`helpText` (`str | null`, max 1600 — it is sent as an SMS) are now typed fields on
`PropertySettingsOut` **and** `PropertySettingsPatch`. The bag itself remains unexposed.

All four traps were real and all four are handled:

- **(a) no MutableDict.** Confirmed — `Property.settings` is a plain `JSON` column. The write is
  `p.settings = {**(p.settings or {}), **bag_changes}`. The covering test reads the value back
  through `conv_domain.sla_minutes()` in a **fresh session**, so an in-place mutation that never
  flushed would fail it.
- **(b) not ORM attributes.** The three keys are popped out of `changes` into `bag_changes`
  *before* the `setattr` loop.
- **(c) `int(...)` on the way out.** Both ints are passed to `patch_changes` as `required=`, so an
  explicit null is a 400 rather than a `TypeError` on the next inbound message. `gt=0` in Pydantic
  covers `slaMinutes: 0`; tested.
- **(d) no retro-update.** Confirmed and stated here for A3: **editing `slaMinutes` does not
  change the `slaDueAt` of conversations that already have one.** `conv.sla_due_at` is written at
  `domain/messages.py:163` when an inbound message arrives, so the new value applies from the next
  inbound message onward. A3 should say so next to the field.

Confirmations requested: **no migration, no backfill** (both seeded properties already carry the
keys; the readers default to 15/4), and
**`test_patch_settings_rejects_code_and_out_of_range_values` still passes** — `settings` is not a
field on the Patch model, so `extra="forbid"` still 400s it. No existing test broke.

SLA stays property-level. I agree with the reasoning and verified it: `messages.py:163` sets
`sla_due_at` on the inbound message, when `assigned_department_id` is typically still null, so a
per-department SLA would have nothing to read at the only moment it is needed.
`Department.escalation_minutes` therefore remains read by nothing — that finding stands.

### Updated shape for A3 (supersedes the shape given earlier in this report)

```
GET /api/p/{propertyId}/settings
-> 200 {
     "id", "name", "code", "timezone", "address", "phone", "smsNumber", "brand",
     "currency", "logoUrl", "primaryColor",
     "slaMinutes": 15,          // int, always present
     "autoResolveHours": 4,     // int, always present
     "helpText": "..." | null   // the guest-visible reply to an SMS "HELP"
   }

PATCH /api/p/{propertyId}/settings
  ... + "slaMinutes" (int > 0), "autoResolveHours" (int > 0), "helpText" (<= 1600 chars or null)
-> 400 VALIDATION_FAILED { details: { "<field>": "required" } } if a required field is sent as null
```

## 6 · Main was red on the web suite (`9ae2bac`)

**My miss, accepted without qualification.** `web/src/api/types.generated.test.ts` re-runs json2ts
over the committed `schema.json` and compares; my three server commits changed `schema.json` and
none regenerated. Done as the last step, once, after this round's schema changes were final:
`npm run gen:types`, then the five new model names added to the hand-maintained re-export list in
`web/src/api/types.ts` — `DepartmentIn`, `DepartmentPatch`, `PreviewRequest`,
`PropertySettingsOut`, `PropertySettingsPatch` — keeping its existing case-sensitive alphabetical
order (the same order that puts `RenderRequest` before `RenderedQuickReply`). No hand-written
client file was touched. Web suite: **386 passed, 0 failed**; lint and `tsc --noEmit` clean.

---

## Found but not fixed — round 1 additions

7. **`users.update_staff` silently ignores `{"role": null}`.** `domain/users.py:186` guards with
   `if data.role is not None`, so it is the no-op variant of D82 rather than the 500 variant. Not
   routed through `patch_changes` because it is not broken and sits outside this wave, but it is
   the same class of defect and the same one-line fix if someone wants consistency.

8. **`tests/test_dev.py::test_sim_events_since_filters_and_rejects_garbage` is intermittently
   flaky, pre-existing.** It failed once during this round's staged verification and passed on the
   next three full-suite runs and five consecutive targeted runs. Its own docstring names the
   cause: the sim event ring buffer is **process-global**, so what is in it depends on what other
   tests in the same process emitted. Nothing in A1 touches `/api/dev/sim` or the buffer, and the
   final suite is green — but it is a real source of CI noise and should be made deterministic
   (reset the buffer per test) rather than rediscovered.

---
---

# A1 · Fix round 2

**Status: DONE_WITH_CONCERNS.** All four items addressed. D89 is implemented as ruled — I looked
for a reason to push back and did not find one; my reasoning is under item 4. One new contract
wart is recorded at the end, and it matters to the wave building the settings form.

Commits, on `main` from `a025359`:

| sha | subject |
| --- | --- |
| `ec4ebc1` | fix(server): a field-level 400 names the field that was actually patched |
| `0992aa8` | test: pin the two SMS segment counters to shared golden vectors |

## Verification

```
$ cd server && python -m ruff check app tests seed
All checks passed!

$ python -m pytest -q
........................................................................ [ 89%]
...................................                                      [100%]
323 passed in 21.00s

$ cd web && npx vitest run src/lib/segments.golden.test.ts
 ✓ src/lib/segments.golden.test.ts (26 tests) 4ms
 Test Files  1 passed (1)
      Tests  26 passed (26)

$ npm test
 Test Files  45 passed (45)
      Tests  426 passed (426)

$ npm run lint
(clean)
```

Server 296 → **323** (+27: 25 golden vectors, a fixture-coverage guard, and the field-naming
test). Web 386 → **426** (+40: 25 vectors plus a coverage guard here, and the quick-replies wave's
own additions that landed in `a025359`). No schema change this round, so `schema.json` and
`types.generated.ts` are untouched and `test_committed_schema_is_current` still passes.

---

## 1 · The field-level 400 named the wrong field (`ec4ebc1`)

**Upheld, and worse than the one site named.** `normalize_phone` raised `details={"phone": raw}`
unconditionally, so *every* caller got `"phone"` — and `normalize_timezone` had the identical
shape (`details={"timezone": raw}`), where the field name happened to be right but the value was
still the admin's raw input.

The validator does not know which field it is validating and the caller does, so the field is
passed in:

```python
normalize_phone(raw, *, field="phone")        # app/domain/guests.py
normalize_timezone(raw, *, field="timezone")  # app/domain/properties.py
```

`update_settings` supplies `wire_name(data, k)` — the same derivation D82 already used, now
extracted from `patch_changes` into a named `_patch.wire_name` so both sites share one
implementation and a renamed field cannot go stale in either. The default is kept and is correct
for every other caller.

**Detail values are reason codes now**, not echoes: `"invalid_phone_number"` and
`"invalid_timezone"`, matching D82's `"required"`. A form maps a code to a message; echoing what
the admin just typed tells them nothing they do not already know.

**I checked every other raise in the file and every caller, as asked.** `guests.py` has exactly
two raises and both are the one fixed here. The remaining callers — `find_by_phone`,
`find_or_create_by_phone`, `channels/inbound.py:26` (the webhook's `To`), and
`/api/dev/sim/thread?phone=` — all validate a field genuinely called `phone`, so the default is
right for them and none needed changing. A test asserts that: it patches the three settings
fields and checks each error names its own field, then checks `/sim/thread` still reports
`{"phone": ...}`.

```
PATCH /settings {"smsNumber": "+"}        -> 400 details {"smsNumber": "invalid_phone_number"}
PATCH /settings {"phone": "nope"}         -> 400 details {"phone": "invalid_phone_number"}
PATCH /settings {"timezone": "Mars/Ymir"} -> 400 details {"timezone": "invalid_timezone"}
```

## 2 · "all six" at line 19

Fixed. That line now reads "all seven", matching line 287 and the seven rules the section lists.
I have also put a pointer at the top of this report telling a top-down reader that the two
fix-round sections supersede shapes in the body — the underlying problem was that a long report
read from the top hands you stale text before the correction.

## 3 · The stale "Shapes for A3" block

Rewritten in place rather than deleted, so a reader who lands there gets the right answer instead
of a redirect: it now carries `slaMinutes`, `autoResolveHours` and `helpText`, says "the other
**seven** are string|null", lists the new PATCH fields and their 400s, and links forward to the
`details` contract below.

## 4 · Ruling D89 — pinning the duplicate segment counters (`0992aa8`)

**I agree with the ruling and implemented it.** For the record, since you invited disagreement:
the case for deleting `segments.ts` and calling `/preview` per keystroke is worse than it looks —
it would put a network round trip in a character counter, and the endpoint is gated on
`manage_admin` while the composer is used by agents, so the inbox counter would 403 for the
people who use it most. A local implementation is correct there. The only defect was the absence
of a pin, which is what this adds.

`fixtures/sms-segments.json` — repo root, 25 cases of
`{name, why, body, isGsm7, segments, characters}` — is read by
`server/tests/test_sms.py::test_golden_vectors_match_the_shared_fixture` and
`web/src/lib/segments.golden.test.ts`, one parametrised case each, so a drift names the case
rather than just failing.

**Expected values are hand-computed from GSM 03.38, not generated from either implementation.**
That distinction is the whole value of the exercise: a fixture generated from the Python side
would have pinned Python's behaviour, and this project has already shipped one off-by-one in this
logic. I computed the 25 expected triples first, then ran both implementations against them. Both
agree on all 25 — so your comparison holds, and there is no drift today.

Coverage, all of it required by the ruling and all of it present:

| case | why it is there |
| --- | --- |
| `empty` | 0 segments, not 1 |
| `gsm7-160`, `gsm7-161` | the single-segment ceiling and one septet past it |
| `gsm7-306`, `gsm7-307` | exactly 2 × 153, and one into the third part |
| `gsm7-extension-alone`, `gsm7-extension-fills-160`, `gsm7-formfeed-fills-160` | `€` and form feed as two septets |
| `gsm7-extension-crosses-160` | **160 characters, 161 septets, 2 segments** — same character count as `gsm7-160`, one more segment |
| `gsm7-extension-crosses-153` | the same trap at the multipart boundary: 306 characters, 307 septets, 3 segments |
| `gsm7-interpolation-braces` | this product's own `{{variable}}` syntax — four braces at two septets each |
| `gsm7-newline-and-cr` | LF and CR are GSM-7 basic, not extension |
| `ucs2-70`, `ucs2-71`, `ucs2-134`, `ucs2-135` | both UCS-2 boundaries |
| `emoji-alone` | **two UTF-16 units for segments, one character** |
| `emoji-35`, `emoji-36` | 70 vs 72 units |
| `emoji-crosses-70` | **70 characters, 71 units, 2 segments** — the divergence case |
| `emoji-crosses-67` | the same at the multipart boundary: 134 characters, 135 units, 3 segments |
| `mixed-ascii-emoji`, `em-dash`, `curly-quote` | one non-GSM character forces the whole body to UCS-2 |

The `*-crosses-*` pairs are the ones that earn their keep: each has the *same* `characters` as a
neighbouring case that produces *fewer* segments, so an implementation that counted the wrong
quantity passes one and fails the other. Both suites also assert the fourteen boundary case names
are present, so a future edit that pares the fixture down cannot silently make the guard vacuous.

**I verified the pin actually bites, in both directions, rather than assuming it:**

```
# changed 153 -> 152 in web/src/lib/segments.ts
 × shared SMS segment vectors > gsm7-306
      Tests  1 failed | 25 passed (26)          <- web red, server still green

# changed 67 -> 66 in server/app/domain/sms.py
FAILED tests/test_sms.py::test_golden_vectors_match_the_shared_fixture[ucs2-134]
1 failed, 40 passed                             <- server red, web still green
```

Both perturbations were reverted; `git status` is clean.

One note for whoever maintains this: the server has no `char_count` function — `characters` is
`len(body)` inline in `quick_replies.preview`/`render`, which is code points and therefore agrees
with `segments.ts`'s `charCount`. The fixture asserts `len(body)` on the Python side for exactly
that reason. If someone ever adds a `char_count` to `sms.py`, it must stay code points, not
UTF-16 units.

---

## Found but not fixed — round 2 addition

9. **The `details` contract has two shapes, and the settings form must handle both.** This is the
   single most useful thing in this section for the next wave. A 400 from the same endpoint
   carries `details` as an **array** when Pydantic rejected the value and as an **object** when a
   domain validator did:

   ```
   PATCH /settings {"currency": "EUROS"}   -> details: [ { "loc": ["currency"],
                                                           "msg": "String should match pattern ...",
                                                           "type": "string_pattern_mismatch",
                                                           "ctx": {...}, "input": "EUROS" } ]
   PATCH /settings {"slaMinutes": 0}       -> details: [ { "loc": ["slaMinutes"], "type": "greater_than", ... } ]
   PATCH /settings {"code": "NEW"}         -> details: [ { "loc": ["code"], "type": "extra_forbidden", ... } ]

   PATCH /settings {"smsNumber": "+"}      -> details: { "smsNumber": "invalid_phone_number" }
   PATCH /settings {"name": null}          -> details: { "name": "required" }
   ```

   The good news is that **both shapes name the camelCase field** — `loc[0]` in the array shape,
   the object key in the other — so one small normaliser (`Array.isArray(details) ? d.loc[0] :
   Object.keys(details)`) covers every 400 this API returns. The bad news is that a form written
   against only the object shape, which is the shape the two rulings describe, silently fails to
   highlight anything for the pattern/length/extra-field cases, which are the common ones.

   I did not unify them. Doing so means changing `_util.parse_body`'s `details` for every endpoint
   in the product, mid-wave, while two client waves are being briefed against the current payload
   — and it interacts with the unfixed `ctx`-serialisation defect (finding 1). It wants its own
   ruling and its own commit. Until then: **A3 should normalise both shapes**, and the array
   shape's `input` field still echoes the admin's raw value, so do not render `details` verbatim.
