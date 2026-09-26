# Hotel log post templates — design

**Status: APPROVED.** Sections 1–4 were presented and approved one at a time
in the brainstorming session of 2026-09-26; the user then approved building it without further
review ("go ahead and build, no more questions").

---

## 1. What this is and why

`docs/design.md` §6.8 "Incumbent parity" and Phase 2b item 1. The hotel's current tool (Kipsu
Exceed) has **log post templates**: structured shift-report forms staff fill in instead of free
text. The hotel uses three, 5–7 times each:

- **AM Checklist** (their shift 7AM–2PM), **PM Checklist** (2PM–9PM), **Night Audit** (9PM–7AM)
- Fields: number of enrollments · arrivals left · arrivals actual · departures actual · departures
  left · walk-ins · occupancy % · max occupied · min available tonight · notes
- Each template is shared with particular users and departments ("3 users, 1 department") and shows
  a usage count.

Relay's log today is free text only. This adds templates without changing what a log entry is.

### 1.1 Decisions made during brainstorming

- **Typed values now, reporting later (option C).** Each answer is stored as a typed row, so
  occupancy or walk-ins can be charted later without parsing text. This round builds the form,
  storage and feed display, **not** reports.
- **The audience controls who can post with a template (option A).** Only audience users and
  department members see the template in the composer. Everyone at the property still sees the
  resulting posts, as with any log entry. Acknowledgement is not preset by the template: the
  existing required-acknowledgement feature still applies to any post.
- **Approach 1: new template tables beside the log.** A templated post is an ordinary `log_entry`
  plus value rows. Rejected: JSON answers on the entry (not portably queryable — CLAUDE.md), and
  reusing shift checklists (these are reports posted to the feed, not tasks with required items,
  missed states and a tick).

### 1.2 Decided without asking (approved with the approach)

- **No Name / Date / Shift-time fields.** A log entry already records its author, time and shift.
- **Field types:** `short_text`, `long_text`, `integer`, `decimal`, `percent` (0–100); each field
  required or optional.
- **A template can optionally be tagged with a shift.** The composer lists every template the
  caller may use, the current shift's first.
- **Editing a template never changes past posts.** Each value row keeps a snapshot of the field's
  label and type as they were when posted.
- **Kipsu's "Enable using templates during post creation" switch is left out.** With no active
  templates the picker doesn't appear; deactivating every template has the same effect.

### 1.3 Scope

**In:** templates (name, optional shift, active, ordered fields, audience); posting with a
template; typed value storage with snapshots; feed display; the Admin → Log templates screen; the
usage count; seed data.

**Out (deferred):** reports or charts over template values; PMS pre-fill of arrivals, departures and
occupancy (needs §8.1 — the field model leaves room for it); a template-preset acknowledgement
audience; per-language template content (§6.18); Kipsu's "Team engagement" page.

**Operational note:** shift boundaries are a per-property setting. Kipsu's shifts are 7/14/21;
Relay's defaults are 07:00 / 15:00 / 23:00. The hotel's admin sets theirs in Property settings —
no code change.

---

## 2. Data model

One migration, `0010_log_templates`. Engine-portable; every enum through `enum_type()`; no JSON
filtering.

### 2.1 Tables

**`log_template`** — `property_id`, `name` (String 200), `shift` (nullable, the existing `Shift`
enum), `active` (default true), `position` (Integer, picker order), `created_by_user_id`.
Retired with `active = false`, never deleted, so old posts keep their link.

**`log_template_field`** — `template_id`, `property_id`, `position`, `label` (String 200),
`field_type` (new `LogFieldType` enum: `short_text` · `long_text` · `integer` · `decimal` ·
`percent`), `required` (default true), `active` (default true).
Fields are replaced by list on save exactly as checklist items are: a field carrying an existing id
is updated, a missing one is soft-deleted (`active = false`), and **a saved field's type never
changes** (a type change is a 400).

**`log_template_audience`** — `template_id`, `property_id`, `type` (the existing
`MentionTargetType`: `user` | `department`), `target_id`. Unique `(template_id, type, target_id)`.
**No rows = everyone at the property may post with it.**

**`log_entry`** gains one nullable column, **`template_id`** → `log_template.id`. Free-form posts
leave it null. This is the only change to an existing table.

**`log_entry_field_value`** — `log_entry_id`, `property_id`, `field_id` → `log_template_field.id`,
`position`, `label` (snapshot), `field_type` (snapshot), `text_value` (Text, nullable),
`number_value` (`Numeric(10, 2, asdecimal=False)`, the PM `READING` type, nullable).
Unique `(log_entry_id, field_id)`. Index `(property_id, field_id)` for future reporting.
One row per **answered** field; written once, never updated (log entries are immutable).

