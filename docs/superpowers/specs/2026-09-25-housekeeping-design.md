# Housekeeping — design

**Status: AWAITING WRITTEN-SPEC REVIEW.** All eight sections were presented and approved section
by section in the brainstorming sessions of 2026-09-25, and the spec has had its self-review.
Next: the user reviews this file; on approval, an implementation plan is written from it. Do not
start implementation from this file directly.

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

At most one non-`passed` assignment per room **per `shift_date`**, enforced in the domain layer —
a partial unique index is not portable enough to lean on across SQLite and Postgres. Scoping it to
the day matters: a room left `clean` overnight with its `done` assignment never inspected is
re-dirtied by the tick (§3.1), and yesterday's unfinished row must stay as history rather than
block today's assignment. "Today's assignment" everywhere means `shift_date` = property-local
today.

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
| `inspected` → `dirty` (mark dirty) | front desk, HK staff, supervisor+ | `service_type` = `touch_up` if occupied, else `departure`; optional note. From `dirty` / `in_progress` it is a 409 (already on its way); from `clean` it is a 409 telling the user a supervisor must fail the inspection, so mark-dirty can never bypass the fail path and its note |
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
| `GET /board` | `view_housekeeping` | every active room with unit info, `hkStatus`, `serviceType`, `rush`, derived occupancy, guest name and departure when occupied, today's assignment; plus summary counts and the housekeeping roster (for the Assign picker) in the same payload |
| `GET /my-rooms` | `perform_housekeeping` | the caller's assignments for today, in sequence, rush first |
| `GET /inspections` | `inspect_housekeeping` | rooms awaiting inspection, oldest first, with who cleaned each and their photos |
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
- **Room Inspection** → `/app/room-inspection`, needs `inspect_housekeeping` — a sibling of
  `/app/housekeeping`, not a child, so it stays outside the board's prefix match, for the same
  reason PM Inspection is `/app/inspection`: two lit rail entries reads as a bug.

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

**`/app/room-inspection` — `RoomInspectionPage`** (supervisor). The queue of rooms
awaiting inspection, oldest first, with who cleaned each and their photos. Pass, or Fail which
opens a required note box. Mirrors `InspectionPage` so supervisors meet one pattern twice.

**Landing screen.** `docs/design.md` §134 calls "the housekeeper lands in their room list" the
single decision that does most for adoption. `landingPath` currently takes only `role`, which
cannot distinguish a housekeeping `dept_staff` from an engineering one. So `MembershipOut` gains
a `departmentType` field (already joinable) and `dept_staff` in a housekeeping department lands
on `/app/my-rooms`. Every other role is unchanged.

Query hooks in `web/src/api/hooks/housekeeping.ts`, keyed and invalidated on the
`housekeeping.rooms.changed` realtime event (§5) exactly as the PM hooks are.

---

## 5. Realtime

**One event type:** `housekeeping.rooms.changed`, payload `{ ids: [roomId, …] }` — named in the
style of `pm.run.changed`. The payload is always a list, so a bulk action (assigning twelve rooms,
the tick dirtying forty after midnight, a reorder) sends **one** event, not N. It carries ids only,
no guest data, so it goes property-wide like every other operational event.

**One emission point.** A single domain helper calls `queue_event`, and every mutation in §3 goes
through it — transitions, assign, reassign, unassign, reorder, rush, inspect, photo upload, the
tick, and the PMS checkout hook — so no code path can change a room silently. The tick emits only
when it actually changed a row; a no-op tick is silent. Delivery is after commit, as for every
event (`app/realtime/broadcast.py`).

**What refetches** — a new case in `web/src/api/ws.ts`:

| query key | why |
|---|---|
| `hkBoardAll` | tiles, summary counts, assignee initials |
| `hkMyRoomsAll` | a housekeeper's list changes when assigned, reordered, rushed or failed back |
| `hkInspectionsAll` | a room reaching `clean` joins the queue; passing removes it |
| `hkRoom(id)` per id | an open detail drawer stays current |

Every screen refetches on every event, with no per-user filtering — at one property's volume that
is a few small GETs per change, the trade PM already makes, and filtering client-side would
duplicate the server's "is this mine" logic in the browser.

