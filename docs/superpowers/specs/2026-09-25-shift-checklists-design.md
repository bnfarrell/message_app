# Shift checklists — design

**Status: AWAITING WRITTEN-SPEC REVIEW.** Sections 1–7 were presented and approved one at a time
in the brainstorming session of 2026-09-25, and the spec has had its self-review. Next: the user
reviews this file; on approval an implementation plan is written from it.

---

## 1. What this is and why

`docs/design.md` §6.7 — per-department, per-shift routines with typed readings: front-desk
opening duties, engineering rounds, night audit. "Number-with-bounds is what makes pool chemistry
and HVAC setpoints work. An out-of-range reading auto-creates a work order and alerts the
supervisor." Missed checklists "are visible on the manager dashboard, not silently forgotten."

### 1.1 Decisions made during brainstorming

- **Who a checklist is for: the department by default, optionally assigned.** A due instance
  shows for everyone in its department; a supervisor *can* assign it; anyone in the department
  can claim it by starting it.
- **Schedules: a chosen shift on chosen weekdays, plus on-demand.** Monthly-or-rarer is
  preventative maintenance's job (PM already has full RRULEs).
- **Missed = not completed when its shift ends,** on the property's configured shift boundaries.
- **Structure: new checklist tables that share PM's typed-item *logic*, not its tables.** PM runs
  are bound to a unit, a cycle, compliance and an inspection gate — none of which applies to a
  shift routine. Rejected: a third PM template mode (every PM query would need a "unless shift"
  branch and shipped tables would change) and a generic engine migrating PM's production data
  (highest risk, rewrites a shipped feature to add a new one).

### 1.2 Scope

**In:** templates (department, schedule, typed items); instance generation; assign / claim /
start / continuous save / handover comment / complete; out-of-range → work order + supervisor
alert; missed marking; a Checklists page, a checklist page, a managers' Missed view; an Admin
section for templates.

**Out (deferred):** monthly-or-rarer schedules; supervisor sign-off/inspection on checklists;
checklist analytics beyond the missed list; notifications on miss (the Missed view is the
surface); pushing checklists into housekeeping assignments (`design.md` §6.5).

---

## 2. Data model

One migration, `0009_shift_checklists`. Engine-portable; every enum through `enum_type()`.

### 2.1 Tables

**`checklist_template`** — property, name, `department_id`, `schedule` (`weekly` | `on_demand`),
`shift` (`am` | `pm` | `overnight`, the existing `Shift` enum), `weekdays` (Integer bitmask,
bit 0 = Monday … bit 6 = Sunday), `active`.
A portable CHECK keeps the schedule fields honest, as `pm_template` does:
`(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL AND weekdays > 0)
 OR (schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)`.

**`checklist_template_item`** — template, property, `position`, `label`, `item_type`
(the existing `PmItemType`: checkbox · text · number · photo), `unit`, `min_value`, `max_value`,
`required`, `active`. Exactly PM's item columns; soft-deleted the same way so old answers keep
their item.

**`checklist_instance`** — property, template, `due_date` (property-local date the shift
*starts*), `shift`, `slot` (Integer, nullable), `status` (`open` → `in_progress` → `complete`,
or `missed`), `assigned_user_id`, `started_by_user_id`, `completed_by_user_id`, `started_at`,
`completed_at`, `comment` (Text — the handover note).
**Unique `(template_id, due_date, shift, slot)`.** Scheduled instances carry `slot = 0`, so
generation is idempotent at the database level. On-demand instances carry `slot = NULL`; both
PostgreSQL and SQLite treat NULLs as distinct in a unique constraint, so an on-demand template
can run any number of times a day.
Index `(property_id, due_date)` for the list, `(property_id, status)` for the miss sweep.

**`checklist_answer`** — instance, property, item, `bool_value`, `text_value`, `number_value`,
`out_of_range`, `answered_at`. One row per active item, created at start — the instance's
snapshot of the checklist. Unique `(instance_id, item_id)`.

**`checklist_photo`** — instance, property, item (nullable), uploader, `content_type`,
`byte_size`, `data` (LargeBinary, **NOT NULL**, deferred) — as every photo table.

### 2.2 Shared typed-item rules

A new module `app/domain/typed_items.py` holds what is today inside `pm_runs.py`: the
value-column-per-type rule, answer validation (right field for the type; text trimmed, blank =
unanswered), the out-of-range test, "missing required", and the out-of-range title format. PM
calls it with no behaviour change — its existing tests are the guard. Checklists call it too, so
a fix to either applies to both.

---

## 3. Behaviour

### 3.1 Shift windows

