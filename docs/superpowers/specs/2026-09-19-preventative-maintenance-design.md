# Preventative Maintenance — design

**Date:** 2026-09-19
**Status:** approved in brainstorming; awaiting implementation plan
**Binding over:** `docs/design.md` §6.6 where the two differ (see §12)

---

## 1. What this is and why

Preventative maintenance (PM) is the scheduled, evidence-producing upkeep of a property's rooms,
common areas and equipment — the thing a brand inspector asks to see. `docs/design.md` §11 files
it under Phase 2 ("Preventative maintenance with recurrence").

### 1.1 Origin

The reference product (Kipsu exceed FCX, `images/image (4).png` and `image (5).png`) ships PM as a
**cycle sweep**: a quarterly window, a flat list of every guest room, a `Start` button per room,
and three counters — Remaining, Cycle with days left, Completed. A separate **PM Inspection**
screen queues completed rooms for a supervisor to verify. `docs/design.md` §6.6 instead
specifies **iCal RRULE templates that generate work orders**.

Those are different products. This design builds **both**, in one spec, on one data model, with
one compliance currency (§3.6) so the dashboard never has to merge two shapes.

### 1.2 Scope

In scope:

- A maintainable-unit inventory (guest rooms, common/BOH areas, equipment), managed in Admin, with
  CSV import and seeded sample data.
- PM templates in two modes — `sweep` (cadence + unit kind) and `scheduled` (RRULE + specific
  units) — sharing one typed checklist item model.
- Auto-rolled cycles for sweep templates, with missed units frozen at close.
- RRULE expansion that materializes `WorkOrder(type=pm)` rows onto the existing Board.
- Runs with continuously-saved typed answers, photos, out-of-range work order creation, and a
  supervisor inspection step that gates cycle credit.
- The sweep page, the checklist page, the inspection page, a compliance tab, and two admin
  sections.

Out of scope:

- A `PmsAdapter.list_rooms()` method. The inventory carries `source` and `external_id` so a later
  PMS sync can upsert guest rooms without touching hand-managed rows (§3.1), but the adapter
  contract is not designed against a mock with no real counterpart.
- Housekeeping inspection (`design.md` §6.5). Different object, different actor.
- Shift checklists (§6.7). The typed item model here is the one §6.7 will reuse, but checklist
  instances, assignment and the manager dashboard are their own spec.
- More than one active sweep template per unit kind per property (§7.1).
- Translation, export of anything other than the sweep table.

---

## 2. Approach

**One template table, `PmRun` is the common currency.** A `pm_template` row has a `mode`. Sweep
mode owns a cadence and a unit kind; scheduled mode owns an RRULE and a list of target units. Both
own the same ordered, typed checklist items. A sweep `Start` creates a `PmRun`; an RRULE firing
creates a `WorkOrder(type=pm)` *with* a `PmRun` attached. Completing the run completes the work
order. Compliance is therefore one query over `pm_run`.

**Remaining is computed, never stored.** A unit is remaining in a cycle if it has no `passed` run
in that cycle. Failing an inspection returns the unit to Remaining with no state mutation.

**Inspection gates credit.** A run counts toward a cycle only when `passed`. "Completed" on the
sweep page means passed. An uninspected or failed PM is not a swept room.

**Cycle windows are property-local calendar dates.** `starts_on`/`ends_on` are `Date` columns,
not `UTCDateTime`. "Jul 01 – Sep 30" is not an instant, and "12 days left" is computed against
today in the property's timezone. `Stay.arrival_date` already sets this precedent.

**One recurring job.** `pm.tick` runs every 300 s via the existing `RECURRING` chain and does two
idempotent scans: roll cycles, expand RRULEs.

---

## 3. Data model

Eight tables. Every enum goes through `enum_type()` (`native_enum=False` → VARCHAR + CHECK). The
two many-to-many relationships are tables, not JSON arrays, for the portability reason
`log_entry_mention` is. All tables carry `property_id` (FK, indexed) and use `TimestampMixin`.

### 3.1 `maintainable_unit`