**Notifications need nothing new.** Assigned, rush, ready-for-inspection and failed-back all go
through `notifications.notify_users`, which already emits a per-user `notification.created`, so
the bell and toast work unchanged. `notification.type` is a free string; no constraint changes.

---

## 6. Sample data

**The seed goes through the domain, never around it.** It stages a plausible "last night" and then
runs the real code — `housekeeping.tick`, then domain calls made as the seeded users — so seeding
doubles as an end-to-end smoke test: a broken transition rule fails the seed loudly instead of
seeding a state the app could never produce.

1. **Last night.** A `room` row per HVH guest-room unit (120, floors 1–6 × 01–20), created by the
   same ensure-rooms function the tick uses. Every room starts `inspected` with
   `status_changed_at` = yesterday 18:00 property-local.
2. **This morning.** One `housekeeping.tick(now)`. The real rules dirty the stayovers
   (`stayover`) and the ten departures-today (`departure`); vacant rooms stay `inspected`. No
   hand-picked dirty list.
3. **Mid-shift**, scripted and deterministic under the seeder's existing `rng(42)`. Grace (HK
   supervisor) assigns 14 rooms each to Hana and Rosa. For each housekeeper:
   - 4 **passed** — started, completed, inspected by Grace; one carries a photo (the seeder's
     existing 1×1 PNG constant);
   - 2 **done**, awaiting inspection, so the inspection queue is not empty;
   - 1 **in progress**;
   - 1 **failed back once** — `fail_count` 1, note "Hair in the bathroom sink.";
   - 6 **assigned**, not started.

   Then: Marcus (front desk) sets **rush** on one of Rosa's assigned departures; 2 rooms go
   **out of order** ("AC unit leaking, WO open") and 1 **out of service**. The remaining dirty
   rooms stay **unassigned** — realistic for two seeded housekeepers in a 120-room hotel, and it
   gives the unassigned-only filter something to show.

LSI gets no housekeeping data beyond what ensure-rooms creates for any guest-room units it has.

`SeedSummary` gains `rooms` and `hk_assignments`; `test_seed_matches_spec_counts` asserts them.
`server/data/app.db` is regenerated and committed — a genuine seed change (CLAUDE.md).

**Production is never seeded.** Its rows come from the migration backfill (§7) and the tick; its
board starts with every room `inspected`.

**Known consequence, accepted:** seeded assignments belong to the day the seed ran. On later days
the tick dirties rooms normally and nothing is assigned until someone assigns it — the same way
PM's seeded runs age.

---

## 7. Migration and portability

**`0008_housekeeping`** — revision `0008`, down-revision `0007`, in 0007's style: the same
`_enum()` / `_timestamps()` helpers, `native_enum=False` with CHECK constraints, indexes via
`batch_alter_table`. It only adds tables; no existing table or CHECK constraint changes (the
class of migration that needed care in 0004). The recurring job is an entry in
`app/queue/jobs.py:RECURRING` (`"housekeeping.tick": 300`), not schema.

**Tables, in FK order:** `room` → `housekeeping_assignment` → `room_event` →
`housekeeping_photo`. `room.unit_id` unique. Indexes: `property_id` on all four;
`(property_id, hk_status)` on `room`; `(property_id, shift_date, housekeeper_user_id)` on
assignments; `(room_id, created_at)` on events for the history panel. No partial indexes (§2.2).

**Backfill in Python, not SQL.** Select active `guest_room` units through a lightweight
`sa.table()`, generate ids with `uuid4()` in Python, insert with `op.bulk_insert`. No
`gen_random_uuid()` (Postgres-only) and no `INSERT … SELECT` id tricks. Timestamps written as
naive UTC — `UTCDateTime`'s storage form.

**Backfilled rooms start `inspected`, with `status_changed_at` = migration time.** Not `clean`:
that means awaiting inspection (§2.1) and would put every production room in the inspection
queue. The before-midnight rule (§3.1) then means a mid-shift deploy never floods the board — the
first dirty wave is the next local midnight. A supervisor can mark rooms dirty sooner.

**Staying in step afterwards.** The migration and the tick's ensure-rooms share one rule: a row
per active guest-room unit. A unit added later gets its row within five minutes. Units are only
ever deactivated, never deleted, so a deactivated unit keeps its row and history but leaves the
board (which filters on `unit.active` and `kind`); reactivating it brings the same row back.

