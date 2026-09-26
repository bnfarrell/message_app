# Shift checklist structure — categories, readings kind, unscheduled, starter library — design

**Status: APPROVED.** Sections 1–3 were presented and approved one at a time in the brainstorming
session of 2026-09-26; the user then approved building and pushing it without further review
("yes, build it and push when done").

---

## 1. What this is and why

`docs/design.md` §6.7 "Incumbent parity" and Phase 2b item 2 (first half — the multilingual half,
§6.18, is a separate spec). The hotel's current tool (Kipsu Exceed) structures shift checklists
in ways Relay's shipped checklists (`docs/superpowers/specs/2026-09-25-shift-checklists-design.md`)
don't yet:

- **Categories** — Kipsu's Night Audit has 7 categories, Front Desk (AM) 4, Front Desk (PM) 3.
- **Normal vs Readings checklists** — "Normal Checklists 4 · Readings Checklists 0".
- **Import From Library** — starter checklists a property copies and edits.
- **Checklists saved without a schedule** — Kipsu's Housekeeping checklist shows "Set Schedule".

### 1.1 Decisions made during brainstorming

- **Split Phase 2b item 2 in two:** this spec (checklist structure) first; multilingual content and
  per-user language (§6.18) next, so it translates the finished structure.
- **Library = a starter library that ships with Relay (option A).** Fixed, code-maintained
  definitions any property copies and edits. No portfolio sharing this round.
- **Categories group only (option A).** A category is a collapsible section with its own progress;
  completion, missed and assignment stay per checklist exactly as shipped.
- **Approach 1: a category table.** `checklist_template_category` plus a nullable
  `checklist_template_item.category_id`. Rejected: a category name string on each item (renames
  touch every item; two spellings silently become two categories) and "heading" rows as a new item
  type (item types are shared with PM).

### 1.2 Decided without asking (approved with the approach)

- **Readings vs Normal** is a template `kind` (`normal` / `readings`); it drives a filter and a tag,
  no other behaviour.
- **Unscheduled** is a third `schedule` value alongside `weekly` and `on_demand`: no shift, no days;
  never generates instances; never offered as on-demand.
- **Library import** copies a starter checklist into the property **as unscheduled** through the
  normal template create path; no link back to the library; importing twice gives two copies.

### 1.3 Scope

**In:** categories (create/rename/reorder/soft-delete, items assigned to them) in the template
editor; grouped display with per-category progress on the checklist page; template `kind`;
`unscheduled` schedule; the six-checklist starter library and its import; seed updates.

**Out (deferred):** per-category ownership/assignment; optional categories; portfolio library
sharing; multilingual content (§6.18, next spec).

---

## 2. Data model

One migration, `0011_checklist_structure`. Engine-portable; enums through `enum_type()` / the
migration's `_enum()`.

### 2.1 Changes

**New `checklist_template_category`** — `template_id` → `checklist_template.id`, `property_id`,
`name` (String 120), `position` (Integer), `active` (default true). Soft-deleted.

**`checklist_template_item`** gains nullable **`category_id`** → `checklist_template_category.id`.
The domain enforces that a category belongs to the item's own template.

**`checklist_template`** gains:
- **`kind`** — new enum `ChecklistKind` (`normal` · `readings`), NOT NULL, server default
  `'normal'` so existing rows migrate.
- **`schedule`** accepts **`unscheduled`**. The migration rebuilds the enum CHECK
  (`ck_enum_checklistschedule`) with the new value and the schedule-fields CHECK
  (`ck_checklist_template_schedule_fields`) as:
  `(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL AND weekdays > 0)
   OR (schedule IN ('on_demand', 'unscheduled') AND shift IS NULL AND weekdays IS NULL)`.

**`downgrade()`** drops `category_id` (and its FK), `kind`, and the category table, and restores
both CHECKs to their 0009 form. It **refuses** (raises with a clear message) if any
`checklist_template.schedule = 'unscheduled'` row exists, rather than corrupting data.

### 2.2 Behaviour

- **Grouping.** A checklist's items render grouped by category (category `position`, then item
  `position`). Ungrouped items come first with no heading — existing checklists look exactly as
  today. Each category heading shows `done / total` for its items using the shared
  `typed_items.is_answered` rule.
