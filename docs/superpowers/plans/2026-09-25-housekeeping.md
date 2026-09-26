# Housekeeping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the housekeeping core loop — live room board, supervisor assignment, housekeeper
Start → Ready on a phone, supervisor inspection — on top of the existing guest-room inventory.

**Architecture:** Four new tables (`room`, `housekeeping_assignment`, `room_event`,
`housekeeping_photo`) keyed to `maintainable_unit` (kind `guest_room`), one migration `0008`
with a Python-side backfill. Domain logic is split by responsibility into `hk_rooms` (rows,
occupancy, audit, the single realtime emission point), `hk_assignments`, `hk_transitions`,
`hk_photos`, `hk_tick` and `hk_views` (read models). One blueprint at
`/api/p/<property_id>/housekeeping`, three React screens, one realtime event.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · pytest; Vite +
React + TypeScript + TanStack Query + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-25-housekeeping-design.md` — read it before starting
any task. This plan argues from it; where the plan is more precise than the spec, the
"Spec clarifications" section below says so.

## Global Constraints

- Python by explicit path only: `cd server && ../.venv/Scripts/python.exe -m pytest -q`. Bare
  `python` is a silent Windows Store stub.
- Lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` — line length 100.
- Frontend: `cd web && npm test && npm run lint && npm run build` — all three clean.
- Engine-portable SQL only. No `json_each`, no SQLite-only functions, no `gen_random_uuid()`, no
  partial indexes. Pin NULL ordering explicitly (`.nulls_last()`) — SQLite and PostgreSQL
  disagree on it.
- Every enum column through `enum_type()` in `app/models/core.py`; in migrations through the
  local `_enum()` helper (`native_enum=False`, `create_constraint=True`, `length=32`).
- Times come from `app.clock.now()` (aware UTC). `UTCDateTime` rejects naive input.
- Property-local dates only through `pm_cycles.local_today(prop, at=None)` and
  `pm_cycles.local_day_start_utc(prop, day)`. Never compare a UTC column with a UTC date.
- `ValidationFailed` is **HTTP 400 `VALIDATION_FAILED`** in this codebase. Wherever the spec
  says "422", raise `ValidationFailed`.
- API models subclass `CamelModel`. Every housekeeping wire model is prefixed `Hk` — the JSON
  schema is flat and PM already owns `InspectRequest` / `InspectionRowOut`.
- After any schema change: `cd server && ../.venv/Scripts/python.exe -m
  app.schemas.export_json_schema`, then `cd web && npm run gen:types`, then re-export the new
  names from `web/src/api/types.ts`. Never hand-edit `schema.json` / `types.generated.ts`.
- `server/app/auth/permissions.py` and `web/src/auth/capabilities.ts` change in the **same
  commit**. Every new capability includes `Role.admin` (`tests/test_isolation.py`).
- SQLite runs with `PRAGMA foreign_keys = 1`: deleting a row that another row references fails.
- Commit after every task. **Do not push** until Task 16 — pushing `main` deploys to production.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Spec clarifications (decided while planning)

1. **`GET /inspections` is added** (`inspect_housekeeping`). §4.3's Room Inspection screen and §5's
   `hkInspectionsAll` key need it; §4.1's route table omitted it.
2. **The board payload carries `housekeepers`** (id, name, assigned/done counts) — the source for
   the "Assign to…" picker. No separate roster endpoint.
3. **Removing an assignment** (unassign, or a room going OOO/OOS) nulls `room_event.assignment_id`
   on its events and deletes its photos before deleting the row — FKs are enforced. History
   survives on `room_id`.
4. **Occupancy precedence:** checked-in beats reserved-arriving-today. A checked-in stay whose
   `departure_date <= today` is a `departure` (covers overdue). A checkout today is tracked
   separately (`checked_out_at`) so the tick can dirty a room whose checkout the PMS hook missed.
5. **Displayed assignment for a room:** today's open one; else, if the room is `clean`, its latest
   `done` assignment from any day (a vacant room cleaned late yesterday is still awaiting
   inspection); else today's latest `passed` one. A stale `done` row never shows on a dirty room.
6. **Rush** may be set only on a `dirty` or `in_progress` room (409 otherwise); setting it twice or
   clearing an unset rush is a no-op, not an error.
7. **Reassigning** moves an `assigned` or `in_progress` assignment; a `done` one (awaiting
   inspection) is a 409.
8. **"HK supervisors"** (who hear about rush and ready-for-inspection) = active members whose role
   is `supervisor` or `manager` **and** whose department type is `housekeeping`.
9. **`landingPath` takes the membership**, not the role: `landingPath({ role, departmentType })`.
10. **Room Inspection lives at `/app/room-inspection`**, not `/app/housekeeping/inspection`. The
    spec's stated intent is that the entry sits *outside* the board's match prefix so two rail
    entries never light together — but `/app/housekeeping/inspection` is inside it
    (`isNavItemActive` is prefix-based). A sibling path honours the intent, exactly as PM's
    `/app/inspection` does.

## Review Focus

1. **A guest-room unit with no floor** — the board must group it under "No floor" and sort it
   last on both engines, not crash or reorder differently on Postgres. → Task 3
   (`test_active_rooms_puts_floorless_units_last`), Task 13 (board test).
2. **Double-submitted Assign** (a double click, or two supervisors at once assigning the same room
   to the same person) — must leave exactly one open assignment and send one notification, not
   two. → Task 5 (`test_assigning_again_to_the_same_housekeeper_is_a_no_op`).
3. **A disabled housekeeper** — must not be assignable (400), while their existing rows still
   render with their name. → Task 5 (`test_cannot_assign_to_a_disabled_housekeeper`).
4. **A whitespace-only fail note** — must count as missing (400), never pass as a note. → Task 6
   (`test_fail_requires_a_non_blank_note`).
5. **A PMS checkout for a room number with no unit** (typo, or a room PM never imported) — must be
   a silent no-op for housekeeping and still process the stay. → Task 4
   (`test_checkout_for_an_unknown_room_number_is_ignored`).

## File map

**Server — create**
- `server/app/models/housekeeping.py` — the four ORM models.
- `server/alembic/versions/0008_housekeeping.py` — tables + backfill.
- `server/app/domain/hk_rooms.py` — room rows, occupancy, events, emission, shared helpers.
- `server/app/domain/hk_assignments.py` — assign / unassign / reorder.
- `server/app/domain/hk_transitions.py` — mark dirty, rush, OOO/OOS, start, complete, inspect,
  self-assign-start.
- `server/app/domain/hk_photos.py` — photo attach / fetch.
- `server/app/domain/hk_tick.py` — the stateless daily roll.
- `server/app/domain/hk_views.py` — board, my-rooms, room detail, inspection queue.
- `server/app/schemas/housekeeping.py` — wire models.
- `server/app/api/housekeeping.py` — the blueprint.
- `server/app/queue/handlers/housekeeping.py` — `housekeeping.tick` handler.
- Tests: `server/tests/hk_helpers.py`, `test_hk_models.py`, `test_hk_permissions.py`,
  `test_hk_rooms.py`, `test_hk_tick.py`, `test_hk_assignments.py`, `test_hk_transitions.py`,
  `test_hk_photos.py`, `test_hk_views.py`, `test_hk_api.py`.

**Server — modify**
- `server/app/schemas/enums.py` (5 enums), `server/app/models/__init__.py`,
  `server/app/auth/permissions.py`, `server/app/pms/handle_event.py`,
  `server/app/queue/jobs.py`, `server/app/queue/handlers/__init__.py`,
  `server/app/schemas/auth.py`, `server/app/api/auth.py`, `server/app/__init__.py`,
  `server/app/schemas/export_json_schema.py`, `server/seed/seed.py`,
  `server/tests/test_models.py`, `server/tests/test_schema_export.py`,
  `server/tests/test_seed.py`, `server/data/app.db` (regenerated).

**Web — create**
- `web/src/api/hooks/housekeeping.ts`
- `web/src/features/housekeeping/labels.ts`, `RoomBoardPage.tsx`, `RoomDrawer.tsx`,
  `MyRoomsPage.tsx`, `RoomInspectionPage.tsx` and a `.test.tsx` per page.

**Web — modify**
- `web/src/auth/capabilities.ts` (+test), `web/src/api/queryKeys.ts`, `web/src/api/ws.ts`
  (+test), `web/src/api/types.ts`, `web/src/components/navModel.ts` (+test),
  `web/src/components/NavIcon.tsx`, `web/src/routes.tsx`, `web/src/test/harness.tsx`, and the
  `landingPath` call sites: `components/AppShell.tsx`, `components/CommandPalette.tsx`,
  `features/login/LoginPage.tsx`.

---

### Task 1: Enums, models and migration `0008`

**Files:**
- Modify: `server/app/schemas/enums.py` (append)
- Create: `server/app/models/housekeeping.py`
- Modify: `server/app/models/__init__.py`
- Create: `server/alembic/versions/0008_housekeeping.py`
- Modify: `server/tests/test_models.py:14-23` (`EXPECTED_TABLES`)
- Test: `server/tests/test_hk_models.py`

**Interfaces:**
- Produces: enums `HkStatus`, `HkServiceType`, `HkAssignmentStatus`, `RoomEventType`,
  `HkOccupancy` in `app.schemas.enums`; models `Room`, `HousekeepingAssignment`, `RoomEvent`,
  `HousekeepingPhoto` exported from `app.models`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_models.py` — add the four tables to `EXPECTED_TABLES`:

```python
    "pm_cycle", "pm_run", "pm_run_answer", "pm_run_photo",
    "room", "housekeeping_assignment", "room_event", "housekeeping_photo",
}
```

`server/tests/test_hk_models.py`:

```python
"""Housekeeping schema (spec §2, §7)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError, StatementError

from alembic import command
from app.models import MaintainableUnit, Room
from app.schemas.enums import HkStatus, PmUnitKind

SERVER = Path(__file__).resolve().parent.parent
T = "2026-09-10 12:00:00"


def _alembic(url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _room_count(engine) -> int:
    with engine.connect() as c:
        return c.execute(sa.text("SELECT COUNT(*) FROM room")).scalar()


def test_0008_backfills_active_guest_rooms_and_downgrades_cleanly(tmp_path):
    """An empty database would hide a backfill bug (spec §7), so units exist before 0008."""
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "0007")
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO property (id, name, code, timezone, currency, settings, created_at, "
            "updated_at) VALUES ('p1', 'P', 'PPP', 'UTC', 'USD', '{}', :t, :t)"), {"t": T})
        for i, (kind, active) in enumerate([("guest_room", True), ("guest_room", True),
                                            ("guest_room", False), ("equipment", True)]):
            c.execute(sa.text(
                "INSERT INTO maintainable_unit (id, property_id, kind, code, name, active, "
                "source, created_at, updated_at) VALUES (:id, 'p1', :kind, :code, :code, "
                ":active, 'manual', :t, :t)"),
                {"id": f"u{i}", "kind": kind, "code": f"C{i}", "active": active, "t": T})

    command.upgrade(cfg, "head")
    assert _room_count(engine) == 2
    with engine.connect() as c:
        rows = c.execute(sa.text("SELECT unit_id, hk_status, rush FROM room")).all()
    assert {r.unit_id for r in rows} == {"u0", "u1"}
    assert {r.hk_status for r in rows} == {"inspected"}  # never `clean` (spec §7)
    assert not any(r.rush for r in rows)

    command.downgrade(cfg, "0007")
    assert "room" not in sa.inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert _room_count(engine) == 2
    engine.dispose()


def test_room_unit_id_is_unique(database, fx):
    from app.domain import hk_rooms  # arrives in Task 3; imported here so collection works now
    with pytest.raises(IntegrityError), database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204", floor=2)
        db.add(unit)
        db.flush()
        hk_rooms.ensure_rooms(db, fx.property_a.id)
        db.add(Room(property_id=fx.property_a.id, unit_id=unit.id))
        db.flush()


def test_hk_status_round_trips_and_rejects_unknown_values(database, fx):
    from app.domain import hk_rooms  # arrives in Task 3
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="205", name="Room 205", floor=2)
        db.add(unit)
        db.flush()
        (room,) = hk_rooms.ensure_rooms(db, fx.property_a.id)
        room.hk_status = HkStatus.out_of_service
        db.flush()
        db.expire(room)
        assert room.hk_status is HkStatus.out_of_service
    with pytest.raises(StatementError), database.session() as db:
        db.execute(sa.update(Room).values(hk_status="sparkling"))
```

> `hk_rooms.ensure_rooms` arrives in Task 3. Until then, the last two tests fail with an
> ImportError — that is expected. Task 1 is done when the migration test and
> `test_migration_creates_all_tables` pass; the other two go green in Task 3.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_models.py tests/test_models.py -q`
Expected: FAIL — `room` missing from the tables; `No such revision '0008'`-style errors or
`ImportError: cannot import name 'hk_rooms'`.

- [ ] **Step 3: Append the enums to `server/app/schemas/enums.py`**

```python
class HkStatus(StrEnum):
    """`clean` = the housekeeper finished and it awaits inspection; `inspected` = a supervisor
    passed it (spec §2.1)."""
    clean = "clean"
    dirty = "dirty"
    in_progress = "in_progress"
    inspected = "inspected"
    out_of_order = "out_of_order"
    out_of_service = "out_of_service"


class HkServiceType(StrEnum):
    departure = "departure"
    stayover = "stayover"
    touch_up = "touch_up"


class HkAssignmentStatus(StrEnum):
    assigned = "assigned"
    in_progress = "in_progress"
    done = "done"
    passed = "passed"


class RoomEventType(StrEnum):
    status_changed = "status_changed"
    assigned = "assigned"
    reassigned = "reassigned"
    unassigned = "unassigned"
    started = "started"
    completed = "completed"
    inspection_passed = "inspection_passed"
    inspection_failed = "inspection_failed"
    marked_dirty = "marked_dirty"
    rush_set = "rush_set"
    rush_cleared = "rush_cleared"


class HkOccupancy(StrEnum):
    """Derived per request from `stay`, never stored (spec §2.1)."""
    vacant = "vacant"
    arrival = "arrival"
    stayover = "stayover"
    departure = "departure"
```

- [ ] **Step 4: Create `server/app/models/housekeeping.py`**

```python
"""Housekeeping (spec §2).

Built on `maintainable_unit` (kind guest_room), not a second room list — spec §1.2. Number,
floor and room type live on the unit; `room` holds only the housekeeping state.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utcnow
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import HkAssignmentStatus, HkServiceType, HkStatus, RoomEventType