**`downgrade()`** drops the four tables, children first. That truly reverses: the backfill wrote
only into tables being dropped, and nothing pre-existing was altered.

**Verification before merge** (CLAUDE.md), against a `postgres:18` container:

1. `upgrade head` from a database at `0007` **that has units in it** — an empty one hides a
   backfill bug;
2. backfilled row count equals active guest-room unit count;
3. `downgrade 0007`, then `upgrade head` again, counts unchanged;
4. `dev_start.py` on Postgres end to end, so the seed (§6) runs the tick and domain — the
   timezone-shaped code — on the real engine.

**Deploy check:** the Railway log shows `==> alembic upgrade head` before gunicorn, `/api/health`
is ok, and the board's room count equals production's guest-room count.

---

## 8. Testing

TDD per plan task; these are the tests each task writes first. All run on SQLite in CI; Postgres
is covered by §7's verification, per CLAUDE.md's deliberate split. Tests freeze the clock at
2026-09-10 12:00 UTC (08:00 at HVH, New York; LSI is Chicago).

### 8.1 Server

- **`test_hk_models.py`** — the four tables in `EXPECTED_TABLES` (`test_models.py`); `unit_id`
  unique; enums round-trip through `enum_type()`.
- **`test_hk_transitions.py`** — the heart. §3.3 as a **parametrised matrix** of (from status,
  action, role, assigned or not) → allowed plus side effects, or 409 / 403. Every combination not
  in the table is asserted 409, so a new status cannot silently gain a transition. Fail without a
  note → 422; fail returns the *same* row to `assigned` with `fail_count + 1`; rush cleared on
  pass; OOO/OOS removes the open assignment; supervisor self-assign-start creates the assignment.
- **`test_hk_tick.py`** — stayover and departure dirtying; **idempotency** (a second run changes
  nothing and queues no event); a room cleaned at 07:00 local today is not re-dirtied; the
  midnight boundary in **property-local** time, including a case where UTC and local disagree on
  the date, and LSI against HVH to prove each property uses its own midnight; one case across the
  2026-11-01 DST change; `dirty` / `in_progress` / OOO / OOS untouched; ensure-rooms creates a row
  for a new guest-room unit and restores a reactivated one.
- **`test_hk_assignments.py`** — bulk assign produces exactly one notification; reassign moves the
  row and records the event; unassign → 409 once started; reorder rejects ids not belonging to
  that housekeeper (422); engineering `dept_staff` as target → 422; a manager from another
  department can assign; one open assignment per room per shift date.
- **`test_hk_api.py`** — board occupancy derived from `stay`, including a departs-today room;
  summary counts agree with the tiles; `my-rooms` is rush first then sequence and only the
  caller's; front desk can mark dirty and rush but gets 403 on assign and inspect; photo upload
  size cap and bytes-in-DB, reusing the work-order photo helpers; PMS `stay.checked_out` dirties
  the room immediately.
- **`test_hk_permissions.py`** — §4.2 pinned in the style of `test_pm_permissions.py`, including
  admin on every capability.
- **Realtime** — each mutation queues exactly one `housekeeping.rooms.changed` with the right
  `ids`; a bulk assign queues one, not N.
- **`test_isolation.py`** — no edit needed; it enumerates routes itself. The plan still runs it
  once to see the new routes counted.
- **`test_schema_export.py`, `test_seed.py`** — new models in the tuple; §6's counts, plus "the
  seed produced every board status".

### 8.2 Web

- **`capabilities.test.ts`** — the mirrored capabilities; `landingPath` sends housekeeping
  `dept_staff` to `/app/my-rooms` and leaves engineering `dept_staff` unchanged.
- **`navModel.test.ts`** — the Housekeeping group; Room Inspection does not light Rooms.
- **`ws.test.tsx`** — the event invalidates the four keys in §5.
- **`features/housekeeping/*.test.tsx`** — RoomBoard (floor grouping, filters, multi-select →
  assign, front desk sees only Mark dirty and Rush); MyRooms (the button walks Start → Mark ready,
  rush pinned, failed-back note shown); RoomInspection (Fail requires a note).

### 8.3 Definition of done

`pytest`, `ruff`, `npm test`, `npm run lint`, `npm run build` all clean; generated types fresh;
§7's Postgres verification run; after the push, the Railway deploy log shows the migration line
and `/api/health` is ok.