| column | type | notes |
|---|---|---|
| `kind` | `PmUnitKind` | `guest_room` / `common_area` / `equipment` |
| `code` | String(40) | `204`, `POOL-PUMP-1`; unique with `property_id` |
| `name` | String(200) | `Room 204`, `Pool pump 1` |
| `floor` | Integer, nullable | |
| `room_type` | String(20), nullable | `KNGN`, `KWHN` — the PMS room-type code |
| `active` | Boolean, default true | deactivate, never delete: historical runs reference it |
| `source` | `PmUnitSource` | `manual` / `csv` / `pms` |
| `external_id` | String(100), nullable | the PMS's id, for a future sync to upsert by |
| `notes` | Text, nullable | |

`UniqueConstraint(property_id, code)`. A future PMS sync upserts by `(property_id, external_id)`
and never modifies a row whose `source` is `manual` or `csv`. The PMS will only ever supply guest
rooms; common areas and equipment stay on the admin/CSV path permanently.

### 3.2 `pm_template`

| column | type | notes |
|---|---|---|
| `name` | String(200) | |
| `mode` | `PmTemplateMode` | `sweep` / `scheduled` |
| `department_id` | FK, nullable | owning department; receives out-of-range alerts |
| `active` | Boolean | |
| `unit_kind` | `PmUnitKind`, nullable | sweep only |
| `cadence` | `PmCadence`, nullable | sweep only: `monthly` / `quarterly` / `semiannual` / `annual` |
| `rrule` | String(500), nullable | scheduled only; RFC 5545 RRULE without the `RRULE:` prefix |
| `rrule_dtstart` | Date, nullable | scheduled only; anchor for expansion |
| `last_fired_at` | UTCDateTime, nullable | scheduled only; where expansion left off |

A CHECK constraint enforces the mode split:
`(mode = 'sweep' AND unit_kind IS NOT NULL AND cadence IS NOT NULL AND rrule IS NULL)
OR (mode = 'scheduled' AND rrule IS NOT NULL AND rrule_dtstart IS NOT NULL AND cadence IS NULL)`.
Written as a `CheckConstraint` in the model so both engines get it.

### 3.3 `pm_template_item`

| column | type | notes |
|---|---|---|
| `template_id` | FK | |
| `position` | Integer | display order |
| `label` | String(200) | |
| `item_type` | `PmItemType` | `checkbox` / `text` / `number` / `photo` |
| `unit` | String(16), nullable | `°F`, `psi`; number only |
| `min_value` | Numeric(10,2), nullable | number only |
| `max_value` | Numeric(10,2), nullable | number only |
| `required` | Boolean | |
| `active` | Boolean | soft delete — `pm_run_answer` references this row |

### 3.4 `pm_template_unit`

`template_id` FK, `unit_id` FK, unique together. Which specific units a **scheduled** template
targets. Sweep templates do not use it; their scope is every active unit of `unit_kind`.

### 3.5 `pm_cycle`

| column | type | notes |
|---|---|---|
| `template_id` | FK | sweep templates only |
| `ordinal` | Integer | position within the calendar year: 3 → "3rd Cycle" |
| `starts_on` | Date | property-local |
| `ends_on` | Date | property-local, inclusive |
| `status` | `PmCycleStatus` | `open` / `closed` |

`UniqueConstraint(template_id, starts_on)`.

### 3.6 `pm_run` — the compliance currency

| column | type | notes |
|---|---|---|
| `template_id` | FK | |
| `unit_id` | FK | |
| `cycle_id` | FK, nullable | sweep runs only |
| `work_order_id` | FK, nullable | scheduled runs only |
| `status` | `PmRunStatus` | `pending` / `in_progress` / `completed` / `passed` / `failed` / `missed` |
| `started_by_user_id` | FK, nullable | |
| `started_at` | UTCDateTime, nullable | |
| `completed_at` | UTCDateTime, nullable | |
| `inspected_by_user_id` | FK, nullable | |
| `inspected_at` | UTCDateTime, nullable | |
| `inspection_note` | Text, nullable | |
| `due_at` | UTCDateTime, nullable | scheduled runs: the RRULE occurrence; mirrors the work order |

Status transitions:

```
pending ──start──▶ in_progress ──complete──▶ completed ──pass──▶ passed
                                                       └──fail──▶ failed
(cycle close) ──▶ missed        (materialized, never transitions)
```