### 2.2 The post's body

`log_entry.body` stays required: it drives notification snippets, search and @mentions. For a
templated post the domain **generates** it: one `Label: value` line per answered field in position
order (percent rendered `87%`), then a blank line and the author's notes if any. @mention tokens
live in the notes part and resolve as they do today. The **value rows are the data**; the body is
the text form for places that can't show a table. The combined body must fit `MAX_BODY` (4000);
over that is a 400.

### 2.3 Validation on post

- The template exists at this property, is active, and the caller may post with it (§3.1) —
  otherwise 404 (not this property) or 403 (not in audience).
- Every `fieldValues[].fieldId` is an active field of that template; duplicates are a 400.
- Every required active field has a value.
- `integer`: a whole number. `decimal`: any number. `percent`: 0–100 inclusive. Values arrive as
  JSON numbers or numeric strings (the multipart path sends strings).
- Text is trimmed; blank means unanswered (so a blank required field fails).
- Failures are `ValidationFailed` (400) whose `details` map each failing field id to a reason
  (`required`, `not_a_number`, `not_whole`, `out_of_range`, `unknown_field`, `too_long`).
- A templated post may have an empty notes body; a free-form post still needs a non-empty body.

---

## 3. API and permissions

### 3.1 Permissions

No new capabilities.

- **Posting** uses the existing `post_log` (all of `STAFF`).
- **Managing templates** uses the existing `manage_admin` (admin, corporate), as checklist and PM
  templates do.
- **Audience** is enforced in the domain layer, on top of `post_log`: the caller may use a template
  if its audience is empty, **or** they are a listed user, **or** their membership's department is a
  listed department, **or** their role is manager, admin or corporate (exempt).

### 3.2 Routes

Under `/api/p/<property_id>`; every route `@require_auth` + `@require_property` + a capability.

| Route | Capability | Purpose |
|---|---|---|
| `GET /log/templates` | `post_log` | Active templates the **caller** may post with, each with its active fields in order. Sorted: templates tagged with the current shift first, then untagged and other shifts, then by `position`, `name`. The composer's picker. |
| `GET /log-templates` | `manage_admin` | Every template including inactive, with active fields, audience and **`usedCount`** (count of `log_entry.template_id`). The admin list. |
| `POST /log-templates` | `manage_admin` | Create: `name`, `shift?`, `active`, `fields[]`, `audience[]`. 201. |
| `PATCH /log-templates/<template_id>` | `manage_admin` | Edit; `fields` synced as §2.1, `audience` replaced wholesale when given. |
| `POST /log` *(existing)* | `post_log` | Gains optional `templateId` and `fieldValues: [{ fieldId, value }]` (JSON, or a JSON string on the multipart path, as `mentions` already is). Body, mentions, required acknowledgement, audience, photo, department and links unchanged. |

The admin routes live at `/log-templates`, apart from `/log/templates`: the two lists have different
capabilities and contents, and one route with a capability-dependent flag is a trap. `/log/templates`
is a static segment, so it takes precedence over `/log/<entry_id>` (as `/log/mentionables` already
does).

### 3.3 Wire models

In `app/schemas/log.py`, `CamelModel` subclasses:

- `LogTemplateFieldIn` (`id?`, `label`, `fieldType`, `required`), `LogTemplateFieldOut` (+ `id`,
  `position`, `active`).
- `LogTemplateIn` / `LogTemplatePatch` (`name`, `shift?`, `active`, `fields` 1–50, `audience`:
  `list[MentionRef]` ≤ 100).
- `LogTemplateOut` (`id`, `name`, `shift`, `active`, `position`, `fields`, `audience`, `usedCount`).
- `LogFieldValueIn` (`fieldId`, `value: str | float | int | None`).
- `LogFieldValueOut` (`fieldId`, `label`, `fieldType`, `textValue`, `numberValue`).
- `CreateLogEntryRequest` gains `template_id` and `field_values`.
- `LogEntryOut` gains `template: { id, name } | None` and `field_values: list[LogFieldValueOut]`.

New public models go in `test_schema_export.py`'s tuple; new tables in `EXPECTED_TABLES`;
`schema.json` and `types.generated.ts` are regenerated, never hand-edited.

### 3.4 Realtime and isolation

- A templated post is created through the existing path and emits the existing
  `log.entry.created { id }` event — nothing new. Template edits emit nothing; the admin screen and
  composer refetch.