class Room(TimestampMixin, Base):
    """One row per guest-room unit. Occupancy is derived from `stay`, never stored."""

    __tablename__ = "room"
    __table_args__ = (
        UniqueConstraint("unit_id", name="uq_room_unit"),
        Index("ix_room_property_status", "property_id", "hk_status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("maintainable_unit.id"), nullable=False)
    hk_status: Mapped[HkStatus] = mapped_column(
        enum_type(HkStatus), default=HkStatus.inspected, nullable=False)
    service_type: Mapped[HkServiceType | None] = mapped_column(enum_type(HkServiceType))
    rush: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_cleaned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                                        nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class HousekeepingAssignment(TimestampMixin, Base):
    """One housekeeper's task on one room for one property-local day (spec §2.2). A failed
    inspection returns this same row to `assigned` rather than creating another."""

    __tablename__ = "housekeeping_assignment"
    __table_args__ = (
        Index("ix_hk_assignment_property_day_keeper",
              "property_id", "shift_date", "housekeeper_user_id"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"), nullable=False, index=True)
    housekeeper_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"),
                                                     nullable=False, index=True)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[HkServiceType] = mapped_column(enum_type(HkServiceType), nullable=False)
    status: Mapped[HkAssignmentStatus] = mapped_column(
        enum_type(HkAssignmentStatus), default=HkAssignmentStatus.assigned, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspection_note: Mapped[str | None] = mapped_column(Text)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class RoomEvent(TimestampMixin, Base):
    """The audit trail, shaped like work_order_event (spec §2.3)."""

    __tablename__ = "room_event"
    __table_args__ = (Index("ix_room_event_room_created", "room_id", "created_at"),)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"), nullable=False)
    assignment_id: Mapped[str | None] = mapped_column(ForeignKey("housekeeping_assignment.id"))
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    type: Mapped[RoomEventType] = mapped_column(enum_type(RoomEventType), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(40))
    to_value: Mapped[str | None] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(Text)


class HousekeepingPhoto(TimestampMixin, Base):
    """Bytes in the table, `data` deferred — same reason as work_order_photo: the deployment
    filesystem is ephemeral (spec §2.4)."""

    __tablename__ = "housekeeping_photo"
    assignment_id: Mapped[str] = mapped_column(ForeignKey("housekeeping_assignment.id"),
                                               nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
```

- [ ] **Step 5: Export the models from `server/app/models/__init__.py`**

Add after the `app.models.guests` import:

```python
from app.models.housekeeping import HousekeepingAssignment, HousekeepingPhoto, Room, RoomEvent
```

and add `"HousekeepingAssignment", "HousekeepingPhoto", "Room", "RoomEvent"` to `__all__`
(keep it alphabetical like the existing list).

- [ ] **Step 6: Create `server/alembic/versions/0008_housekeeping.py`**

```python
"""housekeeping: room, housekeeping_assignment, room_event, housekeeping_photo

Phase 2 §6.5 (docs/superpowers/specs/2026-09-25-housekeeping-design.md). Only adds tables; no
existing table or CHECK constraint changes. The backfill is Python-side so it is portable: no
gen_random_uuid(), no INSERT ... SELECT id tricks.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25

"""
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

HK_STATUS = ("clean", "dirty", "in_progress", "inspected", "out_of_order", "out_of_service")
SERVICE = ("departure", "stayover", "touch_up")
ASSIGNMENT = ("assigned", "in_progress", "done", "passed")
EVENT = ("status_changed", "assigned", "reassigned", "unassigned", "started", "completed",
         "inspection_passed", "inspection_failed", "marked_dirty", "rush_set", "rush_cleared")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "room",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("hk_status", _enum("ck_enum_hkstatus", *HK_STATUS), nullable=False),
        sa.Column("service_type", _enum("ck_enum_hkservicetype", *SERVICE), nullable=True),
        sa.Column("rush", sa.Boolean(), nullable=False),
        sa.Column("last_cleaned_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("last_inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("status_changed_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id", name="uq_room_unit"),
    )
    with op.batch_alter_table("room", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_property_id"), ["property_id"], unique=False)
        batch_op.create_index("ix_room_property_status", ["property_id", "hk_status"],
                              unique=False)

    op.create_table(
        "housekeeping_assignment",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("housekeeper_user_id", sa.String(length=36), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", _enum("ck_enum_hkservicetype", *SERVICE), nullable=False),
        sa.Column("status", _enum("ck_enum_hkassignmentstatus", *ASSIGNMENT), nullable=False),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("completed_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspection_note", sa.Text(), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(["housekeeper_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["inspected_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("housekeeping_assignment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_property_id"),
                              ["property_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_room_id"), ["room_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_housekeeper_user_id"),
                              ["housekeeper_user_id"], unique=False)
        batch_op.create_index("ix_hk_assignment_property_day_keeper",
                              ["property_id", "shift_date", "housekeeper_user_id"], unique=False)

    op.create_table(
        "room_event",
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=True),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("type", _enum("ck_enum_roomeventtype", *EVENT), nullable=False),
        sa.Column("from_value", sa.String(length=40), nullable=True),
        sa.Column("to_value", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(["assignment_id"], ["housekeeping_assignment.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("room_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_event_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index("ix_room_event_room_created", ["room_id", "created_at"],
                              unique=False)

    op.create_table(
        "housekeeping_photo",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["assignment_id"], ["housekeeping_assignment.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("housekeeping_photo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_housekeeping_photo_assignment_id"),
                              ["assignment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_photo_property_id"), ["property_id"],
                              unique=False)

    _backfill_rooms()


def _backfill_rooms() -> None:
    """A room per active guest-room unit, starting `inspected` as of now (spec §7): `clean`
    would put every room in the inspection queue, and the before-midnight rule then means a
    mid-shift deploy never floods the board."""
    unit = sa.table("maintainable_unit", sa.column("id", sa.String),
                    sa.column("property_id", sa.String), sa.column("kind", sa.String),
                    sa.column("active", sa.Boolean))
    rows = op.get_bind().execute(
        sa.select(unit.c.id, unit.c.property_id)
        .where(unit.c.kind == "guest_room", unit.c.active.is_(True))).all()
    if not rows:
        return
    room = sa.table("room", sa.column("id", sa.String), sa.column("property_id", sa.String),
                    sa.column("unit_id", sa.String), sa.column("hk_status", sa.String),
                    sa.column("rush", sa.Boolean), sa.column("status_changed_at", sa.DateTime),
                    sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime))
    now = datetime.now(UTC).replace(tzinfo=None)  # UTCDateTime stores naive UTC
    op.bulk_insert(room, [
        {"id": str(uuid.uuid4()), "property_id": property_id, "unit_id": unit_id,
         "hk_status": "inspected", "rush": False, "status_changed_at": now,
         "created_at": now, "updated_at": now}
        for unit_id, property_id in rows
    ])


def downgrade() -> None:
    # FK-safe order: children before parents. The backfill wrote only into these tables, so
    # dropping them is a true reversal.
    for table in ("housekeeping_photo", "room_event", "housekeeping_assignment", "room"):
        op.drop_table(table)
```

- [ ] **Step 7: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_models.py tests/test_hk_models.py::test_0008_backfills_active_guest_rooms_and_downgrades_cleanly -q`
Expected: PASS. (`test_room_unit_id_is_unique` and the round-trip test still ImportError until
Task 3.)

- [ ] **Step 8: Run the whole suite and lint**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q --deselect tests/test_hk_models.py::test_room_unit_id_is_unique --deselect tests/test_hk_models.py::test_hk_status_round_trips_and_rejects_unknown_values && ../.venv/Scripts/python.exe -m ruff check .`
Expected: all pass, ruff clean.

- [ ] **Step 9: Commit**

```bash
git add server/app/schemas/enums.py server/app/models/housekeeping.py server/app/models/__init__.py server/alembic/versions/0008_housekeeping.py server/tests/test_models.py server/tests/test_hk_models.py
git commit -m "feat(housekeeping): enums, models and migration 0008 with room backfill"
```

---

### Task 2: Capabilities (server and web, same commit)

**Files:**
- Modify: `server/app/auth/permissions.py`
- Modify: `web/src/auth/capabilities.ts`
- Test: `server/tests/test_hk_permissions.py`, `web/src/auth/capabilities.test.ts`

**Interfaces:**
- Produces: capabilities `view_housekeeping`, `mark_room_dirty`, `perform_housekeeping`,
  `manage_housekeeping`, `inspect_housekeeping` — on both sides, same role sets.

- [ ] **Step 1: Write the failing server test** — `server/tests/test_hk_permissions.py`:

```python
"""Spec §4.2. Every one includes admin — test_isolation.py demands it."""
from app.auth.permissions import CAPABILITIES, STAFF, has_capability
from app.schemas.enums import Role

HK = ("view_housekeeping", "mark_room_dirty", "perform_housekeeping", "manage_housekeeping",
      "inspect_housekeeping")


def test_housekeeping_capabilities_match_the_spec():
    assert CAPABILITIES["view_housekeeping"] == STAFF
    assert CAPABILITIES["mark_room_dirty"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                               Role.manager, Role.admin}
    assert CAPABILITIES["perform_housekeeping"] == {Role.dept_staff, Role.supervisor,
                                                    Role.manager, Role.admin}
    assert CAPABILITIES["manage_housekeeping"] == {Role.supervisor, Role.manager, Role.admin}
    assert CAPABILITIES["inspect_housekeeping"] == {Role.supervisor, Role.manager, Role.admin}


def test_admin_holds_every_housekeeping_capability():
    for cap in HK:
        assert has_capability(Role.admin, cap), cap


def test_front_desk_can_mark_dirty_but_not_run_the_floor():
    assert has_capability(Role.agent, "mark_room_dirty")
    for cap in ("perform_housekeeping", "manage_housekeeping", "inspect_housekeeping"):
        assert not has_capability(Role.agent, cap), cap
    assert not has_capability(Role.corporate, "mark_room_dirty")
```

- [ ] **Step 2: Write the failing web test** — append to `web/src/auth/capabilities.test.ts`
inside the existing capabilities `describe` (or a new one):

```ts
describe('housekeeping capabilities', () => {
  it('mirrors server/app/auth/permissions.py', () => {
    expect(hasCapability('corporate', 'view_housekeeping')).toBe(true)
    expect(hasCapability('agent', 'mark_room_dirty')).toBe(true)
    expect(hasCapability('corporate', 'mark_room_dirty')).toBe(false)
    expect(hasCapability('agent', 'perform_housekeeping')).toBe(false)
    expect(hasCapability('dept_staff', 'perform_housekeeping')).toBe(true)
    expect(hasCapability('dept_staff', 'manage_housekeeping')).toBe(false)
    expect(hasCapability('supervisor', 'manage_housekeeping')).toBe(true)
    expect(hasCapability('supervisor', 'inspect_housekeeping')).toBe(true)
    for (const cap of ['view_housekeeping', 'mark_room_dirty', 'perform_housekeeping',
      'manage_housekeeping', 'inspect_housekeeping'] as const) {
      expect(hasCapability('admin', cap)).toBe(true)
    }
  })
})
```

- [ ] **Step 3: Run both to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_permissions.py -q` → FAIL (KeyError).
Run: `cd web && npx vitest run src/auth/capabilities.test.ts` → FAIL (type error / false).

- [ ] **Step 4: Implement — `server/app/auth/permissions.py`**, append inside `CAPABILITIES`
after `inspect_pm`:

```python
    # Housekeeping (spec §4.2). All include admin, as above. Front desk (agent) can see the
    # board and mark a room dirty or rush it, and nothing more.
    "view_housekeeping": STAFF,
    "mark_room_dirty": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "perform_housekeeping": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "manage_housekeeping": {Role.supervisor, Role.manager, Role.admin},
    "inspect_housekeeping": {Role.supervisor, Role.manager, Role.admin},
```

- [ ] **Step 5: Implement — `web/src/auth/capabilities.ts`**: add the five names to the
`Capability` union after `'inspect_pm'`, and to `CAPABILITIES`:

```ts
  view_housekeeping: STAFF,
  mark_room_dirty: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  perform_housekeeping: ['dept_staff', 'supervisor', 'manager', 'admin'],
  manage_housekeeping: ['supervisor', 'manager', 'admin'],
  inspect_housekeeping: ['supervisor', 'manager', 'admin'],
```

- [ ] **Step 6: Run both, then the isolation suite**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_permissions.py tests/test_isolation.py -q` → PASS.
Run: `cd web && npx vitest run src/auth/capabilities.test.ts && npm run lint` → PASS.

- [ ] **Step 7: Commit (both files together — CLAUDE.md)**

```bash
git add server/app/auth/permissions.py server/tests/test_hk_permissions.py web/src/auth/capabilities.ts web/src/auth/capabilities.test.ts
git commit -m "feat(housekeeping): capabilities, mirrored server and web"
```

---

### Task 3: Room rows, occupancy, audit trail and the emission point (`hk_rooms`)

**Files:**
- Create: `server/app/domain/hk_rooms.py`
- Create: `server/tests/hk_helpers.py`
- Test: `server/tests/test_hk_rooms.py`

**Interfaces:**
- Consumes: Task 1 models and enums.
- Produces (all in `app.domain.hk_rooms`):
  - `EVENT = "housekeeping.rooms.changed"`
  - `emit(db, property_id: str, room_ids: list[str]) -> None`
  - `ensure_rooms(db, property_id: str) -> list[Room]` (rows created)
  - `get(db, property_id: str, room_id: str) -> Room` (NotFound)
  - `unit_of(db, room: Room) -> MaintainableUnit`
  - `active_rooms(db, property_id: str) -> list[tuple[Room, MaintainableUnit]]`
  - `@dataclass(frozen=True) Occupancy(kind: HkOccupancy, guest_name: str | None = None,
    departure_date: date | None = None, checked_out_at: datetime | None = None)`; `VACANT`
  - `occupancy_by_code(db, prop: Property) -> dict[str, Occupancy]`
  - `occupancy_of(db, room: Room) -> Occupancy`
  - `service_type_for(occ: Occupancy) -> HkServiceType`
  - `record(db, room, type: RoomEventType, user_id: str | None, *, assignment_id=None,
    from_value=None, to_value=None, comment=None) -> RoomEvent`
  - `set_status(db, room, status: HkStatus, user_id: str | None, *, event_type:
    RoomEventType = RoomEventType.status_changed, assignment_id=None, comment=None) -> None`
  - `today(db, property_id: str) -> date`
  - `open_assignment(db, room: Room, day: date) -> HousekeepingAssignment | None`
  - `next_sequence(db, property_id: str, user_id: str, day: date) -> int`
  - `delete_assignment(db, assignment: HousekeepingAssignment) -> None`
  - `hk_supervisors(db, property_id: str) -> list[str]`
  - `names_for(db, user_ids: list[str | None]) -> dict[str, str]`
  - `dirty_on_checkout(db, property_id: str, room_number: str | None) -> None` (used by Task 4)

- [ ] **Step 1: Create the shared test helpers** — `server/tests/hk_helpers.py`:

```python
"""Shared set-up for the housekeeping tests."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.domain import hk_rooms, pm_cycles
from app.models import (
    Guest,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    Stay,
    UserAccount,
)
from app.schemas.enums import PmUnitKind, Role, StayStatus
from tests.fixtures import PASSWORD


def make_rooms(db: Session, property_id: str, codes=("101", "102", "204")) -> dict[str, Room]:
    for code in codes:
        db.add(MaintainableUnit(property_id=property_id, kind=PmUnitKind.guest_room, code=code,
                                name=f"Room {code}",
                                floor=int(code[0]) if code[:1].isdigit() else None))
    db.flush()
    hk_rooms.ensure_rooms(db, property_id)
    return rooms_by_code(db, property_id)


def rooms_by_code(db: Session, property_id: str) -> dict[str, Room]:
    return {unit.code: room for room, unit in hk_rooms.active_rooms(db, property_id)}


def local_today(db: Session, property_id: str) -> date:
    return pm_cycles.local_today(db.get(Property, property_id))


def add_stay(db: Session, property_id: str, room_number: str, *, status: StayStatus,
             arrival: date, departure: date, checked_out_at: datetime | None = None,
             first: str = "Test", last: str = "Guest") -> Stay:
    guest = Guest(property_id=property_id, first_name=first, last_name=last,
                  phone_e164=f"+1555{uuid.uuid4().int % 10**7:07d}")
    db.add(guest)
    db.flush()
    stay = Stay(guest_id=guest.id, property_id=property_id, room_number=room_number,
                status=status, arrival_date=arrival, departure_date=departure,
                actual_checkout_at=checked_out_at)
    db.add(stay)
    db.flush()
    return stay


def add_user(db: Session, property_id: str, email: str, role: Role,
             department_id: str | None, first: str = "Pat", last: str = "Person") -> str:
    user = UserAccount(email=email, first_name=first, last_name=last,
                       password_hash=hash_password(PASSWORD, rounds=4))
    db.add(user)
    db.flush()
    db.add(PropertyMembership(user_id=user.id, property_id=property_id, role=role,
                              department_id=department_id))
    db.flush()
    return user.id


def add_hk_supervisor(db: Session, fx) -> str:
    """The fixture's supervisor is Engineering; housekeeping needs its own."""
    return add_user(db, fx.property_a.id, "grace@hvh.test", Role.supervisor,
                    fx.dept_housekeeping.id, "Grace", "Osei")
```

- [ ] **Step 2: Write the failing tests** — `server/tests/test_hk_rooms.py`:

```python
"""hk_rooms (spec §2.1, §2.3, §5)."""
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.domain import hk_rooms
from app.models import HousekeepingAssignment, MaintainableUnit, Property, RoomEvent
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    PmUnitKind,
    RoomEventType,
    StayStatus,
)
from tests.hk_helpers import add_stay, local_today, make_rooms


def test_ensure_rooms_covers_active_guest_rooms_only_and_is_idempotent(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        db.add_all([
            MaintainableUnit(property_id=pid, kind=PmUnitKind.guest_room, code="101", name="R"),
            MaintainableUnit(property_id=pid, kind=PmUnitKind.guest_room, code="102", name="R",
                             active=False),
            MaintainableUnit(property_id=pid, kind=PmUnitKind.equipment, code="BOILER-1",
                             name="Boiler"),
        ])
        db.flush()
        created = hk_rooms.ensure_rooms(db, pid)
        assert len(created) == 1
        assert created[0].hk_status is HkStatus.inspected
        assert hk_rooms.ensure_rooms(db, pid) == []


def test_active_rooms_puts_floorless_units_last(database, fx):
    """Review focus 1: SQLite sorts NULL first on ASC, PostgreSQL last — pinned either way."""
    with database.session() as db:
        make_rooms(db, fx.property_a.id, codes=("PH", "301", "101"))
        codes = [u.code for _, u in hk_rooms.active_rooms(db, fx.property_a.id)]
        assert codes == ["101", "301", "PH"]


def test_occupancy_is_derived_from_stays(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        make_rooms(db, pid, codes=("101", "102", "103", "104", "105", "106"))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=2), first="Stella", last="Over")
        add_stay(db, pid, "102", status=StayStatus.checked_in, arrival=today - timedelta(days=2),
                 departure=today)
        add_stay(db, pid, "103", status=StayStatus.checked_in, arrival=today - timedelta(days=4),
                 departure=today - timedelta(days=1))  # overdue: still a departure
        add_stay(db, pid, "104", status=StayStatus.reserved, arrival=today,
                 departure=today + timedelta(days=1))
        add_stay(db, pid, "105", status=StayStatus.checked_out, arrival=today - timedelta(days=2),
                 departure=today, checked_out_at=clock.now() - timedelta(hours=1))
        # 106: a checked-in guest beats a reservation arriving today
        add_stay(db, pid, "106", status=StayStatus.reserved, arrival=today,
                 departure=today + timedelta(days=2))
        add_stay(db, pid, "106", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today)
        occ = hk_rooms.occupancy_by_code(db, db.get(Property, pid))
        assert occ["101"].kind is HkOccupancy.stayover
        assert occ["101"].guest_name == "Stella Over"
        assert occ["102"].kind is HkOccupancy.departure
        assert occ["103"].kind is HkOccupancy.departure
        assert occ["104"].kind is HkOccupancy.arrival
        assert occ["105"].kind is HkOccupancy.vacant
        assert occ["105"].checked_out_at is not None
        assert occ["106"].kind is HkOccupancy.departure
        assert "999" not in occ  # no stay = vacant, by absence


def test_service_type_for_occupied_is_touch_up_else_departure():
    assert hk_rooms.service_type_for(hk_rooms.Occupancy(HkOccupancy.stayover)) \
        is HkServiceType.touch_up
    assert hk_rooms.service_type_for(hk_rooms.VACANT) is HkServiceType.departure


def test_set_status_stamps_time_and_records_the_event(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        hk_rooms.set_status(db, room, HkStatus.out_of_order, fx.supervisor_a.id,
                            comment="Leak")
        assert room.hk_status is HkStatus.out_of_order
        assert room.status_changed_at == clock.now()
        ev = db.scalar(select(RoomEvent).where(RoomEvent.room_id == room.id))
        assert (ev.type, ev.from_value, ev.to_value, ev.comment) == (
            RoomEventType.status_changed, "inspected", "out_of_order", "Leak")


def test_emit_dedups_and_skips_empty(database, fx, events):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        hk_rooms.emit(db, fx.property_a.id, [room.id, room.id])
        hk_rooms.emit(db, fx.property_a.id, [])
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and hk[0].payload == {"ids": [room.id]}


def test_delete_assignment_keeps_the_history(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        a = HousekeepingAssignment(property_id=fx.property_a.id, room_id=room.id,
                                   housekeeper_user_id=fx.housekeeper_a.id,
                                   shift_date=local_today(db, fx.property_a.id), sequence=1,
                                   type=HkServiceType.departure,
                                   status=HkAssignmentStatus.assigned)
        db.add(a)
        db.flush()
        hk_rooms.record(db, room, RoomEventType.assigned, None, assignment_id=a.id)
        hk_rooms.delete_assignment(db, a)
        ev = db.scalar(select(RoomEvent).where(RoomEvent.room_id == room.id))
        assert ev.assignment_id is None
        assert db.scalar(select(HousekeepingAssignment)) is None


def test_hk_supervisors_are_housekeeping_supervisors_and_managers(database, fx):
    from tests.hk_helpers import add_hk_supervisor
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        # fx.supervisor_a is Engineering and must not be paged about a dirty room
        assert hk_rooms.hk_supervisors(db, fx.property_a.id) == [grace]
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_rooms.py -q`
Expected: FAIL — `ImportError: cannot import name 'hk_rooms'`.

- [ ] **Step 4: Implement `server/app/domain/hk_rooms.py`**

```python
"""Housekeeping rooms: the row, derived occupancy, the audit trail and the single realtime
emission point (spec §2.1, §2.3, §5). Every other hk_* module builds on these."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app import clock
from app.domain import pm_cycles
from app.errors import NotFound
from app.models import (
    Department,
    Guest,
    HousekeepingAssignment,
    HousekeepingPhoto,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    RoomEvent,
    Stay,
    UserAccount,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    PmUnitKind,
    Role,
    RoomEventType,
    StayStatus,
    UserStatus,
)

EVENT = "housekeeping.rooms.changed"


def emit(db: Session, property_id: str, room_ids: list[str]) -> None:
    """The one place housekeeping calls queue_event (spec §5). Ids only, always a list, so a
    bulk action sends one event and no guest data goes property-wide."""
    ids = list(dict.fromkeys(room_ids))
    if ids:
        queue_event(db, property_id, EVENT, {"ids": ids})


def ensure_rooms(db: Session, property_id: str) -> list[Room]:
    """A room row for every active guest-room unit that lacks one — the same rule the 0008
    backfill applied, so a later CSV import just works. Returns the rows it created."""
    existing = set(db.scalars(select(Room.unit_id).where(Room.property_id == property_id)))
    units = db.scalars(select(MaintainableUnit).where(
        MaintainableUnit.property_id == property_id,
        MaintainableUnit.kind == PmUnitKind.guest_room,
        MaintainableUnit.active.is_(True))).all()
    now = clock.now()
    created = [Room(property_id=property_id, unit_id=u.id, hk_status=HkStatus.inspected,
                    rush=False, status_changed_at=now)
               for u in units if u.id not in existing]
    db.add_all(created)
    db.flush()
    return created


def get(db: Session, property_id: str, room_id: str) -> Room:
    room = db.scalar(select(Room).where(Room.id == room_id, Room.property_id == property_id))
    if room is None:
        raise NotFound("Room not found")
    return room


def unit_of(db: Session, room: Room) -> MaintainableUnit:
    return db.get(MaintainableUnit, room.unit_id)


def active_rooms(db: Session, property_id: str) -> list[tuple[Room, MaintainableUnit]]:
    """The board's rooms. A deactivated unit keeps its row and history but leaves the board;
    reactivating it brings the same row back (spec §7)."""
    return [(r, u) for r, u in db.execute(
        select(Room, MaintainableUnit)
        .join(MaintainableUnit, MaintainableUnit.id == Room.unit_id)
        .where(Room.property_id == property_id, MaintainableUnit.active.is_(True),
               MaintainableUnit.kind == PmUnitKind.guest_room)
        # NULLS LAST pinned: SQLite sorts NULL first on ASC, PostgreSQL last.
        .order_by(MaintainableUnit.floor.asc().nulls_last(), MaintainableUnit.code)).all()]


@dataclass(frozen=True)
class Occupancy:
    kind: HkOccupancy
    guest_name: str | None = None
    departure_date: date | None = None
    # The latest checkout today, tracked apart from `kind` so the tick can dirty a room whose
    # checkout the PMS hook missed even when an arrival now occupies the `kind` slot.
    checked_out_at: datetime | None = None


VACANT = Occupancy(HkOccupancy.vacant)


def occupancy_by_code(db: Session, prop: Property) -> dict[str, Occupancy]:
    """Derived from `stay` on `stay.room_number == unit.code`, never stored (spec §2.1).
    A checked-in stay beats a reservation arriving today; checked-in with a departure date of
    today or earlier is a departure. Rooms with no relevant stay are absent (= VACANT)."""
    today = pm_cycles.local_today(prop)
    midnight = pm_cycles.local_day_start_utc(prop, today)
    rows = db.execute(
        select(Stay, Guest).join(Guest, Guest.id == Stay.guest_id)
        .where(Stay.property_id == prop.id, Stay.room_number.is_not(None),
               or_(Stay.status == StayStatus.checked_in,
                   and_(Stay.status == StayStatus.reserved, Stay.arrival_date == today),
                   and_(Stay.status == StayStatus.checked_out,
                        Stay.actual_checkout_at >= midnight)))).all()
    best: dict[str, tuple[int, Occupancy]] = {}
    checkouts: dict[str, datetime] = {}
    for stay, guest in rows:
        code = stay.room_number
        if stay.status == StayStatus.checked_out:
            if code not in checkouts or stay.actual_checkout_at > checkouts[code]:
                checkouts[code] = stay.actual_checkout_at
            continue
        name = " ".join(p for p in (guest.first_name, guest.last_name) if p) or None
        if stay.status == StayStatus.checked_in:
            kind = (HkOccupancy.departure if stay.departure_date <= today
                    else HkOccupancy.stayover)
            rank = 2
        else:
            kind, rank = HkOccupancy.arrival, 1
        if code not in best or rank > best[code][0]:
            best[code] = (rank, Occupancy(kind, name, stay.departure_date))
    return {code: replace(best.get(code, (0, VACANT))[1], checked_out_at=checkouts.get(code))
            for code in set(best) | set(checkouts)}


def occupancy_of(db: Session, room: Room) -> Occupancy:
    prop = db.get(Property, room.property_id)
    return occupancy_by_code(db, prop).get(unit_of(db, room).code, VACANT)


def service_type_for(occ: Occupancy) -> HkServiceType:
    """Spec §3.3: touch_up if someone is in the room, else a departure clean."""
    if occ.kind in (HkOccupancy.stayover, HkOccupancy.departure):
        return HkServiceType.touch_up
    return HkServiceType.departure


def record(db: Session, room: Room, type: RoomEventType, user_id: str | None, *,
           assignment_id: str | None = None, from_value: str | None = None,
           to_value: str | None = None, comment: str | None = None) -> RoomEvent:
    ev = RoomEvent(room_id=room.id, assignment_id=assignment_id, property_id=room.property_id,
                   user_id=user_id, type=type, from_value=from_value, to_value=to_value,
                   comment=comment)
    db.add(ev)
    db.flush()
    return ev


def set_status(db: Session, room: Room, status: HkStatus, user_id: str | None, *,
               event_type: RoomEventType = RoomEventType.status_changed,
               assignment_id: str | None = None, comment: str | None = None) -> None:
    old = room.hk_status
    room.hk_status = status
    room.status_changed_at = clock.now()
    record(db, room, event_type, user_id, assignment_id=assignment_id, from_value=old.value,
           to_value=status.value, comment=comment)


def today(db: Session, property_id: str) -> date:
    return pm_cycles.local_today(db.get(Property, property_id))


def open_assignment(db: Session, room: Room, day: date) -> HousekeepingAssignment | None:
    """At most one non-passed assignment per room per shift date (spec §2.2)."""
    return db.scalar(select(HousekeepingAssignment).where(
        HousekeepingAssignment.room_id == room.id, HousekeepingAssignment.shift_date == day,
        HousekeepingAssignment.status != HkAssignmentStatus.passed))


def next_sequence(db: Session, property_id: str, user_id: str, day: date) -> int:
    top = db.scalar(select(func.max(HousekeepingAssignment.sequence)).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.housekeeper_user_id == user_id,
        HousekeepingAssignment.shift_date == day))
    return (top or 0) + 1


def delete_assignment(db: Session, assignment: HousekeepingAssignment) -> None:
    """FKs are enforced, so detach the history and drop the photos first. The events keep
    their room_id, so the room's story survives."""
    db.execute(update(RoomEvent).where(RoomEvent.assignment_id == assignment.id)
               .values(assignment_id=None))
    db.execute(delete(HousekeepingPhoto).where(HousekeepingPhoto.assignment_id == assignment.id))
    db.delete(assignment)
    db.flush()


def hk_supervisors(db: Session, property_id: str) -> list[str]:
    """Who hears about rush and ready-for-inspection: active supervisors and managers in a
    housekeeping-type department."""
    return list(db.scalars(
        select(PropertyMembership.user_id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.role.in_([Role.supervisor, Role.manager]),
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)
        .order_by(PropertyMembership.user_id)).all())


def names_for(db: Session, user_ids: list[str | None]) -> dict[str, str]:
    """Display names for ids read off this property's own rows."""
    ids = [u for u in user_ids if u]
    if not ids:
        return {}
    rows = db.execute(select(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
                      .where(UserAccount.id.in_(ids))).all()
    return {uid: f"{first} {last}" for uid, first, last in rows}


def dirty_on_checkout(db: Session, property_id: str, room_number: str | None) -> None:
    """PMS `stay.checked_out` (spec §3.2): the room appears dirty at checkout, not at the next
    tick. A room number with no unit is ignored — the stay itself is still processed."""
    if not room_number:
        return
    room = db.scalar(
        select(Room).join(MaintainableUnit, MaintainableUnit.id == Room.unit_id)
        .where(Room.property_id == property_id, MaintainableUnit.code == room_number,
               MaintainableUnit.kind == PmUnitKind.guest_room,
               MaintainableUnit.active.is_(True)))
    if room is None or room.hk_status not in (HkStatus.clean, HkStatus.inspected):
        return
    room.service_type = HkServiceType.departure
    set_status(db, room, HkStatus.dirty, None, comment="Guest checked out")
    emit(db, property_id, [room.id])
```

- [ ] **Step 5: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_rooms.py tests/test_hk_models.py -q`
Expected: PASS — including the two Task 1 tests that were waiting on `ensure_rooms`.

- [ ] **Step 6: Lint and commit**

```bash
cd server && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/app/domain/hk_rooms.py server/tests/hk_helpers.py server/tests/test_hk_rooms.py server/tests/test_hk_models.py
git commit -m "feat(housekeeping): room rows, derived occupancy, audit trail, emission point"
```

---

### Task 4: The daily tick and the PMS checkout hook

**Files:**
- Create: `server/app/domain/hk_tick.py`
- Create: `server/app/queue/handlers/housekeeping.py`
- Modify: `server/app/queue/handlers/__init__.py:11` (`MODULES`)
- Modify: `server/app/queue/jobs.py:12` (`RECURRING`)
- Modify: `server/app/pms/handle_event.py` (after `db.flush()` that follows the status block)
- Test: `server/tests/test_hk_tick.py`

**Interfaces:**
- Consumes: `hk_rooms.ensure_rooms`, `active_rooms`, `occupancy_by_code`, `set_status`, `emit`,
  `VACANT`, `dirty_on_checkout`.
- Produces: `hk_tick.tick(db) -> dict[str, int]` with keys `"created"`, `"dirtied"`; job type
  `"housekeeping.tick"` every 300 s.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_tick.py`:

```python
"""housekeeping.tick (spec §3.1) and the PMS checkout hook (spec §3.2)."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app import clock
from app.domain import hk_rooms, hk_tick
from app.models import MaintainableUnit, Room, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent
from app.pms.handle_event import handle_event
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.schemas.enums import HkServiceType, HkStatus, PmUnitKind, StayStatus
from tests.hk_helpers import add_stay, local_today, make_rooms, rooms_by_code


def _at(room: Room, when: datetime) -> None:
    room.status_changed_at = when


def test_tick_is_registered_every_five_minutes():
    load_all()
    assert "housekeeping.tick" in HANDLERS and jobs.RECURRING["housekeeping.tick"] == 300


def test_stayover_and_departure_rooms_go_dirty_after_local_midnight(database, fx, events):
    # FROZEN is 2026-09-10 12:00 UTC = 08:00 in New York; HVH midnight = 04:00 UTC.
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "104"))
        yesterday_evening = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
        for r in rooms.values():
            _at(r, yesterday_evening)
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        add_stay(db, pid, "102", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today)
        # 103 vacant; 104 cleaned at 07:00 local today and occupied — stays clean
        add_stay(db, pid, "104", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        _at(rooms["104"], datetime(2026, 9, 10, 11, 0, tzinfo=UTC))
        result = hk_tick.tick(db)
        assert result["dirtied"] == 2
        assert (rooms["101"].hk_status, rooms["101"].service_type) == (
            HkStatus.dirty, HkServiceType.stayover)
        assert (rooms["102"].hk_status, rooms["102"].service_type) == (
            HkStatus.dirty, HkServiceType.departure)
        assert rooms["103"].hk_status is HkStatus.inspected
        assert rooms["104"].hk_status is HkStatus.inspected
        ids = {rooms["101"].id, rooms["102"].id}
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and set(hk[0].payload["ids"]) == ids


def test_tick_is_idempotent_and_a_noop_tick_is_silent(database, fx, events):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 9, 22, 0, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 1
    events.clear()
    with database.session() as db:
        assert hk_tick.tick(db) == {"created": 0, "dirtied": 0}
    assert [e for e in events if e.type == hk_rooms.EVENT] == []


def test_dirty_in_progress_and_out_of_order_rooms_are_untouched(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "104"))
        for code, status in (("101", HkStatus.dirty), ("102", HkStatus.in_progress),
                             ("103", HkStatus.out_of_order), ("104", HkStatus.out_of_service)):
            rooms[code].hk_status = status
            _at(rooms[code], datetime(2026, 9, 9, 22, 0, tzinfo=UTC))
            add_stay(db, pid, code, status=StayStatus.checked_in, arrival=today,
                     departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 0
        assert [r.hk_status for r in rooms.values()] == [
            HkStatus.dirty, HkStatus.in_progress, HkStatus.out_of_order,
            HkStatus.out_of_service]


def test_midnight_is_property_local_not_utc(database, fx):
    """At 02:00 UTC on Sep 11 it is still 22:00 on Sep 10 in New York: a room last changed at
    01:00 local on Sep 10 was changed *today* and must not roll, although a UTC midnight has
    passed since."""
    clock.freeze(datetime(2026, 9, 11, 2, 0, tzinfo=UTC))
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        assert today == date(2026, 9, 10)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 10, 5, 0, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 0


def test_each_property_rolls_at_its_own_midnight(database, fx):
    """04:30 UTC: 00:30 in New York (HVH has rolled), 23:30 the day before in Chicago (LSI has
    not). Both rooms last changed at 03:00 UTC."""
    clock.freeze(datetime(2026, 9, 10, 4, 30, tzinfo=UTC))
    with database.session() as db:
        changed = datetime(2026, 9, 10, 3, 0, tzinfo=UTC)
        for prop in (fx.property_a, fx.property_b):
            today = local_today(db, prop.id)
            room = make_rooms(db, prop.id, codes=("501",))["501"]
            _at(room, changed)
            add_stay(db, prop.id, "501", status=StayStatus.checked_in,
                     arrival=today - timedelta(days=1), departure=today + timedelta(days=2))
        hk_tick.tick(db)
        assert rooms_by_code(db, fx.property_a.id)["501"].hk_status is HkStatus.dirty
        assert rooms_by_code(db, fx.property_b.id)["501"].hk_status is HkStatus.inspected


def test_midnight_after_the_dst_change_uses_the_new_offset(database, fx):
    """2026-11-01 New York leaves EDT. On Nov 2, local midnight is 05:00 UTC, not 04:00: a room
    changed at 04:30 UTC (23:30 EST on Nov 1) must roll. A fixed -4 offset would skip it."""
    clock.freeze(datetime(2026, 11, 2, 5, 30, tzinfo=UTC))
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        assert today == date(2026, 11, 2)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 11, 2, 4, 30, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        assert hk_tick.tick(db)["dirtied"] == 1


def test_a_checkout_the_hook_missed_is_caught_by_the_tick(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 10, 5, 0, tzinfo=UTC))  # after midnight, before checkout
        add_stay(db, pid, "101", status=StayStatus.checked_out,
                 arrival=today - timedelta(days=2), departure=today,
                 checked_out_at=datetime(2026, 9, 10, 11, 0, tzinfo=UTC))
        assert hk_tick.tick(db)["dirtied"] == 1
        assert room.service_type is HkServiceType.departure


def test_tick_creates_rooms_for_new_guest_room_units(database, fx):
    with database.session() as db:
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="777", name="Room 777", floor=7))
        db.flush()
        assert hk_tick.tick(db)["created"] == 1
        assert "777" in rooms_by_code(db, fx.property_a.id)


def _checkout_event(fx, room_number: str) -> PmsEvent:
    """RES-412 is the fixture's in-house stay (Sarah Chen, +15551234567)."""
    return PmsEvent(
        external_id=f"evt-{room_number}", type="stay.checked_out",
        property_id=fx.property_a.id,
        guest=NormalizedGuest(first_name="Sarah", last_name="Chen", phone_e164="+15551234567"),
        stay=NormalizedStay(pms_reservation_id="RES-412", room_number=room_number,
                            room_type="King", rate_code=None, status=StayStatus.checked_out,
                            arrival_date=date(2026, 9, 7), departure_date=date(2026, 9, 10)))


def test_pms_checkout_dirties_the_room_immediately(database, fx):
    with database.session() as db:
        make_rooms(db, fx.property_a.id, codes=("412",))
        assert handle_event(db, _checkout_event(fx, "412"))
        room = rooms_by_code(db, fx.property_a.id)["412"]
        assert (room.hk_status, room.service_type) == (HkStatus.dirty, HkServiceType.departure)


def test_checkout_for_an_unknown_room_number_is_ignored(database, fx):
    """Review focus 5."""
    with database.session() as db:
        assert handle_event(db, _checkout_event(fx, "9999"))
        stay = db.scalar(select(Stay).where(Stay.pms_reservation_id == "RES-412"))
        assert stay.status is StayStatus.checked_out
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_tick.py -q`
Expected: FAIL — `ImportError: cannot import name 'hk_tick'`.

- [ ] **Step 3: Implement `server/app/domain/hk_tick.py`**

```python
"""`housekeeping.tick` (spec §3.1): every 5 minutes, deliberately stateless.

It never records "I rolled today"; it asks each room whether it ought to be dirty and is not.
The before-midnight test makes it idempotent: a room it dirtied now has status_changed_at =
now, and a room cleaned today has status_changed_at after midnight, so neither rolls again.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import hk_rooms, pm_cycles
from app.models import Property
from app.schemas.enums import HkOccupancy, HkServiceType, HkStatus

_ROLLS = {HkOccupancy.stayover: HkServiceType.stayover,
          HkOccupancy.departure: HkServiceType.departure}


def tick(db: Session) -> dict[str, int]:
    created = dirtied = 0
    for prop in db.scalars(select(Property).order_by(Property.id)).all():
        new = hk_rooms.ensure_rooms(db, prop.id)
        changed = [r.id for r in new]
        created += len(new)
        midnight = pm_cycles.local_day_start_utc(prop, pm_cycles.local_today(prop))
        occupancy = hk_rooms.occupancy_by_code(db, prop)
        for room, unit in hk_rooms.active_rooms(db, prop.id):
            if room.hk_status not in (HkStatus.clean, HkStatus.inspected):
                continue
            occ = occupancy.get(unit.code, hk_rooms.VACANT)
            service = None
            if occ.checked_out_at and occ.checked_out_at > room.status_changed_at:
                service = HkServiceType.departure
            elif room.status_changed_at < midnight and occ.kind in _ROLLS:
                service = _ROLLS[occ.kind]
            if service is None:
                continue
            room.service_type = service
            hk_rooms.set_status(db, room, HkStatus.dirty, None, comment="Daily roll")
            changed.append(room.id)
            dirtied += 1
        hk_rooms.emit(db, prop.id, changed)
    return {"created": created, "dirtied": dirtied}
```

- [ ] **Step 4: Register the job** — create `server/app/queue/handlers/housekeeping.py`:

```python
"""`housekeeping.tick` (spec §3.1): every 300 s. Idempotent, so a retried job is harmless."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import hk_tick
from app.queue.handlers import handler


@handler("housekeeping.tick")
def housekeeping_tick(db: Session, payload: dict) -> None:
    hk_tick.tick(db)
```

In `server/app/queue/handlers/__init__.py` set
`MODULES = ("outbound", "mock_delivery", "sla", "snooze", "pms", "pm", "housekeeping")`.
In `server/app/queue/jobs.py` set
`RECURRING: dict[str, int] = {"sla.sweep": 30, "snooze.wake": 60, "pm.tick": 300, "housekeeping.tick": 300}`
(wrap to stay under 100 columns). `app/__init__.py:127` already ensures every `RECURRING` type at
boot, so production picks it up with no further change.

- [ ] **Step 5: Hook the PMS checkout** — in `server/app/pms/handle_event.py`, import
`from app.domain import audit, guests, hk_rooms` and, immediately after the `db.flush()` that
follows the `actual_checkout_at` block, add:

```python
    if event.type == "stay.checked_out":
        # Spec §3.2: a 9am checkout appears on the housekeeping board at 9am, not at the next
        # tick. check-in and room change do not touch status — occupancy is derived.
        hk_rooms.dirty_on_checkout(db, event.property_id, stay.room_number)
```

- [ ] **Step 6: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_tick.py tests/test_pms.py tests/test_queue.py tests/test_pm_tick.py -q`
Expected: PASS.

- [ ] **Step 7: Lint and commit**

```bash
cd server && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/app/domain/hk_tick.py server/app/queue/handlers/housekeeping.py server/app/queue/handlers/__init__.py server/app/queue/jobs.py server/app/pms/handle_event.py server/tests/test_hk_tick.py
git commit -m "feat(housekeeping): stateless daily tick and PMS checkout hook"
```

---

### Task 5: Assignment — assign, reassign, unassign, reorder

**Files:**
- Create: `server/app/domain/hk_assignments.py`
- Test: `server/tests/test_hk_assignments.py`

**Interfaces:**
- Consumes: `hk_rooms.*` (Task 3), `notifications.notify_users`.
- Produces (in `app.domain.hk_assignments`):
  - `get(db, property_id, assignment_id) -> HousekeepingAssignment` (NotFound)
  - `assign(db, property_id, actor_id, room_ids: list[str], housekeeper_id: str) ->
    list[HousekeepingAssignment]`
  - `unassign(db, property_id, actor_id, assignment_id) -> Room`
  - `reorder(db, property_id, actor_id, housekeeper_id, assignment_ids: list[str]) ->
    list[HousekeepingAssignment]`

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_assignments.py`:

```python
"""Assignment (spec §3.4, §4.2)."""
import pytest
from sqlalchemy import func, select

from app.domain import hk_assignments, hk_rooms
from app.errors import TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Notification, RoomEvent, UserAccount
from app.schemas.enums import (
    HkAssignmentStatus,
    HkStatus,
    Role,
    RoomEventType,
    UserStatus,
)
from tests.hk_helpers import add_user, make_rooms


def _dirty(rooms):
    for r in rooms.values():
        r.hk_status = HkStatus.dirty
    return rooms


def _count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_bulk_assign_appends_in_order_and_notifies_once(database, fx, events):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102", "103")))
        out = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                    [r.id for r in rooms.values()], fx.housekeeper_a.id)
        assert [a.sequence for a in out] == [1, 2, 3]
        assert all(a.status is HkAssignmentStatus.assigned for a in out)
        notes = db.scalars(select(Notification).where(
            Notification.user_id == fx.housekeeper_a.id)).all()
        assert [n.title for n in notes] == ["3 rooms assigned to you"]
        ids = {r.id for r in rooms.values()}
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and set(hk[0].payload["ids"]) == ids


def test_assigning_again_to_the_same_housekeeper_is_a_no_op(database, fx):
    """Review focus 2: a double-submit must not duplicate the row or the notification."""
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                              fx.housekeeper_a.id)
        hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                              fx.housekeeper_a.id)
        assert _count(db, HousekeepingAssignment) == 1
        assert _count(db, Notification, Notification.user_id == fx.housekeeper_a.id) == 1


def test_reassign_moves_the_row_and_records_it(database, fx):
    with database.session() as db:
        rosa = add_user(db, fx.property_a.id, "rosa@hvh.test", Role.dept_staff,
                        fx.dept_housekeeping.id, "Rosa", "Lima")
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (first,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                         fx.housekeeper_a.id)
        (moved,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                         rosa)
        assert moved.id == first.id and moved.housekeeper_user_id == rosa
        ev = db.scalar(select(RoomEvent).where(RoomEvent.type == RoomEventType.reassigned))
        assert (ev.from_value, ev.to_value) == (fx.housekeeper_a.id, rosa)


def test_a_room_awaiting_inspection_cannot_be_reassigned(database, fx):
    with database.session() as db:
        rosa = add_user(db, fx.property_a.id, "rosa@hvh.test", Role.dept_staff,
                        fx.dept_housekeeping.id, "Rosa", "Lima")
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (a,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                     fx.housekeeper_a.id)
        a.status = HkAssignmentStatus.done
        room.hk_status = HkStatus.in_progress  # still assignable, so the done row is what blocks
        with pytest.raises(TransitionError, match="awaiting inspection"):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id], rosa)


def test_only_dirty_or_in_progress_rooms_can_be_assigned(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]  # inspected
        with pytest.raises(TransitionError):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.housekeeper_a.id)


def test_engineering_staff_cannot_receive_housekeeping_rooms(database, fx):
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        with pytest.raises(ValidationFailed):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.engineer_a.id)


def test_cannot_assign_to_a_disabled_housekeeper(database, fx):
    """Review focus 3."""
    with database.session() as db:
        db.get(UserAccount, fx.housekeeper_a.id).status = UserStatus.disabled
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        with pytest.raises(ValidationFailed):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.housekeeper_a.id)


def test_unassign_refuses_a_started_room_and_keeps_history_otherwise(database, fx):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102")))
        a1, a2 = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                       [rooms["101"].id, rooms["102"].id], fx.housekeeper_a.id)
        a2.status = HkAssignmentStatus.in_progress
        with pytest.raises(TransitionError):
            hk_assignments.unassign(db, fx.property_a.id, fx.supervisor_a.id, a2.id)
        hk_assignments.unassign(db, fx.property_a.id, fx.supervisor_a.id, a1.id)
        assert db.get(HousekeepingAssignment, a1.id) is None
        types = set(db.scalars(select(RoomEvent.type).where(
            RoomEvent.room_id == rooms["101"].id)))
        assert types == {RoomEventType.assigned, RoomEventType.unassigned}


def test_reorder_sets_the_sequence_and_rejects_foreign_ids(database, fx):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102", "103")))
        a = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                  [r.id for r in rooms.values()], fx.housekeeper_a.id)
        out = hk_assignments.reorder(db, fx.property_a.id, fx.supervisor_a.id,
                                     fx.housekeeper_a.id, [a[2].id, a[0].id, a[1].id])
        assert [(x.id, x.sequence) for x in out] == [(a[2].id, 1), (a[0].id, 2), (a[1].id, 3)]
        with pytest.raises(ValidationFailed):
            hk_assignments.reorder(db, fx.property_a.id, fx.supervisor_a.id,
                                   fx.housekeeper_a.id, [a[0].id, a[1].id])


def test_a_manager_from_another_department_can_assign(database, fx):
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (a,) = hk_assignments.assign(db, fx.property_a.id, fx.manager_a.id, [room.id],
                                     fx.housekeeper_a.id)
        assert a.housekeeper_user_id == fx.housekeeper_a.id
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_assignments.py -q`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `server/app/domain/hk_assignments.py`**

```python
"""Assignment (spec §3.4): a supervisor gives today's dirty rooms to housekeepers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import hk_rooms, notifications
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import Department, HousekeepingAssignment, PropertyMembership, Room, UserAccount
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    RoomEventType,
    UserStatus,
)

ASSIGNABLE = (HkStatus.dirty, HkStatus.in_progress)
MOVABLE = (HkAssignmentStatus.assigned, HkAssignmentStatus.in_progress)


def get(db: Session, property_id: str, assignment_id: str) -> HousekeepingAssignment:
    a = db.scalar(select(HousekeepingAssignment).where(
        HousekeepingAssignment.id == assignment_id,
        HousekeepingAssignment.property_id == property_id))
    if a is None:
        raise NotFound("Assignment not found")
    return a


def _is_housekeeper(db: Session, property_id: str, user_id: str) -> bool:
    """Role alone is not enough: an engineering dept_staff must not get rooms (spec §4.2)."""
    return db.scalar(
        select(PropertyMembership.id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.user_id == user_id,
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)) is not None


def assign(db: Session, property_id: str, actor_id: str, room_ids: list[str],
           housekeeper_id: str) -> list[HousekeepingAssignment]:
    if not _is_housekeeper(db, property_id, housekeeper_id):
        raise ValidationFailed("Rooms can only be assigned to active housekeeping staff",
                               details={"housekeeperUserId": "not_housekeeping"})
    day = hk_rooms.today(db, property_id)
    rooms = [hk_rooms.get(db, property_id, rid) for rid in dict.fromkeys(room_ids)]
    # Validate everything before touching anything, so a bad room in a batch of twelve
    # leaves the other eleven as they were.
    plan: list[tuple[Room, HousekeepingAssignment | None]] = []
    for room in rooms:
        if room.hk_status not in ASSIGNABLE:
            code = hk_rooms.unit_of(db, room).code
            raise TransitionError(f"Room {code} is {room.hk_status.value} and cannot be assigned")
        current = hk_rooms.open_assignment(db, room, day)
        if current and current.housekeeper_user_id != housekeeper_id \
                and current.status not in MOVABLE:
            code = hk_rooms.unit_of(db, room).code
            raise TransitionError(f"Room {code} is awaiting inspection and cannot be reassigned")
        plan.append((room, current))

    seq = hk_rooms.next_sequence(db, property_id, housekeeper_id, day)
    out: list[HousekeepingAssignment] = []
    changed: list[str] = []
    for room, current in plan:
        if current and current.housekeeper_user_id == housekeeper_id:
            out.append(current)
            continue
        if current:
            previous = current.housekeeper_user_id
            current.housekeeper_user_id = housekeeper_id
            current.sequence = seq
            hk_rooms.record(db, room, RoomEventType.reassigned, actor_id,
                            assignment_id=current.id, from_value=previous,
                            to_value=housekeeper_id)
            a = current
        else:
            a = HousekeepingAssignment(
                property_id=property_id, room_id=room.id, housekeeper_user_id=housekeeper_id,
                shift_date=day, sequence=seq, type=room.service_type or HkServiceType.departure,
                status=HkAssignmentStatus.assigned, fail_count=0)
            db.add(a)
            db.flush()
            hk_rooms.record(db, room, RoomEventType.assigned, actor_id, assignment_id=a.id,
                            to_value=housekeeper_id)
        seq += 1
        out.append(a)
        changed.append(room.id)
    if changed:
        n = len(changed)
        notifications.notify_users(db, property_id, [housekeeper_id], "hk.assigned",
                                   f"{n} room{'' if n == 1 else 's'} assigned to you",
                                   entity_type="room", entity_id=changed[0] if n == 1 else None)
    hk_rooms.emit(db, property_id, changed)
    return out


def unassign(db: Session, property_id: str, actor_id: str, assignment_id: str) -> Room:
    a = get(db, property_id, assignment_id)
    if a.status != HkAssignmentStatus.assigned:
        raise TransitionError("A started room cannot be unassigned")
    room = db.get(Room, a.room_id)
    previous = a.housekeeper_user_id
    hk_rooms.delete_assignment(db, a)
    hk_rooms.record(db, room, RoomEventType.unassigned, actor_id, from_value=previous)
    hk_rooms.emit(db, property_id, [room.id])
    return room


def reorder(db: Session, property_id: str, actor_id: str, housekeeper_id: str,
            assignment_ids: list[str]) -> list[HousekeepingAssignment]:
    """The ids must be exactly that housekeeper's open assignments for today."""
    day = hk_rooms.today(db, property_id)
    current = {a.id: a for a in db.scalars(select(HousekeepingAssignment).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.housekeeper_user_id == housekeeper_id,
        HousekeepingAssignment.shift_date == day,
        HousekeepingAssignment.status != HkAssignmentStatus.passed))}
    if len(assignment_ids) != len(current) or set(assignment_ids) != set(current):
        raise ValidationFailed("List every one of that housekeeper's rooms for today, once",
                               details={"assignmentIds": "mismatch"})
    ordered = [current[i] for i in assignment_ids]
    for position, a in enumerate(ordered, start=1):
        a.sequence = position
    db.flush()
    hk_rooms.emit(db, property_id, [a.room_id for a in ordered])
    return ordered
```

- [ ] **Step 4: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_assignments.py -q`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

```bash
cd server && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/app/domain/hk_assignments.py server/tests/test_hk_assignments.py
git commit -m "feat(housekeeping): assign, reassign, unassign and reorder"
```

---

### Task 6: Transitions — the §3.3 table

**Files:**
- Create: `server/app/domain/hk_transitions.py`
- Test: `server/tests/test_hk_transitions.py`

**Interfaces:**
- Consumes: `hk_rooms.*`, `hk_assignments.get`, `notifications.notify_users`,
  `app.auth.permissions.has_capability`.
- Produces (in `app.domain.hk_transitions`):
  - `mark_dirty(db, property_id, actor_id, room_id, note: str | None) -> Room`
  - `set_rush(db, property_id, actor_id, room_id, on: bool) -> Room`
  - `set_room_status(db, property_id, actor_id, room_id, status: HkStatus, note: str | None) ->
    Room` — `status` ∈ {out_of_order, out_of_service, dirty}
  - `start(db, property_id, actor_id, role: Role, assignment_id) -> HousekeepingAssignment`
  - `complete(db, property_id, actor_id, role: Role, assignment_id) -> HousekeepingAssignment`
  - `inspect(db, property_id, actor_id, assignment_id, result: Literal["pass", "fail"],
    note: str | None) -> HousekeepingAssignment`
  - `self_assign_start(db, property_id, actor_id, room_id) -> HousekeepingAssignment`
  - `require_owner_or_manager(a, actor_id, role) -> None` (also used by Task 7)

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_transitions.py`:

```python
"""The transition table (spec §3.3), as a matrix: every (from status, action) not in ALLOWED
must be a 409, so a new status can never silently gain a transition."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.domain import hk_assignments, hk_rooms, hk_transitions
from app.errors import Conflict, Forbidden, TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Notification, RoomEvent
from app.schemas.enums import (
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    Role,
    RoomEventType,
    StayStatus,
)
from tests.hk_helpers import add_hk_supervisor, add_stay, local_today, make_rooms

STATES = ["inspected", "dirty", "in_progress", "clean", "out_of_order", "out_of_service"]
ACTIONS = ["mark_dirty", "start", "complete", "pass", "fail", "ooo", "oos", "back"]
ALLOWED = {
    ("inspected", "mark_dirty"), ("inspected", "ooo"), ("inspected", "oos"),
    ("dirty", "start"), ("dirty", "ooo"), ("dirty", "oos"),
    ("in_progress", "complete"), ("in_progress", "ooo"), ("in_progress", "oos"),
    ("clean", "pass"), ("clean", "fail"), ("clean", "ooo"), ("clean", "oos"),
    ("out_of_order", "back"), ("out_of_order", "oos"),
    ("out_of_service", "back"), ("out_of_service", "ooo"),
}
RESULT = {"mark_dirty": HkStatus.dirty, "start": HkStatus.in_progress,
          "complete": HkStatus.clean, "pass": HkStatus.inspected, "fail": HkStatus.dirty,
          "ooo": HkStatus.out_of_order, "oos": HkStatus.out_of_service, "back": HkStatus.dirty}


def _build(db, fx, state):
    """A room in `state`, reached through the real domain calls."""
    pid, sup, hk = fx.property_a.id, fx.supervisor_a.id, fx.housekeeper_a.id
    room = make_rooms(db, pid, codes=("101",))["101"]
    if state in ("out_of_order", "out_of_service"):
        hk_transitions.set_room_status(db, pid, sup, room.id, HkStatus(state), None)
        return room
    if state == "inspected":
        return room
    hk_transitions.mark_dirty(db, pid, sup, room.id, None)
    (a,) = hk_assignments.assign(db, pid, sup, [room.id], hk)
    if state in ("in_progress", "clean"):
        hk_transitions.start(db, pid, hk, Role.dept_staff, a.id)
    if state == "clean":
        hk_transitions.complete(db, pid, hk, Role.dept_staff, a.id)
    return room


def _assignment_for(db, fx, room):
    """The room's latest assignment, or a bare `assigned` row so the room-status guard (not a
    missing id) is what gets exercised."""
    a = db.scalar(select(HousekeepingAssignment).where(HousekeepingAssignment.room_id == room.id)
                  .order_by(HousekeepingAssignment.created_at.desc()))
    if a is None:
        a = HousekeepingAssignment(property_id=room.property_id, room_id=room.id,
                                   housekeeper_user_id=fx.housekeeper_a.id,
                                   shift_date=local_today(db, room.property_id), sequence=1,
                                   type=HkServiceType.departure,
                                   status=HkAssignmentStatus.assigned)
        db.add(a)
        db.flush()
    return a


def _act(db, fx, room, action):
    pid, sup = fx.property_a.id, fx.supervisor_a.id
    if action == "mark_dirty":
        return hk_transitions.mark_dirty(db, pid, sup, room.id, None)
    if action in ("ooo", "oos", "back"):
        status = {"ooo": HkStatus.out_of_order, "oos": HkStatus.out_of_service,
                  "back": HkStatus.dirty}[action]
        return hk_transitions.set_room_status(db, pid, sup, room.id, status, None)
    a = _assignment_for(db, fx, room)
    if action == "start":
        return hk_transitions.start(db, pid, sup, Role.supervisor, a.id)
    if action == "complete":
        return hk_transitions.complete(db, pid, sup, Role.supervisor, a.id)
    return hk_transitions.inspect(db, pid, sup, a.id, action, "Streaky mirror.")


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("action", ACTIONS)
def test_transition_matrix(database, fx, state, action):
    with database.session() as db:
        room = _build(db, fx, state)
        assert room.hk_status is HkStatus(state)
        if (state, action) in ALLOWED:
            _act(db, fx, room, action)
            assert room.hk_status is RESULT[action]
        else:
            with pytest.raises(TransitionError):
                _act(db, fx, room, action)


def test_mark_dirty_on_a_room_awaiting_inspection_points_at_the_fail_path(database, fx):
    with database.session() as db:
        room = _build(db, fx, "clean")
        with pytest.raises(TransitionError, match="supervisor must fail"):
            hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)


def test_mark_dirty_sets_touch_up_when_occupied(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        hk_transitions.mark_dirty(db, pid, fx.agent_a.id, room.id, "Spill")
        assert room.service_type is HkServiceType.touch_up
        ev = db.scalar(select(RoomEvent).where(RoomEvent.type == RoomEventType.marked_dirty))
        assert ev.comment == "Spill"


def test_fail_requires_a_non_blank_note(database, fx):
    """Review focus 4: whitespace is not a note."""
    with database.session() as db:
        room = _build(db, fx, "clean")
        a = _assignment_for(db, fx, room)
        for note in (None, "", "   "):
            with pytest.raises(ValidationFailed):
                hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "fail",
                                       note)


def test_fail_returns_the_same_row_and_tells_the_housekeeper(database, fx):
    with database.session() as db:
        room = _build(db, fx, "clean")
        a = _assignment_for(db, fx, room)
        hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "fail",
                               "Hair in the sink.")
        assert db.scalar(select(func.count()).select_from(HousekeepingAssignment)) == 1
        assert (a.status, a.fail_count, a.inspection_note) == (
            HkAssignmentStatus.assigned, 1, "Hair in the sink.")
        assert a.started_at is None and a.completed_at is None
        note = db.scalar(select(Notification).where(
            Notification.user_id == fx.housekeeper_a.id,
            Notification.type == "hk.inspection_failed"))
        assert note.body == "Hair in the sink."


def test_pass_clears_rush_and_stamps_the_inspection(database, fx):
    with database.session() as db:
        room = _build(db, fx, "in_progress")
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        a = _assignment_for(db, fx, room)
        hk_transitions.complete(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id)
        hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "pass", None)
        assert room.rush is False and room.last_inspected_at is not None
        assert a.status is HkAssignmentStatus.passed


def test_rush_only_on_rooms_waiting_to_be_cleaned_and_notifies_hk_supervisors(database, fx):
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
        with pytest.raises(TransitionError):
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)  # no-op
        titles = db.scalars(select(Notification.title).where(Notification.user_id == grace)).all()
        assert titles == ["Rush: Room 101"]


def test_complete_notifies_hk_supervisors(database, fx):
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        _build(db, fx, "clean")
        assert db.scalar(select(Notification.type).where(Notification.user_id == grace)) \
            == "hk.ready_for_inspection"


def test_out_of_order_removes_the_open_assignment(database, fx):
    with database.session() as db:
        room = _build(db, fx, "in_progress")
        hk_transitions.set_room_status(db, fx.property_a.id, fx.supervisor_a.id, room.id,
                                       HkStatus.out_of_order, "AC leak")
        assert db.scalar(select(func.count()).select_from(HousekeepingAssignment)) == 0
        assert room.rush is False


def test_a_housekeeper_cannot_start_someone_elses_room(database, fx):
    with database.session() as db:
        room = _build(db, fx, "dirty")
        a = _assignment_for(db, fx, room)
        with pytest.raises(Forbidden):
            hk_transitions.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, a.id)
        hk_transitions.start(db, fx.property_a.id, fx.supervisor_a.id, Role.supervisor, a.id)


def test_supervisor_self_assign_start(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
        a = hk_transitions.self_assign_start(db, fx.property_a.id, fx.supervisor_a.id, room.id)
        assert (a.housekeeper_user_id, a.status) == (fx.supervisor_a.id,
                                                     HkAssignmentStatus.in_progress)
        assert room.hk_status is HkStatus.in_progress


def test_self_assign_start_refuses_an_assigned_room(database, fx):
    with database.session() as db:
        room = _build(db, fx, "dirty")
        with pytest.raises(Conflict):
            hk_transitions.self_assign_start(db, fx.property_a.id, fx.supervisor_a.id, room.id)


def test_each_mutation_emits_exactly_one_event(database, fx, events):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
    events.clear()
    with database.session() as db:
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and hk[0].payload == {"ids": [room.id]}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_transitions.py -q`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `server/app/domain/hk_transitions.py`**

```python
"""The housekeeping transition table (spec §3.3). Anything not implemented here is a 409."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app import clock
from app.auth.permissions import has_capability
from app.domain import hk_assignments, hk_rooms, notifications
from app.errors import Conflict, Forbidden, TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Room
from app.schemas.enums import (
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    Role,
    RoomEventType,
)

OUT = (HkStatus.out_of_order, HkStatus.out_of_service)


def _clean_note(note: str | None) -> str | None:
    return (note or "").strip() or None


def _code(db: Session, room: Room) -> str:
    return hk_rooms.unit_of(db, room).code


def mark_dirty(db: Session, property_id: str, actor_id: str, room_id: str,
               note: str | None) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if room.hk_status == HkStatus.clean:
        raise TransitionError("This room is awaiting inspection — a supervisor must fail the "
                              "inspection to send it back")
    if room.hk_status != HkStatus.inspected:
        raise TransitionError(f"A room that is {room.hk_status.value} cannot be marked dirty")
    room.service_type = hk_rooms.service_type_for(hk_rooms.occupancy_of(db, room))
    hk_rooms.set_status(db, room, HkStatus.dirty, actor_id,
                        event_type=RoomEventType.marked_dirty, comment=_clean_note(note))
    hk_rooms.emit(db, property_id, [room.id])
    return room


def set_rush(db: Session, property_id: str, actor_id: str, room_id: str, on: bool) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if on:
        if room.hk_status not in (HkStatus.dirty, HkStatus.in_progress):
            raise TransitionError("Only a room waiting to be cleaned can be rushed")
        if room.rush:
            return room
        room.rush = True
        hk_rooms.record(db, room, RoomEventType.rush_set, actor_id)
        notifications.notify_users(db, property_id, hk_rooms.hk_supervisors(db, property_id),
                                   "hk.rush", f"Rush: Room {_code(db, room)}",
                                   entity_type="room", entity_id=room.id)
    else:
        if not room.rush:
            return room
        room.rush = False
        hk_rooms.record(db, room, RoomEventType.rush_cleared, actor_id)
    hk_rooms.emit(db, property_id, [room.id])
    return room


def set_room_status(db: Session, property_id: str, actor_id: str, room_id: str,
                    status: HkStatus, note: str | None) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if status in OUT:
        if room.hk_status == status:
            raise TransitionError(f"The room is already {status.value}")
        current = hk_rooms.open_assignment(db, room, hk_rooms.today(db, property_id))
        if current:
            hk_rooms.delete_assignment(db, current)
        room.rush = False
    elif status == HkStatus.dirty:
        if room.hk_status not in OUT:
            raise TransitionError("Only an out-of-order or out-of-service room can be put back "
                                  "in service; use Mark dirty otherwise")
        room.service_type = hk_rooms.service_type_for(hk_rooms.occupancy_of(db, room))
    else:
        raise ValidationFailed("Unsupported status", details={"status": "unsupported"})
    hk_rooms.set_status(db, room, status, actor_id, comment=_clean_note(note))
    hk_rooms.emit(db, property_id, [room.id])
    return room


def require_owner_or_manager(a: HousekeepingAssignment, actor_id: str, role: Role) -> None:
    if a.housekeeper_user_id != actor_id and not has_capability(role, "manage_housekeeping"):
        raise Forbidden("That room is assigned to someone else")


def _begin(db: Session, room: Room, a: HousekeepingAssignment, actor_id: str) -> None:
    a.status = HkAssignmentStatus.in_progress
    a.started_at = clock.now()
    hk_rooms.set_status(db, room, HkStatus.in_progress, actor_id,
                        event_type=RoomEventType.started, assignment_id=a.id)
    hk_rooms.emit(db, room.property_id, [room.id])


def start(db: Session, property_id: str, actor_id: str, role: Role,
          assignment_id: str) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    require_owner_or_manager(a, actor_id, role)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.assigned or room.hk_status != HkStatus.dirty:
        raise TransitionError("Only an assigned, dirty room can be started")
    _begin(db, room, a, actor_id)
    return a


def complete(db: Session, property_id: str, actor_id: str, role: Role,
             assignment_id: str) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    require_owner_or_manager(a, actor_id, role)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.in_progress or room.hk_status != HkStatus.in_progress:
        raise TransitionError("Only a room in progress can be marked ready")
    now = clock.now()
    a.status = HkAssignmentStatus.done
    a.completed_at = now
    room.last_cleaned_at = now
    hk_rooms.set_status(db, room, HkStatus.clean, actor_id,
                        event_type=RoomEventType.completed, assignment_id=a.id)
    notifications.notify_users(db, property_id, hk_rooms.hk_supervisors(db, property_id),
                               "hk.ready_for_inspection",
                               f"Ready for inspection: Room {_code(db, room)}",
                               entity_type="room", entity_id=room.id)
    hk_rooms.emit(db, property_id, [room.id])
    return a


def inspect(db: Session, property_id: str, actor_id: str, assignment_id: str,
            result: Literal["pass", "fail"], note: str | None) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.done or room.hk_status != HkStatus.clean:
        raise TransitionError("Only a room awaiting inspection can be inspected")
    note = _clean_note(note)
    if result == "fail" and not note:
        raise ValidationFailed("A note is required when failing an inspection",
                               details={"note": "required"})
    now = clock.now()
    a.inspected_by_user_id = actor_id
    a.inspected_at = now
    a.inspection_note = note
    if result == "pass":
        a.status = HkAssignmentStatus.passed
        room.rush = False
        room.last_inspected_at = now
        hk_rooms.set_status(db, room, HkStatus.inspected, actor_id,
                            event_type=RoomEventType.inspection_passed, assignment_id=a.id,
                            comment=note)
    else:
        # The same row goes back (spec §2.2): one row tells the room's whole day.
        a.status = HkAssignmentStatus.assigned
        a.fail_count += 1
        a.started_at = None
        a.completed_at = None
        hk_rooms.set_status(db, room, HkStatus.dirty, actor_id,
                            event_type=RoomEventType.inspection_failed, assignment_id=a.id,
                            comment=note)
        notifications.notify_users(db, property_id, [a.housekeeper_user_id],
                                   "hk.inspection_failed",
                                   f"Room {_code(db, room)} failed inspection", body=note[:140],
                                   entity_type="room", entity_id=room.id)
    hk_rooms.emit(db, property_id, [room.id])
    return a


def self_assign_start(db: Session, property_id: str, actor_id: str,
                      room_id: str) -> HousekeepingAssignment:
    """Supervisors clean rooms too (spec §3.3): assign to self and start in one step."""
    room = hk_rooms.get(db, property_id, room_id)
    if room.hk_status != HkStatus.dirty:
        raise TransitionError("Only a dirty room can be started")
    day = hk_rooms.today(db, property_id)
    if hk_rooms.open_assignment(db, room, day):
        raise Conflict("This room is already assigned — start it from the assignment")
    a = HousekeepingAssignment(
        property_id=property_id, room_id=room.id, housekeeper_user_id=actor_id, shift_date=day,
        sequence=hk_rooms.next_sequence(db, property_id, actor_id, day),
        type=room.service_type or HkServiceType.departure, status=HkAssignmentStatus.assigned,
        fail_count=0)
    db.add(a)
    db.flush()
    hk_rooms.record(db, room, RoomEventType.assigned, actor_id, assignment_id=a.id,
                    to_value=actor_id)
    _begin(db, room, a, actor_id)
    return a
```

- [ ] **Step 4: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_transitions.py -q`
Expected: PASS (48 matrix cases plus the named tests).

- [ ] **Step 5: Lint and commit**

```bash
cd server && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/app/domain/hk_transitions.py server/tests/test_hk_transitions.py
git commit -m "feat(housekeeping): transition table with a 409 for everything unlisted"
```

---

### Task 7: Photos

**Files:**
- Create: `server/app/domain/hk_photos.py`
- Test: `server/tests/test_hk_photos.py`

**Interfaces:**
- Consumes: `hk_assignments.get`, `hk_transitions.require_owner_or_manager`, `hk_rooms.emit`,
  `app.domain.work_orders.MAX_PHOTO_BYTES`, `sniff_image_type`.
- Produces (in `app.domain.hk_photos`):
  - `attach(db, property_id, actor_id, role: Role, assignment_id, *, data: bytes) ->
    HousekeepingPhoto`
  - `get_photo(db, property_id, assignment_id, photo_id) -> HousekeepingPhoto` (NotFound)
  - `photo_url(property_id, assignment_id, photo_id) -> str`
  - `photos_for(db, assignment_ids: list[str]) -> dict[str, list[HousekeepingPhoto]]`

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_photos.py`:

```python
"""Housekeeper photos (spec §2.4): bytes in the table, same cap and sniffing as work orders."""
import pytest

from app.domain import hk_assignments, hk_photos, hk_transitions
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import Forbidden, NotFound, TransitionError, ValidationFailed
from app.schemas.enums import Role
from tests.hk_helpers import make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"
GIF = b"GIF89a" + b"\x00" * 40


def _assignment(db, fx, start=True):
    room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
    hk_transitions.mark_dirty(db, fx.property_a.id, fx.supervisor_a.id, room.id, None)
    (a,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                 fx.housekeeper_a.id)
    if start:
        hk_transitions.start(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id)
    return a


def test_attach_stores_the_bytes_while_in_progress(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        photo = hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=PNG)
        assert (photo.content_type, photo.byte_size) == ("image/png", len(PNG))
        assert hk_photos.get_photo(db, fx.property_a.id, a.id, photo.id).data == PNG
        assert hk_photos.photos_for(db, [a.id])[a.id] == [photo]


def test_attach_refuses_bad_input_without_a_500(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        for data in (b"", GIF, PNG + b"\x00" * MAX_PHOTO_BYTES):
            with pytest.raises(ValidationFailed):
                hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=data)
        with pytest.raises(Forbidden):
            hk_photos.attach(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, a.id,
                             data=PNG)


def test_photos_only_while_the_room_is_being_cleaned(database, fx):
    with database.session() as db:
        a = _assignment(db, fx, start=False)
        with pytest.raises(TransitionError):
            hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id,
                             data=PNG)


def test_get_photo_is_scoped_by_property_and_assignment(database, fx):
    with database.session() as db:
        a = _assignment(db, fx)
        photo = hk_photos.attach(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                                 a.id, data=PNG)
        with pytest.raises(NotFound):
            hk_photos.get_photo(db, fx.property_b.id, a.id, photo.id)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_photos.py -q`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement `server/app/domain/hk_photos.py`**

```python
"""Housekeeper photos (spec §2.4). Bytes in the table with `data` deferred, exactly as
work_order_photo and pm_run_photo, because the deployment filesystem is ephemeral."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, hk_assignments, hk_rooms, hk_transitions
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import HousekeepingPhoto
from app.schemas.enums import HkAssignmentStatus, Role


def attach(db: Session, property_id: str, actor_id: str, role: Role, assignment_id: str, *,
           data: bytes) -> HousekeepingPhoto:
    a = hk_assignments.get(db, property_id, assignment_id)
    hk_transitions.require_owner_or_manager(a, actor_id, role)
    if a.status != HkAssignmentStatus.in_progress:
        raise TransitionError("Photos can only be added while the room is being cleaned")
    if not data:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    if len(data) > MAX_PHOTO_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    content_type = sniff_image_type(data)
    if content_type is None:
        raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                               details={"photo": "unsupported_image_type"})
    photo = HousekeepingPhoto(assignment_id=a.id, property_id=property_id,
                              uploaded_by_user_id=actor_id, content_type=content_type,
                              byte_size=len(data), data=data)
    db.add(photo)
    db.flush()
    audit.record(db, property_id, actor_id, "housekeeping.photo_attached", "housekeeping_photo",
                 photo.id, after={"assignment_id": a.id, "byte_size": len(data)})
    hk_rooms.emit(db, property_id, [a.room_id])
    return photo


def get_photo(db: Session, property_id: str, assignment_id: str,
              photo_id: str) -> HousekeepingPhoto:
    """Scoped by property and assignment, never by the guessable id alone."""
    photo = db.scalar(select(HousekeepingPhoto).where(
        HousekeepingPhoto.id == photo_id, HousekeepingPhoto.property_id == property_id,
        HousekeepingPhoto.assignment_id == assignment_id))
    if photo is None:
        raise NotFound("Photo not found")
    return photo


def photo_url(property_id: str, assignment_id: str, photo_id: str) -> str:
    return f"/api/p/{property_id}/housekeeping/assignments/{assignment_id}/photos/{photo_id}"


def photos_for(db: Session, assignment_ids: list[str]) -> dict[str, list[HousekeepingPhoto]]:
    out: dict[str, list[HousekeepingPhoto]] = defaultdict(list)
    if not assignment_ids:
        return out
    for p in db.scalars(select(HousekeepingPhoto)
                        .where(HousekeepingPhoto.assignment_id.in_(assignment_ids))
                        .order_by(HousekeepingPhoto.created_at, HousekeepingPhoto.id)):
        out[p.assignment_id].append(p)
    return out
```

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_photos.py -q && ../.venv/Scripts/python.exe -m ruff check .` → PASS.

```bash
git add server/app/domain/hk_photos.py server/tests/test_hk_photos.py
git commit -m "feat(housekeeping): assignment photos stored in the database"
```

---

### Task 8: Wire models and read models (board, my rooms, detail, inspection queue)

**Files:**
- Create: `server/app/schemas/housekeeping.py`
- Create: `server/app/domain/hk_views.py`
- Test: `server/tests/test_hk_views.py`

**Interfaces:**
- Consumes: `hk_rooms.*`, `hk_photos.photos_for`, `hk_photos.photo_url`.
- Produces:
  - Schemas: `HkAssignmentOut`, `HkRoomOut`, `HkSummaryOut`, `HkHousekeeperOut`, `HkBoardOut`,
    `HkPhotoOut`, `HkEventOut`, `HkRoomDetailOut`, `HkInspectionRowOut`, `HkMarkDirtyRequest`,
    `HkStatusRequest`, `HkAssignRequest`, `HkReorderRequest`, `HkInspectRequest`.
  - In `app.domain.hk_views`: `board(db, property_id) -> HkBoardOut`,
    `my_rooms(db, property_id, user_id) -> list[HkRoomOut]`,
    `room_detail(db, property_id, room_id) -> HkRoomDetailOut`,
    `room_row(db, property_id, room_id) -> HkRoomOut`,
    `inspections(db, property_id) -> list[HkInspectionRowOut]`,
    `assignment_out(db, a) -> HkAssignmentOut`.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_views.py`:

```python
"""Read models (spec §4.1, §4.3; plan clarifications 2 and 5)."""
from datetime import timedelta

from app import clock
from app.domain import hk_assignments, hk_photos, hk_transitions, hk_views
from app.models import HousekeepingAssignment, MaintainableUnit
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    Role,
    StayStatus,
)
from tests.hk_helpers import add_stay, local_today, make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _dirty_and_assign(db, fx, codes):
    rooms = make_rooms(db, fx.property_a.id, codes=codes)
    for r in rooms.values():
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.supervisor_a.id, r.id, None)
    out = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                [r.id for r in rooms.values()], fx.housekeeper_a.id)
    return rooms, out


def test_board_rows_occupancy_summary_and_housekeepers(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "PH"))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2), first="Sarah", last="Chen")
        hk_transitions.mark_dirty(db, pid, fx.agent_a.id, rooms["101"].id, None)
        hk_transitions.set_room_status(db, pid, fx.supervisor_a.id, rooms["103"].id,
                                       HkStatus.out_of_order, "Leak")
        hk_assignments.assign(db, pid, fx.supervisor_a.id, [rooms["101"].id],
                              fx.housekeeper_a.id)
        out = hk_views.board(db, pid)
        assert [r.code for r in out.rooms] == ["101", "102", "103", "PH"]
        r101 = out.rooms[0]
        assert (r101.occupancy, r101.guest_name) == (HkOccupancy.stayover, "Sarah Chen")
        assert r101.assignment.housekeeper_name == "Hana Keeper"
        assert out.rooms[3].floor is None
        s = out.summary
        assert (s.dirty, s.in_progress, s.awaiting_inspection, s.inspected, s.out_of_order) \
            == (1, 0, 0, 2, 1)
        assert sum((s.dirty, s.in_progress, s.awaiting_inspection, s.inspected,
                    s.out_of_order)) == len(out.rooms)
        assert [(h.name, h.assigned, h.done) for h in out.housekeepers] == [
            ("Hana Keeper", 1, 0)]


def test_my_rooms_is_rush_first_then_sequence_and_only_mine(database, fx):
    with database.session() as db:
        rooms, assigned = _dirty_and_assign(db, fx, ("101", "102", "103"))
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["103"].id, True)
        mine = hk_views.my_rooms(db, fx.property_a.id, fx.housekeeper_a.id)
        assert [r.code for r in mine] == ["103", "101", "102"]
        assert hk_views.my_rooms(db, fx.property_a.id, fx.engineer_a.id) == []


def test_room_detail_history_names_people_and_caps_at_thirty(database, fx):
    with database.session() as db:
        rooms, (a,) = _dirty_and_assign(db, fx, ("101",))
        for _ in range(20):
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["101"].id, True)
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["101"].id, False)
        detail = hk_views.room_detail(db, fx.property_a.id, rooms["101"].id)
        assert len(detail.events) == 30
        assert all(e.user_name for e in detail.events)


def test_assignment_events_show_names_not_ids(database, fx):
    with database.session() as db:
        rooms, _ = _dirty_and_assign(db, fx, ("101",))
        detail = hk_views.room_detail(db, fx.property_a.id, rooms["101"].id)
        ev = next(e for e in detail.events if e.type.value == "assigned")
        assert ev.to_value == "Hana Keeper"


def test_inspection_queue_is_oldest_first_with_photos(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        rooms, (a1, a2) = _dirty_and_assign(db, fx, ("101", "102"))
        for a in (a2, a1):  # 102 finishes first
            hk_transitions.start(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id)
            if a is a2:
                hk_photos.attach(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id, data=PNG)
            hk_transitions.complete(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id)
            clock.freeze(clock.now() + timedelta(minutes=20))
        queue = hk_views.inspections(db, pid)
        assert [row.room.code for row in queue] == ["102", "101"]
        assert len(queue[0].photos) == 1 and queue[0].photos[0].url.endswith(
            f"/photos/{queue[0].photos[0].id}")


def test_deactivated_unit_leaves_the_board_and_comes_back_as_the_same_row(database, fx):
    with database.session() as db:
        rooms = make_rooms(db, fx.property_a.id, codes=("101",))
        unit = db.get(MaintainableUnit, rooms["101"].unit_id)
        unit.active = False
        db.flush()
        assert hk_views.board(db, fx.property_a.id).rooms == []
        unit.active = True
        db.flush()
        assert hk_views.board(db, fx.property_a.id).rooms[0].id == rooms["101"].id


def test_yesterdays_uninspected_clean_shows_but_a_stale_done_never_does(database, fx):
    """Plan clarification 5."""
    with database.session() as db:
        pid = fx.property_a.id
        yesterday = local_today(db, pid) - timedelta(days=1)
        rooms = make_rooms(db, pid, codes=("101", "102"))
        for code, status in (("101", HkStatus.clean), ("102", HkStatus.dirty)):
            rooms[code].hk_status = status
            db.add(HousekeepingAssignment(
                property_id=pid, room_id=rooms[code].id, housekeeper_user_id=fx.housekeeper_a.id,
                shift_date=yesterday, sequence=1, type=HkServiceType.departure,
                status=HkAssignmentStatus.done, completed_at=clock.now() - timedelta(hours=14)))
        db.flush()
        board = {r.code: r for r in hk_views.board(db, pid).rooms}
        assert board["101"].assignment is not None
        assert board["102"].assignment is None
        assert [row.room.code for row in hk_views.inspections(db, pid)] == ["101"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_views.py -q`
Expected: FAIL — ImportError.

- [ ] **Step 3: Create `server/app/schemas/housekeeping.py`**

```python
"""Housekeeping wire models (spec §4). Prefixed `Hk`: the exported JSON schema is flat and PM
already owns InspectRequest / InspectionRowOut."""
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    RoomEventType,
)


class HkAssignmentOut(CamelModel):
    id: str
    room_id: str
    housekeeper_user_id: str
    housekeeper_name: str | None = None
    shift_date: date
    sequence: int
    type: HkServiceType
    status: HkAssignmentStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None
    inspection_note: str | None = None
    fail_count: int


class HkRoomOut(CamelModel):
    id: str
    unit_id: str
    code: str
    floor: int | None = None
    room_type: str | None = None
    hk_status: HkStatus
    service_type: HkServiceType | None = None
    rush: bool
    occupancy: HkOccupancy
    guest_name: str | None = None
    departure_date: date | None = None
    status_changed_at: datetime
    last_cleaned_at: datetime | None = None
    last_inspected_at: datetime | None = None
    notes: str | None = None
    assignment: HkAssignmentOut | None = None


class HkSummaryOut(CamelModel):
    dirty: int
    in_progress: int
    awaiting_inspection: int
    inspected: int
    out_of_order: int  # out of order + out of service


class HkHousekeeperOut(CamelModel):
    user_id: str
    name: str
    assigned: int
    done: int


class HkBoardOut(CamelModel):
    rooms: list[HkRoomOut]
    summary: HkSummaryOut
    housekeepers: list[HkHousekeeperOut]


class HkPhotoOut(CamelModel):
    id: str
    content_type: str
    byte_size: int
    url: str
    created_at: datetime


class HkEventOut(CamelModel):
    id: str
    type: RoomEventType
    from_value: str | None = None
    to_value: str | None = None
    comment: str | None = None
    user_name: str | None = None
    created_at: datetime


class HkRoomDetailOut(CamelModel):
    room: HkRoomOut
    events: list[HkEventOut]
    photos: list[HkPhotoOut]


class HkInspectionRowOut(CamelModel):
    room: HkRoomOut
    photos: list[HkPhotoOut]


class HkMarkDirtyRequest(CamelModel):
    note: str | None = Field(default=None, max_length=2000)


class HkStatusRequest(CamelModel):
    status: Literal["out_of_order", "out_of_service", "dirty"]
    note: str | None = Field(default=None, max_length=2000)


class HkAssignRequest(CamelModel):
    room_ids: list[str] = Field(min_length=1, max_length=500)
    housekeeper_user_id: str


class HkReorderRequest(CamelModel):
    housekeeper_user_id: str
    assignment_ids: list[str] = Field(min_length=1, max_length=500)


class HkInspectRequest(CamelModel):
    result: Literal["pass", "fail"]
    note: str | None = Field(default=None, max_length=2000)
```

- [ ] **Step 4: Create `server/app/domain/hk_views.py`**

```python
"""Housekeeping read models (spec §4.1). Everything the three screens render comes from here."""
from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import hk_photos, hk_rooms, pm_cycles
from app.models import (
    Department,
    HousekeepingAssignment,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    RoomEvent,
    UserAccount,
)
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkStatus,
    RoomEventType,
    UserStatus,
)
from app.schemas.housekeeping import (
    HkAssignmentOut,
    HkBoardOut,
    HkEventOut,
    HkHousekeeperOut,
    HkInspectionRowOut,
    HkPhotoOut,
    HkRoomDetailOut,
    HkRoomOut,
    HkSummaryOut,
)

HISTORY = 30
_PERSON_EVENTS = (RoomEventType.assigned, RoomEventType.reassigned, RoomEventType.unassigned)
_DONE = (HkAssignmentStatus.done, HkAssignmentStatus.passed)


def _pick(db: Session, property_id: str, rooms: dict[str, Room],
          day: date) -> dict[str, HousekeepingAssignment]:
    """The assignment each room displays (plan clarification 5): today's open one; else, for a
    `clean` room, its latest `done` from any day; else today's latest passed one."""
    if not rooms:
        return {}
    rows = db.scalars(
        select(HousekeepingAssignment)
        .where(HousekeepingAssignment.property_id == property_id,
               HousekeepingAssignment.room_id.in_(list(rooms)),
               or_(HousekeepingAssignment.shift_date == day,
                   HousekeepingAssignment.status == HkAssignmentStatus.done))
        .order_by(HousekeepingAssignment.shift_date.desc(),
                  HousekeepingAssignment.created_at.desc(), HousekeepingAssignment.id.desc()))
    picked: dict[str, HousekeepingAssignment] = {}
    for a in rows:
        if a.shift_date != day and rooms[a.room_id].hk_status != HkStatus.clean:
            continue  # a stale done row never shows on a room that has moved on
        current = picked.get(a.room_id)
        if current is None or (current.status == HkAssignmentStatus.passed
                               and a.status != HkAssignmentStatus.passed):
            picked[a.room_id] = a
    return picked


def _names_for_assignments(db: Session, rows) -> dict[str, str]:
    return hk_rooms.names_for(db, [a.housekeeper_user_id for a in rows]
                              + [a.inspected_by_user_id for a in rows])


def _assignment_out(a: HousekeepingAssignment, names: dict[str, str]) -> HkAssignmentOut:
    return HkAssignmentOut(
        id=a.id, room_id=a.room_id, housekeeper_user_id=a.housekeeper_user_id,
        housekeeper_name=names.get(a.housekeeper_user_id), shift_date=a.shift_date,
        sequence=a.sequence, type=a.type, status=a.status, started_at=a.started_at,
        completed_at=a.completed_at, inspected_by_name=names.get(a.inspected_by_user_id or ""),
        inspected_at=a.inspected_at, inspection_note=a.inspection_note, fail_count=a.fail_count)


def assignment_out(db: Session, a: HousekeepingAssignment) -> HkAssignmentOut:
    return _assignment_out(a, _names_for_assignments(db, [a]))


def _room_out(room: Room, unit: MaintainableUnit, occ: hk_rooms.Occupancy,
              a: HousekeepingAssignment | None, names: dict[str, str]) -> HkRoomOut:
    return HkRoomOut(
        id=room.id, unit_id=unit.id, code=unit.code, floor=unit.floor, room_type=unit.room_type,
        hk_status=room.hk_status, service_type=room.service_type, rush=room.rush,
        occupancy=occ.kind, guest_name=occ.guest_name, departure_date=occ.departure_date,
        status_changed_at=room.status_changed_at, last_cleaned_at=room.last_cleaned_at,
        last_inspected_at=room.last_inspected_at, notes=room.notes,
        assignment=_assignment_out(a, names) if a else None)


def _rows(db: Session, property_id: str,
          pairs: list[tuple[Room, MaintainableUnit]] | None = None) -> tuple[date, list[HkRoomOut]]:
    prop = db.get(Property, property_id)
    day = pm_cycles.local_today(prop)
    pairs = hk_rooms.active_rooms(db, property_id) if pairs is None else pairs
    occupancy = hk_rooms.occupancy_by_code(db, prop)
    picked = _pick(db, property_id, {r.id: r for r, _ in pairs}, day)
    names = _names_for_assignments(db, list(picked.values()))
    return day, [_room_out(r, u, occupancy.get(u.code, hk_rooms.VACANT), picked.get(r.id), names)
                 for r, u in pairs]


def _housekeepers(db: Session, property_id: str, day: date) -> list[HkHousekeeperOut]:
    people = db.execute(
        select(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .where(PropertyMembership.property_id == property_id,
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)
        .order_by(UserAccount.first_name, UserAccount.last_name, UserAccount.id)).all()
    today = db.scalars(select(HousekeepingAssignment).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.shift_date == day)).all()
    assigned = Counter(a.housekeeper_user_id for a in today)
    done = Counter(a.housekeeper_user_id for a in today if a.status in _DONE)
    return [HkHousekeeperOut(user_id=uid, name=f"{first} {last}", assigned=assigned[uid],
                             done=done[uid]) for uid, first, last in people]


def board(db: Session, property_id: str) -> HkBoardOut:
    day, rooms = _rows(db, property_id)
    count = Counter(r.hk_status for r in rooms)
    summary = HkSummaryOut(
        dirty=count[HkStatus.dirty], in_progress=count[HkStatus.in_progress],
        awaiting_inspection=count[HkStatus.clean], inspected=count[HkStatus.inspected],
        out_of_order=count[HkStatus.out_of_order] + count[HkStatus.out_of_service])
    return HkBoardOut(rooms=rooms, summary=summary,
                      housekeepers=_housekeepers(db, property_id, day))


def my_rooms(db: Session, property_id: str, user_id: str) -> list[HkRoomOut]:
    day, rooms = _rows(db, property_id)
    mine = [r for r in rooms if r.assignment and r.assignment.housekeeper_user_id == user_id
            and r.assignment.shift_date == day]
    return sorted(mine, key=lambda r: (not r.rush, r.assignment.sequence))


def room_row(db: Session, property_id: str, room_id: str) -> HkRoomOut:
    room = hk_rooms.get(db, property_id, room_id)
    _, (row,) = _rows(db, property_id, [(room, hk_rooms.unit_of(db, room))])
    return row


def _photos_out(property_id: str, assignment_id: str, photos) -> list[HkPhotoOut]:
    return [HkPhotoOut(id=p.id, content_type=p.content_type, byte_size=p.byte_size,
                       url=hk_photos.photo_url(property_id, assignment_id, p.id),
                       created_at=p.created_at) for p in photos]


def room_detail(db: Session, property_id: str, room_id: str) -> HkRoomDetailOut:
    row = room_row(db, property_id, room_id)
    events = db.scalars(select(RoomEvent).where(RoomEvent.room_id == row.id)
                        .order_by(RoomEvent.created_at.desc(), RoomEvent.id.desc())
                        .limit(HISTORY)).all()
    people = [e.user_id for e in events] + [v for e in events if e.type in _PERSON_EVENTS
                                             for v in (e.from_value, e.to_value)]
    names = hk_rooms.names_for(db, people)

    def person(e: RoomEvent, value: str | None) -> str | None:
        return names.get(value or "", value) if e.type in _PERSON_EVENTS else value

    photos = []
    if row.assignment:
        photos = _photos_out(property_id, row.assignment.id,
                             hk_photos.photos_for(db, [row.assignment.id])[row.assignment.id])
    return HkRoomDetailOut(
        room=row, photos=photos,
        events=[HkEventOut(id=e.id, type=e.type, from_value=person(e, e.from_value),
                           to_value=person(e, e.to_value), comment=e.comment,
                           user_name=names.get(e.user_id or ""), created_at=e.created_at)
                for e in events])


def inspections(db: Session, property_id: str) -> list[HkInspectionRowOut]:
    """Rooms awaiting inspection, oldest finished first, with who cleaned them and photos."""
    _, rooms = _rows(db, property_id)
    waiting = [r for r in rooms if r.hk_status == HkStatus.clean and r.assignment
               and r.assignment.status == HkAssignmentStatus.done]
    photos = hk_photos.photos_for(db, [r.assignment.id for r in waiting])
    waiting.sort(key=lambda r: (r.assignment.completed_at or r.status_changed_at, r.code))
    return [HkInspectionRowOut(room=r, photos=_photos_out(property_id, r.assignment.id,
                                                          photos[r.assignment.id]))
            for r in waiting]
```

- [ ] **Step 5: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_views.py -q && ../.venv/Scripts/python.exe -m ruff check .` → PASS.

```bash
git add server/app/schemas/housekeeping.py server/app/domain/hk_views.py server/tests/test_hk_views.py
git commit -m "feat(housekeeping): wire models and read models for the three screens"
```

---

### Task 9: The blueprint, `departmentType` on the session, schema export

**Files:**
- Create: `server/app/api/housekeeping.py`
- Modify: `server/app/__init__.py` (import + `app.register_blueprint(housekeeping.bp)` after `pm.bp`)
- Modify: `server/app/schemas/auth.py:30-35`, `server/app/api/auth.py:19-33`
- Modify: `server/app/schemas/export_json_schema.py` (`MODULES`)
- Modify: `server/tests/test_schema_export.py:10-17`
- Regenerate: `web/src/api/schema.json`, `web/src/api/types.generated.ts`
- Modify: `web/src/api/types.ts` (re-export the new names), `web/src/test/harness.tsx`
- Test: `server/tests/test_hk_api.py`

**Interfaces:**
- Consumes: every domain module above.
- Produces: the HTTP surface below, and `MembershipOut.department_type` (`departmentType` on the
  wire) for Task 12.

| method + path under `/api/p/<property_id>/housekeeping` | capability | returns |
|---|---|---|
| `GET /board` | view_housekeeping | `HkBoardOut` |
| `GET /my-rooms` | perform_housekeeping | `list[HkRoomOut]` |
| `GET /inspections` | inspect_housekeeping | `list[HkInspectionRowOut]` |
| `GET /rooms/<room_id>` | view_housekeeping | `HkRoomDetailOut` |
| `POST /rooms/<room_id>/mark-dirty` | mark_room_dirty | `HkRoomOut` |
| `POST /rooms/<room_id>/rush`, `DELETE …/rush` | mark_room_dirty | `HkRoomOut` |
| `POST /rooms/<room_id>/status` | manage_housekeeping | `HkRoomOut` |
| `POST /rooms/<room_id>/self-assign-start` | manage_housekeeping | `HkRoomOut` |
| `POST /assignments` | manage_housekeeping | `list[HkAssignmentOut]`, 201 |
| `DELETE /assignments/<assignment_id>` | manage_housekeeping | `HkRoomOut` |
| `POST /assignments/reorder` | manage_housekeeping | `list[HkAssignmentOut]` |
| `POST /assignments/<assignment_id>/start`, `/complete` | perform_housekeeping | `HkRoomOut` |
| `POST /assignments/<assignment_id>/inspect` | inspect_housekeeping | `HkRoomOut` |
| `POST /assignments/<assignment_id>/photos` | perform_housekeeping | `HkRoomDetailOut`, 201 |
| `GET /assignments/<assignment_id>/photos/<photo_id>` | view_housekeeping | image bytes |

- [ ] **Step 1: Write the failing tests** — `server/tests/test_hk_api.py`:

```python
"""The housekeeping HTTP surface (spec §4.1, §4.2)."""
import io

from app.domain import hk_rooms
from app.schemas.enums import HkStatus
from tests.hk_helpers import make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _hk(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/housekeeping{rest}"


def _rooms(database, fx, codes=("101", "102")):
    with database.session() as db:
        return {c: r.id for c, r in make_rooms(db, fx.property_a.id, codes=codes).items()}


def test_the_whole_loop_over_http(database, fx, login):
    rooms = _rooms(database, fx)
    desk, sup, hana = login("agent@hvh.test"), login("supervisor@hvh.test"), \
        login("housekeeper@hvh.test")
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/mark-dirty"),
                     json={"note": "Spill"}).status_code == 200
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/rush")).get_json()["rush"] is True
    res = sup.post(_hk(fx, "/assignments"),
                   json={"roomIds": [rooms["101"]], "housekeeperUserId": fx.housekeeper_a.id})
    assert res.status_code == 201, res.get_json()
    aid = res.get_json()[0]["id"]
    mine = hana.get(_hk(fx, "/my-rooms")).get_json()
    assert [r["code"] for r in mine] == ["101"]
    assert hana.post(_hk(fx, f"/assignments/{aid}/start")).get_json()["hkStatus"] \
        == "in_progress"
    up = hana.post(_hk(fx, f"/assignments/{aid}/photos"),
                   data={"photo": (io.BytesIO(PNG), "p.png", "image/png")},
                   content_type="multipart/form-data")
    assert up.status_code == 201, up.get_json()
    photo_url = up.get_json()["photos"][0]["url"]
    assert hana.post(_hk(fx, f"/assignments/{aid}/complete")).get_json()["hkStatus"] == "clean"
    queue = sup.get(_hk(fx, "/inspections")).get_json()
    assert [row["room"]["code"] for row in queue] == ["101"]
    img = desk.get(photo_url)
    assert img.status_code == 200 and img.data == PNG
    assert sup.post(_hk(fx, f"/assignments/{aid}/inspect"),
                    json={"result": "fail"}).status_code == 400
    passed = sup.post(_hk(fx, f"/assignments/{aid}/inspect"), json={"result": "pass"})
    assert passed.get_json()["hkStatus"] == "inspected" and passed.get_json()["rush"] is False


def test_front_desk_cannot_assign_inspect_or_perform(database, fx, login):
    rooms = _rooms(database, fx)
    desk = login("agent@hvh.test")
    assert desk.post(_hk(fx, "/assignments"), json={
        "roomIds": [rooms["101"]], "housekeeperUserId": fx.housekeeper_a.id}).status_code == 403
    assert desk.get(_hk(fx, "/inspections")).status_code == 403
    assert desk.get(_hk(fx, "/my-rooms")).status_code == 403
    assert desk.post(_hk(fx, f"/rooms/{rooms['101']}/status"),
                     json={"status": "out_of_order"}).status_code == 403
    assert desk.get(_hk(fx, "/board")).status_code == 200


def test_board_summary_agrees_with_the_tiles(database, fx, login):
    _rooms(database, fx, codes=("101", "102", "103"))
    body = login("corporate@hvh.test").get(_hk(fx, "/board")).get_json()
    assert len(body["rooms"]) == 3
    assert sum(body["summary"].values()) == 3 and body["summary"]["inspected"] == 3


def test_assigning_to_engineering_is_a_400(database, fx, login):
    rooms = _rooms(database, fx)
    with database.session() as db:
        hk_rooms.get(db, fx.property_a.id, rooms["101"]).hk_status = HkStatus.dirty
    res = login("supervisor@hvh.test").post(_hk(fx, "/assignments"), json={
        "roomIds": [rooms["101"]], "housekeeperUserId": fx.engineer_a.id})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"housekeeperUserId": "not_housekeeping"}


def test_rooms_of_another_property_are_404_not_leaked(database, fx, login):
    with database.session() as db:
        other = make_rooms(db, fx.property_b.id, codes=("101",))["101"].id
    assert login("admin@hvh.test").get(_hk(fx, f"/rooms/{other}")).status_code == 404


def test_session_carries_the_department_type(fx, login):
    body = login("housekeeper@hvh.test").get("/api/auth/me").get_json()
    assert body["memberships"][0]["departmentType"] == "housekeeping"
```

In `server/tests/test_schema_export.py`, append to the tuple in
`test_export_contains_the_public_models`:

```python
                 "InspectionRowOut", "CycleOut", "ComplianceOut",
                 "HkBoardOut", "HkRoomOut", "HkAssignmentOut", "HkRoomDetailOut",
                 "HkInspectionRowOut", "HkAssignRequest", "HkReorderRequest",
                 "HkInspectRequest", "HkStatusRequest", "HkMarkDirtyRequest"):
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_api.py tests/test_schema_export.py -q`
Expected: FAIL — 404s on every housekeeping route; schema names missing.

- [ ] **Step 3: Create `server/app/api/housekeeping.py`**

```python
"""Housekeeping routes (spec §4.1). Every route: auth + property + a capability."""
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import hk_assignments, hk_photos, hk_transitions, hk_views
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import ValidationFailed
from app.schemas.enums import HkStatus
from app.schemas.housekeeping import (
    HkAssignRequest,
    HkInspectRequest,
    HkMarkDirtyRequest,
    HkReorderRequest,
    HkStatusRequest,
)

bp = Blueprint("housekeeping", __name__, url_prefix="/api/p/<property_id>/housekeeping")

# Defined per-api-module by existing convention (app/api/log.py, app/api/pm.py).
MULTIPART_OVERHEAD_BYTES = 4096


def _read_photo() -> bytes:
    """Mirrors app/api/pm.py: refuse before Werkzeug buffers the body, then read cap + 1."""
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    upload = request.files.get("photo")
    if upload is None:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    return upload.read(MAX_PHOTO_BYTES + 1)


@bp.get("/board")
@require_auth
@require_property
@require_capability("view_housekeeping")
def board(property_id: str):
    with db_session() as db:
        return ok(hk_views.board(db, g.property_id))


@bp.get("/my-rooms")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def my_rooms(property_id: str):
    with db_session() as db:
        return ok(hk_views.my_rooms(db, g.property_id, g.user.id))


@bp.get("/inspections")
@require_auth
@require_property
@require_capability("inspect_housekeeping")
def inspections(property_id: str):
    with db_session() as db:
        return ok(hk_views.inspections(db, g.property_id))


@bp.get("/rooms/<room_id>")
@require_auth
@require_property
@require_capability("view_housekeeping")
def room_detail(property_id: str, room_id: str):
    with db_session() as db:
        return ok(hk_views.room_detail(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/mark-dirty")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def mark_dirty(property_id: str, room_id: str):
    data = parse_body(HkMarkDirtyRequest)
    with db_session() as db:
        hk_transitions.mark_dirty(db, g.property_id, g.user.id, room_id, data.note)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/rush")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def set_rush(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.set_rush(db, g.property_id, g.user.id, room_id, True)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.delete("/rooms/<room_id>/rush")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def clear_rush(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.set_rush(db, g.property_id, g.user.id, room_id, False)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/status")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def set_status(property_id: str, room_id: str):
    data = parse_body(HkStatusRequest)
    with db_session() as db:
        hk_transitions.set_room_status(db, g.property_id, g.user.id, room_id,
                                       HkStatus(data.status), data.note)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/self-assign-start")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def self_assign_start(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.self_assign_start(db, g.property_id, g.user.id, room_id)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/assignments")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def assign(property_id: str):
    data = parse_body(HkAssignRequest)
    with db_session() as db:
        out = hk_assignments.assign(db, g.property_id, g.user.id, data.room_ids,
                                    data.housekeeper_user_id)
        return ok([hk_views.assignment_out(db, a) for a in out], 201)


@bp.post("/assignments/reorder")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def reorder(property_id: str):
    data = parse_body(HkReorderRequest)
    with db_session() as db:
        out = hk_assignments.reorder(db, g.property_id, g.user.id, data.housekeeper_user_id,
                                     data.assignment_ids)
        return ok([hk_views.assignment_out(db, a) for a in out])


@bp.delete("/assignments/<assignment_id>")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def unassign(property_id: str, assignment_id: str):
    with db_session() as db:
        room = hk_assignments.unassign(db, g.property_id, g.user.id, assignment_id)
        return ok(hk_views.room_row(db, g.property_id, room.id))


@bp.post("/assignments/<assignment_id>/start")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def start(property_id: str, assignment_id: str):
    with db_session() as db:
        a = hk_transitions.start(db, g.property_id, g.user.id, g.membership.role, assignment_id)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/complete")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def complete(property_id: str, assignment_id: str):
    with db_session() as db:
        a = hk_transitions.complete(db, g.property_id, g.user.id, g.membership.role,
                                    assignment_id)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/inspect")
@require_auth
@require_property
@require_capability("inspect_housekeeping")
def inspect(property_id: str, assignment_id: str):
    data = parse_body(HkInspectRequest)
    with db_session() as db:
        a = hk_transitions.inspect(db, g.property_id, g.user.id, assignment_id, data.result,
                                   data.note)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/photos")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def add_photo(property_id: str, assignment_id: str):
    data = _read_photo()
    with db_session() as db:
        photo = hk_photos.attach(db, g.property_id, g.user.id, g.membership.role, assignment_id,
                                 data=data)
        room_id = hk_assignments.get(db, g.property_id, photo.assignment_id).room_id
        return ok(hk_views.room_detail(db, g.property_id, room_id), 201)


@bp.get("/assignments/<assignment_id>/photos/<photo_id>")
@require_auth
@require_property
@require_capability("view_housekeeping")
def get_photo(property_id: str, assignment_id: str, photo_id: str):
    with db_session() as db:
        photo = hk_photos.get_photo(db, g.property_id, assignment_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })
```

Register it in `server/app/__init__.py`: add `housekeeping` to the `from app.api import (...)`
list and `app.register_blueprint(housekeeping.bp)` after `app.register_blueprint(pm.bp)`.

- [ ] **Step 4: Put `departmentType` on the session**

`server/app/schemas/auth.py` — `MembershipOut` gains a field (import `DepartmentType`):

```python
class MembershipOut(CamelModel):
    property_id: str
    property_name: str
    property_code: str
    role: Role
    department_id: str | None = None
    # Lets the client land a housekeeping dept_staff on My Rooms (spec §4.3) — role alone cannot
    # tell a housekeeper from an engineer.
    department_type: DepartmentType | None = None
```

`server/app/api/auth.py` — `_session_out` outer-joins the department (import `Department`):

```python
    rows = db.execute(
        select(PropertyMembership, Property, Department.type)
        .join(Property, Property.id == PropertyMembership.property_id)
        .outerjoin(Department, Department.id == PropertyMembership.department_id)
        .where(PropertyMembership.user_id == user.id)
        .order_by(Property.name)
    ).all()
    return SessionOut(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipOut(property_id=p.id, property_name=p.name, property_code=p.code,
                          role=m.role, department_id=m.department_id, department_type=dept_type)
            for m, p, dept_type in rows
        ],
    )
```

- [ ] **Step 5: Export and regenerate**

In `server/app/schemas/export_json_schema.py`, import `housekeeping` with the other schema
modules and append it to `MODULES`. Then:

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

Add to the `export type { ... }` list in `web/src/api/types.ts` (keep it alphabetical):
`HkAssignRequest, HkAssignmentOut, HkAssignmentStatus, HkBoardOut, HkEventOut,
HkHousekeeperOut, HkInspectRequest, HkInspectionRowOut, HkMarkDirtyRequest, HkOccupancy,
HkPhotoOut, HkReorderRequest, HkRoomDetailOut, HkRoomOut, HkServiceType, HkStatus,
HkStatusRequest, HkSummaryOut, RoomEventType`.

In `web/src/test/harness.tsx`, let `sessionFixture` carry the new field — add
`departmentType?: DepartmentType | null` to its options (import `DepartmentType` from
`../api/types`) and `departmentType: opts.departmentType ?? null,` to the first membership, and
`departmentType: null,` to the second.

- [ ] **Step 6: Run everything that could notice**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_hk_api.py tests/test_schema_export.py tests/test_isolation.py tests/test_auth.py -q`
Expected: PASS. `test_isolation.py` must now count the new routes — confirm with
`../.venv/Scripts/python.exe -c "from app import create_app; from app.config import Config; a=create_app(Config(DATABASE_URL='sqlite://', TESTING=True, START_WORKER=False, ENV='testing')); print(sum(1 for r in a.url_map.iter_rules() if '/housekeeping' in r.rule))"`
→ 17 rules (if the Config call needs other fields, copy them from `conftest.py`).

Run: `cd web && npm test && npm run lint && npm run build` → PASS (types compile; the generated-types
staleness test passes).

- [ ] **Step 7: Full server suite, lint, commit**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/app/api/housekeeping.py server/app/__init__.py server/app/schemas/auth.py server/app/api/auth.py server/app/schemas/export_json_schema.py server/tests/test_hk_api.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts web/src/test/harness.tsx
git commit -m "feat(housekeeping): API blueprint, departmentType on the session, schema export"
```

---

### Task 10: Sample data

**Files:**
- Modify: `server/seed/seed.py` (imports; the housekeeping block just before `# ---- recurring
  jobs`; `ensure_recurring` list; `SeedSummary` and its construction)
- Modify: `server/tests/test_seed.py`
- Regenerate: `server/data/app.db`

**Interfaces:**
- Consumes: `hk_rooms`, `hk_tick`, `hk_assignments`, `hk_transitions`, `hk_photos`.
- Produces: `SeedSummary.rooms`, `SeedSummary.hk_assignments`.

- [ ] **Step 1: Write the failing assertions** — in `server/tests/test_seed.py`, inside
`test_seed_matches_spec_counts` after the existing PM assertions (import `Room`,
`HousekeepingAssignment`, `HkStatus`, `HkAssignmentStatus`):

```python
        # housekeeping (spec §6): seeded through the real domain code
        assert count(Room, Room.property_id == hvh.id) == 120
        assert count(Room, Room.property_id == lsi.id) == 0
        assert set(db.scalars(select(Room.hk_status).where(Room.property_id == hvh.id))) \
            == set(HkStatus)  # every board status is on screen
        by_status = lambda s: count(HousekeepingAssignment,  # noqa: E731
                                    HousekeepingAssignment.status == s)
        assert count(HousekeepingAssignment) == 28
        assert by_status(HkAssignmentStatus.passed) == 8
        assert by_status(HkAssignmentStatus.done) == 4
        assert by_status(HkAssignmentStatus.in_progress) == 2
        assert by_status(HkAssignmentStatus.assigned) == 14
        assert count(HousekeepingAssignment, HousekeepingAssignment.fail_count == 1) == 2
        assert count(Room, Room.rush.is_(True)) == 1
        assert count(Room, Room.hk_status == HkStatus.out_of_order) == 2
        assert count(Room, Room.hk_status == HkStatus.out_of_service) == 1
    assert (summary.rooms, summary.hk_assignments) == (120, 28)
```

(Place the final `summary` assertion wherever the test already checks `summary` fields; if it
checks none, put it after the `with` block.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q`
Expected: FAIL — `room` has 0 rows / `SeedSummary` has no `rooms`.

- [ ] **Step 3: Implement the seed block** — `server/seed/seed.py`:

Imports: extend `from app.domain import pm_cycles, staff_messages` to
`from app.domain import hk_assignments, hk_photos, hk_rooms, hk_tick, hk_transitions, pm_cycles, staff_messages`
(wrapped), add `Room`, `HousekeepingAssignment` to the `app.models` import, and `HkStatus`,
`HkServiceType` to the `app.schemas.enums` import (`Role` is already there).

`SeedSummary` gains two fields after `pm_runs: int`:

```python
    rooms: int
    hk_assignments: int
```

and its construction gains:

```python
            rooms=db.scalar(select(func.count()).select_from(Room)),
            hk_assignments=db.scalar(select(func.count()).select_from(HousekeepingAssignment)),
```

Just before `# ---- recurring jobs`, insert:

```python
        # ---- housekeeping (spec §6). Through the domain, never around it: stage "last night",
        # run the real tick, then a mid-shift morning as the seeded users — so a broken
        # transition rule fails the seed loudly instead of seeding an impossible board. Last in
        # the file so the rng draws above it are unchanged.
        hk_rooms.ensure_rooms(db, hvh.id)
        last_night = datetime.combine(pm_cycles.local_today(hvh) - timedelta(days=1), time(18, 0),
                                      tzinfo=ZoneInfo(hvh.timezone))
        for room, _ in hk_rooms.active_rooms(db, hvh.id):
            room.status_changed_at = last_night
        db.flush()
        hk_tick.tick(db)  # dirties the stayovers and today's departures by the real rules

        grace, hana, rosa = staff["hk_sup"], staff["hana"], staff["rosa"]
        dirty = [r for r, _ in hk_rooms.active_rooms(db, hvh.id) if r.hk_status == HkStatus.dirty]
        rng.shuffle(dirty)
        by_keeper = {}
        for keeper, batch in ((hana, dirty[:14]), (rosa, dirty[14:28])):
            assigned = hk_assignments.assign(db, hvh.id, grace.id, [r.id for r in batch],
                                             keeper.id)
            by_keeper[keeper.id] = assigned
            # per housekeeper: 0-3 passed, 4-5 done, 6 in progress, 7 failed back, 8-13 assigned
            for i, a in enumerate(assigned[:8]):
                hk_transitions.start(db, hvh.id, keeper.id, Role.dept_staff, a.id)
                if i == 0:
                    hk_photos.attach(db, hvh.id, keeper.id, Role.dept_staff, a.id,
                                     data=TINY_PNG)
                if i == 6:
                    continue
                hk_transitions.complete(db, hvh.id, keeper.id, Role.dept_staff, a.id)
                if i <= 3:
                    hk_transitions.inspect(db, hvh.id, grace.id, a.id, "pass", None)
                elif i == 7:
                    hk_transitions.inspect(db, hvh.id, grace.id, a.id, "fail",
                                           "Hair in the bathroom sink.")
        waiting = by_keeper[rosa.id][8:]
        rush = next((a for a in waiting if a.type == HkServiceType.departure), waiting[0])
        hk_transitions.set_rush(db, hvh.id, staff["marcus"].id, rush.room_id, True)
        worked = {a.room_id for batch in by_keeper.values() for a in batch}
        vacant = [r for r, _ in hk_rooms.active_rooms(db, hvh.id)
                  if r.hk_status == HkStatus.inspected and r.id not in worked][:3]
        for room, status, note in ((vacant[0], HkStatus.out_of_order, "AC unit leaking, WO open"),
                                   (vacant[1], HkStatus.out_of_order, "AC unit leaking, WO open"),
                                   (vacant[2], HkStatus.out_of_service, "Carpet replacement")):
            hk_transitions.set_room_status(db, hvh.id, grace.id, room.id, status, note)
        db.flush()
```

Add `"housekeeping.tick"` to the tuple in the `ensure_recurring` loop.

> Why 8 passed rooms leave the seed with an `inspected` room still vacant: 120 rooms minus ~85
> occupied leaves ~35 vacant `inspected` rooms before the three go OOO/OOS, so `vacant[:3]`
> always has three. If `test_seed` ever reports fewer than 28 dirty rooms, the stays block
> above changed — do not paper over it here.

- [ ] **Step 4: Run the seed tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py tests/test_dev_start.py -q`
Expected: PASS.

- [ ] **Step 5: Regenerate the tracked fixture database**

```bash
cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('sqlite:///data/app.db', reset=True))"
```

Expected: a `SeedSummary(... rooms=120, hk_assignments=28)` line.

- [ ] **Step 6: Full suite, lint, commit (including `app.db` — a genuine seed change)**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check . && cd ..
git add server/seed/seed.py server/tests/test_seed.py server/data/app.db
git commit -m "feat(housekeeping): seed a mid-shift morning through the real domain code"
```

---

### Task 11: Web data layer — query keys, realtime, hooks

**Files:**
- Modify: `web/src/api/queryKeys.ts`, `web/src/api/ws.ts`
- Create: `web/src/api/hooks/housekeeping.ts`
- Test: `web/src/api/ws.test.tsx`

**Interfaces:**
- Consumes: the Task 9 types from `web/src/api/types.ts`.
- Produces: `qk.hkAll`, `qk.hkBoardAll`, `qk.hkMyRoomsAll`, `qk.hkInspectionsAll`,
  `qk.hkRoom(propertyId, id)`; hooks `useHkBoard`, `useMyRooms`, `useHkRoom(id | null)`,
  `useHkInspections`, and mutations `useMarkDirty` ({roomId, note?}), `useSetRush`
  ({roomId, on}), `useSetRoomStatus` ({roomId, status, note?}), `useAssignRooms`
  (HkAssignRequest), `useUnassign` (assignmentId), `useReorder` (HkReorderRequest),
  `useStartAssignment` (assignmentId), `useCompleteAssignment` (assignmentId),
  `useInspectRoom` ({assignmentId, result, note?}), `useSelfAssignStart` (roomId),
  `useUploadHkPhoto` ({assignmentId, file}).

- [ ] **Step 1: Write the failing test** — add to `web/src/api/ws.test.tsx` next to the PM
cases, using the file's existing `base` (`{ propertyId: 'prop-a', at: … }`):

```ts
  it('refreshes the board, my rooms, the inspection queue and each room for housekeeping.rooms.changed', () => {
    const keys = invalidationsFor(
      { ...base, type: 'housekeeping.rooms.changed', payload: { ids: ['r-1', 'r-2'] } },
      'prop-a',
    )
    expect(keys).toEqual([
      ['hk', 'prop-a', 'board'],
      ['hk', 'prop-a', 'my-rooms'],
      ['hk', 'prop-a', 'inspections'],
      ['hk', 'prop-a', 'room', 'r-1'],
      ['hk', 'prop-a', 'room', 'r-2'],
    ])
  })
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/api/ws.test.tsx` → FAIL (`[]`).

- [ ] **Step 3: Add the keys** — in `web/src/api/queryKeys.ts`, after the PM block:

```ts
  hkAll: (propertyId: string) => ['hk', propertyId] as const,
  hkBoardAll: (propertyId: string) => ['hk', propertyId, 'board'] as const,
  hkMyRoomsAll: (propertyId: string) => ['hk', propertyId, 'my-rooms'] as const,
  hkInspectionsAll: (propertyId: string) => ['hk', propertyId, 'inspections'] as const,
  hkRoom: (propertyId: string, id: string) => ['hk', propertyId, 'room', id] as const,
```

- [ ] **Step 4: Map the event** — in `web/src/api/ws.ts` `invalidationsFor`, before `default:`:

```ts
    case 'housekeeping.rooms.changed': {
      // One event per action, ids only (spec §5): every housekeeping screen refetches.
      keys.push([...qk.hkBoardAll(propertyId)])
      keys.push([...qk.hkMyRoomsAll(propertyId)])
      keys.push([...qk.hkInspectionsAll(propertyId)])
      const ids = event.payload['ids']
      if (Array.isArray(ids)) {
        for (const value of ids) {
          const roomId = str(value)
          if (roomId) keys.push([...qk.hkRoom(propertyId, roomId)])
        }
      }
      break
    }
```

- [ ] **Step 5: Create `web/src/api/hooks/housekeeping.ts`**

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  HkAssignRequest,
  HkAssignmentOut,
  HkBoardOut,
  HkInspectionRowOut,
  HkReorderRequest,
  HkRoomDetailOut,
  HkRoomOut,
} from '../types'

function hkPath(propertyId: string, rest: string): string {
  return propertyPath(propertyId, `housekeeping/${rest}`)
}

export function useHkBoard() {
  const { propertyId } = useSession()
  return useQuery<HkBoardOut, ApiError>({
    queryKey: qk.hkBoardAll(propertyId),
    queryFn: () => api<HkBoardOut>(hkPath(propertyId, 'board')),
  })
}

export function useMyRooms() {
  const { propertyId } = useSession()
  return useQuery<HkRoomOut[], ApiError>({
    queryKey: qk.hkMyRoomsAll(propertyId),
    queryFn: () => api<HkRoomOut[]>(hkPath(propertyId, 'my-rooms')),
  })
}

export function useHkRoom(roomId: string | null) {
  const { propertyId } = useSession()
  return useQuery<HkRoomDetailOut, ApiError>({
    queryKey: qk.hkRoom(propertyId, roomId ?? ''),
    queryFn: () => api<HkRoomDetailOut>(hkPath(propertyId, `rooms/${roomId}`)),
    enabled: roomId !== null,
  })
}

export function useHkInspections() {
  const { propertyId } = useSession()
  return useQuery<HkInspectionRowOut[], ApiError>({
    queryKey: qk.hkInspectionsAll(propertyId),
    queryFn: () => api<HkInspectionRowOut[]>(hkPath(propertyId, 'inspections')),
  })
}

/** Every housekeeping mutation refreshes every housekeeping query: the realtime event will do
 *  the same a moment later, but the actor should not wait for the round trip. */
function useHkMutation<TVars, TOut>(fn: (propertyId: string, vars: TVars) => Promise<TOut>) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TOut, ApiError, TVars>({
    mutationFn: (vars) => fn(propertyId, vars),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.hkAll(propertyId) })
    },
  })
}