Sweep runs are created directly in `in_progress` by `Start`. Scheduled runs are created in
`pending` by `pm.tick` and move to `in_progress` when someone opens the checklist and starts it.
A `missed` run is written by cycle close for every in-scope unit lacking a `passed` run; it is the
frozen evidence and stays true even if the unit is later deactivated.

Index: `(property_id, cycle_id, unit_id, status)` — the sweep page's `NOT EXISTS` and the
inspection queue both hit it.

### 3.7 `pm_run_answer`

| column | type | notes |
|---|---|---|
| `run_id` | FK | |
| `item_id` | FK → `pm_template_item` | |
| `bool_value` | Boolean, nullable | |
| `text_value` | Text, nullable | |
| `number_value` | Numeric(10,2), nullable | |
| `out_of_range` | Boolean, default false | set on save when number is outside `[min,max]` |
| `answered_at` | UTCDateTime, nullable | null = not yet answered |

`UniqueConstraint(run_id, item_id)`. One row per active item, created at `Start`, so progress
saves continuously and the frontend never holds unsaved answers.

### 3.8 `pm_run_photo`

Same shape and rationale as `WorkOrderPhoto`: `run_id`, `property_id`, `uploaded_by_user_id`,
`content_type`, `byte_size`, `data` (`LargeBinary`, `deferred=True`). Bytes live in the table
because the deploy target's filesystem is ephemeral. Plus `item_id` (FK → `pm_template_item`,
nullable): a photo with an `item_id` answers that `photo` item (§4.2); one without is general
evidence for the run.

### 3.9 Enums

`PmUnitKind`, `PmUnitSource`, `PmTemplateMode`, `PmCadence`, `PmItemType`, `PmCycleStatus`,
`PmRunStatus` — all in `app/schemas/enums.py`, all `StrEnum`. `WorkOrderType.pm` already
exists.

### 3.10 New dependency

`python-dateutil>=2.9` for `dateutil.rrule.rrulestr`. Not currently installed. Hand-rolling
RFC 5545 is not an option.

---

## 4. Behaviour

### 4.1 `pm.tick`

Registered in `RECURRING` at `300`. Uses `schedule_next_recurrence` and its existing duplicate
guard. Both phases are idempotent, date-driven scans — the worker retries, so running twice must
be harmless.

**Phase A — cycles.** For each active sweep template, with `today` = the property-local date:

1. If no `open` cycle has `starts_on <= today <= ends_on`, open one. Windows align to
   calendar-year cadence boundaries: monthly = calendar months; quarterly = Jan–Mar, Apr–Jun,
   Jul–Sep, Oct–Dec; semiannual = Jan–Jun, Jul–Dec; annual = the year. `ordinal` is the window's
   position in the year (1-based).
2. For each `open` cycle with `ends_on < today`: for every active unit of the template's
   `unit_kind` with no `passed` run in that cycle, insert `PmRun(status=missed, cycle_id=…)`.
   Then set the cycle `closed`.

A newly-created template gets its first cycle on the next tick, or immediately on creation
(the create route calls the same function).

**Phase B — RRULE.** For each active scheduled template:

1. `last_fired_at` is stamped `clock.now()` when a scheduled template is created, and again
   whenever its mode, rrule or start date changes — a changed schedule restarts from now and
   never backfills. The expansion window is therefore always `(last_fired_at, window_end]`,
   `window_end = clock.now()` — exclusive on the left so the occurrence that ended the last
   window is not emitted twice.
2. Expand `rrulestr(rrule, dtstart=dtstart)` over that window, where `dtstart` = `rrule_dtstart`
   at 00:00 property-local converted to UTC — the RRULE's anchor, not the window bound.
   `dateutil`'s `between()` is exclusive at both ends by default, so the implementation passes
   `inc=True` and filters the left edge itself. Bounding by the window is what stops a template
   with a 2020 `dtstart` from emitting five years of work orders.
3. For each occurrence × each unit in `pm_template_unit`: create
   `WorkOrder(type=pm, priority=normal, title=f"{template.name} — {unit.name}",
   location_type=<from unit.kind>, location_ref=unit.code, department_id=template.department_id,
   due_at=occurrence, status=open)` and `PmRun(status=pending, work_order_id=…, due_at=occurrence)`.
