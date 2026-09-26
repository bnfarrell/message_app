# Housekeeping — design

**Status: DRAFT IN PROGRESS.** Sections 1–4 below were presented and approved section by section
in the brainstorming session of 2026-09-25. Sections 5–8 (realtime, sample data, migration and
portability, testing) are still to be drafted, and the spec has not yet had its self-review or
user review pass. Do not start implementation from this file until it is complete and approved —
resume by drafting §5 onward, then re-reading the whole thing.

---

## 1. What this is and why

`docs/design.md` §6.5 — the housekeeping module, the first Phase 2 "Operations" feature after
preventative maintenance and the hotel log. The daily loop a hotel actually runs on: rooms become
dirty, a supervisor assigns them, housekeepers clean them, a supervisor inspects them.

### 1.1 Scope

**In (the core loop):**

- Room board: floor by floor, colour coded by housekeeping status, live.
- Supervisor assigns today's dirty rooms to housekeepers; reassign, unassign, reorder.
- Housekeeper phone view: an ordered list of their rooms, Start → Ready for inspection, photos.
- Supervisor inspection: pass, or fail back to the housekeeper with a required note.
- Front desk read plus two actions: mark a room dirty, flag it rush.
- Real-time updates and notifications across all four.

**Out (deferred, the data model does not block them):** credits-based auto-assignment by
workload, deep-clean checklists pushed into an assignment, bidirectional PMS room-status sync,
housekeeping analytics (rooms per hour, inspection pass rate) beyond the board's summary counts,
offline queueing for stairwells (`docs/design.md` §9.3 — a PWA-wide concern, not this feature's).

### 1.2 The one structural decision

`docs/design.md` §5.4 specifies a standalone `room` table. That document was written before
preventative maintenance shipped its own room inventory, and following it literally now would
give the property **two** room lists to maintain — admin importing room 204 twice, as two
unrelated rows that drift apart.

So: housekeeping builds on `maintainable_unit` (`kind = guest_room`), the inventory PM already
imports, CSV-imports and exposes in Admin. `maintainable_unit.code` is the PMS room number
(`204`, `1012`), which is what occupancy joins on. The PMS-sync hook PM left on the unit
(`source`, `external_id`) then serves both features when a real PMS integration lands.

Two alternatives were considered and rejected: a separate `room` table (spec-literal, but creates
the drift described above), and modelling each clean as a `work_order` of type `housekeeping`
(real reuse, but a 60-room hotel generates 60+ work orders every day, flooding the board and
analytics, and the work-order status vocabulary has no "ready for inspection" or "inspected").

---

## 2. Data model

Three new tables plus a photo table, one migration (`0008_housekeeping`). Engine-portable SQL
only; every enum through `enum_type()` per `CLAUDE.md`.

### 2.1 `room`

The housekeeping face of a guest room. One row per `maintainable_unit` with `kind = guest_room`.

| column | type | notes |
|---|---|---|
| `property_id` | FK property, indexed | |
| `unit_id` | FK `maintainable_unit`, **unique** | number, floor and room type all live on the unit; nothing is duplicated |
| `hk_status` | `HkStatus` | `clean` · `dirty` · `in_progress` · `inspected` · `out_of_order` · `out_of_service` |
| `service_type` | `HkServiceType`, nullable | `departure` · `stayover` · `touch_up`; set when the room becomes dirty, so the board can say *why* it needs cleaning after the guest has gone |
| `rush` | Boolean, default false | front desk's "this one first"; cleared on inspection |
| `last_cleaned_at`, `last_inspected_at`, `status_changed_at` | `UTCDateTime` | |
| `notes` | Text, nullable | |

`clean` means the housekeeper finished and it is awaiting inspection; `inspected` means a
supervisor passed it. Rows are created by the migration for every active guest-room unit, and by
the domain whenever a guest-room unit appears without one — so a later CSV import just works.

**Occupancy is not stored.** Vacant / arrival / departure / stayover is derived per request from
`stay` rows matched on `unit.code == stay.room_number` against the property-local date. That is
what the PMS says; a stored copy could only drift from it.

### 2.2 `housekeeping_assignment`

One housekeeper's task on one room for one day.

| column | type | notes |
|---|---|---|
| `property_id`, `room_id`, `housekeeper_user_id` | FKs, indexed | |
| `shift_date` | `Date` | property-local, via the `pm_cycles` local-date helpers |
| `sequence` | Integer | order within that housekeeper's list; supervisor can reorder |
| `type` | `HkServiceType` | copied from the room at assignment time |
| `status` | `HkAssignmentStatus` | `assigned` → `in_progress` → `done` → `passed` |
| `started_at`, `completed_at` | `UTCDateTime`, nullable | |
| `inspected_by_user_id`, `inspected_at`, `inspection_note` | nullable | |
| `fail_count` | Integer, default 0 | |

A **failed inspection returns the row to `assigned`** with the note and `fail_count + 1`, rather
than creating a second row. One row therefore tells the whole story of that room's day, and
inspection-pass-rate analytics later are a count of fail events rather than a join.

At most one non-`passed` assignment per room at a time, enforced in the domain layer — a partial
unique index is not portable enough to lean on across SQLite and Postgres.

### 2.3 `room_event`

The audit trail, same shape as `work_order_event`: `room_id`, `assignment_id` (nullable),
`property_id`, `user_id`, `type`, `from_value`, `to_value`, `comment`.

Event types: `status_changed`, `assigned`, `reassigned`, `unassigned`, `started`, `completed`,
`inspection_passed`, `inspection_failed`, `marked_dirty`, `rush_set`, `rush_cleared`.

Feeds the room detail drawer's history panel, and the deferred analytics.

### 2.4 `housekeeping_photo`

Housekeeper photos attached to an assignment. Bytes in the table with `data` deferred, exactly as
`work_order_photo` and `pm_run_photo` do it, and for the same reason: the deployment target's
filesystem is ephemeral.

### 2.5 New enums

`HkStatus`, `HkServiceType`, `HkAssignmentStatus`, `RoomEventType` — in `app/schemas/enums.py`.

---

## 3. Behaviour

### 3.1 `housekeeping.tick`

A recurring job like `pm.tick`, every 5 minutes, and deliberately **stateless** — it does not
record "I rolled today", it asks each room whether it ought to be dirty and is not:

- Room is **occupied by a stayover**, `hk_status` is `clean`/`inspected`, and `status_changed_at`
  is before today's local midnight → `dirty` (`stayover`).
- Room's guest **departs today** (or has checked out and the room was not dirtied yet), same
  status and before-midnight test → `dirty` (`departure`).
- `dirty`, `in_progress`, `out_of_order`, `out_of_service`: untouched. A room cleaned today stays
  clean.

The before-midnight test is what makes it idempotent: running it fifty times is the same as
running it once. The tick also ensures a `room` row exists for every active guest-room unit.

### 3.2 PMS checkout

`pms/handle_event.py` on `stay.checked_out` additionally marks the room `dirty` (`departure`)
immediately, so a 9am checkout appears on the board at 9am rather than at the next tick.
`stay.checked_in` and `stay.room_changed` do not touch status — occupancy is derived.

### 3.3 Transitions

An explicit table in the domain layer. Anything not listed is a 409:

| from → to | who | side effects |
|---|---|---|
| any non-OOO → `dirty` | front desk, HK staff, supervisor+ | `service_type` = `touch_up` if occupied, else `departure`; optional note |
| `dirty` → `in_progress` | the assigned housekeeper, or supervisor+ | assignment → `in_progress`, `started_at` |
| `in_progress` → `clean` | same | assignment → `done`, `completed_at`, `last_cleaned_at`; supervisors notified |
| `clean` → `inspected` | supervisor+ | assignment → `passed`, `rush` cleared, `last_inspected_at` |
| `clean` → `dirty` (fail) | supervisor+, **note required** | assignment → `assigned`, `fail_count + 1`; housekeeper notified with the note |
| `dirty` → `in_progress` with no assignment | supervisor+ only | creates the assignment on the fly for the acting user — supervisors clean rooms too |
| ↔ `out_of_order` / `out_of_service` | supervisor+ | any open assignment is removed; the tick ignores the room until cleared |

### 3.4 Assignment

A supervisor assigns one or many rooms to a housekeeper for today; `sequence` appends. Reassign
moves the row and records the event; unassign deletes it unless it has started (409). Reorder is
a single call taking the ordered assignment ids.

Assigning notifies the housekeeper **once per action** ("4 rooms assigned"), not once per room.

### 3.5 Rush

Front desk sets `rush` on a dirty room → HK supervisors notified; the room sorts to the top of
the board and of its housekeeper's list. Cleared automatically on inspection.

---

## 4. API, capabilities and screens

### 4.1 Blueprint

`app/api/housekeeping.py`, `url_prefix="/api/p/<property_id>/housekeeping"`, following `pm.py`'s
shape. Every route `@require_auth` + `@require_property` + a capability.

| route | capability | purpose |
|---|---|---|
| `GET /board` | `view_housekeeping` | every active room with unit info, `hkStatus`, `serviceType`, `rush`, derived occupancy, guest name and departure when occupied, today's assignment; plus summary counts in the same payload |
| `GET /my-rooms` | `perform_housekeeping` | the caller's assignments for today, in sequence, rush first |
| `GET /rooms/<id>` | `view_housekeeping` | board row + today's assignment + last 30 `room_event`s + photos |
| `POST /rooms/<id>/mark-dirty` | `mark_room_dirty` | `{ note? }` |
| `POST /rooms/<id>/rush`, `DELETE /rooms/<id>/rush` | `mark_room_dirty` | |
| `POST /rooms/<id>/status` | `manage_housekeeping` | `{ status: out_of_order \| out_of_service \| dirty }` |
| `POST /assignments` | `manage_housekeeping` | `{ roomIds[], housekeeperUserId }`; creates or reassigns, one notification |
| `DELETE /assignments/<id>` | `manage_housekeeping` | 409 if started |
| `POST /assignments/reorder` | `manage_housekeeping` | `{ housekeeperUserId, assignmentIds[] }` |
| `POST /assignments/<id>/start`, `/complete` | `perform_housekeeping` | own assignment, or supervisor+ on any |
| `POST /assignments/<id>/photos`, `GET …/photos/<photoId>` | `perform_housekeeping` / `view_housekeeping` | multipart; same size cap and bytes-in-DB storage as work orders |
| `POST /assignments/<id>/inspect` | `inspect_housekeeping` | `{ result: pass \| fail, note? }`; note required on fail, else 422 |
| `POST /rooms/<id>/self-assign-start` | `manage_housekeeping` | supervisor starts an unassigned room themselves (§3.3) |

### 4.2 Capabilities

Added to `app/auth/permissions.py` and mirrored in `web/src/auth/capabilities.ts` **in the same
commit** (CLAUDE.md). All include `admin`, so `tests/test_isolation.py` stays green.

| capability | roles |
|---|---|
| `view_housekeeping` | all of `STAFF` — front desk sees the board |
| `mark_room_dirty` | agent, dept_staff, supervisor, manager, admin |
| `perform_housekeeping` | dept_staff, supervisor, manager, admin |
| `manage_housekeeping` | supervisor, manager, admin |
| `inspect_housekeeping` | supervisor, manager, admin |

Role alone is not sufficient in one place: an *engineering* `dept_staff` must not receive
housekeeping assignments. `POST /assignments` therefore also requires the target user to belong
to a `housekeeping`-type department (422 otherwise). `GET /my-rooms` is naturally empty for
anyone unassigned. Supervisors of **any** department may assign — the HK supervisor is a
`supervisor` in the housekeeping department, but a duty manager covering the shift must not be
blocked.

Schemas live in `app/schemas/housekeeping.py` (`CamelModel`), are added to the tuple in
`test_schema_export.py::test_export_contains_the_public_models`, and `schema.json` /
`types.generated.ts` are regenerated. The new tables are added to `EXPECTED_TABLES` in
`test_models.py`.

### 4.3 Screens

A new `Housekeeping` nav group in `web/src/components/navModel.ts`, above Maintenance:

- **Rooms** → `/app/housekeeping`, needs `view_housekeeping`
- **My Rooms** → `/app/my-rooms`, needs `perform_housekeeping`
- **Room Inspection** → `/app/housekeeping/inspection`, needs `inspect_housekeeping` —
  deliberately outside the board's `match` prefix, for the same reason PM Inspection is a sibling
  of `/app/pm`: two lit rail entries reads as a bug.

**`/app/housekeeping` — `RoomBoardPage`** (supervisor and front desk). Summary strip across the
top (dirty · in progress · awaiting inspection · inspected · OOO), then floor-by-floor sections of
room tiles. A tile carries number, status colour, occupancy glyph, assignee initials and the rush
flag. Filters: floor, status, assignee, unassigned-only. Selecting tiles reveals an action bar —
Assign to…, Mark dirty, Rush — so assigning twelve rooms is one action. Clicking a tile opens a
detail drawer: status, guest and departure, today's assignment, photos, event history. Front desk
sees the same board with only Mark dirty and Rush enabled.

**`/app/my-rooms` — `MyRoomsPage`** (housekeeper, phone-first). An ordered list of today's rooms,
rush pinned to the top; each row is room number, type, departure/stayover and one big button
showing the next action — Start, then Mark ready. Tapping a room opens it full screen: the same
big button, a photo capture control, and the supervisor's note if it was failed back. A progress
line at the top ("3 of 11 done"). Nothing else on the screen — `docs/design.md` §6.5 is more
prescriptive about this view than any other.

**`/app/housekeeping/inspection` — `RoomInspectionPage`** (supervisor). The queue of rooms
awaiting inspection, oldest first, with who cleaned each and their photos. Pass, or Fail which
opens a required note box. Mirrors `InspectionPage` so supervisors meet one pattern twice.

**Landing screen.** `docs/design.md` §134 calls "the housekeeper lands in their room list" the
single decision that does most for adoption. `landingPath` currently takes only `role`, which
cannot distinguish a housekeeping `dept_staff` from an engineering one. So `MembershipOut` gains
a `departmentType` field (already joinable) and `dept_staff` in a housekeeping department lands
on `/app/my-rooms`. Every other role is unchanged.

Query hooks in `web/src/api/hooks/housekeeping.ts`, keyed and invalidated on the `room.updated`
realtime event exactly as the PM hooks are.

---

## 5–8. Still to draft

- **§5 Realtime** — one `room.updated {id}` event broadcast on every change, following PM's
  invalidate-on-event pattern. Needs writing out properly, including which of the three screens
  refetch on it.
- **§6 Sample data** — seeding rooms, a day's assignments across the two seeded housekeepers and
  the HK supervisor, and rooms in each status so the board is not empty on a fresh database.
- **§7 Migration and portability** — `0008_housekeeping`, backfilling a `room` row per active
  guest-room unit, and the `downgrade()` that truly reverses it. Verified against Postgres 18 per
  CLAUDE.md before merge.
- **§8 Testing** — the transition table, tick idempotency, the assignment/inspection loop,
  cross-property isolation, and the capability matrix.