export const useMarkDirty = () =>
  useHkMutation<{ roomId: string; note?: string | null }, HkRoomOut>((p, { roomId, note }) =>
    api(hkPath(p, `rooms/${roomId}/mark-dirty`), { method: 'POST', json: { note: note ?? null } }),
  )

export const useSetRush = () =>
  useHkMutation<{ roomId: string; on: boolean }, HkRoomOut>((p, { roomId, on }) =>
    api(hkPath(p, `rooms/${roomId}/rush`), { method: on ? 'POST' : 'DELETE' }),
  )

export const useSetRoomStatus = () =>
  useHkMutation<
    { roomId: string; status: 'out_of_order' | 'out_of_service' | 'dirty'; note?: string | null },
    HkRoomOut
  >((p, { roomId, status, note }) =>
    api(hkPath(p, `rooms/${roomId}/status`), { method: 'POST', json: { status, note: note ?? null } }),
  )

export const useAssignRooms = () =>
  useHkMutation<HkAssignRequest, HkAssignmentOut[]>((p, body) =>
    api(hkPath(p, 'assignments'), { method: 'POST', json: body }),
  )

export const useUnassign = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}`), { method: 'DELETE' }),
  )

export const useReorder = () =>
  useHkMutation<HkReorderRequest, HkAssignmentOut[]>((p, body) =>
    api(hkPath(p, 'assignments/reorder'), { method: 'POST', json: body }),
  )

export const useStartAssignment = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}/start`), { method: 'POST' }),
  )