4. Set `last_fired_at = window_end`.

`LocationType` mapping: `guest_room → room`, `common_area → public_area`, `equipment → equipment`.

### 4.2 Sweep lifecycle

- **Remaining** = active units of `unit_kind` with no `passed` run in the open cycle. Computed by
  `NOT EXISTS`, never stored.
- **Start** (`perform_pm`): refuses if the unit already has an `in_progress` or `completed` run in
  the open cycle (409 with the run id, so the client can offer Continue instead). Otherwise creates
  `PmRun(in_progress)` and one `pm_run_answer` per active item.
- **Answer** (`perform_pm`): PATCH sets exactly one of the value columns by `item_type`, stamps
  `answered_at`, and for `number` sets `out_of_range` when outside `[min_value, max_value]`
  (either bound may be null). Rejected once the run is past `in_progress`.
- **Complete** (`perform_pm`): every `required` item must have `answered_at`; a `photo` item is
  answered when at least one `pm_run_photo` carries its `item_id`. Moves to `completed`, stamps
  `completed_at`. If the run has a `work_order_id`, transitions the work order to `completed`
  through the existing work-order domain function so its event log stays honest. Then §4.3.

### 4.3 Out-of-range readings

On `Complete`, for each answer with `out_of_range`: create
`WorkOrder(type=maintenance, priority=high,
title=f"{item.label} {value}{item.unit} out of range ({min}–{max}) — {unit.name}",
location from the unit, department_id=template.department_id)` and notify every
active supervisor-or-above member of that department (`notify` helper, type `pm.out_of_range`,
entity the new work order). This is `design.md` §6.7's rule applied here because the item model is
shared.

Deliberately at Complete, not at answer save: an engineer who fat-fingers 1220 and corrects it
should not have spawned a work order.

### 4.4 Inspection

- `completed` runs appear in *Available for Inspection*.
- **Inspect** (`inspect_pm`): `{result: "pass" | "fail", note?}`. Requires `note` on fail. Sets
  `inspected_by`, `inspected_at`, `inspection_note`, and status `passed` or `failed`.
- On fail, notify `started_by_user_id` (type `pm.inspection_failed`, entity the run). The unit is
  back in Remaining by the computed rule; nothing else changes.
- A run cannot be inspected twice. A run may not be inspected by the user who performed it, unless
  that user is the only `inspect_pm` holder in the property — small properties have one engineer
  who is also the supervisor, and blocking them would block PM entirely.

### 4.5 Template editing

Changing a template's items never deletes an item row. Removing one sets `active = false`. Runs
already started keep their answer rows; new runs get answers only for active items. Changing
`min`/`max` does not recompute historical `out_of_range`.

Switching `mode` on a template with any runs is rejected (409).

Deactivating a sweep template leaves its open cycle open; `pm.tick` skips inactive templates for
both phases, so the cycle simply never closes and never rolls. Reactivating resumes.

---

## 5. API

Two blueprints under `/api/p/<property_id>/`. Bodies and responses are `CamelModel`s.

### 5.1 `app/api/maintainable_units.py` — `/maintainable-units`

| method | path | capability | notes |
|---|---|---|---|
| GET | `/` | `view_pm` | `?kind=&active=&q=`; `q` matches `code` and `name` |
| POST | `/` | `manage_admin` | |
| PATCH | `/<id>` | `manage_admin` | any column except `property_id`; `active=false` to retire |
| POST | `/import` | `manage_admin` | multipart `file`; see §5.4 |

### 5.2 `app/api/pm.py` — `/pm`