- Every new row carries `property_id` and every lookup is scoped by it. `tests/test_isolation.py`
  enumerates the four new routes automatically; admins pass all of them.

---

## 4. Screens

### 4.1 Log composer

- A **"Use a template"** `<select>` above the message box, shown only when `GET /log/templates`
  returns at least one template; current shift's first. "No template" clears the form.
- Choosing a template renders its fields above the message box, in order: `short_text` → input;
  `long_text` → textarea; `integer` / `decimal` → numeric input (`inputMode` numeric/decimal);
  `percent` → numeric input with a `%` suffix. Required fields are marked.
- The message box stays, labelled **"Notes (optional)"** when a template is chosen; @mentions,
  photo, required acknowledgement, department all work as today.
- **Post** is disabled until required fields are filled; server `details` render beside the field
  they name, other errors inline as today.

### 4.2 Feed card

- A templated post shows a **template-name tag** (e.g. "Night Audit") and a compact two-column
  label/value list from `fieldValues`; percent as `87%`; unanswered optional fields omitted.
- The author's notes render under it as a normal post's body does — the card renders the notes
  part, not the generated summary, when `fieldValues` is present.
- Acknowledgements, pinning and links unchanged.

### 4.3 Admin → Log templates

A new Admin section beside Checklist templates, same skeleton (`AdminTable`, `EditPanel`,
field errors).

- **List:** Name · Shift (Any / AM / PM / Overnight) · Fields (count) · Shared with ("Everyone" or
  "3 users, 1 department") · Used (count) · Active.
- **Editor:** name; shift; active; a **field list editor** (label, type, required, move up/down,
  remove; type locked once saved); **Shared with** — departments and/or individual users (empty =
  everyone).
- The field editor is specific to this screen, not the checklist `ItemListEditor` — the field
  types differ and bending one component to serve both would hurt both.

---

## 5. Seed data

Through the domain, HVH only:

- The three templates, each shared with the Front Desk department: **AM Checklist** (shift AM),
  **PM Checklist** (PM), **Night Audit** (overnight). Fields in this order: Number of enrollments
  (integer) · Arrivals left (integer) · Arrivals actual (integer) · Departures actual (integer) ·
  Departures left (integer) · Walk-ins (integer) · Occupancy (percent) · Max occupied (integer) ·
  Min available tonight (integer) · Notes (long text, optional).
- A handful of templated posts on the previous two local days, authored by front-desk staff, so
  the feed shows templated cards.
- `SeedSummary` gains `log_templates`; `test_seed` asserts the template count and the planted
  posts only — nothing that depends on the time of day. `server/data/app.db` is regenerated.
- **Production is never seeded.** Admins create the templates in Admin → Log templates.

---

## 6. Migration and portability

`0010_log_templates`: four new tables plus a nullable `log_entry.template_id` column added via
`batch_alter_table` (with its FK). No backfill. `downgrade()` drops the column, then the four
tables children-first — a true reversal. Before merge, per `CLAUDE.md`: upgrade / downgrade /
re-upgrade on Postgres 18, and the app seeded and exercised on Postgres 18. The push is the user's
call; after it, the deploy log must show `alembic upgrade head` before gunicorn. Nothing here needs
the background worker.

---

## 7. Testing

TDD per plan task. Tests run on SQLite; Postgres is covered by §6's verification.

- **Posting:** a templated post stores one value row per answered field with snapshot label and
  type; a missing required field, a malformed number, a percent over 100 and a fractional integer
  each return 400 naming the field; an unknown or inactive field id is a 400; the body is the field
  summary then the notes; @mentions in the notes still notify; over-length combined body is a 400.
- **Audience:** a non-audience user gets 403 posting and doesn't see the template in
  `GET /log/templates`; an audience department member can use it; manager, admin and corporate
  always can; an empty audience means everyone.
- **Snapshots:** renaming, retyping-attempt (400), soft-deleting a field or deactivating a template
  never changes an existing post's values or labels; a deactivated template is absent from
  `GET /log/templates` but still named on old posts.
- **Admin:** create/patch round-trip; type change of a saved field is a 400; `usedCount` is right.
- **API and isolation:** capability matrix pinned; a template of another property is a 404;
  `test_isolation` covers the new routes.
- **Web:** composer (picker only when templates exist; each field type renders; Post blocked until
  required fields filled; sends `templateId` + `fieldValues`; field errors inline); feed card
  (table, percent formatting, notes under it); admin editor (create, edit, type locked on saved
  fields, audience set, list columns).