export const useCompleteAssignment = () =>
  useHkMutation<string, HkRoomOut>((p, assignmentId) =>
    api(hkPath(p, `assignments/${assignmentId}/complete`), { method: 'POST' }),
  )

export const useInspectRoom = () =>
  useHkMutation<{ assignmentId: string; result: 'pass' | 'fail'; note?: string | null }, HkRoomOut>(
    (p, { assignmentId, result, note }) =>
      api(hkPath(p, `assignments/${assignmentId}/inspect`), {
        method: 'POST',
        json: { result, note: note ?? null },
      }),
  )

export const useSelfAssignStart = () =>
  useHkMutation<string, HkRoomOut>((p, roomId) =>
    api(hkPath(p, `rooms/${roomId}/self-assign-start`), { method: 'POST' }),
  )

export const useUploadHkPhoto = () =>
  useHkMutation<{ assignmentId: string; file: File }, HkRoomDetailOut>((p, { assignmentId, file }) => {
    const form = new FormData()
    form.set('photo', file)
    return api(hkPath(p, `assignments/${assignmentId}/photos`), { method: 'POST', body: form })
  })
```

- [ ] **Step 6: Run, lint, build, commit**

Run: `cd web && npx vitest run src/api/ws.test.tsx && npm run lint && npm run build` → PASS.

```bash
git add web/src/api/queryKeys.ts web/src/api/ws.ts web/src/api/ws.test.tsx web/src/api/hooks/housekeeping.ts
git commit -m "feat(housekeeping): web query keys, realtime invalidation and hooks"
```

---

### Task 12: Landing screen and navigation

**Files:**
- Modify: `web/src/auth/capabilities.ts` (`landingPath`), `web/src/auth/capabilities.test.ts`
- Modify: `web/src/routes.tsx:22-37`, `web/src/components/AppShell.tsx:97`,
  `web/src/components/CommandPalette.tsx:73`, `web/src/features/login/LoginPage.tsx:22`
- Modify: `web/src/components/navModel.ts`, `web/src/components/navModel.test.ts`,
  `web/src/components/NavIcon.tsx`

**Interfaces:**
- Consumes: `MembershipOut.departmentType` (Task 9).
- Produces: `landingPath(membership: Pick<MembershipOut, 'role' | 'departmentType'>): string`;
  nav entries to `/app/housekeeping`, `/app/my-rooms`, `/app/room-inspection`.

- [ ] **Step 1: Write the failing tests**

In `web/src/auth/capabilities.test.ts`, rewrite every existing `landingPath('x')` call as
`landingPath({ role: 'x' })` (same expectations), then add:

```ts
  it('lands a housekeeper on My Rooms and leaves engineering on the board', () => {
    expect(landingPath({ role: 'dept_staff', departmentType: 'housekeeping' })).toBe('/app/my-rooms')
    expect(landingPath({ role: 'dept_staff', departmentType: 'engineering' })).toBe('/app/board?mine=1')
    expect(landingPath({ role: 'dept_staff', departmentType: null })).toBe('/app/board?mine=1')
    expect(landingPath({ role: 'supervisor', departmentType: 'housekeeping' })).toBe('/app/board?mine=1')
  })