| method | path | capability | notes |
|---|---|---|---|
| GET | `/templates` | `view_pm` | with items and, for scheduled, target unit ids |
| POST | `/templates` | `manage_admin` | items inline; opens the first cycle for sweep mode |
| PATCH | `/templates/<id>` | `manage_admin` | items inline; §4.5 rules |
| GET | `/sweep` | `view_pm` | `?kind=&status=remaining|completed&q=&sort=`; §5.3 |
| GET | `/cycles` | `view_pm` | `?template_id=`; closed cycles with passed/missed counts |
| POST | `/runs` | `perform_pm` | `{templateId, unitId}` → run with answers; 409 on duplicate |
| GET | `/runs/<id>` | `view_pm` | run, unit, template items, answers, photo metadata |
| POST | `/runs/<id>/start` | `perform_pm` | `pending → in_progress` for scheduled runs |
| PATCH | `/runs/<id>/answers/<answer_id>` | `perform_pm` | one value; §4.2 |
| POST | `/runs/<id>/photos` | `perform_pm` | multipart `photo`, optional `itemId`; oversize/non-image rejected as in `log.py` |
| GET | `/runs/<id>/photos/<photo_id>` | `view_pm` | bytes |
| POST | `/runs/<id>/complete` | `perform_pm` | §4.2, §4.3 |
| GET | `/inspections` | `inspect_pm` | `?kind=&status=available|inspected&sort=days_since_last_pm|completed_at` |
| POST | `/runs/<id>/inspect` | `inspect_pm` | `{result, note?}`; §4.4 |
| GET | `/compliance` | `view_property_analytics` | `?from=&to=` (property-local dates); §5.5 |

### 5.3 `GET /sweep`

Returns, for the requested `kind`:

```
{
  template: {id, name, cadence} | null,
  cycle: {id, ordinal, startsOn, endsOn, daysLeft} | null,
  counts: {remaining, completed, total},
  units: [{
    id, code, name, floor, roomType,
    lastPassedAt, lastPassedBy,          // most recent passed run, any cycle
    currentRun: {id, status, startedBy} | null   // in_progress/completed run in the open cycle
  }]
}
```

`template` and `cycle` are null when the kind has no active sweep template or no open cycle yet;
the page renders an empty state naming which. `daysLeft` is `ends_on - today_local`, floored at 0.
`counts.completed` counts `passed` runs. `sort` accepts `code` (default), `floor`,
`days_since_last_pm` (units never passed sort first). Remaining, current runs and last-passed are
computed in one pass from three set queries per property (active units, runs in the open cycle,
passed runs); nothing is queried per row.

### 5.4 CSV import

Header row required: `code,kind,name,floor,room_type,external_id`. `floor`, `room_type`,
`external_id` may be blank. `kind` must be a `PmUnitKind` value. Rows upsert by
`(property_id, code)`; an existing `manual` row is updated (its `source` becomes `csv`).

Every row is validated before any is written. Any error → nothing committed, a `422` with code
`IMPORT_REJECTED` and the report — `{created: 0, updated: 0, errors: [{line, field, message}]}` —
as `error.details`, not a bare payload. Success → `{created, updated, errors: []}`. The file is
capped at 1 MB and 5,000 rows.

### 5.5 `GET /compliance`

For the window, per template:

```
{ templates: [{
    id, name, mode, unitKind,
    cycles: [{ordinal, startsOn, endsOn, passed, missed, total, onTimePct}],   // sweep
    runs:   {due, passed, failed, missed, overdue},                          // scheduled
    inspectionPassRate: number | null
}]}
```

`onTimePct` and `inspectionPassRate` are percentages (0–100, one decimal): `onTimePct =
round(100 * passed / total, 1)`. A scheduled run is `overdue` when `due_at < now` and status is
`pending` or `in_progress`. `inspectionPassRate = round(100 * passed / (passed + failed), 1)`
across inspected runs in the window.

---

## 6. Capabilities

Three new rows in `server/app/auth/permissions.py`, mirrored in `web/src/auth/capabilities.ts` in
the same commit. **Every one includes `Role.admin`** — `tests/test_isolation.py` asserts a
property's admin is never 403 on any property route.

```
"view_pm":    STAFF
"perform_pm": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin}
"inspect_pm": {Role.supervisor, Role.manager, Role.admin}
```

Inventory and template management reuse `manage_admin`. Export of the sweep table reuses
`export`. The compliance tab reuses `view_property_analytics`.

---

## 7. Frontend

Feature folder `web/src/features/pm/`, hooks in `web/src/api/hooks/pm.ts`, types from
`types.generated.ts`. Same shell, same `md` breakpoint, same `AdminTable`/`EditPanel` idiom.

### 7.1 Navigation

`navModel.ts` gains a **Maintenance** group:

- *Preventative Maintenance* → `/app/pm`, needs `view_pm`, matches `/app/pm` (so runs and the
  compliance tab light it).
- *PM Inspection* → `/app/inspection`, needs `inspect_pm`. It lives at `/app/inspection`, a
  sibling of `/app/pm` rather than under it, so the Preventative Maintenance rail entry — which
  matches the `/app/pm` prefix — does not light on it.

`ADMIN_SECTIONS` gains *Maintainable units* (`/app/admin/units`) and *PM templates*
(`/app/admin/pm-templates`).

`/app/inspection`, `/app/pm/compliance` and `/app/pm/runs/:id` are declared as siblings of
`/app/pm` in `routes.tsx`, not nested under it, so `SweepPage`'s `?kind=` state never leaks into
them.

**One active sweep template per unit kind per property**, enforced in the domain layer on create
and on activate (a partial unique index is not portable). This is what keeps the sweep page a
single table with no template picker.

### 7.2 `/app/pm` — `SweepPage`

Kind tabs (Guest Rooms · Common & BOH · Equipment) in the URL (`?kind=`). Three stat tiles:
**Remaining**, **Cycle** (`3rd Cycle · Jul 01 – Sep 30 · 12 days`), **Completed**. Search,
Remaining/Completed select, sort select, Export button (`export` capability; downloads the current
rows as CSV, built client-side from the loaded list). Table columns: unit (code, room type), floor,
last PM (date + who), action. Action per row from `currentRun`:

| state | button |
|---|---|
| no current run | **Start** → `POST /runs`, navigate to the run |
| `in_progress` | **Continue** (label shows who started it) |
| `completed` | **Awaiting inspection**, disabled |
| unit has a passed run this cycle | **Done**, disabled, row hidden under Remaining filter |

Below `md`, rows become cards. Empty states: no template for this kind (links to admin for
`manage_admin` holders), no open cycle yet, no units of this kind.

A **Compliance** tab appears for `view_property_analytics` holders → `/app/pm/compliance`.

### 7.3 `/app/pm/runs/:id` — `RunPage`

Header: unit name, template name, started by / at, cycle or work order link. Then items in
`position` order, each by `item_type`:

- `checkbox` — a toggle.
- `text` — a text field, saved on blur.
- `number` — a numeric field with the unit as a suffix and the bounds shown beneath; when the
  saved answer is `out_of_range` the field and a warning line turn to the danger colour, and the
  copy says a work order will be raised on completion.
- `photo` — thumbnails of photos carrying this `item_id`, plus an upload control.

Every change PATCHes its answer row; a toast on failure, no local queue. **Complete** is disabled
until every required item is answered, and lists what's missing. Built phone-width first — this is
used standing in a bathroom.

The same component renders in **inspection mode** (`readOnly` + footer) when opened from the
inspection queue: every answer displayed, photos full-size on tap, a Pass button and a Fail button
that reveals a required note field.

Runs in `pending` (scheduled) show a single **Start PM** button in place of the checklist until
`POST /start` succeeds.

### 7.4 `/app/inspection` — `InspectionPage`

Kind tabs; *Available for Inspection (n)* / *Inspected (n)* sub-tabs; sort select. Rows: unit,
completed by / at, days since last PM, and for the Inspected tab the result and inspector. A row
opens `RunPage` in inspection mode.

### 7.5 `/app/pm/compliance` — `CompliancePage`

Per template: a small table of cycles with passed / missed / on-time %, and the inspection pass
rate. Charts, if any, follow the `dataviz` skill. This is a table first; charts are additive.

### 7.6 Admin

**`UnitsAdmin`** (`/app/admin/units`): kind tabs, `AdminTable` (code, name, floor, room type,
source, active), `EditPanel` for create/edit/deactivate, and an **Import CSV** dialog: file picker,
a link to the sample file's column format, and on 422 the per-row error list rendered in place —
nothing was committed, so the user fixes the file and retries.

**`PmTemplatesAdmin`** (`/app/admin/pm-templates`): list with mode, unit kind or target count,
cadence or recurrence summary, active. `EditPanel` with:

- Mode toggle (locked once the template has runs).
- Sweep: unit kind select, cadence select.
- Scheduled: a recurrence builder — *every* `[n]` `[days|weeks|months|years]` — plus a start date
  and a unit multi-select filtered by kind. An *Advanced* disclosure exposes the raw RRULE for
  anything the builder can't express; the builder is disabled while the raw field is non-empty.
- Items editor: ordered rows with label, type, unit + min + max (number only), required; add,
  remove (soft), reorder.

### 7.7 `WorkOrderDetailPage`

When the work order has a linked run (`pmRunId` added to the work-order response), show an
**Open PM checklist** link. Without it a scheduled PM's checklist is unreachable from the Board.

---

## 8. Realtime

Events on the property channel, invalidating the obvious queries:

- `pm.run.changed` `{id, unitId, cycleId, status}` — on start, complete, inspect. Sweep and
  inspection pages refetch. Two engineers looking at the same room list see Start become Continue.
- `pm.cycle.rolled` `{templateId}` — on open/close. Sweep page refetches.

Notifications (existing `notify` path, in-app + push): `pm.out_of_range` (§4.3),
`pm.inspection_failed` (§4.4).

---

## 9. Sample data

Two forms of the same rows, on purpose.

**Seeded** (`server/seed/seed.py`, extending `SeedSummary`):

- 120 guest rooms matching the stay grid the seeder already generates (`floors 1–6 × 01–20`,
  `seed.py:185`), so every seeded stay's `room_number` resolves to a unit. Floor derived from the
  number; `room_type` a code drawn per row (`KNGN`, `KWHN`, `TQNN`, `KSTE`, `KACC` — mapped from
  the existing `ROOM_TYPES`). `source = manual`.
- ~10 common/BOH areas: Lobby, Pool, Fitness Room, Guest Laundry, Boiler Room, Elevator A,
  Elevator B, Stairwell North, Stairwell South, Loading Dock.
- ~8 equipment: Pool pump 1, Boiler 1, Boiler 2, Ice machine 2F, Ice machine 4F, Elevator motor A,
  Elevator motor B, Rooftop HVAC unit 1.
- Sweep template *Guest Room Quarterly* (Engineering) with items: HVAC filter replaced (checkbox,
  required); Tap hot-water temperature (number, °F, 100–120, required); GFCI outlets tested
  (checkbox, required); Caulk and grout condition (text); Bathroom exhaust fan photo (photo,
  required); Smoke detector tested (checkbox, required).
- Sweep template *Common Areas Monthly* (Engineering), three items.
- Scheduled template *Boiler inspection* — `FREQ=MONTHLY;INTERVAL=3`, targeting Boiler 1 and
  Boiler 2, four items.
- The current quarterly cycle open, with ~40 rooms `passed`, 3 `in_progress`, 4 `completed`
  awaiting inspection, 2 `failed` with notes; the previous cycle closed with ~110 passed and ~10
  missed. Timestamps from `app.clock`.

**Sample CSV** (`fixtures/maintainable_units.sample.csv`): the same 138 rows in the import
format, so the load can be practised against a fresh Postgres, and one line can be broken to see
the error report. `dev_start.py` seeds only an empty database, so the two paths never collide.

---

## 10. Migration and portability

`alembic/versions/0007_preventative_maintenance.py`, revises `0006`. Creates the eight tables and
their constraints and indexes; `downgrade()` drops them in FK-safe order. Verified against
Postgres 18 in the container per `CLAUDE.md` (`upgrade head`, `downgrade 0006`, `upgrade head`)
before merge.

Portability rules honoured:

- Enums via `enum_type()`; the mode CHECK via `CheckConstraint` in the model.
- `Numeric(10,2)` for readings — not `Float`, which rounds differently per engine.
- No partial indexes; the one-sweep-per-kind rule lives in the domain layer.
- `Date` columns compared against property-local dates computed in Python from `clock.now()`,
  never against `now()` in SQL.
- RRULE expansion in Python via `dateutil`; nothing date-arithmetic in SQL.

---

## 11. Testing

Backend (pytest, `server/tests/`):

- Cycle windows for every cadence at year boundaries and in a non-UTC property timezone; ordinal
  correct; a tick with an existing open cycle creates nothing; a tick over a closed window
  materializes exactly one `missed` per unswept active unit and none for inactive units or
  already-passed ones; a second tick materializes nothing more.