Beside the hotel log's `shift_for`, a new helper:
`shift_window(prop, day, shift) -> (start, end)` as aware UTC, from the property's configured
`shift_boundaries`. `am` runs from the am boundary to the pm boundary, `pm` from pm to overnight,
`overnight` from that evening's overnight boundary to the **next** morning's am boundary. Built on
`ZoneInfo`, so DST days have their true length. A companion `current_shift(prop, at) ->
(day, shift)` returns the shift `at` falls in and the date that shift started (02:00 is the
previous day's overnight).

### 3.2 `checklist.tick`

Recurring every 300 s; stateless and idempotent like `housekeeping.tick`. Per property:

1. **Generate.** For every active `weekly` template whose `weekdays` include the property-local
   weekday of today, ensure an instance exists for `(today, template.shift, slot 0)`. Today's
   instances therefore appear first thing in the day, so each shift can see what is coming.
2. **Miss.** Every `open` or `in_progress` instance whose `shift_window` has ended becomes
   `missed` and is frozen; a partly answered one keeps its answers as evidence.
3. **Emit** one realtime event per property, only when something changed.

### 3.3 Lifecycle

| action | who | effect |
|---|---|---|
| assign / unassign | supervisor+ (`manage_checklists`) | sets `assigned_user_id`; the target must be an active member of the template's department (400 otherwise); notifies the assignee |
| start | a member of the template's department, the assignee, or supervisor+ | `open → in_progress`; `started_by`, `started_at`; answers pre-created for active items; an unassigned instance becomes assigned to the starter ("claim") |
| save answer / photo / comment | same people, while `in_progress` | continuous save through the shared typed-item rules |
| complete | same people, from `in_progress` | required items enforced (400 whose details list the missing item ids); `completed_by`, `completed_at`; each out-of-range number creates a high-priority work order for the template's department and alerts that department's supervisors (PM's escalation path) |
| start on-demand | a member of the template's department, or supervisor+ | creates an instance for `current_shift(prop, now)` with `slot = NULL` and starts it in one step |
| missed | the tick only | from `open` / `in_progress` once the window ends; no transitions out |

Anything not in this table is a 409. Starting early is allowed (the PM crew may open their
checklist during AM). There is no reopen after complete. A photo is accepted only while
`in_progress`.

**On-demand instances take the shift they are started in,** not a template shift (on-demand
templates have none). This is what keeps them from being born already missed — an AM template
started at 15:00 would otherwise be past its window immediately. They are missed at the end of the
shift they were started in, like any other instance.

### 3.4 Template edits

Items are soft-deleted and each instance snapshots its items at start, as in PM, so editing a
template never alters a started instance. Changing a weekly template's shift or weekdays affects
generation from the next tick on; an already-generated unstarted instance keeps its shift.
Deactivating a template stops generation; today's already-generated unstarted instance stays, so
nobody's list changes under them mid-shift.

### 3.5 Realtime

One event, `checklist.instances.changed { ids }`, from a single emission helper that every
mutation and the tick go through — housekeeping's pattern. It invalidates the list, the missed
view, and each named instance.

---

## 4. API, capabilities and screens

### 4.1 Shared wire shapes

Items, answers and photos go over the wire in PM's existing models — `TemplateItemIn`,
`TemplateItemOut`, `AnswerPatch`, `RunAnswerOut`, `RunPhotoOut` — reused, not duplicated, so
PM's `ChecklistItem` component renders checklist rows unchanged. Checklist-specific models are
prefixed `Checklist` (e.g. `ChecklistTemplateIn`, `ChecklistInstanceOut`) and live in
`app/schemas/checklists.py`.

### 4.2 Blueprint

`app/api/checklists.py`, `url_prefix="/api/p/<property_id>/checklists"`, following `pm.py`.
Every route `@require_auth` + `@require_property` + a capability.

| route | capability | purpose |
|---|---|---|
| `GET /templates` | view_checklists | list (on-demand picker, admin) |
| `POST /templates`, `PATCH /templates/<id>` | manage_admin | create / edit; items synced like PM templates |
| `POST /templates/<id>/start` | perform_checklists | start an on-demand instance now |
| `GET /instances?date&departmentId&status` | view_checklists | list rows: template name, department, shift, status, assignee, progress (answered / required), out-of-range count |
| `GET /instances/<id>` | view_checklists | detail: items, answers, photos, comment, missing-required |
| `POST /instances/<id>/assign` | manage_checklists | `{ userId \| null }` |
| `POST /instances/<id>/start`, `/complete` | perform_checklists | lifecycle §3.3 |
| `PATCH /instances/<id>` | perform_checklists | `{ comment }` |
| `PATCH /instances/<id>/answers/<answerId>` | perform_checklists | a typed answer |
| `POST /instances/<id>/photos`, `GET …/photos/<photoId>` | perform / view | multipart; bytes in the DB, same cap and sniffing as work orders |
| `GET /missed?days=7` | view_property_analytics | the managers' missed list |

Department membership ("only its department acts on a checklist", supervisor+ exempt) is enforced
in the domain layer, not by capability — as housekeeping's assignment rule is.

### 4.3 Capabilities

Added to `app/auth/permissions.py` and mirrored in `web/src/auth/capabilities.ts` in the same
commit. All include `admin` (`tests/test_isolation.py`).

| capability | roles |
|---|---|
| `view_checklists` | all of `STAFF` |
| `perform_checklists` | agent, dept_staff, supervisor, manager, admin |
| `manage_checklists` | supervisor, manager, admin |

Templates use the existing `manage_admin`; the missed list the existing `view_property_analytics`.

### 4.4 Screens

- **Nav:** a **Checklists** entry in the Overview group, next to Log. Needs `view_checklists`.
- **`/app/checklists` — `ChecklistsPage`.** Today's instances grouped by shift (AM / PM /
  Overnight). A card: name, department, status, assignee, progress ("5 / 8"), out-of-range flag,
  Start or Continue; supervisors also see Assign. A department filter defaults to *my
  department* (all departments for people with none). A **Start a checklist** menu lists the
  department's on-demand templates. Managers (`view_property_analytics`) get a **Missed** tab —
  the last 7 days' missed instances with date, shift, department and assignee.
- **`/app/checklists/:id` — `ChecklistRunPage`.** Items via PM's `ChecklistItem`, a handover
  comment box, and Complete — disabled with the missing items listed, like PM's run page.
  Read-only when complete or missed. Every mutation's error shows inline.
- **Admin → Checklist templates.** Name, department, schedule (on-demand, or weekly with a shift
  and seven day checkboxes), items. The items editor is extracted from `PmTemplatesAdmin` into a
  shared `ItemListEditor` used by both; PM's admin behaves identically, its tests the guard.

Schemas are added to `test_schema_export.py`'s tuple; tables to `EXPECTED_TABLES`; `schema.json`
and `types.generated.ts` regenerated.

---

## 5. Sample data

Seeded through the domain for HVH only:

- Templates: **Front Desk AM Opening** (daily; drawer counted — number, $, 150–250; lobby walk;
  key encoder test), **Front Desk Overnight Night Audit** (daily; checkboxes + audit-report photo),
  **Engineering AM Rounds** (daily; pool free chlorine ppm 1.0–3.0, pool pH 7.2–7.8, boiler supply
  °F 140–180), **Housekeeping PM Linen Par** (Mon/Wed/Fri; linen counts), **Engineering Power
  Outage Response** (on-demand).
- Today's instances generated by the real `checklist.tick`; one in progress, claimed by an
  engineer.
- Yesterday's instances created through the same domain generator and completed through the
  domain, one recording pool pH 8.1 so the real out-of-range path raises its work order and alert;
  the tick marks one yesterday instance **missed** with partial answers so the Missed tab is not
  empty. Completion timestamps are then moved into their shift windows so history reads plausibly.
- `SeedSummary` gains `checklist_templates` and `checklist_instances`; `test_seed` asserts them;
  `server/data/app.db` is regenerated. Production is never seeded — staff create templates in
  Admin.

---

## 6. Migration and portability

`0009_shift_checklists`: five new tables only, in 0008's style — `_enum()` helpers, CHECK
constraints, indexes via `batch_alter_table`. No backfill; no existing table altered. The partial
uniqueness is achieved with the nullable `slot` column, not a partial index. `weekdays` is an
Integer bitmask — no JSON. `downgrade()` drops the five tables children-first, a true reversal.
`checklist.tick` joins `RECURRING` (300 s); boot registers it in production.

Before merge, per `CLAUDE.md`: upgrade / downgrade / re-upgrade on Postgres 18, and the whole app
seeded and exercised on Postgres 18. After the push, the deploy log must show
`alembic upgrade head` before gunicorn and `/api/health` must be ok.

---

## 7. Testing

TDD per plan task. Tests run on SQLite; Postgres is covered by §6's verification.

- **Typed-item extraction first**, with PM's entire existing suite as the guard.
- **Shift windows:** am / pm / overnight on default and custom boundaries; overnight wrapping into
  the next date; `current_shift` at 02:00 returning the previous day's overnight; a DST-change
  day; two properties in different zones.
- **Tick:** generates only on the template's weekdays; idempotent (second run creates and emits
  nothing); never generates for on-demand or inactive templates; marks missed exactly when the
  window ends and not a minute before; leaves complete instances alone.
- **Lifecycle:** a status × action matrix like housekeeping's (every unlisted pair is a 409);
  claim-on-start; department-membership 403 with the supervisor exemption; a required item blocks
  Complete; out-of-range creates one work order per reading and alerts supervisors; on-demand runs
  twice in a day and takes the current shift; the template CHECK rejects a weekly template with no
  weekdays.
- **Snapshotting:** editing a template never alters a started instance.
- **API and isolation:** capability matrix pinned; cross-property 404s; `test_isolation` counting
  the new routes.
- **Web:** `ChecklistsPage` (grouping, department filter, Start, Assign only for supervisors,
  Missed only for managers); `ChecklistRunPage` (Complete disabled until required items answered,
  read-only when missed, inline errors); the shared `ItemListEditor` with PM's admin tests still
  passing; nav, capabilities, realtime invalidation.