```

In `web/src/components/navModel.test.ts` (import `hasCapability` if not already):

```ts
describe('housekeeping navigation', () => {
  it('sits above Maintenance and keeps Room Inspection from lighting Rooms', () => {
    const at = NAV_GROUPS.findIndex((g) => g.heading === 'Housekeeping')
    expect(NAV_GROUPS[at + 1]!.heading).toBe('Maintenance')
    const items = NAV_GROUPS[at]!.items
    expect(items.map((i) => i.to)).toEqual(['/app/housekeeping', '/app/my-rooms', '/app/room-inspection'])
    expect(isNavItemActive(items[0]!, '/app/room-inspection')).toBe(false)
    expect(isNavItemActive(items[0]!, '/app/housekeeping')).toBe(true)
  })

  it('shows front desk the board only', () => {
    const groups = visibleNavGroups((c) => hasCapability('agent', c))
    const hk = groups.find((g) => g.heading === 'Housekeeping')!
    expect(hk.items.map((i) => i.label)).toEqual(['Rooms'])
  })
})
```

If an existing navModel test enumerates every group heading, add `'Housekeeping'` before
`'Maintenance'` in its expectation.

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/auth/capabilities.test.ts src/components/navModel.test.ts` → FAIL.

- [ ] **Step 3: Implement `landingPath`** — `web/src/auth/capabilities.ts` (import
`MembershipOut` alongside `Role`):