- RRULE expansion: windowed — a template with an old `dtstart` emits only occurrences after
  `last_fired_at`; each occurrence × unit yields one work order and one pending run; `last_fired_at`
  advances; an inactive template is skipped; invalid RRULE rejected on template create.
- Start: duplicate in cycle → 409 with existing run id; answers pre-created for active items only.
- Answer: type-mismatched value rejected; `out_of_range` set and cleared as the value crosses
  bounds; null bound on one side; rejected after completion.
- Complete: missing required item → 422 naming it; photo item satisfied only by a photo with its
  `item_id`; out-of-range answers each produce one high-priority work order and one notification
  per supervisor-or-above in the department; scheduled run completion transitions the work order.
- Inspect: pass credits the cycle (Remaining drops by one); fail does not, notifies the engineer,
  and the unit shows under Remaining again; note required on fail; double inspect → 409;
  self-inspect blocked unless sole holder.
- Sweep query: counts, Remaining filter, `days_since_last_pm` ordering with never-passed first.
- Template editing: item removal is soft; mode switch with runs → 409; second active sweep
  template for a kind → 409.
- CSV import: happy path; one bad row → 422 and zero rows written; upsert updates existing;
  size and row caps.
- Compliance: on-time % and inspection pass rate against a hand-built fixture.
- Photos: oversize, non-image, round-trip.
- Cross-property ids in every body field rejected.
- All new routes covered by the property-isolation suite automatically; new tables in
  `EXPECTED_TABLES`; new models in the schema-export tuple.

Frontend (vitest, `web/src/features/pm/`):

- Sweep page: tiles from the payload, each row action state, Remaining filter, empty states.
- Run page: each item type renders and PATCHes; out-of-range styling; Complete disabled with
  reasons; inspection mode footer, fail requires note.
- Inspection page: sub-tab counts, row opens run in inspection mode.
- Units admin: import dialog renders per-row errors.
- Templates admin: mode toggle fields, recurrence builder composes the expected RRULE, advanced
  field disables the builder.
- Nav: Maintenance group visible by capability; capability table matches `permissions.py`.
- Realtime invalidation on both events.

---

## 12. Acceptance criteria

1. An admin imports the sample CSV into an empty property; 138 units appear under the right
   kind tabs. Re-importing changes nothing. A CSV with one bad `kind` imports nothing and names
   the line.
2. Creating *Guest Room Quarterly* opens the current quarter's cycle immediately; the sweep page
   shows Remaining = number of active guest rooms, Completed = 0, and the correct days left.
3. An engineer starts Room 204, records 122 °F, sees it flagged, completes; a high-priority
   maintenance work order for Room 204 appears on the Board and the Engineering supervisor is
   notified. Room 204 shows *Awaiting inspection*.
4. A supervisor fails that run with a note; the engineer is notified; Room 204 is back under
   Remaining. The supervisor passes a second run; Completed increments.
5. When the quarter ends, the cycle closes with one `missed` run per unswept room, and the next
   quarter opens with every room Remaining. The compliance tab shows last quarter's on-time %.
6. *Boiler inspection* fires on its schedule, creating one `pm` work order per boiler on the
   Board; opening one reaches its checklist; completing the checklist completes the work order.
7. A member of another property gets 403 on every PM route; a property admin never does.
8. All of the above hold on PostgreSQL 18.

---

## 13. Deviations from `docs/design.md`

| §6.6 says | This design does | Why |
|---|---|---|
| RRULE templates generate work orders | Also builds a cycle sweep with no work order per unit | The reference product's PM is a sweep; 100 quarterly cards would bury the Board (§1.1, §2) |
| "attached to assets or locations" | A `maintainable_unit` inventory with three kinds | No asset or room table existed; `WorkOrder.location_ref` is free text (§3.1) |
| Compliance "by asset category" | Compliance by template, with cycles for sweeps and due/overdue for scheduled | One `pm_run` query serves both (§5.5) |
| No inspection step | Supervisor inspection gates cycle credit | Reference product has it; "completed" without verification is not evidence (§4.4) |
| §6.7's typed items belong to shift checklists | Built here first, on `pm_template_item` | PM needs them to be auditable; §6.7 reuses the model (§1.2) |