- **Snapshot unchanged.** Answers are still one per active item, created at start. Grouping follows
  the item's current `category_id`, as item labels already follow edits; answers never change.
- **Removing a category** (omitted from a save) soft-deletes it and leaves its items ungrouped
  unless the same save moves or removes them.
- **Unscheduled** — `checklist.tick` skips it (only `weekly` generates); the on-demand picker
  excludes it; `start_on_demand` on it is a 409 (`TransitionError`). Admin shows "Set schedule".
  Switching it to weekly or on-demand is an ordinary schedule edit with the existing validation.
- **Readings kind** — a filter chip in admin and a "Readings" tag on list rows, cards and the
  checklist page. No behaviour difference.

---

## 3. API

### 3.1 Wire models (`app/schemas/checklists.py`)

PM's shared item models (`TemplateItemIn` / `TemplateItemOut` in `app/schemas/pm.py`) are **not
modified**.

- `ChecklistItemIn(TemplateItemIn)` + `category_key: str | None`.
- `ChecklistCategoryIn` — `key` (client-side id, 1–64 chars), `id?` (a saved category's id),
  `name` (1–120).
- `ChecklistTemplateIn` / `ChecklistTemplatePatch` gain `kind` (default `normal` on create),
  `categories: list[ChecklistCategoryIn]` (≤ 30), and `items: list[ChecklistItemIn]`;
  `schedule` accepts `unscheduled`.
- `ChecklistItemOut(TemplateItemOut)` + `category_id: str | None`.
- `ChecklistCategoryOut` — `id`, `name`, `position`.
- `ChecklistTemplateOut` gains `kind`, `categories: list[ChecklistCategoryOut]`, and its `items`
  become `list[ChecklistItemOut]`.
- `ChecklistInstanceOut` gains `categories` and its `items` become `list[ChecklistItemOut]`.
- `ChecklistInstanceRowOut` gains `kind`.
- `ChecklistLibraryEntryOut` — `key`, `name`, `kind`, `department_type`, `categories`
  (`[{name, item_count}]`), `item_count`. `ChecklistLibraryImport` — `department_id`, `name?`.

### 3.2 Save semantics

Categories save together with items in the one template create/patch: a category with an `id`
updates in place; a saved category missing from the list is soft-deleted; a category without `id`
is created. Each item's `category_key` resolves against the `key`s in the same request. Errors
(`ValidationFailed`, 400):

- a `category_key` matching no category in the request → `{"items": "unknown_category"}`
- a blank category name → `{"categories": "required"}`
- a repeated `key` → `{"categories": "duplicate"}`
- a category `id` that isn't a saved category of this template → `{"categories": "unknown_category"}`

Categories are only replaced when `categories` is sent on a patch; items' category assignment only
changes when `items` is sent.

### 3.3 Routes

Existing checklist routes keep their capabilities and gain the fields above. New, under
`/api/p/<property_id>/checklists`:

| Route | Capability | Purpose |
|---|---|---|
| `GET /library` | `manage_admin` | The starter checklists (`ChecklistLibraryEntryOut[]`). |
| `POST /library/<key>/import` | `manage_admin` | Copy into this property as unscheduled via `ck_templates.create`; body `ChecklistLibraryImport`; 201 → `ChecklistTemplateOut`. Unknown key 404; department not at this property 400. `name` defaults to the library name. |

`tests/test_isolation.py` covers the new routes automatically.

### 3.4 The starter library (`app/domain/ck_library.py`)

Plain data: a tuple of entries, each `key`, `name`, `kind`, `department_type` (the existing
`DepartmentType`), `categories` (ordered names), and items (label, type, unit, min, max,
required, category name). Six entries:

1. **`front_desk_am`** — Front Desk AM Opening (normal, front_desk). Categories: Cash & drawer ·
   Systems · Lobby. Includes "Cash drawer counted" number $, 150–250.
2. **`front_desk_pm`** — Front Desk PM Shift (normal, front_desk). Categories: Arrivals ·
   Guest requests · Handover.
3. **`night_audit`** — Night Audit (normal, front_desk). 7 categories: Pre-audit · Cash & reports ·
   Rates & folios · Credit cards · Systems & backups · Lobby & security · Handover.
4. **`pool_spa`** — Pool & Spa Readings (readings, engineering): pool free chlorine 1.0–3.0 ppm,
   pool pH 7.2–7.8, pool temperature °F, spa temperature ≤ 104 °F, test-strip photo.
5. **`boiler_rounds`** — Boiler & Mechanical Rounds (readings, engineering): boiler supply °F,
   boiler return °F, boiler pressure psi, chiller supply °F, chiller return °F, log photo.
6. **`linen_par`** — Housekeeping Linen Par (normal, housekeeping): linen and towel counts with
   minimums.

A unit test asserts every library entry is valid input for `ck_templates.create` (every item's
category exists; bounds are ordered; units fit the column).

---

## 4. Screens

### 4.1 Admin → Checklist templates

- **List:** "Normal N · Readings N" filter chips; a Kind tag per row; Schedule shows **"Set
  schedule"** for unscheduled; a **Categories** count column.
- **Editor:** a **Kind** choice (Normal / Readings); schedule gains **"Not scheduled yet"**; a
  **Categories** list (add, rename, move up/down, remove); each item gets a **Category** select
  ("None" + the categories); the item list renders grouped by category. Built on the shared
  `ItemListEditor`, extended with an **optional** category column — PM's admin, which does not pass
  categories, renders and behaves identically (its tests are the guard).
- **Import from library** — a button beside "New template" opens a panel listing the six starter
  checklists (name, kind, categories, item count); choosing one and a department imports it and
  opens the new template in the editor to review and schedule.

### 4.2 Checklist page (`ChecklistRunPage`)

Items grouped under collapsible category headings with `done / total`; ungrouped items first with
no heading; a "Readings" tag in the header for readings checklists. PM's `ChecklistItem` renders
each row unchanged.

### 4.3 Checklists page

Readings checklists' cards show a "Readings" tag. Nothing else changes.

---

## 5. Seed data

Through the domain, HVH only: **Engineering AM Rounds** becomes `kind = readings`; **Front Desk
Overnight Night Audit** gets three categories — Audit · Payments · Reports — with its items
assigned. `test_seed` asserts both. `server/data/app.db` is regenerated. Production is never
seeded; the library is available in Admin regardless.

---

## 6. Migration and portability

`0011_checklist_structure` as §2.1. The CHECK rebuilds go through `batch_alter_table` (SQLite
recreates the table; PostgreSQL drops and re-adds the constraint). Before merge: upgrade /
downgrade / re-upgrade on Postgres 18 (including the downgrade's refusal while an unscheduled row
exists), and the app seeded and exercised on Postgres 18. After the push, the deploy log must show
`alembic upgrade head` before gunicorn, and production must report `alembic_version = 0011`.
Nothing here needs the background worker (scheduled instance generation does, and is unaffected).

---

## 7. Testing

TDD per plan task. SQLite in the suite; Postgres per §6.

- **Categories:** create and patch with new, renamed, reordered, soft-deleted categories and an
  item moved between categories; `unknown_category` (item and category), blank name and duplicate
  key are 400s; an item can't reference another template's category; removing a category leaves
  its items ungrouped; editing never changes a started instance's answers.
- **Unscheduled:** the tick skips it; the on-demand list excludes it; `start_on_demand` is a 409;
  the DB CHECK accepts `unscheduled` without shift/days and rejects it with them; switching to
  weekly requires shift + days.
- **Kind:** defaults to normal; round-trips; appears on rows.
- **Progress:** per-category `done / total` on the instance detail; ungrouped items handled.
- **Library:** list; import creates an unscheduled copy with categories, items, bounds and kind;
  every library entry passes validation; unknown key 404; other-property department 400; importing
  twice gives two templates.
- **Regression:** PM's whole suite unchanged and green; the shipped checklist suites green;
  `test_isolation` covers the new routes.
- **Web:** editor category editing and grouped items; Kind and unscheduled options; library import
  flow (pick → department → lands in editor); list chips, tags, "Set schedule"; run page grouped
  sections with progress and collapse; PM admin tests unchanged.