```ts
/** §5.2: /app redirects here. A housekeeper lands in their room list — docs/design.md calls it
 *  the single decision that does most for adoption — which role alone cannot tell apart from an
 *  engineer, hence the membership. */
export function landingPath(membership: Pick<MembershipOut, 'role' | 'departmentType'>): string {
  switch (membership.role) {
    case 'agent':
      return '/app/inbox'
    case 'dept_staff':
      return membership.departmentType === 'housekeeping' ? '/app/my-rooms' : '/app/board?mine=1'
    case 'supervisor':
      return '/app/board?mine=1'
    case 'manager':
    case 'admin':
    case 'corporate':
      return '/app/analytics'
  }
}
```

Call sites:
- `web/src/routes.tsx` — in `LandingRedirect` and `RequireCapability`, take `membership` from
  `useSession()` and call `landingPath(membership)` (drop the now-unused `role`).
- `web/src/components/AppShell.tsx:97` and `web/src/components/CommandPalette.tsx:73` —
  `landingPath(m.role)` → `landingPath(m)`.
- `web/src/features/login/LoginPage.tsx:22` — `landingPath(session.memberships[0]!.role)` →
  `landingPath(session.memberships[0]!)`.

- [ ] **Step 4: Implement the nav** — `web/src/components/NavIcon.tsx`: add `'bed'` to
`IconName` and to `PATHS`:

```ts
  bed: 'M3 18v-7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v7M3 14h18M7 9V6h4v3M3 18v2M21 18v2',
```

`web/src/components/navModel.ts` — insert this group immediately before the `Maintenance`
group:

```ts
  {
    heading: 'Housekeeping',
    items: [
      { label: 'Rooms', to: '/app/housekeeping', icon: 'bed', needs: ['view_housekeeping'] },
      { label: 'My Rooms', to: '/app/my-rooms', icon: 'log', needs: ['perform_housekeeping'] },
      // A sibling of /app/housekeeping rather than a child, so Rooms does not light with it —
      // the same reason PM Inspection is /app/inspection: two lit entries reads as a bug.
      {
        label: 'Room Inspection',
        to: '/app/room-inspection',
        icon: 'inspect',
        needs: ['inspect_housekeeping'],
      },
    ],
  },
```

- [ ] **Step 5: Run the whole web suite, lint, build, commit**

Run: `cd web && npm test && npm run lint && npm run build` → PASS. (The three new nav targets
fall through to `/app` until Tasks 13–15 add their routes — harmless.)

```bash
git add web/src/auth/capabilities.ts web/src/auth/capabilities.test.ts web/src/routes.tsx web/src/components/AppShell.tsx web/src/components/CommandPalette.tsx web/src/features/login/LoginPage.tsx web/src/components/navModel.ts web/src/components/navModel.test.ts web/src/components/NavIcon.tsx
git commit -m "feat(housekeeping): housekeepers land on My Rooms; Housekeeping nav group"
```

---

### Task 13: Room board and room drawer

**Files:**
- Create: `web/src/features/housekeeping/labels.ts`, `RoomBoardPage.tsx`, `RoomDrawer.tsx`
- Modify: `web/src/routes.tsx`
- Test: `web/src/features/housekeeping/RoomBoardPage.test.tsx`

**Interfaces:**
- Consumes: Task 11 hooks; `useSession().can`.
- Produces: `RoomBoardPage` at `/app/housekeeping`; `labels.ts` exports used by Tasks 14–15:
  `HK_STATUS_LABELS`, `HK_STATUS_TILE`, `SERVICE_LABELS`, `OCCUPANCY_LABELS`, `OCCUPANCY_GLYPH`,
  `EVENT_LABELS`, `HK_STATUSES`, `initials(name)`.

- [ ] **Step 1: Write the failing test** — `web/src/features/housekeeping/RoomBoardPage.test.tsx`:

```tsx
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkBoardOut, HkRoomOut, Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RoomBoardPage } from './RoomBoardPage'

function room(over: Partial<HkRoomOut>): HkRoomOut {
  return {
    id: 'r-101', unitId: 'u-101', code: '101', floor: 1, roomType: 'KNGN', hkStatus: 'dirty',
    serviceType: 'stayover', rush: false, occupancy: 'stayover', guestName: 'Sarah Chen',
    departureDate: '2026-09-12', statusChangedAt: '2026-09-10T08:00:00Z', lastCleanedAt: null,
    lastInspectedAt: null, notes: null, assignment: null, ...over,
  }
}

const BOARD: HkBoardOut = {
  rooms: [
    room({}),
    room({ id: 'r-102', code: '102', hkStatus: 'inspected', occupancy: 'vacant', guestName: null }),
    room({ id: 'r-103', code: '103', rush: true }),
    room({ id: 'r-PH', code: 'PH', floor: null }),
  ],
  summary: { dirty: 3, inProgress: 0, awaitingInspection: 0, inspected: 1, outOfOrder: 0 },
  housekeepers: [{ userId: 'u-hana', name: 'Hana Keeper', assigned: 0, done: 0 }],
}

const calls: { url: string; method: string; body: unknown }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null })
    const body = url.endsWith('/housekeeping/board') ? BOARD : method === 'POST' ? [] : {}
    return Promise.resolve(new Response(JSON.stringify(body), { status: method === 'POST' ? 201 : 200 }))
  })
}

function mount(role: Role) {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/housekeeping" element={<RoomBoardPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/housekeeping' },
  )
}

describe('RoomBoardPage', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows the summary and groups rooms by floor with floorless rooms last', async () => {
    mount('supervisor')
    expect(await screen.findByText('Floor 1')).toBeInTheDocument()
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual(['Floor 1', 'No floor'])
    expect(screen.getByTestId('summary-dirty')).toHaveTextContent('3')
  })

  it('puts rush rooms first on their floor', async () => {
    mount('supervisor')
    await screen.findByText('Floor 1')
    const tiles = screen.getAllByRole('button', { name: /^Room / }).map((b) => b.getAttribute('aria-label'))
    expect(tiles.slice(0, 3)).toEqual(['Room 103, Dirty', 'Room 101, Dirty', 'Room 102, Inspected'])
  })

  it('assigns every selected room in one request', async () => {
    const user = userEvent.setup()
    mount('supervisor')
    await user.click(await screen.findByRole('checkbox', { name: 'Select room 101' }))
    await user.click(screen.getByRole('checkbox', { name: 'Select room PH' }))
    await user.selectOptions(screen.getByLabelText('Assign to'), 'u-hana')
    await user.click(screen.getByRole('button', { name: 'Assign' }))
    const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/housekeeping/assignments'))
    expect(post?.body).toEqual({ roomIds: ['r-101', 'r-PH'], housekeeperUserId: 'u-hana' })
  })

  it('gives front desk Mark dirty and Rush but not Assign', async () => {
    const user = userEvent.setup()
    mount('agent')
    await user.click(await screen.findByRole('checkbox', { name: 'Select room 102' }))
    expect(screen.queryByLabelText('Assign to')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mark dirty' }))
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/rooms/r-102/mark-dirty'))).toBe(true)
  })

  it('filters to unassigned rooms of one status', async () => {
    const user = userEvent.setup()
    mount('supervisor')
    await screen.findByText('Floor 1')
    await user.selectOptions(screen.getByLabelText('Status'), 'inspected')
    const tiles = screen.getAllByRole('button', { name: /^Room / })
    expect(tiles).toHaveLength(1)
    expect(within(tiles[0]!.closest('li')!).getByText('102')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/features/housekeeping/RoomBoardPage.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Create `web/src/features/housekeeping/labels.ts`**

```ts
import type { HkOccupancy, HkServiceType, HkStatus, RoomEventType } from '../../api/types'

export const HK_STATUSES: HkStatus[] = [
  'dirty', 'in_progress', 'clean', 'inspected', 'out_of_order', 'out_of_service',
]

export const HK_STATUS_LABELS: Record<HkStatus, string> = {
  dirty: 'Dirty',
  in_progress: 'In progress',
  clean: 'Awaiting inspection',
  inspected: 'Inspected',
  out_of_order: 'Out of order',
  out_of_service: 'Out of service',
}

/** Tile colours reuse the Badge tones so the board matches the rest of the app. */
export const HK_STATUS_TILE: Record<HkStatus, string> = {
  dirty: 'bg-dangerBg text-dangerText',
  in_progress: 'bg-warnBg text-warnText',
  clean: 'bg-noteBg text-noteText',
  inspected: 'bg-okBg text-okText',
  out_of_order: 'bg-tagBg text-tagText',
  out_of_service: 'bg-tagBg text-tagText',
}

export const SERVICE_LABELS: Record<HkServiceType, string> = {
  departure: 'Departure',
  stayover: 'Stayover',
  touch_up: 'Touch-up',
}

export const OCCUPANCY_LABELS: Record<HkOccupancy, string> = {
  vacant: 'Vacant',
  arrival: 'Arrival',
  stayover: 'Stayover',
  departure: 'Departure',
}

export const OCCUPANCY_GLYPH: Record<HkOccupancy, string> = {
  vacant: '○',
  arrival: '↘',
  stayover: '●',
  departure: '↗',
}

export const EVENT_LABELS: Record<RoomEventType, string> = {
  status_changed: 'Status changed',
  assigned: 'Assigned',
  reassigned: 'Reassigned',
  unassigned: 'Unassigned',
  started: 'Started',
  completed: 'Marked ready',
  inspection_passed: 'Passed inspection',
  inspection_failed: 'Failed inspection',
  marked_dirty: 'Marked dirty',
  rush_set: 'Rush set',
  rush_cleared: 'Rush cleared',
}

export function initials(name: string | null | undefined): string {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase())
    .slice(0, 2)
    .join('')
}
```

- [ ] **Step 4: Create `web/src/features/housekeeping/RoomDrawer.tsx`**

```tsx
import {
  useHkRoom,
  useReorder,
  useSelfAssignStart,
  useSetRoomStatus,
  useUnassign,
} from '../../api/hooks/housekeeping'
import type { HkAssignmentOut, HkRoomOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, Dialog, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { EVENT_LABELS, HK_STATUS_LABELS, OCCUPANCY_LABELS, SERVICE_LABELS } from './labels'

function queueOf(rooms: HkRoomOut[], a: HkAssignmentOut): HkAssignmentOut[] {
  return rooms
    .map((r) => r.assignment)
    .filter((x): x is HkAssignmentOut =>
      !!x && x.housekeeperUserId === a.housekeeperUserId && x.shiftDate === a.shiftDate &&
      x.status !== 'passed')
    .sort((x, y) => x.sequence - y.sequence)
}

export function RoomDrawer({
  roomId,
  rooms,
  onClose,
}: {
  roomId: string | null
  rooms: HkRoomOut[]
  onClose: () => void
}) {
  const { can } = useSession()
  const detail = useHkRoom(roomId)
  const setStatus = useSetRoomStatus()
  const unassign = useUnassign()
  const reorder = useReorder()
  const selfStart = useSelfAssignStart()
  const room = detail.data?.room
  const a = room?.assignment ?? null
  const canManage = can('manage_housekeeping')
  const out = room?.hkStatus === 'out_of_order' || room?.hkStatus === 'out_of_service'

  function move(delta: -1 | 1) {
    if (!a) return
    const ids = queueOf(rooms, a).map((x) => x.id)
    const i = ids.indexOf(a.id)
    const j = i + delta
    if (i < 0 || j < 0 || j >= ids.length) return
    const next = [...ids]
    const held = next[i]!
    next[i] = next[j]!
    next[j] = held
    reorder.mutate({ housekeeperUserId: a.housekeeperUserId, assignmentIds: next })
  }

  return (
    <Dialog open={roomId !== null} onClose={onClose} title={room ? `Room ${room.code}` : 'Room'} wide>
      {!room ? (
        <div className="flex justify-center py-6">
          <Spinner />
        </div>
      ) : (
        <div className="flex flex-col gap-4 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{HK_STATUS_LABELS[room.hkStatus]}</Badge>
            {room.serviceType ? <Badge tone="note">{SERVICE_LABELS[room.serviceType]}</Badge> : null}
            {room.rush ? <Badge tone="danger">Rush</Badge> : null}
          </div>
          <p>
            {OCCUPANCY_LABELS[room.occupancy]}
            {room.guestName ? ` · ${room.guestName}` : ''}
            {room.departureDate ? ` · departs ${room.departureDate}` : ''}
          </p>
          {a ? (
            <section aria-label="Assignment">
              <p>
                {a.housekeeperName ?? 'Unknown'} · {a.status.replace('_', ' ')}
                {a.failCount > 0 ? ` · failed ${a.failCount}×` : ''}
              </p>
              {a.inspectionNote ? <p className="text-text3">“{a.inspectionNote}”</p> : null}
            </section>
          ) : (
            <p className="text-text3">Not assigned today</p>
          )}
          {detail.data!.photos.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {detail.data!.photos.map((p) => (
                <img key={p.id} src={p.url} alt={`Photo from ${formatClock(p.createdAt)}`}
                     className="h-24 w-24 rounded object-cover" />
              ))}
            </div>
          ) : null}
          {canManage ? (
            <div className="flex flex-wrap gap-2">
              {room.hkStatus !== 'out_of_order' ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'out_of_order' })}>
                  Out of order
                </Button>
              ) : null}
              {room.hkStatus !== 'out_of_service' ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'out_of_service' })}>
                  Out of service
                </Button>
              ) : null}
              {out ? (
                <Button onClick={() => setStatus.mutate({ roomId: room.id, status: 'dirty' })}>
                  Back in service
                </Button>
              ) : null}
              {/* Supervisors clean rooms too (spec §3.3); it then appears in their My Rooms. */}
              {room.hkStatus === 'dirty' && !a ? (
                <Button onClick={() => selfStart.mutate(room.id)}>Clean it myself</Button>
              ) : null}
              {a && a.status === 'assigned' ? (
                <>
                  <Button onClick={() => unassign.mutate(a.id)}>Unassign</Button>
                  <Button onClick={() => move(-1)}>Move earlier</Button>
                  <Button onClick={() => move(1)}>Move later</Button>
                </>
              ) : null}
            </div>
          ) : null}
          <section aria-label="History">
            <h3 className="mb-1 text-xs font-bold uppercase text-text3">History</h3>
            <ol className="flex flex-col gap-1">
              {detail.data!.events.map((e) => (
                <li key={e.id} className="text-xs">
                  <span className="font-semibold">{EVENT_LABELS[e.type]}</span>
                  {e.toValue ? ` → ${e.toValue}` : ''}
                  {' · '}
                  {e.userName ?? 'System'} · {formatClock(e.createdAt)}
                  {e.comment ? <span className="text-text3"> — {e.comment}</span> : null}
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
    </Dialog>
  )
}
```

- [ ] **Step 5: Create `web/src/features/housekeeping/RoomBoardPage.tsx`**

```tsx
import { useMemo, useState } from 'react'
import { useAssignRooms, useHkBoard, useMarkDirty, useSetRush } from '../../api/hooks/housekeeping'
import type { HkRoomOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { RoomDrawer } from './RoomDrawer'
import {
  HK_STATUSES,
  HK_STATUS_LABELS,
  HK_STATUS_TILE,
  OCCUPANCY_GLYPH,
  OCCUPANCY_LABELS,
  initials,
} from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'
const UNASSIGNED = '__unassigned__'
type Filters = { floor: string; status: string; assignee: string }

function floorKey(room: HkRoomOut): string {
  return room.floor === null || room.floor === undefined ? 'none' : String(room.floor)
}

function floorLabel(key: string): string {
  return key === 'none' ? 'No floor' : `Floor ${key}`
}

function matches(room: HkRoomOut, f: Filters): boolean {
  if (f.floor && floorKey(room) !== f.floor) return false
  if (f.status && room.hkStatus !== f.status) return false
  if (f.assignee === UNASSIGNED) return !room.assignment
  if (f.assignee && room.assignment?.housekeeperUserId !== f.assignee) return false
  return true
}

export function RoomBoardPage() {
  const { can } = useSession()
  const board = useHkBoard()
  const markDirty = useMarkDirty()
  const setRush = useSetRush()
  const assign = useAssignRooms()
  const [filters, setFilters] = useState<Filters>({ floor: '', status: '', assignee: '' })
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [openId, setOpenId] = useState<string | null>(null)
  const [keeper, setKeeper] = useState('')
  const [error, setError] = useState<string | null>(null)
  const canManage = can('manage_housekeeping')
  const canSelect = can('mark_room_dirty')

  const rooms = useMemo(() => board.data?.rooms ?? [], [board.data])
  const visible = useMemo(() => rooms.filter((r) => matches(r, filters)), [rooms, filters])
  // The server sorts by floor with floorless units last, so insertion order is display order.
  // Within a floor, rush rooms come first (spec §3.5); sort is stable, so the rest keep order.
  const floors = useMemo(() => {
    const groups = new Map<string, HkRoomOut[]>()
    for (const r of visible) groups.set(floorKey(r), [...(groups.get(floorKey(r)) ?? []), r])
    return [...groups.entries()].map(
      ([key, list]) => [key, [...list].sort((a, b) => Number(b.rush) - Number(a.rush))] as const,
    )
  }, [visible])
  const floorOptions = useMemo(() => [...new Set(rooms.map(floorKey))], [rooms])
  const chosen = rooms.filter((r) => selected.has(r.id))

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      setSelected(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    }
  }

  if (board.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (board.error) return <EmptyState title="Could not load the board" hint={board.error.message} />
  const s = board.data.summary

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Rooms</h1>
      </header>
      <dl className="flex flex-wrap gap-4 border-b border-border px-4 py-3 text-sm">
        {([
          ['dirty', 'Dirty', s.dirty],
          ['in-progress', 'In progress', s.inProgress],
          ['awaiting', 'Awaiting inspection', s.awaitingInspection],
          ['inspected', 'Inspected', s.inspected],
          ['ooo', 'Out of order', s.outOfOrder],
        ] as const).map(([key, label, value]) => (
          <div key={key} data-testid={`summary-${key}`} className="flex items-baseline gap-1.5">
            <dt className="text-text3">{label}</dt>
            <dd className="font-mono font-bold">{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3 text-xs font-semibold text-text3">
        <label className="flex items-center gap-2">
          Floor
          <select className={SELECT} value={filters.floor}
                  onChange={(e) => setFilters({ ...filters, floor: e.target.value })}>
            <option value="">All</option>
            {floorOptions.map((k) => <option key={k} value={k}>{floorLabel(k)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Status
          <select className={SELECT} value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
            <option value="">All</option>
            {HK_STATUSES.map((st) => <option key={st} value={st}>{HK_STATUS_LABELS[st]}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2">
          Assignee
          <select className={SELECT} value={filters.assignee}
                  onChange={(e) => setFilters({ ...filters, assignee: e.target.value })}>
            <option value="">Anyone</option>
            <option value={UNASSIGNED}>Unassigned</option>
            {board.data.housekeepers.map((h) => <option key={h.userId} value={h.userId}>{h.name}</option>)}
          </select>
        </label>
      </div>

      {chosen.length > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface2 px-4 py-2 text-sm">
          <span className="font-semibold">{chosen.length} selected</span>
          {canManage ? (
            <>
              <label className="flex items-center gap-2 text-xs font-semibold text-text3">
                Assign to
                <select className={SELECT} value={keeper} onChange={(e) => setKeeper(e.target.value)}>
                  <option value="">Choose…</option>
                  {board.data.housekeepers.map((h) => (
                    <option key={h.userId} value={h.userId}>{h.name} ({h.assigned})</option>
                  ))}
                </select>
              </label>
              <Button variant="primary" disabled={!keeper} loading={assign.isPending}
                      onClick={() => run(() => assign.mutateAsync({
                        roomIds: chosen.map((r) => r.id), housekeeperUserId: keeper }))}>
                Assign
              </Button>
            </>
          ) : null}
          <Button onClick={() => run(async () => {
            for (const r of chosen.filter((x) => x.hkStatus === 'inspected')) {
              await markDirty.mutateAsync({ roomId: r.id })
            }
          })}>
            Mark dirty
          </Button>
          <Button onClick={() => run(async () => {
            for (const r of chosen.filter((x) => x.hkStatus === 'dirty' || x.hkStatus === 'in_progress')) {
              await setRush.mutateAsync({ roomId: r.id, on: true })
            }
          })}>
            Rush
          </Button>
          {error ? <span role="alert" className="text-dangerText">{error}</span> : null}
        </div>
      ) : null}

      {floors.length === 0 ? (
        <EmptyState title="No rooms match" />
      ) : (
        floors.map(([key, list]) => (
          <section key={key} className="px-4 py-3">
            <h2 className="mb-2 text-xs font-bold uppercase text-text3">{floorLabel(key)}</h2>
            <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-8">
              {list.map((r) => (
                <li key={r.id}
                    className={cn('relative rounded-card border border-border2 p-2',
                                  HK_STATUS_TILE[r.hkStatus], selected.has(r.id) && 'ring-2 ring-accent')}>
                  {canSelect ? (
                    <input type="checkbox" aria-label={`Select room ${r.code}`} checked={selected.has(r.id)}
                           onChange={() => toggle(r.id)} className="absolute right-2 top-2" />
                  ) : null}
                  <button type="button" onClick={() => setOpenId(r.id)}
                          aria-label={`Room ${r.code}, ${HK_STATUS_LABELS[r.hkStatus]}`}
                          className="flex w-full flex-col items-start text-left">
                    <span className="font-mono text-sm font-bold">{r.code}</span>
                    <span className="text-xs" title={OCCUPANCY_LABELS[r.occupancy]}>
                      {OCCUPANCY_GLYPH[r.occupancy]} {r.rush ? 'RUSH' : ''}
                    </span>
                    <span className="text-xs">{r.assignment ? initials(r.assignment.housekeeperName) : '—'}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      <RoomDrawer roomId={openId} rooms={rooms} onClose={() => setOpenId(null)} />
    </div>
  )
}
```

- [ ] **Step 6: Route it** — `web/src/routes.tsx`: import `RoomBoardPage` and add inside the
`AppLayout` route:

```tsx
          <Route
            path="housekeeping"
            element={
              <RequireCapability capability="view_housekeeping">
                <RoomBoardPage />
              </RequireCapability>
            }
          />
```

- [ ] **Step 7: Run, lint, build, commit**

Run: `cd web && npx vitest run src/features/housekeeping && npm run lint && npm run build` → PASS.

```bash
git add web/src/features/housekeeping/labels.ts web/src/features/housekeeping/RoomBoardPage.tsx web/src/features/housekeeping/RoomDrawer.tsx web/src/features/housekeeping/RoomBoardPage.test.tsx web/src/routes.tsx
git commit -m "feat(housekeeping): room board with bulk assign and room drawer"
```

---

### Task 14: My Rooms (housekeeper, phone-first)

**Files:**
- Create: `web/src/features/housekeeping/MyRoomsPage.tsx`
- Modify: `web/src/routes.tsx`
- Test: `web/src/features/housekeeping/MyRoomsPage.test.tsx`

**Interfaces:**
- Consumes: `useMyRooms`, `useStartAssignment`, `useCompleteAssignment`, `useUploadHkPhoto`;
  `labels.ts`.
- Produces: `MyRoomsPage` at `/app/my-rooms`.

- [ ] **Step 1: Write the failing test** — `web/src/features/housekeeping/MyRoomsPage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkAssignmentOut, HkRoomOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { MyRoomsPage } from './MyRoomsPage'

function assignment(over: Partial<HkAssignmentOut>): HkAssignmentOut {
  return {
    id: 'a-1', roomId: 'r-1', housekeeperUserId: 'u-hana', housekeeperName: 'Hana Keeper',
    shiftDate: '2026-09-10', sequence: 1, type: 'departure', status: 'assigned', startedAt: null,
    completedAt: null, inspectedByName: null, inspectedAt: null, inspectionNote: null,
    failCount: 0, ...over,
  }
}

function room(code: string, a: HkAssignmentOut, over: Partial<HkRoomOut> = {}): HkRoomOut {
  return {
    id: a.roomId, unitId: `u-${code}`, code, floor: 2, roomType: 'KNGN', hkStatus: 'dirty',
    serviceType: a.type, rush: false, occupancy: 'vacant', guestName: null, departureDate: null,
    statusChangedAt: '2026-09-10T08:00:00Z', lastCleanedAt: null, lastInspectedAt: null,
    notes: null, assignment: a, ...over,
  }
}

const MINE: HkRoomOut[] = [
  room('204', assignment({ id: 'a-rush', roomId: 'r-204' }), { rush: true }),
  room('205', assignment({ id: 'a-2', roomId: 'r-205', status: 'in_progress', sequence: 2 }),
       { hkStatus: 'in_progress' }),
  room('206', assignment({ id: 'a-3', roomId: 'r-206', sequence: 3, failCount: 1,
                           inspectionNote: 'Hair in the bathroom sink.' })),
  room('207', assignment({ id: 'a-4', roomId: 'r-207', status: 'passed', sequence: 4 }),
       { hkStatus: 'inspected' }),
]

const posts: string[] = []

describe('MyRoomsPage', () => {
  beforeEach(() => {
    posts.length = 0
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') posts.push(String(input))
      return Promise.resolve(new Response(JSON.stringify(MINE), { status: 200 }))
    }))
    renderWithProviders(
      <SessionProvider>
        <Routes>
          <Route path="/app/my-rooms" element={<MyRoomsPage />} />
        </Routes>
      </SessionProvider>,
      { session: sessionFixture({ role: 'dept_staff', departmentType: 'housekeeping' }), route: '/app/my-rooms' },
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('shows progress and pins rush at the top', async () => {
    expect(await screen.findByText('1 of 4 done')).toBeInTheDocument()
    const rows = screen.getAllByRole('button', { name: /^Open room / })
    expect(rows[0]).toHaveAccessibleName('Open room 204')
    expect(screen.getByText('Rush')).toBeInTheDocument()
  })

  it('walks the one big button from Start to Mark ready', async () => {
    const user = userEvent.setup()
    const starts = await screen.findAllByRole('button', { name: 'Start' })
    await user.click(starts[0]!)
    expect(posts.some((p) => p.endsWith('/assignments/a-rush/start'))).toBe(true)
    await user.click(screen.getByRole('button', { name: 'Mark ready' }))
    expect(posts.some((p) => p.endsWith('/assignments/a-2/complete'))).toBe(true)
  })

  it('opens a room full screen with the failed-back note', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Open room 206' }))
    expect(screen.getByText(/Hair in the bathroom sink\./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back to my rooms' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/features/housekeeping/MyRoomsPage.test.tsx` → FAIL.

- [ ] **Step 3: Create `web/src/features/housekeeping/MyRoomsPage.tsx`**

```tsx
import { useState } from 'react'
import {
  useCompleteAssignment,
  useMyRooms,
  useStartAssignment,
  useUploadHkPhoto,
} from '../../api/hooks/housekeeping'
import type { HkRoomOut } from '../../api/types'
import { Badge, Button, EmptyState, Spinner } from '../../components/ui'
import { SERVICE_LABELS } from './labels'

const BIG = 'h-12 min-w-32 text-base'

/** The one big button (docs/design.md §6.5): whatever the room needs next, nothing else. */
function NextAction({ room }: { room: HkRoomOut }) {
  const start = useStartAssignment()
  const complete = useCompleteAssignment()
  const a = room.assignment!
  if (a.status === 'assigned') {
    return <Button variant="primary" className={BIG} loading={start.isPending}
                   onClick={() => start.mutate(a.id)}>Start</Button>
  }
  if (a.status === 'in_progress') {
    return <Button variant="primary" className={BIG} loading={complete.isPending}
                   onClick={() => complete.mutate(a.id)}>Mark ready</Button>
  }
  return <Badge tone={a.status === 'passed' ? 'ok' : 'note'}>{a.status === 'passed' ? 'Inspected' : 'Ready'}</Badge>
}

function sentBack(room: HkRoomOut): string | null {
  const a = room.assignment
  if (!a || a.failCount === 0 || !a.inspectionNote) return null
  return a.status === 'assigned' || a.status === 'in_progress' ? a.inspectionNote : null
}

function RoomScreen({ room, onBack }: { room: HkRoomOut; onBack: () => void }) {
  const upload = useUploadHkPhoto()
  const a = room.assignment!
  const note = sentBack(room)
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 overflow-y-auto p-4">
      <Button variant="ghost" className="self-start" onClick={onBack}>Back to my rooms</Button>
      <h1 className="font-mono text-3xl font-bold text-roomNum">{room.code}</h1>
      <p className="text-sm text-text3">
        {[room.roomType, SERVICE_LABELS[a.type]].filter(Boolean).join(' · ')}
      </p>
      {note ? (
        <p role="note" className="rounded-card bg-dangerBg p-3 text-sm text-dangerText">
          Sent back: {note}
        </p>
      ) : null}
      <NextAction room={room} />
      {a.status === 'in_progress' ? (
        <label className="flex flex-col gap-1 text-sm font-semibold">
          Add photo
          <input type="file" accept="image/*" capture="environment"
                 onChange={(e) => {
                   const file = e.target.files?.[0]
                   if (file) upload.mutate({ assignmentId: a.id, file })
                 }} />
        </label>
      ) : null}
      {upload.error ? <p role="alert" className="text-sm text-dangerText">{upload.error.message}</p> : null}
    </div>
  )
}

export function MyRoomsPage() {
  const mine = useMyRooms()
  const [openId, setOpenId] = useState<string | null>(null)
  if (mine.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (mine.error) return <EmptyState title="Could not load your rooms" hint={mine.error.message} />
  const rows = mine.data
  const open = rows.find((r) => r.id === openId)
  if (open) return <RoomScreen room={open} onBack={() => setOpenId(null)} />
  const done = rows.filter((r) => r.assignment?.status === 'done' || r.assignment?.status === 'passed').length

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">My Rooms</h1>
        <p className="text-sm text-text3">{done} of {rows.length} done</p>
      </header>
      {rows.length === 0 ? (
        <EmptyState title="No rooms assigned to you today" />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center gap-3 rounded-card border border-border2 bg-surface p-3">
              <button type="button" aria-label={`Open room ${r.code}`} onClick={() => setOpenId(r.id)}
                      className="flex flex-1 flex-col text-left">
                <span className="flex items-center gap-2">
                  <span className="font-mono text-lg font-bold text-roomNum">{r.code}</span>
                  {r.rush ? <Badge tone="danger">Rush</Badge> : null}
                  {sentBack(r) ? <Badge tone="warn">Sent back</Badge> : null}
                </span>
                <span className="text-xs text-text3">
                  {[r.roomType, r.assignment ? SERVICE_LABELS[r.assignment.type] : null].filter(Boolean).join(' · ')}
                </span>
              </button>
              <NextAction room={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Route it** — `web/src/routes.tsx`:

```tsx
          <Route
            path="my-rooms"
            element={
              <RequireCapability capability="perform_housekeeping">
                <MyRoomsPage />
              </RequireCapability>
            }
          />
```

- [ ] **Step 5: Run, lint, build, commit**

Run: `cd web && npx vitest run src/features/housekeeping && npm run lint && npm run build` → PASS.

```bash
git add web/src/features/housekeeping/MyRoomsPage.tsx web/src/features/housekeeping/MyRoomsPage.test.tsx web/src/routes.tsx
git commit -m "feat(housekeeping): My Rooms, the housekeeper's phone view"
```

---

### Task 15: Room inspection

**Files:**
- Create: `web/src/features/housekeeping/RoomInspectionPage.tsx`
- Modify: `web/src/routes.tsx`
- Test: `web/src/features/housekeeping/RoomInspectionPage.test.tsx`

**Interfaces:**
- Consumes: `useHkInspections`, `useInspectRoom`.
- Produces: `RoomInspectionPage` at `/app/room-inspection`.

- [ ] **Step 1: Write the failing test** — `RoomInspectionPage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { HkInspectionRowOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RoomInspectionPage } from './RoomInspectionPage'

const QUEUE: HkInspectionRowOut[] = [{
  room: {
    id: 'r-204', unitId: 'u-204', code: '204', floor: 2, roomType: 'KNGN', hkStatus: 'clean',
    serviceType: 'departure', rush: false, occupancy: 'vacant', guestName: null,
    departureDate: null, statusChangedAt: '2026-09-10T13:00:00Z', lastCleanedAt: null,
    lastInspectedAt: null, notes: null,
    assignment: {
      id: 'a-204', roomId: 'r-204', housekeeperUserId: 'u-hana', housekeeperName: 'Hana Keeper',
      shiftDate: '2026-09-10', sequence: 1, type: 'departure', status: 'done',
      startedAt: '2026-09-10T12:30:00Z', completedAt: '2026-09-10T13:00:00Z',
      inspectedByName: null, inspectedAt: null, inspectionNote: null, failCount: 0,
    },
  },
  photos: [{ id: 'p-1', contentType: 'image/png', byteSize: 10, url: '/api/p/prop-a/x.png',
             createdAt: '2026-09-10T12:50:00Z' }],
}]

const posts: { url: string; body: unknown }[] = []

describe('RoomInspectionPage', () => {
  beforeEach(() => {
    posts.length = 0
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'POST') {
        posts.push({ url: String(input), body: JSON.parse(String(init!.body)) })
        return Promise.resolve(new Response('{}', { status: 200 }))
      }
      return Promise.resolve(new Response(JSON.stringify(QUEUE), { status: 200 }))
    }))
    renderWithProviders(
      <SessionProvider>
        <Routes>
          <Route path="/app/room-inspection" element={<RoomInspectionPage />} />
        </Routes>
      </SessionProvider>,
      { session: sessionFixture({ role: 'supervisor' }), route: '/app/room-inspection' },
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists who cleaned each room, with their photos', async () => {
    expect(await screen.findByText('204')).toBeInTheDocument()
    expect(screen.getByText(/Hana Keeper/)).toBeInTheDocument()
    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('passes a room', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Pass room 204' }))
    expect(posts).toEqual([{ url: '/api/p/prop-a/housekeeping/assignments/a-204/inspect',
                             body: { result: 'pass', note: null } }])
  })

  it('will not fail a room without a note', async () => {
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Fail room 204' }))
    const confirm = screen.getByRole('button', { name: 'Fail room' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('What needs fixing?'), '   ')
    expect(confirm).toBeDisabled()
    await user.type(screen.getByLabelText('What needs fixing?'), 'Streaky mirror.')
    await user.click(confirm)
    expect(posts[0]!.body).toEqual({ result: 'fail', note: 'Streaky mirror.' })
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/features/housekeeping/RoomInspectionPage.test.tsx` → FAIL.

- [ ] **Step 3: Create `web/src/features/housekeeping/RoomInspectionPage.tsx`**

```tsx
import { useState } from 'react'
import { useHkInspections, useInspectRoom } from '../../api/hooks/housekeeping'
import type { HkInspectionRowOut } from '../../api/types'
import { Button, Dialog, EmptyState, Spinner, Textarea } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { SERVICE_LABELS } from './labels'

/** Mirrors PM's InspectionPage so supervisors meet one pattern twice (spec §4.3). */
export function RoomInspectionPage() {
  const queue = useHkInspections()
  const inspect = useInspectRoom()
  const [failing, setFailing] = useState<HkInspectionRowOut | null>(null)
  const [note, setNote] = useState('')

  function close() {
    setFailing(null)
    setNote('')
  }

  if (queue.isPending) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }
  if (queue.error) return <EmptyState title="Could not load the queue" hint={queue.error.message} />

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Room Inspection</h1>
      </header>
      {queue.data.length === 0 ? (
        <EmptyState title="No rooms are waiting for inspection" />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {queue.data.map((row) => {
            const a = row.room.assignment!
            return (
              <li key={row.room.id} className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-3">
                <span className="font-mono text-sm font-bold text-roomNum">{row.room.code}</span>
                <span className="text-xs text-text3">
                  {SERVICE_LABELS[a.type]} · {a.housekeeperName ?? 'Unknown'}
                  {a.completedAt ? ` · ${formatClock(a.completedAt)}` : ''}
                  {a.failCount > 0 ? ` · failed ${a.failCount}× before` : ''}
                </span>
                <span className="flex gap-1">
                  {row.photos.map((p) => (
                    <img key={p.id} src={p.url} alt={`Photo of room ${row.room.code}`}
                         className="h-12 w-12 rounded object-cover" />
                  ))}
                </span>
                <span className="ml-auto flex gap-2">
                  <Button variant="primary" aria-label={`Pass room ${row.room.code}`}
                          onClick={() => inspect.mutate({ assignmentId: a.id, result: 'pass' })}>
                    Pass
                  </Button>
                  <Button variant="danger" aria-label={`Fail room ${row.room.code}`}
                          onClick={() => setFailing(row)}>
                    Fail
                  </Button>
                </span>
              </li>
            )
          })}
        </ul>
      )}
      <Dialog
        open={failing !== null}
        onClose={close}
        title={failing ? `Fail room ${failing.room.code}` : 'Fail room'}
        footer={
          <>
            <Button onClick={close}>Cancel</Button>
            <Button variant="danger" disabled={!note.trim()} loading={inspect.isPending}
                    onClick={() => {
                      if (!failing) return
                      inspect.mutate(
                        { assignmentId: failing.room.assignment!.id, result: 'fail', note: note.trim() },
                        { onSuccess: close },
                      )
                    }}>
              Fail room
            </Button>
          </>
        }
      >
        <label className="flex flex-col gap-1 text-sm font-semibold">
          What needs fixing?
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </label>
      </Dialog>
    </div>
  )
}
```

> The Fail dialog's title and its confirm button both read "Fail room …"; the test queries the
> button by its exact name `Fail room`, which the title `Fail room 204` does not match.

- [ ] **Step 4: Route it** — `web/src/routes.tsx`:

```tsx
          <Route
            path="room-inspection"
            element={
              <RequireCapability capability="inspect_housekeeping">
                <RoomInspectionPage />
              </RequireCapability>
            }
          />
```

- [ ] **Step 5: Run, lint, build, commit**

Run: `cd web && npm test && npm run lint && npm run build` → PASS.

```bash
git add web/src/features/housekeeping/RoomInspectionPage.tsx web/src/features/housekeeping/RoomInspectionPage.test.tsx web/src/routes.tsx
git commit -m "feat(housekeeping): room inspection queue with required fail note"
```

---

### Task 16: Postgres verification, full check, deploy

**Files:** none new. This task proves the work on the engine production runs.

- [ ] **Step 1: Everything green locally**

```bash
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
cd ../web && npm test && npm run lint && npm run build
```

Expected: all clean. Also confirm the generated files are fresh:
`cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema && cd ../web && npm run gen:types && git status --short web/src/api`
→ no changes.

- [ ] **Step 2: Migrate a Postgres 18 database that already has units** (spec §7)

```bash
docker rm -f relay-pg18 2>/dev/null; docker run -d --name relay-pg18 -e POSTGRES_PASSWORD=relaydev -e POSTGRES_USER=relay -e POSTGRES_DB=relay_test -p 55432:5432 postgres:18
# wait until: docker exec relay-pg18 pg_isready -U relay  → "accepting connections"
cd server
export DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_test"
../.venv/Scripts/python.exe -m alembic upgrade 0007
docker exec -i relay-pg18 psql -U relay -d relay_test <<'SQL'
INSERT INTO property (id, name, code, timezone, currency, settings, created_at, updated_at)
VALUES ('p1', 'P', 'PPP', 'America/New_York', 'USD', '{}', now(), now());
INSERT INTO maintainable_unit (id, property_id, kind, code, name, active, source, created_at, updated_at) VALUES
 ('u1','p1','guest_room','101','Room 101',true,'manual',now(),now()),
 ('u2','p1','guest_room','102','Room 102',true,'manual',now(),now()),
 ('u3','p1','guest_room','103','Room 103',false,'manual',now(),now()),
 ('u4','p1','equipment','BOILER-1','Boiler',true,'manual',now(),now());
SQL
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_test -c "SELECT count(*), min(hk_status) FROM room"
```

Expected: `2 | inspected`.

- [ ] **Step 3: Downgrade and re-upgrade**

```bash
../.venv/Scripts/python.exe -m alembic downgrade 0007
docker exec relay-pg18 psql -U relay -d relay_test -c "\dt room"      # → Did not find any relation
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_test -c "SELECT count(*) FROM room"   # → 2
```

- [ ] **Step 4: Run the whole app on Postgres** (seeds through the tick and domain — the
timezone-shaped code — on the real engine)

```bash
docker exec relay-pg18 psql -U relay -d postgres -c "CREATE DATABASE relay_dev"
cd .. && DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_dev" .venv/Scripts/python.exe server/dev_start.py
```

Expected: migrations run, the seed completes without an exception, the API listens on :5200.
Then, in another shell:

```bash
curl -s -c /tmp/hk.jar -H 'Content-Type: application/json' -d '{"email":"hk.supervisor@hvh.test","password":"Password123!"}' http://localhost:5200/api/auth/login > /dev/null
PID=$(curl -s -b /tmp/hk.jar http://localhost:5200/api/auth/me | ../.venv/Scripts/python.exe -c "import json,sys; print(json.load(sys.stdin)['memberships'][0]['propertyId'])")
curl -s -b /tmp/hk.jar "http://localhost:5200/api/p/$PID/housekeeping/board" | ../.venv/Scripts/python.exe -c "import json,sys; b=json.load(sys.stdin); print(len(b['rooms']), b['summary'])"
```

Expected: `120` and a summary with every count non-zero except possibly `inProgress` totals of
2. Stop the server.

- [ ] **Step 5: Ask before pushing**

Pushing `main` deploys to production (CLAUDE.md). Show the user `git log --oneline origin/main..HEAD`
and get an explicit go-ahead. Then:

```bash
git push origin main
```

- [ ] **Step 6: Verify the deploy — build success is not enough**

Watch the Railway deployment for the new commit hash with reason **`deploy`** (not `redeploy`).
The deploy log must show, in this order:

```
==> alembic upgrade head
Starting Container
==> gunicorn on :$PORT
```

Then:

```bash
curl -s https://messageapp-production-361b.up.railway.app/api/health   # → {"status":"ok"}
```

and confirm the backfill matched production's inventory, from inside the container:

```bash
railway ssh --service message_app --environment production 'python -c "from app.db import Database; import os; from sqlalchemy import text; d=Database(os.environ[\"DATABASE_URL\"]); c=d.engine.connect(); print(c.execute(text(\"SELECT (SELECT count(*) FROM room), (SELECT count(*) FROM maintainable_unit WHERE kind = '"'"'guest_room'"'"' AND active)\")).one())"'
```

Expected: the two numbers are equal. **Do not run the seeder against production.**

If the push does not deploy, follow CLAUDE.md "If a push does not deploy" (check the deployment
trigger; "Redeploy" will not help).
