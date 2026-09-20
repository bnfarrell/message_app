# Preventative Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build preventative maintenance end to end — a maintainable-unit inventory (rooms, common/BOH areas, equipment) with CSV import and seed data; PM templates in two modes (cycle sweep and RRULE-scheduled) sharing one typed checklist; auto-rolled cycles that freeze missed units; RRULE-generated `WorkOrder(type=pm)` rows; runs with continuously-saved answers, photos and out-of-range work orders; a supervisor inspection step that gates cycle credit; and a compliance view — plus the sweep, checklist, inspection, compliance and two admin screens.

**Architecture:** Eight new tables in `app/models/pm.py`, one recurring job `pm.tick` in `app/queue/handlers/pm.py`, six small domain modules under `app/domain/pm_*.py` (units, templates, cycles, runs, inspection, sweep/compliance), two blueprints (`/maintainable-units`, `/pm`), and a `web/src/features/pm/` feature folder plus two admin screens. `PmRun` is the single compliance currency: a sweep `Start` creates one directly; an RRULE firing creates a `WorkOrder(type=pm)` with one attached. Everything reuses the existing deferred-blob photo idiom, `notifications`, `audit.record`, `queue_event`, `patch_changes` and the `RECURRING` job chain without modifying them.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · **python-dateutil (new)** · pytest · Vite + React 18 + TypeScript + TanStack Query + Tailwind · vitest

**Spec:** `docs/superpowers/specs/2026-09-19-preventative-maintenance-design.md`

## Global Constraints

- **Run Python as `../.venv/Scripts/python.exe` from `server/`.** Bare `python` is a 0-byte Windows Store stub that exits silently.
- Backend test: `cd server && ../.venv/Scripts/python.exe -m pytest -q`. Backend lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` (line length 100, rules E F I B UP). Both clean at every commit.
- Frontend: `cd web && npm test && npm run lint && npm run build` — all three clean at every commit.
- **`tests/test_isolation.py` auto-enumerates every rule under `/api/p/<property_id>`.** Two consequences bind every route here: a non-member gets 403, and **a property's admin must never get 403**. Every capability added here therefore includes `Role.admin` (spec §6).
- **Capability tables must not drift.** `server/app/auth/permissions.py` and `web/src/auth/capabilities.ts` change in the same commit (Task 2).
- **Generated files.** After any change to `app/schemas/*`: `cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema` then `cd web && npm run gen:types`. `test_schema_export.py` and `types.generated.test.ts` fail when stale. New API models go in the tuple in `test_schema_export.py::test_export_contains_the_public_models`; new tables in `EXPECTED_TABLES` in `test_models.py`; new type names in the hand-maintained re-export list in `web/src/api/types.ts`.
- **Portability.** Enums via `enum_type()` (`native_enum=False`). `Numeric(10, 2, asdecimal=False)` for readings. No partial indexes, no JSON-array filtering, no date arithmetic in SQL. `UTCDateTime` raises on naive input — every timestamp comes from `app.clock.now()`. Cycle windows are `Date` columns compared with property-local dates computed in Python.
- **Migration 0007 is verified on PostgreSQL 18 before merge** (Task 22): `alembic upgrade head`, `downgrade 0006`, `upgrade head` against the `relay-pg18` container per CLAUDE.md.
- Pydantic models subclass `CamelModel` (`app.schemas.common`): camelCase on the wire, snake_case in Python, `extra="forbid"`.
- Fixture facts the tests rely on: property A `HVH` is `America/New_York`; `conftest.FROZEN` is `2026-09-10 12:00 UTC` (08:00 EDT, so **property-local today is 2026-09-10, inside Q3 = Jul 1 – Sep 30, ordinal 3**); users `agent@hvh.test` (agent), `engineer@hvh.test` (dept_staff, Engineering), `housekeeper@hvh.test` (dept_staff, Housekeeping), `supervisor@hvh.test` (supervisor, Engineering), `manager@hvh.test`, `admin@hvh.test`, `corporate@hvh.test`, `admin@lsi.test` (property B); password `tests.fixtures.PASSWORD`; `fx.dept_engineering`, `fx.engineer_a`, `fx.supervisor_a` etc. from `tests/fixtures.py`.
- Realtime events queue on `db.info["events"]` via `queue_event` and deliver after commit; the `events` fixture captures them.
- Commit trailer on every commit: `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`

---

## File Structure

**Backend — create:**
- `server/app/models/pm.py` — the eight tables
- `server/alembic/versions/0007_preventative_maintenance.py`
- `server/app/schemas/pm.py` — every request/response model
- `server/app/domain/pm_units.py` — inventory CRUD, CSV import, `LOCATION_FOR_KIND`
- `server/app/domain/pm_cycles.py` — window math, open/close cycles, scope
- `server/app/domain/pm_templates.py` — template CRUD, mode rules, item sync, RRULE validation
- `server/app/domain/pm_runs.py` — start, answer, photo, complete, out-of-range work orders, `to_out`
- `server/app/domain/pm_inspection.py` — queue and inspect
- `server/app/domain/pm_reports.py` — sweep payload, cycle history, compliance
- `server/app/queue/handlers/pm.py` — `pm.tick`: roll cycles, expand RRULEs
- `server/app/api/maintainable_units.py`, `server/app/api/pm.py` — blueprints
- `server/seed/pm_units.py` — the deterministic unit rows shared by the seeder and the sample CSV
- `server/seed/write_sample_csv.py` — writes `fixtures/maintainable_units.sample.csv`
- `fixtures/maintainable_units.sample.csv`
- `server/tests/test_pm_models.py`, `test_pm_units.py`, `test_pm_cycles.py`, `test_pm_templates.py`, `test_pm_runs.py`, `test_pm_inspection.py`, `test_pm_reports.py`, `test_pm_tick.py`

**Backend — modify:**
- `server/pyproject.toml` — `python-dateutil>=2.9`
- `server/app/schemas/enums.py` — seven enums
- `server/app/models/__init__.py` — export the eight models
- `server/app/auth/permissions.py` — `view_pm`, `perform_pm`, `inspect_pm`
- `server/app/schemas/export_json_schema.py` — add `pm` to `MODULES`
- `server/app/schemas/work_orders.py` — `WorkOrderDetail.pm_run_id`
- `server/app/domain/work_orders.py` — populate `pm_run_id` in `detail`
- `server/app/queue/jobs.py` — `RECURRING["pm.tick"] = 300`
- `server/app/queue/handlers/__init__.py` — `MODULES += ("pm",)`
- `server/app/__init__.py` — register the two blueprints
- `server/seed/seed.py`, `server/seed/data.py` — sample data, `SeedSummary`
- `server/tests/test_models.py`, `test_schema_export.py`, `test_seed.py`
- `server/data/app.db` — reseeded fixture database

**Frontend — create:**
- `web/src/api/hooks/pm.ts`
- `web/src/features/pm/labels.ts`, `KindTabs.tsx`, `SweepPage.tsx`, `RunPage.tsx`, `ChecklistItem.tsx`, `InspectionPage.tsx`, `CompliancePage.tsx` (+ tests)
- `web/src/features/admin/UnitsAdmin.tsx`, `ImportUnitsDialog.tsx`, `PmTemplatesAdmin.tsx`, `RecurrenceBuilder.tsx` (+ tests)

**Frontend — modify:**
- `web/src/auth/capabilities.ts` (+ test), `web/src/api/queryKeys.ts`, `web/src/api/ws.ts` (+ test), `web/src/api/types.ts`
- `web/src/components/navModel.ts` (+ test), `web/src/components/NavIcon.tsx`
- `web/src/routes.tsx`, `web/src/features/admin/AdminPage.tsx`
- `web/src/features/board/WorkOrderDetailPage.tsx` (+ test), `web/src/test/factories.ts`
- `web/src/api/schema.json`, `web/src/api/types.generated.ts` — regenerated

---

## Task 1: Enums, models, migration, dependency

**Files:**
- Modify: `server/pyproject.toml:6-29`
- Modify: `server/app/schemas/enums.py` (append)
- Create: `server/app/models/pm.py`
- Modify: `server/app/models/__init__.py`
- Create: `server/alembic/versions/0007_preventative_maintenance.py`
- Modify: `server/tests/test_models.py:14-22`
- Create: `server/tests/test_pm_models.py`

**Interfaces:**
- Produces: models `MaintainableUnit`, `PmTemplate`, `PmTemplateItem`, `PmTemplateUnit`, `PmCycle`, `PmRun`, `PmRunAnswer`, `PmRunPhoto`; enums `PmUnitKind`, `PmUnitSource`, `PmTemplateMode`, `PmCadence`, `PmItemType`, `PmCycleStatus`, `PmRunStatus`. `min_value`/`max_value`/`number_value` are Python `float | None`.

- [ ] **Step 1: Add the dependency and install it**

In `server/pyproject.toml`, inside `dependencies = [...]`, after the `psycopg[binary]` line:

```toml
  # RFC 5545 RRULE expansion for scheduled PM templates (spec §3.10). Hand-rolling
  # recurrence is not an option.
  "python-dateutil>=2.9",
```

Run: `cd server && ../.venv/Scripts/python.exe -m pip install -e ".[dev]"`
Expected: ends with `Successfully installed ... python-dateutil-2.9.x` (or "Requirement already satisfied" if transitively present — either way `../.venv/Scripts/python.exe -c "import dateutil.rrule"` must print nothing).

- [ ] **Step 2: Append the enums**

Append to `server/app/schemas/enums.py`:

```python


class PmUnitKind(StrEnum):
    guest_room = "guest_room"
    common_area = "common_area"
    equipment = "equipment"


class PmUnitSource(StrEnum):
    manual = "manual"
    csv = "csv"
    pms = "pms"


class PmTemplateMode(StrEnum):
    sweep = "sweep"
    scheduled = "scheduled"


class PmCadence(StrEnum):
    monthly = "monthly"
    quarterly = "quarterly"
    semiannual = "semiannual"
    annual = "annual"


class PmItemType(StrEnum):
    checkbox = "checkbox"
    text = "text"
    number = "number"
    photo = "photo"


class PmCycleStatus(StrEnum):
    open = "open"
    closed = "closed"


class PmRunStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    passed = "passed"
    failed = "failed"
    missed = "missed"
```

- [ ] **Step 3: Write the failing model round-trip test**

Create `server/tests/test_pm_models.py`:

```python
"""Preventative maintenance tables (spec §3). Round trips and the constraints that matter."""
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import clock
from app.models import (
    MaintainableUnit,
    PmCycle,
    PmRun,
    PmRunAnswer,
    PmRunPhoto,
    PmTemplate,
    PmTemplateItem,
    PmTemplateUnit,
)
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)


def test_unit_template_cycle_run_answer_photo_round_trip(database, fx):
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204", floor=2, room_type="KNGN")
        db.add(unit)
        db.flush()
        template = PmTemplate(property_id=fx.property_a.id, name="Guest Room Quarterly",
                              mode=PmTemplateMode.sweep, unit_kind=PmUnitKind.guest_room,
                              cadence=PmCadence.quarterly,
                              department_id=fx.dept_engineering.id)
        db.add(template)
        db.flush()
        item = PmTemplateItem(template_id=template.id, property_id=fx.property_a.id,
                              position=0, label="Tap hot-water temperature",
                              item_type=PmItemType.number, unit="°F",
                              min_value=100, max_value=120, required=True)
        db.add(item)
        cycle = PmCycle(property_id=fx.property_a.id, template_id=template.id, ordinal=3,
                        starts_on=date(2026, 7, 1), ends_on=date(2026, 9, 30),
                        status=PmCycleStatus.open)
        db.add(cycle)
        db.flush()
        run = PmRun(property_id=fx.property_a.id, template_id=template.id, unit_id=unit.id,
                    cycle_id=cycle.id, status=PmRunStatus.in_progress,
                    started_by_user_id=fx.engineer_a.id, started_at=clock.now())
        db.add(run)
        db.flush()
        db.add(PmRunAnswer(run_id=run.id, property_id=fx.property_a.id, item_id=item.id,
                           number_value=122.5, out_of_range=True, answered_at=clock.now()))
        db.add(PmRunPhoto(run_id=run.id, property_id=fx.property_a.id, item_id=None,
                          uploaded_by_user_id=fx.engineer_a.id, content_type="image/png",
                          byte_size=3, data=b"abc"))
        db.flush()
        ids = (unit.id, template.id, run.id)

    with database.session() as db:
        unit = db.get(MaintainableUnit, ids[0])
        assert unit.source == PmUnitSource.manual and unit.active is True
        template = db.get(PmTemplate, ids[1])
        assert template.mode == PmTemplateMode.sweep and template.rrule is None
        run = db.get(PmRun, ids[2])
        assert run.status == PmRunStatus.in_progress
        answer = db.scalar(select(PmRunAnswer).where(PmRunAnswer.run_id == run.id))
        assert answer.number_value == 122.5 and isinstance(answer.number_value, float)
        assert answer.out_of_range is True
        photo = db.scalar(select(PmRunPhoto).where(PmRunPhoto.run_id == run.id))
        assert photo.data == b"abc"


def test_unit_code_is_unique_per_property(database, fx):
    with database.session() as db:
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204"))
        # Same code at another property is fine.
        db.add(MaintainableUnit(property_id=fx.property_b.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204"))
        db.flush()
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.equipment,
                                code="204", name="Dup"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_mode_check_constraint_rejects_a_sweep_with_an_rrule(database, fx):
    with database.session() as db:
        db.add(PmTemplate(property_id=fx.property_a.id, name="Bad", mode=PmTemplateMode.sweep,
                          unit_kind=PmUnitKind.guest_room, cadence=PmCadence.monthly,
                          rrule="FREQ=DAILY", rrule_dtstart=date(2026, 1, 1)))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_mode_check_constraint_rejects_a_scheduled_template_without_a_start(
        database, fx):
    with database.session() as db:
        db.add(PmTemplate(property_id=fx.property_a.id, name="Bad",
                          mode=PmTemplateMode.scheduled, rrule="FREQ=DAILY"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_template_unit_and_run_answer_are_unique(database, fx):
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.equipment,
                                code="BOILER-1", name="Boiler 1")
        template = PmTemplate(property_id=fx.property_a.id, name="Boiler",
                              mode=PmTemplateMode.scheduled, rrule="FREQ=MONTHLY;INTERVAL=3",
                              rrule_dtstart=date(2026, 7, 1))
        db.add_all([unit, template])
        db.flush()
        db.add(PmTemplateUnit(template_id=template.id, unit_id=unit.id,
                              property_id=fx.property_a.id))
        db.flush()
        db.add(PmTemplateUnit(template_id=template.id, unit_id=unit.id,
                              property_id=fx.property_a.id))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
```

- [ ] **Step 4: Run it to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_models.py -q`
Expected: `ImportError: cannot import name 'MaintainableUnit' from 'app.models'`

- [ ] **Step 5: Write the models**

Create `server/app/models/pm.py`:

```python
"""Preventative maintenance (spec §3).

Eight tables on one design rule: `pm_run` is the compliance currency. A sweep `Start` creates
one directly; an RRULE firing creates a `WorkOrder(type=pm)` with one attached. Compliance is
therefore one query over `pm_run` and never a merge of two shapes.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)

# asdecimal=False: the API and the frontend speak float. Decimal would serialise as a string in
# Pydantic's JSON mode and reach TypeScript as `string`, which is wrong for a reading.
READING = Numeric(10, 2, asdecimal=False)


class MaintainableUnit(TimestampMixin, Base):
    """A room, common/BOH area or piece of equipment that PM is performed on (spec §3.1).

    Deactivate rather than delete: historical runs reference the row. `source` + `external_id`
    are the hook for a later PMS sync, which upserts guest rooms by external id and never touches
    `manual`/`csv` rows.
    """

    __tablename__ = "maintainable_unit"
    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_maintainable_unit_property_code"),
        Index("ix_maintainable_unit_property_kind", "property_id", "kind"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    kind: Mapped[PmUnitKind] = mapped_column(enum_type(PmUnitKind), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    floor: Mapped[int | None] = mapped_column(Integer)
    room_type: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[PmUnitSource] = mapped_column(
        enum_type(PmUnitSource), default=PmUnitSource.manual, nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)


class PmTemplate(TimestampMixin, Base):
    """One table, two modes (spec §3.2). The CHECK keeps the mode-specific columns honest on both
    engines: a sweep row has a kind and cadence and no rrule; a scheduled row has an rrule and a
    start date and no cadence."""

    __tablename__ = "pm_template"
    __table_args__ = (
        CheckConstraint(
            "(mode = 'sweep' AND unit_kind IS NOT NULL AND cadence IS NOT NULL "
            "AND rrule IS NULL) OR "
            "(mode = 'scheduled' AND rrule IS NOT NULL AND rrule_dtstart IS NOT NULL "
            "AND cadence IS NULL)",
            name="ck_pm_template_mode_fields",
        ),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[PmTemplateMode] = mapped_column(enum_type(PmTemplateMode), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unit_kind: Mapped[PmUnitKind | None] = mapped_column(enum_type(PmUnitKind))
    cadence: Mapped[PmCadence | None] = mapped_column(enum_type(PmCadence))
    rrule: Mapped[str | None] = mapped_column(String(500))
    rrule_dtstart: Mapped[date | None] = mapped_column(Date)
    last_fired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmTemplateItem(TimestampMixin, Base):
    """The typed checklist (spec §3.3). Soft-deleted via `active` because `pm_run_answer`
    references it — an admin editing a template must not orphan last quarter's evidence."""

    __tablename__ = "pm_template_item"
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type: Mapped[PmItemType] = mapped_column(enum_type(PmItemType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    min_value: Mapped[float | None] = mapped_column(READING)
    max_value: Mapped[float | None] = mapped_column(READING)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PmTemplateUnit(TimestampMixin, Base):
    """Which specific units a *scheduled* template targets (spec §3.4). A table rather than a
    JSON array for the same portability reason as log_entry_mention."""

    __tablename__ = "pm_template_unit"
    __table_args__ = (
        UniqueConstraint("template_id", "unit_id", name="uq_pm_template_unit"),
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    unit_id: Mapped[str] = mapped_column(
        ForeignKey("maintainable_unit.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)


class PmCycle(TimestampMixin, Base):
    """A sweep window (spec §3.5). `starts_on`/`ends_on` are property-local calendar dates, not
    instants — "Jul 01 – Sep 30" is compared against today in the property timezone, never
    against a UTC column."""

    __tablename__ = "pm_cycle"
    __table_args__ = (
        UniqueConstraint("template_id", "starts_on", name="uq_pm_cycle_template_start"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PmCycleStatus] = mapped_column(
        enum_type(PmCycleStatus), default=PmCycleStatus.open, nullable=False
    )


class PmRun(TimestampMixin, Base):
    """The compliance currency (spec §3.6).

    pending → in_progress → completed → passed | failed; `missed` is written by cycle close for
    every in-scope unit without a passed run and never transitions. `cycle_id` is set on sweep
    runs, `work_order_id` on scheduled ones; never both.
    """

    __tablename__ = "pm_run"
    __table_args__ = (
        Index("ix_pm_run_property_cycle_unit_status",
              "property_id", "cycle_id", "unit_id", "status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    unit_id: Mapped[str] = mapped_column(
        ForeignKey("maintainable_unit.id"), nullable=False, index=True
    )
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("pm_cycle.id"), index=True)
    work_order_id: Mapped[str | None] = mapped_column(ForeignKey("work_order.id"), index=True)
    status: Mapped[PmRunStatus] = mapped_column(enum_type(PmRunStatus), nullable=False)
    started_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspection_note: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmRunAnswer(TimestampMixin, Base):
    """One row per active item, created at Start so progress saves continuously (spec §3.7).
    `answered_at` null means not yet answered."""

    __tablename__ = "pm_run_answer"
    __table_args__ = (
        UniqueConstraint("run_id", "item_id", name="uq_pm_run_answer_run_item"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("pm_run.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("pm_template_item.id"), nullable=False)
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(READING)
    out_of_range: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmRunPhoto(TimestampMixin, Base):
    """Bytes in the table for the same reason as work_order_photo (app/models/work_orders.py:67):
    the deployment target's filesystem is ephemeral. `data` is deferred so listing a run's photos
    never drags the blobs along. A photo with an `item_id` answers that `photo` item; one
    without is general evidence for the run (spec §3.8)."""

    __tablename__ = "pm_run_photo"
    run_id: Mapped[str] = mapped_column(ForeignKey("pm_run.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("pm_template_item.id"))
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
```

Update `server/app/models/__init__.py` — add the import and the `__all__` entries:

```python
from app.models.pm import (
    MaintainableUnit,
    PmCycle,
    PmRun,
    PmRunAnswer,
    PmRunPhoto,
    PmTemplate,
    PmTemplateItem,
    PmTemplateUnit,
)
```

and in `__all__`, keeping it alphabetical: `"MaintainableUnit"` after `"LogEntryPhoto"`, and `"PmCycle", "PmRun", "PmRunAnswer", "PmRunPhoto", "PmTemplate", "PmTemplateItem", "PmTemplateUnit"` after `"Message"` and before `"Notification"`. (`ruff` sorts imports; `__all__` is hand-ordered.)

- [ ] **Step 6: Write the migration**

Create `server/alembic/versions/0007_preventative_maintenance.py`:

```python
"""preventative maintenance: maintainable_unit, pm_template, pm_template_item, pm_template_unit,
pm_cycle, pm_run, pm_run_answer, pm_run_photo

Phase 2 §6.6 (docs/superpowers/specs/2026-09-19-preventative-maintenance-design.md).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-19

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


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
        "maintainable_unit",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("kind", _enum("ck_enum_pmunitkind", "guest_room", "common_area", "equipment"),
                  nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("room_type", sa.String(length=20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source", _enum("ck_enum_pmunitsource", "manual", "csv", "pms"),
                  nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "code", name="uq_maintainable_unit_property_code"),
    )
    with op.batch_alter_table("maintainable_unit", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_maintainable_unit_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index("ix_maintainable_unit_property_kind", ["property_id", "kind"],
                              unique=False)

    op.create_table(
        "pm_template",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mode", _enum("ck_enum_pmtemplatemode", "sweep", "scheduled"), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("unit_kind",
                  _enum("ck_enum_pmunitkind", "guest_room", "common_area", "equipment"),
                  nullable=True),
        sa.Column("cadence",
                  _enum("ck_enum_pmcadence", "monthly", "quarterly", "semiannual", "annual"),
                  nullable=True),
        sa.Column("rrule", sa.String(length=500), nullable=True),
        sa.Column("rrule_dtstart", sa.Date(), nullable=True),
        sa.Column("last_fired_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(mode = 'sweep' AND unit_kind IS NOT NULL AND cadence IS NOT NULL "
            "AND rrule IS NULL) OR "
            "(mode = 'scheduled' AND rrule IS NOT NULL AND rrule_dtstart IS NOT NULL "
            "AND cadence IS NULL)",
            name="ck_pm_template_mode_fields",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_template_item",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("item_type", _enum("ck_enum_pmitemtype", "checkbox", "text", "number", "photo"),
                  nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("min_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("max_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_template_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_item_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_item_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_template_unit",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "unit_id", name="uq_pm_template_unit"),
    )
    with op.batch_alter_table("pm_template_unit", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_unit_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_unit_unit_id"), ["unit_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_unit_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_cycle",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", _enum("ck_enum_pmcyclestatus", "open", "closed"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "starts_on", name="uq_pm_cycle_template_start"),
    )
    with op.batch_alter_table("pm_cycle", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_cycle_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_cycle_template_id"), ["template_id"],
                              unique=False)

    op.create_table(
        "pm_run",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=True),
        sa.Column("work_order_id", sa.String(length=36), nullable=True),
        sa.Column("status",
                  _enum("ck_enum_pmrunstatus", "pending", "in_progress", "completed", "passed",
                        "failed", "missed"),
                  nullable=False),
        sa.Column("started_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("completed_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspection_note", sa.Text(), nullable=True),
        sa.Column("due_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["pm_cycle.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_order.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["inspected_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_run", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_property_id"), ["property_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_template_id"), ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_unit_id"), ["unit_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_work_order_id"), ["work_order_id"],
                              unique=False)
        batch_op.create_index("ix_pm_run_property_cycle_unit_status",
                              ["property_id", "cycle_id", "unit_id", "status"], unique=False)

    op.create_table(
        "pm_run_answer",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("out_of_range", sa.Boolean(), nullable=False),
        sa.Column("answered_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["run_id"], ["pm_run.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["pm_template_item.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "item_id", name="uq_pm_run_answer_run_item"),
    )
    with op.batch_alter_table("pm_run_answer", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_answer_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_answer_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_run_photo",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["run_id"], ["pm_run.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["pm_template_item.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_run_photo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_photo_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_photo_property_id"), ["property_id"],
                              unique=False)


def downgrade() -> None:
    # FK-safe order: children before parents.
    for table in ("pm_run_photo", "pm_run_answer", "pm_run", "pm_cycle", "pm_template_unit",
                  "pm_template_item", "pm_template", "maintainable_unit"):
        op.drop_table(table)
```

`op.drop_table` drops the table's indexes with it on both engines, which is why `downgrade` does not mirror the batch index drops the 0006 migration wrote out — those were belt-and-braces there, and eight tables of them here would be sixty lines saying nothing.

- [ ] **Step 7: Register the tables in the registry test**

In `server/tests/test_models.py`, extend `EXPECTED_TABLES`:

```python
    "log_entry", "log_entry_mention", "log_entry_photo", "log_entry_ack",
    "maintainable_unit", "pm_template", "pm_template_item", "pm_template_unit",
    "pm_cycle", "pm_run", "pm_run_answer", "pm_run_photo",
}
```

- [ ] **Step 8: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_models.py tests/test_models.py -q`
Expected: all pass.

Run: `cd server && ../.venv/Scripts/python.exe -m alembic downgrade 0006 && ../.venv/Scripts/python.exe -m alembic upgrade head` (against the default dev sqlite URL in `alembic.ini`)
Expected: both commands succeed; no traceback.

- [ ] **Step 9: Lint and commit**

Run: `cd server && ../.venv/Scripts/python.exe -m ruff check .`
Expected: `All checks passed!`

```bash
git add server/pyproject.toml server/app/schemas/enums.py server/app/models/pm.py server/app/models/__init__.py server/alembic/versions/0007_preventative_maintenance.py server/tests/test_models.py server/tests/test_pm_models.py
git commit -m "feat(server): preventative maintenance tables and migration 0007

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: Capabilities, both sides

**Files:**
- Modify: `server/app/auth/permissions.py:7-22`
- Modify: `web/src/auth/capabilities.ts`
- Modify: `web/src/auth/capabilities.test.ts` (append)
- Create: `server/tests/test_pm_permissions.py`

**Interfaces:**
- Produces: capabilities `view_pm`, `perform_pm`, `inspect_pm` on both sides.

- [ ] **Step 1: Write the failing server test**

Create `server/tests/test_pm_permissions.py`:

```python
from app.auth.permissions import CAPABILITIES, has_capability
from app.schemas.enums import Role


def test_pm_capabilities_match_the_spec():
    """Spec §6. Every one includes admin — test_isolation.py demands it."""
    assert CAPABILITIES["view_pm"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                       Role.manager, Role.admin, Role.corporate}
    assert CAPABILITIES["perform_pm"] == {Role.dept_staff, Role.supervisor, Role.manager,
                                          Role.admin}
    assert CAPABILITIES["inspect_pm"] == {Role.supervisor, Role.manager, Role.admin}
    for cap in ("view_pm", "perform_pm", "inspect_pm"):
        assert has_capability(Role.admin, cap), cap
    assert not has_capability(Role.agent, "perform_pm")
    assert not has_capability(Role.dept_staff, "inspect_pm")
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_permissions.py -q`
Expected: `KeyError: 'view_pm'`

- [ ] **Step 2: Add the server capabilities**

In `server/app/auth/permissions.py`, after the `"pin_log_entry"` line inside `CAPABILITIES`:

```python
    # Preventative maintenance (PM spec §6). All three include admin: the isolation suite
    # asserts a property's admin is never 403 on a property route.
    "view_pm": STAFF,
    "perform_pm": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "inspect_pm": {Role.supervisor, Role.manager, Role.admin},
```

Run the test again. Expected: PASS.

- [ ] **Step 3: Write the failing web test**

Append to `web/src/auth/capabilities.test.ts`:

```ts

describe('pm capabilities', () => {
  const roles: Role[] = ['agent', 'dept_staff', 'supervisor', 'manager', 'admin', 'corporate']

  it('lets every staff role view PM', () => {
    for (const role of roles) expect(hasCapability(role, 'view_pm'), role).toBe(true)
  })

  it('lets dept_staff and above perform, but not agents or corporate', () => {
    expect(hasCapability('agent', 'perform_pm')).toBe(false)
    expect(hasCapability('corporate', 'perform_pm')).toBe(false)
    for (const role of ['dept_staff', 'supervisor', 'manager', 'admin'] as Role[])
      expect(hasCapability(role, 'perform_pm'), role).toBe(true)
  })

  it('restricts inspection to supervisor and above', () => {
    expect(hasCapability('dept_staff', 'inspect_pm')).toBe(false)
    expect(hasCapability('corporate', 'inspect_pm')).toBe(false)
    for (const role of ['supervisor', 'manager', 'admin'] as Role[])
      expect(hasCapability(role, 'inspect_pm'), role).toBe(true)
  })
})
```

Run: `cd web && npx vitest run src/auth/capabilities.test.ts`
Expected: TypeScript error / failures on the unknown capability names.

- [ ] **Step 4: Mirror on the web**

In `web/src/auth/capabilities.ts`, extend the `Capability` union after `| 'pin_log_entry'`:

```ts
  | 'view_pm'
  | 'perform_pm'
  | 'inspect_pm'
```

and the `CAPABILITIES` record after `pin_log_entry`:

```ts
  view_pm: STAFF,
  perform_pm: ['dept_staff', 'supervisor', 'manager', 'admin'],
  inspect_pm: ['supervisor', 'manager', 'admin'],
```

Run: `cd web && npx vitest run src/auth/capabilities.test.ts && npm run lint`
Expected: all pass, lint clean.

- [ ] **Step 5: Commit**

```bash
git add server/app/auth/permissions.py server/tests/test_pm_permissions.py web/src/auth/capabilities.ts web/src/auth/capabilities.test.ts
git commit -m "feat: view_pm, perform_pm and inspect_pm capabilities on both sides

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 3: API schemas and generated types

**Files:**
- Create: `server/app/schemas/pm.py`
- Modify: `server/app/schemas/work_orders.py:88-92` (`WorkOrderDetail.pm_run_id`)
- Modify: `server/app/schemas/export_json_schema.py:11-27`
- Modify: `server/tests/test_schema_export.py:7-14`
- Modify: `web/src/api/types.ts`
- Regenerate: `web/src/api/schema.json`, `web/src/api/types.generated.ts`

**Interfaces:**
- Produces: every Pydantic model named below, imported by Tasks 4–11 exactly by these names.

- [ ] **Step 1: Extend the schema-export test**

In `server/tests/test_schema_export.py`, extend the tuple in `test_export_contains_the_public_models` after `"LogMentionableOut"`:

```python
                 "UnitOut", "UnitImportOut", "TemplateOut", "SweepOut", "RunOut",
                 "InspectionRowOut", "CycleOut", "ComplianceOut"):
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q`
Expected: FAIL on `UnitOut`.

- [ ] **Step 2: Write the schemas**

Create `server/app/schemas/pm.py`:

```python
"""Preventative maintenance wire models (spec §5). Readings are float on the wire — see
app/models/pm.py READING."""
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 1024 * 1024


# ---- inventory ---------------------------------------------------------------------------

class UnitIn(CamelModel):
    kind: PmUnitKind
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    floor: int | None = None
    room_type: str | None = Field(default=None, max_length=20)
    external_id: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class UnitPatch(CamelModel):
    kind: PmUnitKind | None = None
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    floor: int | None = None
    room_type: str | None = Field(default=None, max_length=20)
    active: bool | None = None
    external_id: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class UnitOut(CamelModel):
    id: str
    kind: PmUnitKind
    code: str
    name: str
    floor: int | None = None
    room_type: str | None = None
    active: bool
    source: PmUnitSource
    external_id: str | None = None
    notes: str | None = None
    created_at: datetime


class UnitListQuery(CamelModel):
    kind: PmUnitKind | None = None
    active: bool | None = None
    q: str | None = None


class UnitImportError(CamelModel):
    line: int
    field: str
    message: str


class UnitImportOut(CamelModel):
    created: int
    updated: int
    errors: list[UnitImportError] = Field(default_factory=list)


# ---- templates ---------------------------------------------------------------------------

class TemplateItemIn(CamelModel):
    """`id` set = update that item in place; omitted = a new item. An item missing from the
    list is soft-deleted (spec §4.5)."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    item_type: PmItemType
    unit: str | None = Field(default=None, max_length=16)
    min_value: float | None = None
    max_value: float | None = None
    required: bool = True


class TemplateItemOut(CamelModel):
    id: str
    position: int
    label: str
    item_type: PmItemType
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    required: bool
    active: bool


class TemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    mode: PmTemplateMode
    department_id: str | None = None
    active: bool = True
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = Field(default=None, max_length=500)
    rrule_dtstart: date | None = None
    unit_ids: list[str] = Field(default_factory=list, max_length=500)
    items: list[TemplateItemIn] = Field(default_factory=list, max_length=100)


class TemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    mode: PmTemplateMode | None = None
    department_id: str | None = None
    active: bool | None = None
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = Field(default=None, max_length=500)
    rrule_dtstart: date | None = None
    unit_ids: list[str] | None = Field(default=None, max_length=500)
    items: list[TemplateItemIn] | None = Field(default=None, max_length=100)


class TemplateOut(CamelModel):
    id: str
    name: str
    mode: PmTemplateMode
    department_id: str | None = None
    active: bool
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = None
    rrule_dtstart: date | None = None
    last_fired_at: datetime | None = None
    unit_ids: list[str] = Field(default_factory=list)
    items: list[TemplateItemOut] = Field(default_factory=list)
    has_runs: bool
    created_at: datetime


# ---- cycles and the sweep page ----------------------------------------------------------

class CycleOut(CamelModel):
    id: str
    template_id: str
    ordinal: int
    starts_on: date
    ends_on: date
    status: PmCycleStatus
    days_left: int
    passed: int
    missed: int
    total: int


class SweepQuery(CamelModel):
    kind: PmUnitKind
    status: Literal["remaining", "completed"] | None = None
    q: str | None = None
    sort: Literal["code", "floor", "days_since_last_pm"] = "code"


class SweepTemplateOut(CamelModel):
    id: str
    name: str
    cadence: PmCadence


class SweepCycleOut(CamelModel):
    id: str
    ordinal: int
    starts_on: date
    ends_on: date
    days_left: int


class SweepCounts(CamelModel):
    remaining: int
    completed: int
    total: int


class SweepRunBrief(CamelModel):
    id: str
    status: PmRunStatus
    started_by_user_id: str | None = None
    started_by_name: str | None = None


class SweepUnitOut(CamelModel):
    id: str
    code: str
    name: str
    floor: int | None = None
    room_type: str | None = None
    last_passed_at: datetime | None = None
    last_passed_by_name: str | None = None
    passed_this_cycle: bool
    current_run: SweepRunBrief | None = None


class SweepOut(CamelModel):
    template: SweepTemplateOut | None = None
    cycle: SweepCycleOut | None = None
    counts: SweepCounts
    units: list[SweepUnitOut] = Field(default_factory=list)


# ---- runs --------------------------------------------------------------------------------

class StartRunRequest(CamelModel):
    template_id: str
    unit_id: str


class AnswerPatch(CamelModel):
    """Exactly one of these, matching the item's type (spec §4.2)."""

    bool_value: bool | None = None
    text_value: str | None = Field(default=None, max_length=2000)
    number_value: float | None = None


class RunAnswerOut(CamelModel):
    id: str
    item_id: str
    bool_value: bool | None = None
    text_value: str | None = None
    number_value: float | None = None
    out_of_range: bool
    answered_at: datetime | None = None


class RunPhotoOut(CamelModel):
    id: str
    item_id: str | None = None
    content_type: str
    byte_size: int
    uploaded_by_user_id: str | None = None
    url: str
    created_at: datetime


class RunOut(CamelModel):
    id: str
    template_id: str
    template_name: str
    unit_id: str
    unit_code: str
    unit_name: str
    unit_kind: PmUnitKind
    cycle_id: str | None = None
    work_order_id: str | None = None
    status: PmRunStatus
    started_by_user_id: str | None = None
    started_by_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    inspected_by_user_id: str | None = None
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None
    inspection_note: str | None = None
    due_at: datetime | None = None
    items: list[TemplateItemOut] = Field(default_factory=list)
    answers: list[RunAnswerOut] = Field(default_factory=list)
    photos: list[RunPhotoOut] = Field(default_factory=list)
    # Item ids that still block Complete. Empty once the run can be completed.
    missing_required: list[str] = Field(default_factory=list)


class InspectRequest(CamelModel):
    result: Literal["pass", "fail"]
    note: str | None = Field(default=None, max_length=2000)


class InspectionQuery(CamelModel):
    kind: PmUnitKind | None = None
    status: Literal["available", "inspected"] = "available"
    sort: Literal["days_since_last_pm", "completed_at"] = "completed_at"


class InspectionRowOut(CamelModel):
    run_id: str
    unit_id: str
    unit_code: str
    unit_name: str
    unit_kind: PmUnitKind
    template_name: str
    completed_by_name: str | None = None
    completed_at: datetime | None = None
    # Days since this unit's previous passed PM (not counting this run). None = never.
    days_since_last_pm: int | None = None
    status: PmRunStatus
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None


# ---- compliance --------------------------------------------------------------------------

class ComplianceQuery(CamelModel):
    from_: str = Field(alias="from")
    to: str


class ComplianceCycleOut(CamelModel):
    ordinal: int
    starts_on: date
    ends_on: date
    status: PmCycleStatus
    passed: int
    missed: int
    total: int
    on_time_pct: float


class ComplianceRunsOut(CamelModel):
    due: int
    passed: int
    failed: int
    overdue: int


class ComplianceTemplateOut(CamelModel):
    id: str
    name: str
    mode: PmTemplateMode
    unit_kind: PmUnitKind | None = None
    cycles: list[ComplianceCycleOut] = Field(default_factory=list)
    runs: ComplianceRunsOut | None = None
    inspection_pass_rate: float | None = None


class ComplianceOut(CamelModel):
    templates: list[ComplianceTemplateOut] = Field(default_factory=list)
```

- [ ] **Step 3: `WorkOrderDetail.pm_run_id` and the export registry**

In `server/app/schemas/work_orders.py`, `WorkOrderDetail`:

```python
class WorkOrderDetail(WorkOrderOut):
    events: list[WorkOrderEventOut]
    photos: list[WorkOrderPhotoOut]
    guest_name: str | None = None
    room_number: str | None = None
    # Set on a scheduled-PM work order; the detail page links to the checklist (PM spec §7.7).
    pm_run_id: str | None = None
```

In `server/app/schemas/export_json_schema.py`, add `pm` to the import list (alphabetical: after `notifications`) and to `MODULES`:

```python
MODULES = (auth, users, conversations, work_orders, content, notifications, analytics,
           properties, staff_messages, log, pm, dev)
```

- [ ] **Step 4: Regenerate and re-export**

Run:
```
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```
Expected: `wrote .../web/src/api/schema.json`; json2ts writes `types.generated.ts` without error.

Add to the re-export list in `web/src/api/types.ts` (keep the list roughly alphabetical; the exact position does not matter to the compiler):

```ts
  AnswerPatch, ComplianceCycleOut, ComplianceOut, ComplianceRunsOut, ComplianceTemplateOut,
  CycleOut, InspectRequest, InspectionRowOut, PmCadence, PmCycleStatus, PmItemType, PmRunStatus,
  PmTemplateMode, PmUnitKind, PmUnitSource, RunAnswerOut, RunOut, RunPhotoOut, StartRunRequest,
  SweepCounts, SweepCycleOut, SweepOut, SweepRunBrief, SweepTemplateOut, SweepUnitOut,
  TemplateIn, TemplateItemIn, TemplateItemOut, TemplateOut, TemplatePatch, UnitImportError,
  UnitImportOut, UnitIn, UnitOut, UnitPatch,
```

- [ ] **Step 5: Verify**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q && ../.venv/Scripts/python.exe -m ruff check .`
Run: `cd web && npm test && npm run lint && npm run build`
Expected: all clean. (`types.generated.test.ts` checks the generated file matches `schema.json`.)

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas/pm.py server/app/schemas/work_orders.py server/app/schemas/export_json_schema.py server/tests/test_schema_export.py web/src/api/types.ts web/src/api/schema.json web/src/api/types.generated.ts
git commit -m "feat: preventative maintenance API schemas and generated types

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 4: Inventory — domain, CSV import, blueprint

**Files:**
- Create: `server/app/domain/pm_units.py`
- Create: `server/app/api/maintainable_units.py`
- Modify: `server/app/__init__.py:65-82` (register)
- Create: `server/tests/test_pm_units.py`

**Interfaces:**
- Produces: `pm_units.get(db, property_id, unit_id) -> MaintainableUnit`, `pm_units.to_out(unit) -> UnitOut`, `pm_units.natural_key(code) -> tuple`, `pm_units.LOCATION_FOR_KIND: dict[PmUnitKind, LocationType]`, `pm_units.import_csv(db, property_id, actor_user_id, text) -> UnitImportOut`.
- Routes: `GET/POST /api/p/<pid>/maintainable-units`, `PATCH …/<unit_id>`, `POST …/import`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_units.py`:

```python
"""Maintainable-unit inventory (spec §3.1, §5.1, §5.4)."""
import io

from sqlalchemy import func, select

from app.models import MaintainableUnit

SAMPLE = (
    "code,kind,name,floor,room_type,external_id\n"
    "204,guest_room,Room 204,2,KNGN,\n"
    "POOL-PUMP-1,equipment,Pool pump 1,,,\n"
    "LOBBY,common_area,Lobby,1,,pms-lobby\n"
)


def _base(fx):
    return f"/api/p/{fx.property_a.id}/maintainable-units"


def _import(client, fx, text: str):
    return client.post(f"{_base(fx)}/import",
                       data={"file": (io.BytesIO(text.encode()), "units.csv", "text/csv")},
                       content_type="multipart/form-data")


def test_create_list_and_patch(app, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(_base(fx), json={"kind": "guest_room", "code": " 204 ", "name": "Room 204",
                                      "floor": 2, "roomType": "KNGN"})
    assert res.status_code == 201, res.get_json()
    unit = res.get_json()
    assert unit["code"] == "204" and unit["source"] == "manual" and unit["active"] is True

    rows = login("agent@hvh.test").get(f"{_base(fx)}?kind=guest_room").get_json()
    assert [r["id"] for r in rows] == [unit["id"]]
    assert login("agent@hvh.test").get(f"{_base(fx)}?kind=equipment").get_json() == []
    assert login("agent@hvh.test").get(f"{_base(fx)}?q=room+2").get_json()[0]["id"] == unit["id"]

    res = admin.patch(f"{_base(fx)}/{unit['id']}", json={"active": False, "notes": "Out of order"})
    assert res.status_code == 200 and res.get_json()["active"] is False
    assert login("agent@hvh.test").get(f"{_base(fx)}?active=true").get_json() == []


def test_duplicate_code_is_a_409_on_create_and_patch(app, fx, login):
    admin = login("admin@hvh.test")
    a = admin.post(_base(fx), json={"kind": "guest_room", "code": "204", "name": "A"}).get_json()
    admin.post(_base(fx), json={"kind": "guest_room", "code": "205", "name": "B"})
    assert admin.post(_base(fx), json={"kind": "equipment", "code": "204",
                                       "name": "C"}).status_code == 409
    assert admin.patch(f"{_base(fx)}/{a['id']}", json={"code": "205"}).status_code == 409


def test_writes_require_manage_admin_and_reads_are_open_to_staff(app, fx, login):
    for c in (login("engineer@hvh.test"), login("manager@hvh.test")):
        assert c.get(_base(fx)).status_code == 200
        assert c.post(_base(fx), json={"kind": "guest_room", "code": "1", "name": "x"}) \
            .status_code == 403
        assert _import(c, fx, SAMPLE).status_code == 403


def test_natural_sort_puts_numeric_codes_first_in_numeric_order(app, fx, login):
    admin = login("admin@hvh.test")
    for code in ("1001", "205", "BOILER-1", "99", "ANNEX"):
        admin.post(_base(fx), json={"kind": "equipment", "code": code, "name": code})
    codes = [r["code"] for r in admin.get(f"{_base(fx)}?kind=equipment").get_json()]
    assert codes == ["99", "205", "1001", "ANNEX", "BOILER-1"]


def test_import_creates_then_updates_idempotently(app, fx, login, database):
    admin = login("admin@hvh.test")
    res = _import(admin, fx, SAMPLE)
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {"created": 3, "updated": 0, "errors": []}
    with database.session() as db:
        pump = db.scalar(select(MaintainableUnit).where(MaintainableUnit.code == "POOL-PUMP-1"))
        assert pump.kind.value == "equipment" and pump.floor is None and pump.source.value == "csv"
        lobby = db.scalar(select(MaintainableUnit).where(MaintainableUnit.code == "LOBBY"))
        assert lobby.external_id == "pms-lobby"

    res = _import(admin, fx, SAMPLE.replace("Room 204", "Room 204 (renamed)"))
    assert res.get_json() == {"created": 0, "updated": 3, "errors": []}
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(MaintainableUnit)) == 3
        assert db.scalar(select(MaintainableUnit.name)
                         .where(MaintainableUnit.code == "204")) == "Room 204 (renamed)"


def test_import_with_one_bad_row_writes_nothing_and_names_the_line(app, fx, login, database):
    admin = login("admin@hvh.test")
    bad = SAMPLE.replace("equipment,Pool pump 1", "gadget,Pool pump 1")
    res = _import(admin, fx, bad)
    assert res.status_code == 422
    # The report rides in the standard error envelope so the client's ApiError.details is
    # the report itself (web/src/api/client.ts reads only `body.error`).
    body = res.get_json()["error"]
    assert body["code"] == "IMPORT_REJECTED"
    report = body["details"]
    assert report["created"] == 0 and report["updated"] == 0
    assert report["errors"][0]["line"] == 3 and report["errors"][0]["field"] == "kind"
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(MaintainableUnit)) == 0


def test_import_rejects_duplicate_codes_in_the_file_and_a_wrong_header(app, fx, login):
    admin = login("admin@hvh.test")
    dup = SAMPLE + "204,guest_room,Again,2,,\n"
    report = _import(admin, fx, dup).get_json()["error"]["details"]
    assert [e["line"] for e in report["errors"]] == [5]
    assert "duplicate" in report["errors"][0]["message"]

    report = _import(admin, fx, "code,kind,name\n204,guest_room,Room\n").get_json()["error"]["details"]
    assert report["errors"][0]["line"] == 1 and report["errors"][0]["field"] == "header"


def test_import_requires_a_file_and_caps_its_size(app, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(f"{_base(fx)}/import", data={}, content_type="multipart/form-data")
    assert res.status_code == 400 and res.get_json()["error"]["details"] == {"file": "required"}
    huge = "code,kind,name,floor,room_type,external_id\n" + ("x" * 1024 * 1024) + "\n"
    res = _import(admin, fx, huge)
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"file": "file_too_large"}


def test_units_are_property_scoped(app, fx, login):
    admin_a = login("admin@hvh.test")
    unit = admin_a.post(_base(fx), json={"kind": "guest_room", "code": "204",
                                         "name": "Room 204"}).get_json()
    admin_b = login("admin@lsi.test")
    base_b = f"/api/p/{fx.property_b.id}/maintainable-units"
    assert admin_b.get(base_b).get_json() == []
    assert admin_b.patch(f"{base_b}/{unit['id']}", json={"name": "x"}).status_code == 404
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_units.py -q`
Expected: every test fails with 404 (blueprint not registered).

- [ ] **Step 2: Write the domain module**

Create `server/app/domain/pm_units.py`:

```python
"""Maintainable-unit inventory (spec §3.1, §5.1, §5.4)."""
from __future__ import annotations

import csv
import io
from enum import StrEnum
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import audit
from app.domain._patch import patch_changes
from app.errors import AppError, Conflict, NotFound
from app.models import MaintainableUnit
from app.schemas.enums import LocationType, PmUnitKind, PmUnitSource
from app.schemas.pm import (
    MAX_IMPORT_ROWS,
    UnitImportError,
    UnitImportOut,
    UnitIn,
    UnitListQuery,
    UnitOut,
    UnitPatch,
)


class ImportRejected(AppError):
    """422 whose `details` is the whole UnitImportOut report (spec §5.4). It rides in the
    standard error envelope because the web client's ApiError only reads `body.error` — a
    bare 422 payload would reach the form as "Request failed (422)" with the row list lost.
    Raised before any row is written."""

    status = 422
    code = "IMPORT_REJECTED"


# Where a work order raised from a unit is located (spec §4.1).
LOCATION_FOR_KIND: dict[PmUnitKind, LocationType] = {
    PmUnitKind.guest_room: LocationType.room,
    PmUnitKind.common_area: LocationType.public_area,
    PmUnitKind.equipment: LocationType.equipment,
}

IMPORT_COLUMNS = ("code", "kind", "name", "floor", "room_type", "external_id")
_LIMITS = {"code": 40, "name": 200, "room_type": 20, "external_id": 100}


def natural_key(code: str) -> tuple[int, int, str]:
    """Room numbers sort numerically (99 before 205 before 1001); everything else after them,
    alphabetically."""
    return (0, int(code), "") if code.isdigit() else (1, 0, code.lower())


def get(db: Session, property_id: str, unit_id: str) -> MaintainableUnit:
    unit = db.scalar(select(MaintainableUnit).where(MaintainableUnit.id == unit_id,
                                                    MaintainableUnit.property_id == property_id))
    if unit is None:
        raise NotFound("Unit not found")
    return unit


def to_out(unit: MaintainableUnit) -> UnitOut:
    return UnitOut.model_validate(unit)


def list_units(db: Session, property_id: str, query: UnitListQuery) -> list[UnitOut]:
    stmt = select(MaintainableUnit).where(MaintainableUnit.property_id == property_id)
    if query.kind:
        stmt = stmt.where(MaintainableUnit.kind == query.kind)
    if query.active is not None:
        stmt = stmt.where(MaintainableUnit.active.is_(query.active))
    if query.q and query.q.strip():
        needle = f"%{query.q.strip()}%"
        stmt = stmt.where(or_(MaintainableUnit.code.ilike(needle),
                              MaintainableUnit.name.ilike(needle)))
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda u: (u.kind.value, natural_key(u.code)))
    return [to_out(u) for u in rows]


def _assert_code_free(db: Session, property_id: str, code: str,
                      exclude_id: str | None = None) -> None:
    stmt = select(MaintainableUnit.id).where(MaintainableUnit.property_id == property_id,
                                             MaintainableUnit.code == code)
    if exclude_id:
        stmt = stmt.where(MaintainableUnit.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"A unit with code {code} already exists", details={"code": "duplicate"})


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, StrEnum) else value


def create(db: Session, property_id: str, actor_user_id: str, data: UnitIn) -> MaintainableUnit:
    code = data.code.strip()
    _assert_code_free(db, property_id, code)
    unit = MaintainableUnit(property_id=property_id, kind=data.kind, code=code,
                            name=data.name.strip(), floor=data.floor, room_type=data.room_type,
                            external_id=data.external_id, notes=data.notes,
                            source=PmUnitSource.manual)
    db.add(unit)
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.created",
                 "maintainable_unit", unit.id, after={"code": unit.code, "kind": unit.kind.value})
    return unit


def patch(db: Session, property_id: str, actor_user_id: str, unit_id: str,
          data: UnitPatch) -> MaintainableUnit:
    unit = get(db, property_id, unit_id)
    changes = patch_changes(MaintainableUnit, data)
    if "code" in changes:
        changes["code"] = changes["code"].strip()
        _assert_code_free(db, property_id, changes["code"], exclude_id=unit.id)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    before = {k: _plain(getattr(unit, k)) for k in changes}
    for key, value in changes.items():
        setattr(unit, key, value)
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.updated",
                 "maintainable_unit", unit.id, before=before,
                 after={k: _plain(v) for k, v in changes.items()})
    return unit


def _rejected(errors: list[UnitImportError]) -> ImportRejected:
    report = UnitImportOut(created=0, updated=0, errors=errors)
    return ImportRejected("Import rejected — fix the listed rows and try again",
                          details=report.model_dump(mode="json", by_alias=True))


def import_csv(db: Session, property_id: str, actor_user_id: str, text: str) -> UnitImportOut:
    """Validate every row before writing any (spec §5.4). Rows upsert by (property, code); an
    updated row's `source` becomes `csv`. Any error → nothing written, ImportRejected raised
    with every error listed."""
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip() for h in (reader.fieldnames or [])]
    if header != list(IMPORT_COLUMNS):
        raise _rejected([UnitImportError(
            line=1, field="header",
            message=f"Header must be exactly: {','.join(IMPORT_COLUMNS)}")])

    errors: list[UnitImportError] = []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    def error(line: int, field: str, message: str) -> None:
        errors.append(UnitImportError(line=line, field=field, message=message))

    # Line 1 is the header, so the first data row is line 2.
    for line, raw in enumerate(reader, start=2):
        if line - 1 > MAX_IMPORT_ROWS:
            error(line, "file", f"At most {MAX_IMPORT_ROWS} rows per import")
            break
        row = {k: (v or "").strip() for k, v in raw.items() if k is not None}
        if not row["code"]:
            error(line, "code", "required")
            continue
        if row["code"] in seen:
            error(line, "code", f"duplicate code {row['code']} in this file")
            continue
        seen.add(row["code"])
        try:
            kind = PmUnitKind(row["kind"])
        except ValueError:
            error(line, "kind", "must be one of " + ", ".join(k.value for k in PmUnitKind))
            continue
        if not row["name"]:
            error(line, "name", "required")
            continue
        floor: int | None = None
        if row["floor"]:
            try:
                floor = int(row["floor"])
            except ValueError:
                error(line, "floor", "must be a whole number")
                continue
        too_long = [f for f, limit in _LIMITS.items() if len(row[f]) > limit]
        if too_long:
            error(line, too_long[0], f"longer than {_LIMITS[too_long[0]]} characters")
            continue
        rows.append({"code": row["code"], "kind": kind, "name": row["name"], "floor": floor,
                     "room_type": row["room_type"] or None,
                     "external_id": row["external_id"] or None})

    if errors:
        raise _rejected(errors)

    existing = {u.code: u for u in db.scalars(select(MaintainableUnit).where(
        MaintainableUnit.property_id == property_id)).all()}
    created = updated = 0
    for row in rows:
        unit = existing.get(row["code"])
        if unit is None:
            db.add(MaintainableUnit(property_id=property_id, source=PmUnitSource.csv, **row))
            created += 1
        else:
            unit.kind, unit.name, unit.floor = row["kind"], row["name"], row["floor"]
            unit.room_type = row["room_type"]
            unit.external_id = row["external_id"] or unit.external_id
            unit.source = PmUnitSource.csv
            updated += 1
    db.flush()
    audit.record(db, property_id, actor_user_id, "maintainable_unit.imported",
                 "maintainable_unit", None, after={"created": created, "updated": updated})
    return UnitImportOut(created=created, updated=updated, errors=[])
```

- [ ] **Step 3: Write the blueprint**

Create `server/app/api/maintainable_units.py`:

```python
from flask import Blueprint, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_units
from app.errors import ValidationFailed
from app.schemas.pm import MAX_IMPORT_BYTES, UnitIn, UnitListQuery, UnitPatch

bp = Blueprint("maintainable_units", __name__,
               url_prefix="/api/p/<property_id>/maintainable-units")

MULTIPART_OVERHEAD_BYTES = 4096


@bp.get("")
@require_auth
@require_property
@require_capability("view_pm")
def list_units(property_id: str):
    query = parse_query(UnitListQuery)
    with db_session() as db:
        return ok(pm_units.list_units(db, g.property_id, query))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_unit(property_id: str):
    data = parse_body(UnitIn)
    with db_session() as db:
        unit = pm_units.create(db, g.property_id, g.user.id, data)
        return ok(pm_units.to_out(unit), 201)


@bp.patch("/<unit_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_unit(property_id: str, unit_id: str):
    data = parse_body(UnitPatch)
    with db_session() as db:
        unit = pm_units.patch(db, g.property_id, g.user.id, unit_id, data)
        return ok(pm_units.to_out(unit))


@bp.post("/import")
@require_auth
@require_property
@require_capability("manage_admin")
def import_units(property_id: str):
    """multipart/form-data with a `file` part. 200 with counts on success; the domain raises
    ImportRejected (422, report in `error.details`) with nothing written otherwise (spec §5.4)."""
    # Before request.files: reading it is what makes Werkzeug buffer the whole body.
    if (request.content_length or 0) > MAX_IMPORT_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed("The file must be 1 MB or smaller",
                               details={"file": "file_too_large"})
    upload = request.files.get("file")
    if upload is None:
        raise ValidationFailed("A CSV file is required", details={"file": "required"})
    raw = upload.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValidationFailed("The file must be 1 MB or smaller",
                               details={"file": "file_too_large"})
    try:
        text = raw.decode("utf-8-sig")  # Excel writes a BOM; tolerate it
    except UnicodeDecodeError as e:
        raise ValidationFailed("The file must be UTF-8 text",
                               details={"file": "not_utf8"}) from e
    with db_session() as db:
        return ok(pm_units.import_csv(db, g.property_id, g.user.id, text))
```

Register it in `server/app/__init__.py`: add `maintainable_units` to the `from app.api import (...)` list and, after `app.register_blueprint(log.bp)`:

```python
    app.register_blueprint(maintainable_units.bp)
```

- [ ] **Step 4: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_units.py tests/test_isolation.py -q`
Expected: all pass (the isolation suite now covers the four new routes automatically).

- [ ] **Step 5: Lint and commit**

Run: `cd server && ../.venv/Scripts/python.exe -m ruff check .`

```bash
git add server/app/domain/pm_units.py server/app/api/maintainable_units.py server/app/__init__.py server/tests/test_pm_units.py
git commit -m "feat(server): maintainable-unit inventory with CSV import

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 5: Cycle windows — open, close, freeze missed

**Files:**
- Create: `server/app/domain/pm_cycles.py`
- Create: `server/tests/test_pm_cycles.py`

**Interfaces:**
- Produces: `window_for(cadence, today) -> (starts_on, ends_on, ordinal)`, `local_today(prop, at=None) -> date`, `local_day_start_utc(prop, day) -> datetime`, `scope_unit_ids(db, template) -> list[str]`, `open_cycle(db, template) -> PmCycle | None`, `ensure_open_cycle(db, template, today) -> PmCycle | None`, `close_expired(db, template, today) -> int`.
- Consumes: models from Task 1.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_cycles.py`:

```python
"""Cycle windows (spec §3.5, §4.1 phase A)."""
from datetime import UTC, date, datetime

from sqlalchemy import func, select

from app import clock
from app.domain import pm_cycles
from app.models import MaintainableUnit, PmCycle, PmRun, PmTemplate, Property
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
)


def test_window_for_aligns_to_the_calendar_year():
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 9, 10)) == (
        date(2026, 7, 1), date(2026, 9, 30), 3)
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 12, 31)) == (
        date(2026, 10, 1), date(2026, 12, 31), 4)
    assert pm_cycles.window_for(PmCadence.quarterly, date(2026, 1, 1)) == (
        date(2026, 1, 1), date(2026, 3, 31), 1)
    assert pm_cycles.window_for(PmCadence.monthly, date(2028, 2, 15)) == (
        date(2028, 2, 1), date(2028, 2, 29), 2)  # leap year
    assert pm_cycles.window_for(PmCadence.semiannual, date(2026, 7, 1)) == (
        date(2026, 7, 1), date(2026, 12, 31), 2)
    assert pm_cycles.window_for(PmCadence.annual, date(2026, 6, 6)) == (
        date(2026, 1, 1), date(2026, 12, 31), 1)


def test_local_today_uses_the_property_timezone(database, fx):
    with database.session() as db:
        prop = db.get(Property, fx.property_a.id)  # America/New_York
        # 02:00 UTC on the 11th is still the 10th in New York.
        assert pm_cycles.local_today(prop, datetime(2026, 9, 11, 2, 0, tzinfo=UTC)) == \
            date(2026, 9, 10)
        assert pm_cycles.local_day_start_utc(prop, date(2026, 9, 10)) == \
            datetime(2026, 9, 10, 4, 0, tzinfo=UTC)  # EDT is UTC-4


def _sweep(db, fx, active=True):
    t = PmTemplate(property_id=fx.property_a.id, name="Rooms", mode=PmTemplateMode.sweep,
                   unit_kind=PmUnitKind.guest_room, cadence=PmCadence.quarterly, active=active)
    db.add(t)
    db.flush()
    return t


def _unit(db, fx, code, kind=PmUnitKind.guest_room, active=True):
    u = MaintainableUnit(property_id=fx.property_a.id, kind=kind, code=code, name=code,
                         active=active)
    db.add(u)
    db.flush()
    return u


def test_ensure_open_cycle_opens_once_for_today_and_only_for_active_sweeps(database, fx, events):
    with database.session() as db:
        t = _sweep(db, fx)
        cycle = pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        assert (cycle.ordinal, cycle.starts_on, cycle.ends_on) == (
            3, date(2026, 7, 1), date(2026, 9, 30))
        assert cycle.status == PmCycleStatus.open
        assert pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10)) is None
        assert pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1)) is None, \
            "an open cycle blocks a second, even an expired one — close_expired goes first"
        inactive = _sweep(db, fx, active=False)
        assert pm_cycles.ensure_open_cycle(db, inactive, date(2026, 9, 10)) is None
    assert any(e.type == "pm.cycle.rolled" for e in events)


def test_scope_is_every_active_unit_of_the_kind(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        a = _unit(db, fx, "201")
        _unit(db, fx, "202", active=False)
        _unit(db, fx, "LOBBY", kind=PmUnitKind.common_area)
        assert pm_cycles.scope_unit_ids(db, t) == [a.id]


def test_close_expired_freezes_a_missed_run_per_unswept_active_unit_once(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        cycle = pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        swept = _unit(db, fx, "201")
        _unit(db, fx, "202")
        _unit(db, fx, "203")
        _unit(db, fx, "204", active=False)
        db.add(PmRun(property_id=fx.property_a.id, template_id=t.id, unit_id=swept.id,
                     cycle_id=cycle.id, status=PmRunStatus.passed,
                     started_by_user_id=fx.engineer_a.id, started_at=clock.now(),
                     completed_at=clock.now(), inspected_at=clock.now()))
        db.flush()
        assert pm_cycles.close_expired(db, t, date(2026, 9, 30)) == 0, "still inside the window"
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 2
        assert db.get(PmCycle, cycle.id).status == PmCycleStatus.closed
        missed = db.scalars(select(PmRun.unit_id).where(
            PmRun.cycle_id == cycle.id, PmRun.status == PmRunStatus.missed)).all()
        assert swept.id not in missed and len(missed) == 2
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 0, "idempotent"
        assert db.scalar(select(func.count()).select_from(PmRun)) == 3
        # And the next window opens cleanly afterwards.
        nxt = pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1))
        assert (nxt.ordinal, nxt.starts_on) == (4, date(2026, 10, 1))


def test_inactive_template_neither_closes_nor_opens(database, fx):
    with database.session() as db:
        t = _sweep(db, fx)
        pm_cycles.ensure_open_cycle(db, t, date(2026, 9, 10))
        t.active = False
        db.flush()
        assert pm_cycles.close_expired(db, t, date(2027, 1, 1)) == 0
        assert pm_cycles.open_cycle(db, t).status == PmCycleStatus.open
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_cycles.py -q`
Expected: `ImportError` on `pm_cycles`.

- [ ] **Step 2: Write the module**

Create `server/app/domain/pm_cycles.py`:

```python
"""Sweep cycles (spec §3.5, §4.1 phase A).

Windows align to the calendar year for the template's cadence, so every property on quarterly
gets the same Jan–Mar / Apr–Jun / Jul–Sep / Oct–Dec that a brand audit expects. Dates are
property-local: `today` is always computed with `local_today`, never taken from a UTC column.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import MaintainableUnit, PmCycle, PmRun, PmTemplate, PmTemplateUnit, Property
from app.realtime.broadcast import queue_event
from app.schemas.enums import PmCadence, PmCycleStatus, PmRunStatus, PmTemplateMode

MONTHS: dict[PmCadence, int] = {
    PmCadence.monthly: 1,
    PmCadence.quarterly: 3,
    PmCadence.semiannual: 6,
    PmCadence.annual: 12,
}


def window_for(cadence: PmCadence, today: date) -> tuple[date, date, int]:
    """The calendar-aligned window containing `today`: (starts_on, ends_on inclusive, ordinal)."""
    span = MONTHS[cadence]
    ordinal = (today.month - 1) // span + 1
    start_month = (ordinal - 1) * span + 1
    starts_on = date(today.year, start_month, 1)
    next_month = start_month + span
    first_after = (date(today.year + 1, 1, 1) if next_month > 12
                   else date(today.year, next_month, 1))
    return starts_on, first_after - timedelta(days=1), ordinal


def local_today(prop: Property, at: datetime | None = None) -> date:
    return (at or clock.now()).astimezone(ZoneInfo(prop.timezone)).date()


def local_day_start_utc(prop: Property, day: date) -> datetime:
    """Midnight on `day` in the property's zone, as an aware UTC instant."""
    return datetime.combine(day, time(0, 0), tzinfo=ZoneInfo(prop.timezone)).astimezone(UTC)


def scope_unit_ids(db: Session, template: PmTemplate) -> list[str]:
    """Sweep: every active unit of the template's kind. Scheduled: its explicit targets."""
    if template.mode == PmTemplateMode.sweep:
        return list(db.scalars(select(MaintainableUnit.id).where(
            MaintainableUnit.property_id == template.property_id,
            MaintainableUnit.kind == template.unit_kind,
            MaintainableUnit.active.is_(True))).all())
    return list(db.scalars(select(PmTemplateUnit.unit_id).where(
        PmTemplateUnit.template_id == template.id)).all())


def open_cycle(db: Session, template: PmTemplate) -> PmCycle | None:
    return db.scalar(select(PmCycle).where(PmCycle.template_id == template.id,
                                           PmCycle.status == PmCycleStatus.open))


def ensure_open_cycle(db: Session, template: PmTemplate, today: date) -> PmCycle | None:
    """Open the window containing `today` when the template has no open cycle at all.

    An open-but-expired cycle is *not* replaced here — `close_expired` must run first, so a
    template never carries two open cycles. Returns the new cycle, or None if nothing opened.
    """
    if template.mode != PmTemplateMode.sweep or not template.active:
        return None
    if open_cycle(db, template) is not None:
        return None
    starts_on, ends_on, ordinal = window_for(template.cadence, today)
    if db.scalar(select(PmCycle.id).where(PmCycle.template_id == template.id,
                                          PmCycle.starts_on == starts_on)):
        # This window already ran and closed (a template reactivated late in its window).
        # Re-opening it would double-count; it simply waits for the next window.
        return None
    cycle = PmCycle(property_id=template.property_id, template_id=template.id,
                    ordinal=ordinal, starts_on=starts_on, ends_on=ends_on,
                    status=PmCycleStatus.open)
    db.add(cycle)
    db.flush()
    queue_event(db, template.property_id, "pm.cycle.rolled", {"templateId": template.id})
    return cycle


def close_expired(db: Session, template: PmTemplate, today: date) -> int:
    """Close the open cycle once its window has passed, writing a `missed` run for every
    in-scope unit without a `passed` run. That row is the frozen evidence (spec §4.1).
    Returns the number of missed runs written; 0 when there was nothing to close."""
    if not template.active:
        return 0
    cycle = open_cycle(db, template)
    if cycle is None or cycle.ends_on >= today:
        return 0
    passed = set(db.scalars(select(PmRun.unit_id).where(
        PmRun.cycle_id == cycle.id, PmRun.status == PmRunStatus.passed)).all())
    missed = 0
    for unit_id in scope_unit_ids(db, template):
        if unit_id in passed:
            continue
        db.add(PmRun(property_id=template.property_id, template_id=template.id,
                     unit_id=unit_id, cycle_id=cycle.id, status=PmRunStatus.missed))
        missed += 1
    cycle.status = PmCycleStatus.closed
    db.flush()
    queue_event(db, template.property_id, "pm.cycle.rolled", {"templateId": template.id})
    return missed
```

- [ ] **Step 3: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_cycles.py -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: pass, clean.

```bash
git add server/app/domain/pm_cycles.py server/tests/test_pm_cycles.py
git commit -m "feat(server): PM cycle windows — open, close, freeze missed units

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 6: Templates — domain, mode rules, item sync, blueprint

**Files:**
- Create: `server/app/domain/pm_templates.py`
- Create: `server/app/api/pm.py` (templates routes only; later tasks append)
- Modify: `server/app/__init__.py` (register `pm.bp`)
- Create: `server/tests/test_pm_templates.py`

**Interfaces:**
- Produces: `pm_templates.get(db, property_id, template_id) -> PmTemplate`, `pm_templates.to_out(db, template) -> TemplateOut`, `pm_templates.active_items(db, template_id) -> list[PmTemplateItem]`, `pm_templates.item_out(item) -> TemplateItemOut`, `pm_templates.create(...)`, `pm_templates.patch(...)`, `pm_templates.list_templates(db, property_id) -> list[TemplateOut]`.
- Routes: `GET/POST /api/p/<pid>/pm/templates`, `PATCH …/templates/<id>`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_templates.py`:

```python
"""PM templates (spec §3.2–3.4, §4.5, §5.2, §7.1)."""
from sqlalchemy import select

from app import clock
from app.models import PmCycle, PmRun, PmTemplateItem
from app.schemas.enums import PmRunStatus

ITEMS = [
    {"label": "HVAC filter replaced", "itemType": "checkbox"},
    {"label": "Tap hot-water temperature", "itemType": "number", "unit": "°F",
     "minValue": 100, "maxValue": 120},
    {"label": "Caulk condition", "itemType": "text", "required": False},
    {"label": "Bathroom fan photo", "itemType": "photo"},
]


def _base(fx):
    return f"/api/p/{fx.property_a.id}/pm/templates"


def _sweep_body(**over):
    return {"name": "Guest Room Quarterly", "mode": "sweep", "unitKind": "guest_room",
            "cadence": "quarterly", "items": ITEMS} | over


def _unit(client, fx, code, kind="equipment"):
    return client.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                       json={"kind": kind, "code": code, "name": code}).get_json()["id"]


def test_create_sweep_opens_todays_cycle_and_orders_items(app, fx, login, database):
    admin = login("admin@hvh.test")
    res = admin.post(_base(fx), json=_sweep_body(departmentId=fx.dept_engineering.id))
    assert res.status_code == 201, res.get_json()
    t = res.get_json()
    assert [i["position"] for i in t["items"]] == [0, 1, 2, 3]
    assert t["items"][1]["minValue"] == 100.0 and t["items"][2]["required"] is False
    assert t["hasRuns"] is False
    with database.session() as db:
        cycle = db.scalar(select(PmCycle).where(PmCycle.template_id == t["id"]))
        assert cycle is not None and cycle.ordinal == 3  # frozen clock: 2026-09-10, Q3
    assert login("agent@hvh.test").get(_base(fx)).get_json()[0]["id"] == t["id"]


def test_one_active_sweep_per_kind(app, fx, login):
    admin = login("admin@hvh.test")
    assert admin.post(_base(fx), json=_sweep_body()).status_code == 201
    assert admin.post(_base(fx), json=_sweep_body(name="Another")).status_code == 409
    # A different kind is fine, and so is an inactive duplicate.
    assert admin.post(_base(fx), json=_sweep_body(unitKind="equipment")).status_code == 201
    assert admin.post(_base(fx), json=_sweep_body(active=False)).status_code == 201


def test_mode_fields_are_validated(app, fx, login):
    admin = login("admin@hvh.test")
    bad = [
        _sweep_body(rrule="FREQ=DAILY"),
        _sweep_body(cadence=None),
        {"name": "B", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3"},  # no dtstart
        {"name": "B", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
         "rruleDtstart": "2026-07-01", "cadence": "monthly"},
        {"name": "B", "mode": "scheduled", "rrule": "EVERY=THIRD;MOON",
         "rruleDtstart": "2026-07-01"},
    ]
    for body in bad:
        res = admin.post(_base(fx), json=body)
        assert res.status_code == 400, body


def test_scheduled_template_targets_units_of_this_property_only(app, fx, login):
    admin = login("admin@hvh.test")
    boiler = _unit(admin, fx, "BOILER-1")
    other = login("admin@lsi.test").post(
        f"/api/p/{fx.property_b.id}/maintainable-units",
        json={"kind": "equipment", "code": "X", "name": "X"}).get_json()["id"]
    body = {"name": "Boiler inspection", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
            "rruleDtstart": "2026-07-01", "unitIds": [boiler], "items": ITEMS[:1]}
    res = admin.post(_base(fx), json=body)
    assert res.status_code == 201 and res.get_json()["unitIds"] == [boiler]
    assert admin.post(_base(fx), json=body | {"unitIds": [boiler, other]}).status_code == 400


def test_patch_soft_deletes_removed_items_and_keeps_answers_valid(app, fx, login, database):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    keep = t["items"][1]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": keep["id"], "label": "Tap temperature", "itemType": "number", "unit": "°F",
         "minValue": 95, "maxValue": 125},
        {"label": "Smoke detector tested", "itemType": "checkbox"},
    ]})
    assert res.status_code == 200, res.get_json()
    out = res.get_json()
    assert [i["label"] for i in out["items"]] == ["Tap temperature", "Smoke detector tested"]
    assert out["items"][0]["id"] == keep["id"] and out["items"][0]["minValue"] == 95.0
    with database.session() as db:
        rows = db.scalars(select(PmTemplateItem).where(
            PmTemplateItem.template_id == t["id"])).all()
        assert len(rows) == 5, "nothing is hard-deleted"
        assert sorted(r.active for r in rows) == [False, False, False, True, True]


def test_item_type_is_immutable_and_bounds_only_on_numbers(app, fx, login):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    checkbox = t["items"][0]
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={"items": [
        {"id": checkbox["id"], "label": checkbox["label"], "itemType": "text"}]})
    assert res.status_code == 400
    res = admin.post(_base(fx), json=_sweep_body(
        unitKind="equipment", items=[{"label": "x", "itemType": "checkbox", "minValue": 1}]))
    assert res.status_code == 400
    res = admin.post(_base(fx), json=_sweep_body(
        unitKind="equipment", items=[{"label": "x", "itemType": "number", "minValue": 5,
                                     "maxValue": 1}]))
    assert res.status_code == 400


def test_mode_cannot_change_once_the_template_has_runs(app, fx, login, database):
    admin = login("admin@hvh.test")
    t = admin.post(_base(fx), json=_sweep_body()).get_json()
    unit = _unit(admin, fx, "204", kind="guest_room")
    with database.session() as db:
        db.add(PmRun(property_id=fx.property_a.id, template_id=t["id"], unit_id=unit,
                     status=PmRunStatus.in_progress, started_at=clock.now()))
    res = admin.patch(f"{_base(fx)}/{t['id']}", json={
        "mode": "scheduled", "unitKind": None, "cadence": None,
        "rrule": "FREQ=MONTHLY", "rruleDtstart": "2026-07-01"})
    assert res.status_code == 409
    assert admin.get(_base(fx)).get_json()[0]["hasRuns"] is True


def test_writes_require_manage_admin(app, fx, login):
    for c in (login("supervisor@hvh.test"), login("manager@hvh.test")):
        assert c.get(_base(fx)).status_code == 200
        assert c.post(_base(fx), json=_sweep_body()).status_code == 403
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_templates.py -q`
Expected: 404s.

- [ ] **Step 2: Write the domain module**

Create `server/app/domain/pm_templates.py`:

```python
"""PM templates (spec §3.2–3.4, §4.5, §7.1)."""
from __future__ import annotations

from datetime import UTC, date, datetime

from dateutil.rrule import rrulestr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, pm_cycles
from app.domain._patch import patch_changes
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import (
    Department,
    MaintainableUnit,
    PmRun,
    PmTemplate,
    PmTemplateItem,
    PmTemplateUnit,
    Property,
)
from app.schemas.enums import PmCadence, PmItemType, PmTemplateMode, PmUnitKind
from app.schemas.pm import TemplateIn, TemplateItemIn, TemplateItemOut, TemplateOut, TemplatePatch


def get(db: Session, property_id: str, template_id: str) -> PmTemplate:
    t = db.scalar(select(PmTemplate).where(PmTemplate.id == template_id,
                                           PmTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Template not found")
    return t


def active_items(db: Session, template_id: str) -> list[PmTemplateItem]:
    return list(db.scalars(select(PmTemplateItem)
                           .where(PmTemplateItem.template_id == template_id,
                                  PmTemplateItem.active.is_(True))
                           .order_by(PmTemplateItem.position)).all())


def item_out(item: PmTemplateItem) -> TemplateItemOut:
    return TemplateItemOut.model_validate(item)


def has_runs(db: Session, template: PmTemplate) -> bool:
    return db.scalar(select(PmRun.id).where(PmRun.template_id == template.id).limit(1)) is not None


def to_out(db: Session, t: PmTemplate) -> TemplateOut:
    unit_ids = list(db.scalars(select(PmTemplateUnit.unit_id)
                               .where(PmTemplateUnit.template_id == t.id)).all())
    return TemplateOut(
        id=t.id, name=t.name, mode=t.mode, department_id=t.department_id, active=t.active,
        unit_kind=t.unit_kind, cadence=t.cadence, rrule=t.rrule, rrule_dtstart=t.rrule_dtstart,
        last_fired_at=t.last_fired_at, unit_ids=unit_ids,
        items=[item_out(i) for i in active_items(db, t.id)], has_runs=has_runs(db, t),
        created_at=t.created_at)


def list_templates(db: Session, property_id: str) -> list[TemplateOut]:
    rows = db.scalars(select(PmTemplate).where(PmTemplate.property_id == property_id)
                      .order_by(PmTemplate.name, PmTemplate.id)).all()
    return [to_out(db, t) for t in rows]


def validate_rrule(rrule: str) -> None:
    try:
        rrulestr(rrule, dtstart=datetime(2026, 1, 1, tzinfo=UTC))
    except (ValueError, TypeError, KeyError) as e:
        raise ValidationFailed("Invalid recurrence rule",
                               details={"rrule": "invalid_rrule"}) from e


def _validate_mode_fields(mode: PmTemplateMode, unit_kind: PmUnitKind | None,
                          cadence: PmCadence | None, rrule: str | None,
                          rrule_dtstart: date | None) -> None:
    """The model's CHECK constraint, raised as a 400 the form can read instead of a 500."""
    if mode == PmTemplateMode.sweep:
        if unit_kind is None or cadence is None:
            raise ValidationFailed("A sweep template needs a unit kind and a cadence",
                                   details={"unitKind": "required", "cadence": "required"})
        if rrule:
            raise ValidationFailed("A sweep template cannot carry a recurrence rule",
                                   details={"rrule": "not_allowed"})
    else:
        if not rrule or rrule_dtstart is None:
            raise ValidationFailed("A scheduled template needs a recurrence rule and a start",
                                   details={"rrule": "required", "rruleDtstart": "required"})
        if cadence is not None:
            raise ValidationFailed("A scheduled template cannot carry a cadence",
                                   details={"cadence": "not_allowed"})
        validate_rrule(rrule)


def _assert_single_active_sweep(db: Session, property_id: str, unit_kind: PmUnitKind,
                                exclude_id: str | None = None) -> None:
    """Spec §7.1: one active sweep template per unit kind, enforced here rather than by a
    partial unique index, which is not portable."""
    stmt = select(PmTemplate.id).where(PmTemplate.property_id == property_id,
                                       PmTemplate.mode == PmTemplateMode.sweep,
                                       PmTemplate.unit_kind == unit_kind,
                                       PmTemplate.active.is_(True))
    if exclude_id:
        stmt = stmt.where(PmTemplate.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"There is already an active sweep template for {unit_kind.value}",
                       details={"unitKind": "duplicate_sweep"})


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if not db.scalar(select(Department.id).where(Department.id == department_id,
                                                 Department.property_id == property_id)):
        raise ValidationFailed("That department is not part of this property",
                               details={"departmentId": "unknown_department"})


def _assert_units(db: Session, property_id: str, unit_ids: list[str]) -> None:
    if not unit_ids:
        return
    found = set(db.scalars(select(MaintainableUnit.id).where(
        MaintainableUnit.property_id == property_id,
        MaintainableUnit.id.in_(unit_ids))).all())
    if any(u not in found for u in unit_ids):
        raise ValidationFailed("Some units are not part of this property",
                               details={"unitIds": "unknown_unit"})


def _sync_items(db: Session, template: PmTemplate, items: list[TemplateItemIn]) -> None:
    """Replace-by-list with soft deletes: an item in the list is updated or created in its
    position; one missing from it is deactivated. Type never changes on an existing item —
    answers already recorded against it would mean something else."""
    existing = {i.id: i for i in db.scalars(select(PmTemplateItem).where(
        PmTemplateItem.template_id == template.id)).all()}
    keep: set[str] = set()
    for position, data in enumerate(items):
        if data.item_type != PmItemType.number and (
                data.min_value is not None or data.max_value is not None or data.unit):
            raise ValidationFailed("Bounds and units apply to number items only",
                                   details={"items": "bounds_on_non_number"})
        if (data.min_value is not None and data.max_value is not None
                and data.min_value > data.max_value):
            raise ValidationFailed("Minimum must not exceed maximum",
                                   details={"items": "min_over_max"})
        if data.id:
            row = existing.get(data.id)
            if row is None:
                raise ValidationFailed("Unknown item", details={"items": "unknown_item"})
            if row.item_type != data.item_type:
                raise ValidationFailed("An item's type cannot change; remove it and add a new one",
                                       details={"items": "type_change"})
            row.position, row.label, row.unit = position, data.label.strip(), data.unit
            row.min_value, row.max_value = data.min_value, data.max_value
            row.required, row.active = data.required, True
        else:
            row = PmTemplateItem(template_id=template.id, property_id=template.property_id,
                                 position=position, label=data.label.strip(),
                                 item_type=data.item_type, unit=data.unit,
                                 min_value=data.min_value, max_value=data.max_value,
                                 required=data.required)
            db.add(row)
            db.flush()
        keep.add(row.id)
    for row in existing.values():
        if row.id not in keep:
            row.active = False
    db.flush()


def _set_units(db: Session, template: PmTemplate, unit_ids: list[str]) -> None:
    _assert_units(db, template.property_id, unit_ids)
    db.execute(delete(PmTemplateUnit).where(PmTemplateUnit.template_id == template.id))
    for unit_id in dict.fromkeys(unit_ids):
        db.add(PmTemplateUnit(template_id=template.id, unit_id=unit_id,
                              property_id=template.property_id))
    db.flush()


def create(db: Session, property_id: str, actor_user_id: str, data: TemplateIn) -> PmTemplate:
    _validate_mode_fields(data.mode, data.unit_kind, data.cadence, data.rrule, data.rrule_dtstart)
    if data.department_id:
        _assert_department(db, property_id, data.department_id)
    if data.mode == PmTemplateMode.sweep and data.active:
        _assert_single_active_sweep(db, property_id, data.unit_kind)
    t = PmTemplate(property_id=property_id, name=data.name.strip(), mode=data.mode,
                   department_id=data.department_id, active=data.active,
                   unit_kind=data.unit_kind, cadence=data.cadence, rrule=data.rrule,
                   rrule_dtstart=data.rrule_dtstart,
                   # The schedule starts now: past occurrences are never backfilled, which is
                   # what stops a 2020 dtstart from emitting five years of work orders (§4.1).
                   last_fired_at=clock.now() if data.mode == PmTemplateMode.scheduled else None)
    db.add(t)
    db.flush()
    _set_units(db, t, data.unit_ids)
    _sync_items(db, t, data.items)
    # A sweep template gets its first cycle now, not on the next tick (spec §4.1).
    pm_cycles.ensure_open_cycle(db, t, pm_cycles.local_today(db.get(Property, property_id)))
    audit.record(db, property_id, actor_user_id, "pm_template.created", "pm_template", t.id,
                 after={"name": t.name, "mode": t.mode.value})
    return t


def patch(db: Session, property_id: str, actor_user_id: str, template_id: str,
          data: TemplatePatch) -> PmTemplate:
    t = get(db, property_id, template_id)
    changes = patch_changes(PmTemplate, data)
    unit_ids = changes.pop("unit_ids", None)
    changes.pop("items", None)  # handled from `data.items` below: it needs the models
    if "mode" in changes and changes["mode"] != t.mode and has_runs(db, t):
        raise Conflict("Cannot change the mode of a template that has runs",
                       details={"mode": "has_runs"})
    merged = {k: changes.get(k, getattr(t, k))
              for k in ("mode", "unit_kind", "cadence", "rrule", "rrule_dtstart")}
    _validate_mode_fields(**merged)
    if changes.get("department_id"):
        _assert_department(db, property_id, changes["department_id"])
    if merged["mode"] == PmTemplateMode.sweep and changes.get("active", t.active):
        _assert_single_active_sweep(db, property_id, merged["unit_kind"], exclude_id=t.id)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    before = {k: getattr(t, k) for k in changes}
    for key, value in changes.items():
        setattr(t, key, value)
    if (merged["mode"] == PmTemplateMode.scheduled
            and any(k in changes for k in ("mode", "rrule", "rrule_dtstart"))):
        t.last_fired_at = clock.now()  # a changed schedule restarts from now, never backfills
    db.flush()
    if unit_ids is not None:
        _set_units(db, t, unit_ids)
    if "items" in data.model_fields_set and data.items is not None:
        _sync_items(db, t, data.items)
    pm_cycles.ensure_open_cycle(db, t, pm_cycles.local_today(db.get(Property, property_id)))
    audit.record(db, property_id, actor_user_id, "pm_template.updated", "pm_template", t.id,
                 before={k: str(v) for k, v in before.items()},
                 after={k: str(v) for k, v in changes.items()})
    return t
```

- [ ] **Step 3: Write the blueprint (first three routes)**

Create `server/app/api/pm.py`:

```python
"""Preventative maintenance routes (spec §5.2). Templates here; runs, inspection and reports
are appended by later tasks."""
from flask import Blueprint, g

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_templates
from app.schemas.pm import TemplateIn, TemplatePatch

bp = Blueprint("pm", __name__, url_prefix="/api/p/<property_id>/pm")


@bp.get("/templates")
@require_auth
@require_property
@require_capability("view_pm")
def list_templates(property_id: str):
    with db_session() as db:
        return ok(pm_templates.list_templates(db, g.property_id))


@bp.post("/templates")
@require_auth
@require_property
@require_capability("manage_admin")
def create_template(property_id: str):
    data = parse_body(TemplateIn)
    with db_session() as db:
        t = pm_templates.create(db, g.property_id, g.user.id, data)
        return ok(pm_templates.to_out(db, t), 201)


@bp.patch("/templates/<template_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_template(property_id: str, template_id: str):
    data = parse_body(TemplatePatch)
    with db_session() as db:
        t = pm_templates.patch(db, g.property_id, g.user.id, template_id, data)
        return ok(pm_templates.to_out(db, t))
```

Register in `server/app/__init__.py`: add `pm` to the import list and `app.register_blueprint(pm.bp)` after `maintainable_units.bp`.

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_templates.py tests/test_isolation.py -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: pass, clean.

```bash
git add server/app/domain/pm_templates.py server/app/api/pm.py server/app/__init__.py server/tests/test_pm_templates.py
git commit -m "feat(server): PM templates with mode rules and soft-deleted items

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 7: Runs — start, answer, photos, complete, out-of-range work orders

**Files:**
- Create: `server/app/domain/pm_runs.py`
- Modify: `server/app/api/pm.py` (append run routes)
- Create: `server/tests/test_pm_runs.py`

**Interfaces:**
- Produces: `pm_runs.get(db, property_id, run_id) -> PmRun`, `pm_runs.to_out(db, run) -> RunOut`, `pm_runs.emit(db, run)`, `pm_runs.start(db, property_id, actor, StartRunRequest) -> PmRun`, `pm_runs.begin_pending(db, property_id, actor, run_id) -> PmRun`, `pm_runs.save_answer(...) -> PmRunAnswer`, `pm_runs.attach_photo(db, property_id, actor, run_id, *, data, item_id) -> PmRunPhoto`, `pm_runs.get_photo(db, property_id, run_id, photo_id) -> PmRunPhoto`, `pm_runs.complete(db, property_id, actor, run_id) -> PmRun`, `pm_runs.create_answers(db, run)`.
- Consumes: Tasks 4–6.
- Routes: `POST /pm/runs`, `GET /pm/runs/<id>`, `POST /pm/runs/<id>/start`, `PATCH /pm/runs/<id>/answers/<answer_id>`, `POST /pm/runs/<id>/photos`, `GET /pm/runs/<id>/photos/<photo_id>`, `POST /pm/runs/<id>/complete`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_runs.py`:

```python
"""PM runs (spec §3.6–3.8, §4.2, §4.3)."""
import io

from sqlalchemy import select

from app.models import Notification, WorkOrder

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"
GIF = b"GIF89a" + b"\x00" * 40

ITEMS = [
    {"label": "HVAC filter replaced", "itemType": "checkbox"},
    {"label": "Tap hot-water temperature", "itemType": "number", "unit": "°F",
     "minValue": 100, "maxValue": 120},
    {"label": "Caulk condition", "itemType": "text", "required": False},
    {"label": "Bathroom fan photo", "itemType": "photo"},
]


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def setup_sweep(admin, fx, codes=("204", "205")):
    """A guest-room quarterly template (Engineering) and the given rooms. Returns
    (template_id, {code: unit_id})."""
    units = {}
    for code in codes:
        units[code] = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                                 json={"kind": "guest_room", "code": code, "name": f"Room {code}",
                                       "floor": int(code[0])}).get_json()["id"]
    t = admin.post(_pm(fx, "/templates"), json={
        "name": "Guest Room Quarterly", "mode": "sweep", "unitKind": "guest_room",
        "cadence": "quarterly", "departmentId": fx.dept_engineering.id, "items": ITEMS})
    assert t.status_code == 201, t.get_json()
    return t.get_json()["id"], units


def start(client, fx, template_id, unit_id):
    res = client.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": unit_id})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def answer_by_label(run, label):
    item = next(i for i in run["items"] if i["label"] == label)
    return next(a for a in run["answers"] if a["itemId"] == item["id"]), item


def upload(client, fx, run_id, data, item_id=None, filename="p.png", content_type="image/png"):
    form = {"photo": (io.BytesIO(data), filename, content_type)}
    if item_id:
        form["itemId"] = item_id
    return client.post(_pm(fx, f"/runs/{run_id}/photos"), data=form,
                       content_type="multipart/form-data")


def test_start_pre_creates_answers_and_refuses_a_second_run_in_the_cycle(app, fx, login, events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    assert run["status"] == "in_progress" and run["startedByName"] == "Eli Engineer"
    assert run["unitCode"] == "204" and run["cycleId"]
    assert len(run["answers"]) == 4 and all(a["answeredAt"] is None for a in run["answers"])
    required = [i["id"] for i in run["items"] if i["required"]]
    assert run["missingRequired"] == required and len(required) == 3

    res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 409 and res.get_json()["error"]["details"] == {"runId": run["id"]}
    res = login("supervisor@hvh.test").post(_pm(fx, "/runs"),
                                            json={"templateId": template_id,
                                                  "unitId": units["204"]})
    assert res.status_code == 409
    assert any(e.type == "pm.run.changed" and e.payload["id"] == run["id"] for e in events)


def test_start_refuses_a_unit_outside_the_templates_scope(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    pump = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                      json={"kind": "equipment", "code": "PUMP", "name": "Pump"}).get_json()["id"]
    admin.patch(f"/api/p/{fx.property_a.id}/maintainable-units/{units['205']}",
                json={"active": False})
    eng = login("engineer@hvh.test")
    for unit_id in (pump, units["205"]):
        res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": unit_id})
        assert res.status_code == 400, unit_id


def test_answers_save_by_type_and_flag_out_of_range(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    path = _pm(fx, f"/runs/{run['id']}/answers/{temp['id']}")

    res = eng.patch(path, json={"numberValue": 122})
    assert res.status_code == 200, res.get_json()
    saved, _ = answer_by_label(res.get_json(), "Tap hot-water temperature")
    assert saved["numberValue"] == 122.0 and saved["outOfRange"] is True
    assert saved["answeredAt"] is not None

    saved, _ = answer_by_label(eng.patch(path, json={"numberValue": 110}).get_json(),
                               "Tap hot-water temperature")
    assert saved["outOfRange"] is False

    # Wrong value column for the type, and a photo item cannot be PATCHed at all.
    assert eng.patch(path, json={"boolValue": True}).status_code == 400
    assert eng.patch(path, json={"numberValue": 1, "textValue": "x"}).status_code == 400
    photo, _ = answer_by_label(run, "Bathroom fan photo")
    assert eng.patch(_pm(fx, f"/runs/{run['id']}/answers/{photo['id']}"),
                     json={"textValue": "x"}).status_code == 400

    # Clearing a value un-answers it.
    saved, _ = answer_by_label(eng.patch(path, json={"numberValue": None}).get_json(),
                               "Tap hot-water temperature")
    assert saved["numberValue"] is None and saved["answeredAt"] is None

    text, _ = answer_by_label(run, "Caulk condition")
    saved, _ = answer_by_label(
        eng.patch(_pm(fx, f"/runs/{run['id']}/answers/{text['id']}"),
                  json={"textValue": "  Fine  "}).get_json(), "Caulk condition")
    assert saved["textValue"] == "Fine"


def test_complete_requires_every_required_item_then_raises_work_orders(app, fx, login, database,
                                                                        events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    run_path = _pm(fx, f"/runs/{run['id']}")

    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 400
    assert len(res.get_json()["error"]["details"]["missingItemIds"]) == 3

    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan_item = answer_by_label(run, "Bathroom fan photo")
    # A required checkbox left unticked is still missing.
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": False})
    eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 122})
    assert upload(eng, fx, run["id"], PNG, item_id=fan_item["id"]).status_code == 201
    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 400 and res.get_json()["error"]["details"]["missingItemIds"] == \
        [hvac["itemId"]]
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": True})
    assert eng.get(run_path).get_json()["missingRequired"] == []

    res = eng.post(f"{run_path}/complete")
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["status"] == "completed" and res.get_json()["completedAt"]

    with database.session() as db:
        wos = db.scalars(select(WorkOrder).where(WorkOrder.property_id == fx.property_a.id)).all()
        assert len(wos) == 1
        wo = wos[0]
        assert wo.type.value == "maintenance" and wo.priority.value == "high"
        assert wo.location_ref == "204" and wo.department_id == fx.dept_engineering.id
        assert wo.title == "Tap hot-water temperature 122°F out of range (100–120) — Room 204"
        notes = db.scalars(select(Notification).where(
            Notification.type == "pm.out_of_range")).all()
        assert [n.user_id for n in notes] == [fx.supervisor_a.id]
        assert notes[0].entity_id == wo.id

    # Locked after completion.
    assert eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 1}) \
        .status_code == 409
    assert upload(eng, fx, run["id"], PNG).status_code == 409
    assert eng.post(f"{run_path}/complete").status_code == 409
    assert sum(1 for e in events if e.type == "pm.run.changed") >= 2


def test_an_in_range_completion_raises_nothing(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    run_path = _pm(fx, f"/runs/{run['id']}")
    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan_item = answer_by_label(run, "Bathroom fan photo")
    eng.patch(f"{run_path}/answers/{hvac['id']}", json={"boolValue": True})
    eng.patch(f"{run_path}/answers/{temp['id']}", json={"numberValue": 110})
    upload(eng, fx, run["id"], PNG, item_id=fan_item["id"])
    assert eng.post(f"{run_path}/complete").status_code == 200
    with database.session() as db:
        assert db.scalar(select(WorkOrder.id)) is None


def test_photos_validate_and_round_trip(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run = start(eng, fx, template_id, units["204"])
    _, hvac_item = answer_by_label(run, "HVAC filter replaced")

    assert upload(eng, fx, run["id"], GIF).status_code == 400
    assert upload(eng, fx, run["id"], b"x" * (8 * 1024 * 1024 + 1)).status_code == 400
    assert upload(eng, fx, run["id"], PNG, item_id=hvac_item["id"]).status_code == 400

    res = upload(eng, fx, run["id"], PNG)  # general evidence, no item
    assert res.status_code == 201
    photo = res.get_json()["photos"][0]
    assert photo["itemId"] is None and photo["byteSize"] == len(PNG)
    served = eng.get(photo["url"])
    assert served.status_code == 200 and served.data == PNG
    assert served.headers["Content-Type"] == "image/png"
    assert login("admin@lsi.test").get(photo["url"].replace(fx.property_a.id, fx.property_b.id)) \
        .status_code == 404


def test_perform_pm_gates_starting_and_runs_are_property_scoped(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    res = login("agent@hvh.test").post(_pm(fx, "/runs"),
                                       json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 403
    run = start(login("engineer@hvh.test"), fx, template_id, units["204"])
    assert login("agent@hvh.test").get(_pm(fx, f"/runs/{run['id']}")).status_code == 200
    assert login("admin@lsi.test").get(f"/api/p/{fx.property_b.id}/pm/runs/{run['id']}") \
        .status_code == 404
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_runs.py -q`
Expected: 404s on `/pm/runs`.

- [ ] **Step 2: Write the domain module**

Create `server/app/domain/pm_runs.py`:

```python
"""PM runs: start, answer, photograph, complete (spec §3.6–3.8, §4.2, §4.3)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications, pm_cycles, pm_templates, pm_units
from app.domain import work_orders as wo_domain
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import Conflict, NotFound, TransitionError, ValidationFailed
from app.models import (
    MaintainableUnit,
    PmRun,
    PmRunAnswer,
    PmRunPhoto,
    PmTemplate,
    PmTemplateItem,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    Priority,
    Role,
    UserStatus,
    WorkOrderStatus,
    WorkOrderType,
)
from app.schemas.pm import AnswerPatch, RunAnswerOut, RunOut, RunPhotoOut, StartRunRequest
from app.schemas.work_orders import CreateWorkOrder

VALUE_COLUMN: dict[PmItemType, str] = {
    PmItemType.checkbox: "bool_value",
    PmItemType.text: "text_value",
    PmItemType.number: "number_value",
}
WIRE_NAME = {"bool_value": "boolValue", "text_value": "textValue", "number_value": "numberValue"}


def get(db: Session, property_id: str, run_id: str) -> PmRun:
    run = db.scalar(select(PmRun).where(PmRun.id == run_id, PmRun.property_id == property_id))
    if run is None:
        raise NotFound("Run not found")
    return run


def emit(db: Session, run: PmRun) -> None:
    queue_event(db, run.property_id, "pm.run.changed",
                {"id": run.id, "unitId": run.unit_id, "cycleId": run.cycle_id,
                 "status": run.status.value})


def create_answers(db: Session, run: PmRun) -> None:
    """One row per *active* item at the moment the run starts — the run's snapshot of the
    checklist. Items deactivated later keep their answers; items added later do not appear."""
    for item in pm_templates.active_items(db, run.template_id):
        db.add(PmRunAnswer(run_id=run.id, property_id=run.property_id, item_id=item.id))
    db.flush()


def start(db: Session, property_id: str, actor_user_id: str, data: StartRunRequest) -> PmRun:
    template = pm_templates.get(db, property_id, data.template_id)
    unit = pm_units.get(db, property_id, data.unit_id)
    if template.mode != PmTemplateMode.sweep:
        raise ValidationFailed("Scheduled PMs are created by their schedule; start the pending "
                               "run instead", details={"templateId": "not_a_sweep"})
    if not template.active or unit.kind != template.unit_kind or not unit.active:
        raise ValidationFailed("That unit is not in this template's scope",
                               details={"unitId": "out_of_scope"})
    cycle = pm_cycles.open_cycle(db, template)
    if cycle is None:
        raise Conflict("This template has no open cycle")
    current = db.scalar(select(PmRun).where(
        PmRun.cycle_id == cycle.id, PmRun.unit_id == unit.id,
        PmRun.status.in_([PmRunStatus.in_progress, PmRunStatus.completed])))
    if current is not None:
        # The client offers Continue instead (spec §4.2).
        raise Conflict("This unit already has a run in this cycle", details={"runId": current.id})
    if db.scalar(select(PmRun.id).where(PmRun.cycle_id == cycle.id, PmRun.unit_id == unit.id,
                                        PmRun.status == PmRunStatus.passed)):
        raise Conflict("This unit has already passed in this cycle")
    run = PmRun(property_id=property_id, template_id=template.id, unit_id=unit.id,
                cycle_id=cycle.id, status=PmRunStatus.in_progress,
                started_by_user_id=actor_user_id, started_at=clock.now())
    db.add(run)
    db.flush()
    create_answers(db, run)
    audit.record(db, property_id, actor_user_id, "pm_run.started", "pm_run", run.id,
                 after={"unit_id": unit.id, "cycle_id": cycle.id})
    emit(db, run)
    return run


def begin_pending(db: Session, property_id: str, actor_user_id: str, run_id: str) -> PmRun:
    """A scheduled run exists before anyone touches it; this is the engineer picking it up."""
    run = get(db, property_id, run_id)
    if run.status != PmRunStatus.pending:
        raise TransitionError("Only a pending run can be started")
    run.status = PmRunStatus.in_progress
    run.started_by_user_id = actor_user_id
    run.started_at = clock.now()
    db.flush()
    create_answers(db, run)
    if run.work_order_id:
        wo = wo_domain.get(db, property_id, run.work_order_id)
        if wo.status in (WorkOrderStatus.open, WorkOrderStatus.assigned):
            wo_domain.transition(db, property_id, wo.id, actor_user_id,
                                 WorkOrderStatus.in_progress)
    audit.record(db, property_id, actor_user_id, "pm_run.started", "pm_run", run.id,
                 after={"unit_id": run.unit_id, "work_order_id": run.work_order_id})
    emit(db, run)
    return run


def save_answer(db: Session, property_id: str, actor_user_id: str, run_id: str,
                answer_id: str, data: AnswerPatch) -> PmRunAnswer:
    run = get(db, property_id, run_id)
    if run.status != PmRunStatus.in_progress:
        raise TransitionError("Answers can only change while the run is in progress")
    answer = db.scalar(select(PmRunAnswer).where(PmRunAnswer.id == answer_id,
                                                 PmRunAnswer.run_id == run.id))
    if answer is None:
        raise NotFound("Answer not found")
    item = db.get(PmTemplateItem, answer.item_id)
    column = VALUE_COLUMN.get(item.item_type)
    if column is None:
        raise ValidationFailed("A photo item is answered by uploading a photo",
                               details={"itemId": "photo_item"})
    provided = data.model_dump(exclude_unset=True)
    if set(provided) != {column}:
        raise ValidationFailed(f"This item takes {WIRE_NAME[column]} only",
                               details={WIRE_NAME[column]: "required"})
    value = provided[column]
    if column == "text_value" and value is not None:
        value = value.strip() or None
    setattr(answer, column, value)
    answer.answered_at = clock.now() if value is not None else None
    if item.item_type == PmItemType.number:
        answer.out_of_range = value is not None and (
            (item.min_value is not None and value < item.min_value)
            or (item.max_value is not None and value > item.max_value))
    db.flush()
    return answer


def missing_required(db: Session, run: PmRun) -> list[str]:
    """Item ids that still block Complete. A required checkbox must be ticked, not merely
    answered; a photo item is satisfied by a photo carrying its id (spec §4.2)."""
    rows = db.execute(select(PmRunAnswer, PmTemplateItem)
                      .join(PmTemplateItem, PmTemplateItem.id == PmRunAnswer.item_id)
                      .where(PmRunAnswer.run_id == run.id, PmTemplateItem.required.is_(True))
                      .order_by(PmTemplateItem.position)).all()
    photographed = set(db.scalars(select(PmRunPhoto.item_id).where(
        PmRunPhoto.run_id == run.id, PmRunPhoto.item_id.is_not(None))).all())
    missing: list[str] = []
    for answer, item in rows:
        if item.item_type == PmItemType.checkbox:
            done = answer.bool_value is True
        elif item.item_type == PmItemType.text:
            done = bool(answer.text_value)
        elif item.item_type == PmItemType.number:
            done = answer.number_value is not None
        else:
            done = item.id in photographed
        if not done:
            missing.append(item.id)
    return missing


def _escalation_targets(db: Session, property_id: str, department_id: str | None) -> list[str]:
    """Active supervisor-or-above members of the department; failing that, the property's
    managers and admins, so an out-of-range reading is never reported to nobody."""
    stmt = (select(PropertyMembership.user_id)
            .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
            .where(PropertyMembership.property_id == property_id,
                   UserAccount.status == UserStatus.active))
    if department_id:
        scoped = list(db.scalars(stmt.where(
            PropertyMembership.department_id == department_id,
            PropertyMembership.role.in_([Role.supervisor, Role.manager, Role.admin]))).all())
        if scoped:
            return scoped
    return list(db.scalars(stmt.where(
        PropertyMembership.role.in_([Role.manager, Role.admin]))).all())


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _raise_out_of_range(db: Session, run: PmRun, actor_user_id: str) -> list[WorkOrder]:
    rows = db.execute(select(PmRunAnswer, PmTemplateItem)
                      .join(PmTemplateItem, PmTemplateItem.id == PmRunAnswer.item_id)
                      .where(PmRunAnswer.run_id == run.id, PmRunAnswer.out_of_range.is_(True))
                      .order_by(PmTemplateItem.position)).all()
    if not rows:
        return []
    template = db.get(PmTemplate, run.template_id)
    unit = db.get(MaintainableUnit, run.unit_id)
    targets = [t for t in _escalation_targets(db, run.property_id, template.department_id)
               if t != actor_user_id]
    created: list[WorkOrder] = []
    for answer, item in rows:
        title = (f"{item.label} {_fmt(answer.number_value)}{item.unit or ''} out of range "
                 f"({_fmt(item.min_value)}–{_fmt(item.max_value)}) — {unit.name}")[:200]
        wo = wo_domain.create(db, run.property_id, actor_user_id, CreateWorkOrder(
            title=title, description=f"Recorded during {template.name} on {unit.name}.",
            type=WorkOrderType.maintenance, priority=Priority.high,
            location_type=pm_units.LOCATION_FOR_KIND[unit.kind], location_ref=unit.code,
            department_id=template.department_id))
        notifications.notify_users(db, run.property_id, targets, "pm.out_of_range",
                                   f"Out of range: {item.label} at {unit.name}",
                                   body=title[:140], entity_type="work_order", entity_id=wo.id)
        created.append(wo)
    return created


def _complete_work_order(db: Session, run: PmRun, actor_user_id: str) -> None:
    """Drive the linked work order through the existing transition function so its event log
    stays honest. Runs before the run's own status flips, so a refused transition leaves the
    run in progress."""
    wo = wo_domain.get(db, run.property_id, run.work_order_id)
    if wo.status in (WorkOrderStatus.open, WorkOrderStatus.assigned):
        wo = wo_domain.transition(db, run.property_id, wo.id, actor_user_id,
                                  WorkOrderStatus.in_progress)
    if wo.status == WorkOrderStatus.in_progress:
        wo_domain.transition(db, run.property_id, wo.id, actor_user_id, WorkOrderStatus.complete)
    elif wo.status == WorkOrderStatus.blocked:
        raise TransitionError("Unblock the work order before completing this PM")
    # complete / verified / cancelled: nothing to do.


def complete(db: Session, property_id: str, actor_user_id: str, run_id: str) -> PmRun:
    run = get(db, property_id, run_id)
    if run.status != PmRunStatus.in_progress:
        raise TransitionError("Only a run in progress can be completed")
    missing = missing_required(db, run)
    if missing:
        raise ValidationFailed("Answer every required item first",
                               details={"missingItemIds": missing})
    if run.work_order_id:
        _complete_work_order(db, run, actor_user_id)
    run.status = PmRunStatus.completed
    run.completed_at = clock.now()
    db.flush()
    raised = _raise_out_of_range(db, run, actor_user_id)
    audit.record(db, property_id, actor_user_id, "pm_run.completed", "pm_run", run.id,
                 after={"work_orders_raised": [w.id for w in raised]})
    emit(db, run)
    return run


def attach_photo(db: Session, property_id: str, actor_user_id: str, run_id: str, *,
                 data: bytes, item_id: str | None) -> PmRunPhoto:
    run = get(db, property_id, run_id)
    if run.status != PmRunStatus.in_progress:
        raise TransitionError("Photos can only be added while the run is in progress")
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
    if item_id:
        item = db.scalar(select(PmTemplateItem).where(
            PmTemplateItem.id == item_id, PmTemplateItem.template_id == run.template_id))
        if item is None or item.item_type != PmItemType.photo:
            raise ValidationFailed("That item does not take a photo",
                                   details={"itemId": "not_a_photo_item"})
    photo = PmRunPhoto(run_id=run.id, property_id=property_id, item_id=item_id,
                       uploaded_by_user_id=actor_user_id, content_type=content_type,
                       byte_size=len(data), data=data)
    db.add(photo)
    db.flush()
    audit.record(db, property_id, actor_user_id, "pm_run.photo_attached", "pm_run_photo",
                 photo.id, after={"run_id": run.id, "item_id": item_id, "byte_size": len(data)})
    return photo


def get_photo(db: Session, property_id: str, run_id: str, photo_id: str) -> PmRunPhoto:
    """Scoped by property and run, never by the guessable id alone."""
    photo = db.scalar(select(PmRunPhoto).where(PmRunPhoto.id == photo_id,
                                               PmRunPhoto.property_id == property_id,
                                               PmRunPhoto.run_id == run_id))
    if photo is None:
        raise NotFound("Photo not found")
    return photo


def photo_url(property_id: str, run_id: str, photo_id: str) -> str:
    return f"/api/p/{property_id}/pm/runs/{run_id}/photos/{photo_id}"


def names_for(db: Session, user_ids: list[str | None]) -> dict[str, str]:
    """Display names for ids already read off this property's own rows, so an unscoped
    user_account SELECT by id cannot leak anything across properties here."""
    ids = [u for u in user_ids if u]
    if not ids:
        return {}
    rows = db.execute(select(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
                      .where(UserAccount.id.in_(ids))).all()
    return {uid: f"{first} {last}" for uid, first, last in rows}


def to_out(db: Session, run: PmRun) -> RunOut:
    template = db.get(PmTemplate, run.template_id)
    unit = db.get(MaintainableUnit, run.unit_id)
    rows = db.execute(select(PmRunAnswer, PmTemplateItem)
                      .join(PmTemplateItem, PmTemplateItem.id == PmRunAnswer.item_id)
                      .where(PmRunAnswer.run_id == run.id)
                      .order_by(PmTemplateItem.position)).all()
    photos = db.scalars(select(PmRunPhoto).where(PmRunPhoto.run_id == run.id)
                        .order_by(PmRunPhoto.created_at, PmRunPhoto.id)).all()
    names = names_for(db, [run.started_by_user_id, run.inspected_by_user_id])
    return RunOut(
        id=run.id, template_id=template.id, template_name=template.name,
        unit_id=unit.id, unit_code=unit.code, unit_name=unit.name, unit_kind=unit.kind,
        cycle_id=run.cycle_id, work_order_id=run.work_order_id, status=run.status,
        started_by_user_id=run.started_by_user_id,
        started_by_name=names.get(run.started_by_user_id or ""),
        started_at=run.started_at, completed_at=run.completed_at,
        inspected_by_user_id=run.inspected_by_user_id,
        inspected_by_name=names.get(run.inspected_by_user_id or ""),
        inspected_at=run.inspected_at, inspection_note=run.inspection_note, due_at=run.due_at,
        items=[pm_templates.item_out(item) for _, item in rows],
        answers=[RunAnswerOut.model_validate(answer) for answer, _ in rows],
        photos=[RunPhotoOut(id=p.id, item_id=p.item_id, content_type=p.content_type,
                            byte_size=p.byte_size, uploaded_by_user_id=p.uploaded_by_user_id,
                            url=photo_url(run.property_id, run.id, p.id),
                            created_at=p.created_at) for p in photos],
        missing_required=(missing_required(db, run)
                          if run.status == PmRunStatus.in_progress else []),
    )
```

- [ ] **Step 3: Append the run routes**

In `server/app/api/pm.py`, extend the imports:

```python
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_runs, pm_templates
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import ValidationFailed
from app.schemas.pm import AnswerPatch, StartRunRequest, TemplateIn, TemplatePatch
```

and append after the template routes:

```python
# Defined per-api-module by existing convention (app/api/log.py:14).
MULTIPART_OVERHEAD_BYTES = 4096


def _read_photo() -> bytes:
    """Mirrors app/api/log.py: refuse before Werkzeug buffers the body, then read cap + 1."""
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    upload = request.files.get("photo")
    if upload is None:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    return upload.read(MAX_PHOTO_BYTES + 1)


@bp.post("/runs")
@require_auth
@require_property
@require_capability("perform_pm")
def start_run(property_id: str):
    data = parse_body(StartRunRequest)
    with db_session() as db:
        run = pm_runs.start(db, g.property_id, g.user.id, data)
        return ok(pm_runs.to_out(db, run), 201)


@bp.get("/runs/<run_id>")
@require_auth
@require_property
@require_capability("view_pm")
def get_run(property_id: str, run_id: str):
    with db_session() as db:
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)))


@bp.post("/runs/<run_id>/start")
@require_auth
@require_property
@require_capability("perform_pm")
def begin_run(property_id: str, run_id: str):
    with db_session() as db:
        run = pm_runs.begin_pending(db, g.property_id, g.user.id, run_id)
        return ok(pm_runs.to_out(db, run))


@bp.patch("/runs/<run_id>/answers/<answer_id>")
@require_auth
@require_property
@require_capability("perform_pm")
def save_answer(property_id: str, run_id: str, answer_id: str):
    """Returns the whole run, so the client gets `missingRequired` refreshed in the same round
    trip as the answer it just saved."""
    data = parse_body(AnswerPatch)
    with db_session() as db:
        pm_runs.save_answer(db, g.property_id, g.user.id, run_id, answer_id, data)
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)))


@bp.post("/runs/<run_id>/photos")
@require_auth
@require_property
@require_capability("perform_pm")
def add_run_photo(property_id: str, run_id: str):
    """multipart/form-data: a `photo` part and an optional `itemId` field naming a photo item."""
    data = _read_photo()
    item_id = request.form.get("itemId") or None
    with db_session() as db:
        pm_runs.attach_photo(db, g.property_id, g.user.id, run_id, data=data, item_id=item_id)
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)), 201)


@bp.get("/runs/<run_id>/photos/<photo_id>")
@require_auth
@require_property
@require_capability("view_pm")
def get_run_photo(property_id: str, run_id: str, photo_id: str):
    with db_session() as db:
        photo = pm_runs.get_photo(db, g.property_id, run_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@bp.post("/runs/<run_id>/complete")
@require_auth
@require_property
@require_capability("perform_pm")
def complete_run(property_id: str, run_id: str):
    with db_session() as db:
        run = pm_runs.complete(db, g.property_id, g.user.id, run_id)
        return ok(pm_runs.to_out(db, run))
```

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_runs.py tests/test_isolation.py -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: pass, clean.

```bash
git add server/app/domain/pm_runs.py server/app/api/pm.py server/tests/test_pm_runs.py
git commit -m "feat(server): PM runs — start, typed answers, photos, complete, out-of-range work orders

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 8: Inspection — queue and pass/fail

**Files:**
- Create: `server/app/domain/pm_inspection.py`
- Modify: `server/app/api/pm.py` (append two routes)
- Create: `server/tests/test_pm_inspection.py`

**Interfaces:**
- Produces: `pm_inspection.queue(db, property_id, InspectionQuery) -> list[InspectionRowOut]`, `pm_inspection.inspect(db, property_id, actor, run_id, InspectRequest) -> PmRun`.
- Routes: `GET /pm/inspections`, `POST /pm/runs/<id>/inspect`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_inspection.py`:

```python
"""Inspection (spec §4.4, §5.2)."""
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.domain import pm_inspection
from app.errors import Forbidden
from app.models import Notification, PmRun, PropertyMembership
from app.schemas.enums import PmRunStatus, Role
from app.schemas.pm import InspectRequest
from tests.test_pm_runs import PNG, answer_by_label, setup_sweep, start, upload


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def complete_run(client, fx, template_id, unit_id, temperature=110):
    run = start(client, fx, template_id, unit_id)
    path = _pm(fx, f"/runs/{run['id']}")
    hvac, _ = answer_by_label(run, "HVAC filter replaced")
    temp, _ = answer_by_label(run, "Tap hot-water temperature")
    _, fan = answer_by_label(run, "Bathroom fan photo")
    client.patch(f"{path}/answers/{hvac['id']}", json={"boolValue": True})
    client.patch(f"{path}/answers/{temp['id']}", json={"numberValue": temperature})
    upload(client, fx, run["id"], PNG, item_id=fan["id"])
    res = client.post(f"{path}/complete")
    assert res.status_code == 200, res.get_json()
    return run["id"]


def test_queue_lists_completed_runs_and_pass_credits_the_unit(app, fx, login, events):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run_id = complete_run(eng, fx, template_id, units["204"])
    sup = login("supervisor@hvh.test")

    rows = sup.get(_pm(fx, "/inspections?kind=guest_room")).get_json()
    assert [r["runId"] for r in rows] == [run_id]
    assert rows[0]["completedByName"] == "Eli Engineer" and rows[0]["daysSinceLastPm"] is None
    assert sup.get(_pm(fx, "/inspections?kind=equipment")).get_json() == []
    assert sup.get(_pm(fx, "/inspections?status=inspected")).get_json() == []

    res = sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["status"] == "passed"
    assert res.get_json()["inspectedByName"] == "Sam Super"
    assert sup.get(_pm(fx, "/inspections")).get_json() == []
    inspected = sup.get(_pm(fx, "/inspections?status=inspected")).get_json()
    assert inspected[0]["status"] == "passed" and inspected[0]["inspectedByName"] == "Sam Super"

    # A passed unit cannot be started again this cycle.
    res = eng.post(_pm(fx, "/runs"), json={"templateId": template_id, "unitId": units["204"]})
    assert res.status_code == 409
    assert "details" not in res.get_json()["error"], "no Continue offered for a passed unit"
    assert any(e.type == "pm.run.changed" and e.payload["status"] == "passed" for e in events)


def test_fail_needs_a_note_notifies_the_engineer_and_returns_the_unit_to_remaining(
        app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    eng = login("engineer@hvh.test")
    run_id = complete_run(eng, fx, template_id, units["204"])
    sup = login("supervisor@hvh.test")

    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "fail"}).status_code == 400
    res = sup.post(_pm(fx, f"/runs/{run_id}/inspect"),
                   json={"result": "fail", "note": "Fan photo shows the grille still dusty."})
    assert res.status_code == 200 and res.get_json()["status"] == "failed"
    assert res.get_json()["inspectionNote"].startswith("Fan photo")
    with database.session() as db:
        notes = db.scalars(select(Notification).where(
            Notification.type == "pm.inspection_failed")).all()
        assert [n.user_id for n in notes] == [fx.engineer_a.id]
        assert notes[0].entity_id == run_id

    # Back in Remaining: a fresh run can start, and the failed one is a permanent record.
    new = start(eng, fx, template_id, units["204"])
    assert new["id"] != run_id
    with database.session() as db:
        assert db.get(PmRun, run_id).status == PmRunStatus.failed


def test_a_run_is_inspected_once_and_not_by_its_own_engineer(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    sup = login("supervisor@hvh.test")
    run_id = complete_run(sup, fx, template_id, units["204"])  # the supervisor did the PM
    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"}).status_code == 403
    manager = login("manager@hvh.test")
    assert manager.post(_pm(fx, f"/runs/{run_id}/inspect"),
                        json={"result": "pass"}).status_code == 200
    assert manager.post(_pm(fx, f"/runs/{run_id}/inspect"),
                        json={"result": "pass"}).status_code == 409
    assert login("engineer@hvh.test").post(_pm(fx, f"/runs/{run_id}/inspect"),
                                           json={"result": "pass"}).status_code == 403


def test_the_sole_inspector_may_inspect_their_own_run(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    sup = login("supervisor@hvh.test")
    run_id = complete_run(sup, fx, template_id, units["204"])
    with database.session() as db:
        # Demote every other inspect_pm holder at property A.
        for m in db.scalars(select(PropertyMembership).where(
                PropertyMembership.property_id == fx.property_a.id,
                PropertyMembership.role.in_([Role.manager, Role.admin]))).all():
            m.role = Role.agent
        db.flush()
        try:
            pm_inspection.inspect(db, fx.property_a.id, fx.supervisor_a.id, run_id,
                                  InspectRequest(result="pass"))
        except Forbidden:
            raise AssertionError("the only inspector must be allowed to inspect") from None
        assert db.get(PmRun, run_id).status == PmRunStatus.passed


def test_days_since_last_pm_counts_from_the_units_previous_pass(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx)
    with database.session() as db:
        db.add(PmRun(property_id=fx.property_a.id, template_id=template_id,
                     unit_id=units["204"], status=PmRunStatus.passed,
                     started_at=clock.now() - timedelta(days=31),
                     completed_at=clock.now() - timedelta(days=30),
                     inspected_at=clock.now() - timedelta(days=29)))
    eng = login("engineer@hvh.test")
    complete_run(eng, fx, template_id, units["204"])
    complete_run(eng, fx, template_id, units["205"])
    rows = login("supervisor@hvh.test").get(
        _pm(fx, "/inspections?sort=days_since_last_pm")).get_json()
    # Never-inspected sorts first, then the longest-ago.
    assert [(r["unitCode"], r["daysSinceLastPm"]) for r in rows] == [("205", None), ("204", 30)]
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_inspection.py -q`
Expected: 404s / ImportError.

- [ ] **Step 2: Write the domain module**

Create `server/app/domain/pm_inspection.py`:

```python
"""Inspection gates cycle credit (spec §4.4)."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.permissions import CAPABILITIES
from app.domain import audit, notifications, pm_cycles, pm_runs
from app.domain import work_orders as wo_domain
from app.errors import Forbidden, TransitionError, ValidationFailed
from app.models import (
    MaintainableUnit,
    PmRun,
    PmTemplate,
    Property,
    PropertyMembership,
    UserAccount,
)
from app.schemas.enums import PmRunStatus, UserStatus, WorkOrderStatus
from app.schemas.pm import InspectionQuery, InspectionRowOut, InspectRequest

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def queue(db: Session, property_id: str, query: InspectionQuery) -> list[InspectionRowOut]:
    statuses = ([PmRunStatus.completed] if query.status == "available"
                else [PmRunStatus.passed, PmRunStatus.failed])
    stmt = (select(PmRun, MaintainableUnit, PmTemplate)
            .join(MaintainableUnit, MaintainableUnit.id == PmRun.unit_id)
            .join(PmTemplate, PmTemplate.id == PmRun.template_id)
            .where(PmRun.property_id == property_id, PmRun.status.in_(statuses)))
    if query.kind:
        stmt = stmt.where(MaintainableUnit.kind == query.kind)
    rows = db.execute(stmt).all()
    prop = db.get(Property, property_id)
    today = pm_cycles.local_today(prop)
    names = pm_runs.names_for(db, [r.started_by_user_id for r, _, _ in rows]
                              + [r.inspected_by_user_id for r, _, _ in rows])
    # Every unit's previous pass in one query; each row then excludes itself.
    previous_all = db.scalars(select(PmRun).where(
        PmRun.property_id == property_id, PmRun.status == PmRunStatus.passed,
        PmRun.unit_id.in_([u.id for _, u, _ in rows] or [""]))
        .order_by(PmRun.completed_at, PmRun.id)).all()
    out: list[InspectionRowOut] = []
    for run, unit, template in rows:
        previous = [p for p in previous_all if p.unit_id == unit.id and p.id != run.id]
        days = ((today - pm_cycles.local_today(prop, previous[-1].completed_at)).days
                if previous and previous[-1].completed_at else None)
        out.append(InspectionRowOut(
            run_id=run.id, unit_id=unit.id, unit_code=unit.code, unit_name=unit.name,
            unit_kind=unit.kind, template_name=template.name,
            completed_by_name=names.get(run.started_by_user_id or ""),
            completed_at=run.completed_at, days_since_last_pm=days, status=run.status,
            inspected_by_name=names.get(run.inspected_by_user_id or ""),
            inspected_at=run.inspected_at))
    if query.sort == "days_since_last_pm":
        # Never-inspected first (None), then the longest-ago.
        out.sort(key=lambda r: (r.days_since_last_pm is not None, -(r.days_since_last_pm or 0)))
    else:
        out.sort(key=lambda r: r.completed_at or _EPOCH, reverse=True)
    return out


def _sole_inspector(db: Session, property_id: str, user_id: str) -> bool:
    holders = list(db.scalars(
        select(PropertyMembership.user_id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.role.in_(list(CAPABILITIES["inspect_pm"])),
               UserAccount.status == UserStatus.active)).all())
    return holders == [user_id]


def inspect(db: Session, property_id: str, actor_user_id: str, run_id: str,
            data: InspectRequest) -> PmRun:
    run = pm_runs.get(db, property_id, run_id)
    if run.status != PmRunStatus.completed:
        raise TransitionError("Only a completed run can be inspected")
    note = (data.note or "").strip() or None
    if data.result == "fail" and not note:
        raise ValidationFailed("A note is required when failing an inspection",
                               details={"note": "required"})
    if run.started_by_user_id == actor_user_id and not _sole_inspector(db, property_id,
                                                                       actor_user_id):
        # A one-engineer property where that engineer is also the supervisor must not be
        # locked out of PM entirely; anyone else must not mark their own work (spec §4.4).
        raise Forbidden("You cannot inspect your own PM")
    run.status = PmRunStatus.passed if data.result == "pass" else PmRunStatus.failed
    run.inspected_by_user_id = actor_user_id
    run.inspected_at = clock.now()
    run.inspection_note = note
    db.flush()
    unit = db.get(MaintainableUnit, run.unit_id)
    if run.status == PmRunStatus.failed and run.started_by_user_id:
        notifications.create(db, property_id, run.started_by_user_id, "pm.inspection_failed",
                             f"PM failed inspection: {unit.name}", body=note[:140],
                             entity_type="pm_run", entity_id=run.id)
    if run.status == PmRunStatus.passed and run.work_order_id:
        wo = wo_domain.get(db, property_id, run.work_order_id)
        if wo.status == WorkOrderStatus.complete:
            wo_domain.transition(db, property_id, wo.id, actor_user_id, WorkOrderStatus.verified)
    audit.record(db, property_id, actor_user_id, "pm_run.inspected", "pm_run", run.id,
                 after={"result": data.result, "unit_id": unit.id})
    pm_runs.emit(db, run)
    return run
```

- [ ] **Step 3: Append the routes**

In `server/app/api/pm.py`: add `pm_inspection` to the `from app.domain import …` line, `parse_query` to the `_util` import, and `InspectRequest, InspectionQuery` to the schema import. Append:

```python
@bp.get("/inspections")
@require_auth
@require_property
@require_capability("inspect_pm")
def list_inspections(property_id: str):
    query = parse_query(InspectionQuery)
    with db_session() as db:
        return ok(pm_inspection.queue(db, g.property_id, query))


@bp.post("/runs/<run_id>/inspect")
@require_auth
@require_property
@require_capability("inspect_pm")
def inspect_run(property_id: str, run_id: str):
    data = parse_body(InspectRequest)
    with db_session() as db:
        run = pm_inspection.inspect(db, g.property_id, g.user.id, run_id, data)
        return ok(pm_runs.to_out(db, run))
```

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_inspection.py tests/test_isolation.py -q && ../.venv/Scripts/python.exe -m ruff check .`

```bash
git add server/app/domain/pm_inspection.py server/app/api/pm.py server/tests/test_pm_inspection.py
git commit -m "feat(server): PM inspection queue and pass/fail gating cycle credit

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 9: Sweep payload and cycle history

**Files:**
- Create: `server/app/domain/pm_reports.py`
- Modify: `server/app/api/pm.py` (append two routes)
- Create: `server/tests/test_pm_reports.py`

**Interfaces:**
- Produces: `pm_reports.sweep(db, property_id, SweepQuery) -> SweepOut`, `pm_reports.cycles(db, property_id, template_id) -> list[CycleOut]`, `pm_reports.cycle_unit_counts(db, cycle) -> (passed, missed, total)`.
- Routes: `GET /pm/sweep`, `GET /pm/cycles`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_reports.py`:

```python
"""Sweep page payload and cycle history (spec §5.3, §5.2)."""
from datetime import date

from app.domain import pm_cycles
from app.models import PmTemplate
from tests.test_pm_inspection import complete_run
from tests.test_pm_runs import setup_sweep, start


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def test_sweep_without_a_template_reports_the_kind_as_unconfigured(app, fx, login):
    admin = login("admin@hvh.test")
    admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
               json={"kind": "equipment", "code": "PUMP", "name": "Pump"})
    body = login("agent@hvh.test").get(_pm(fx, "/sweep?kind=equipment")).get_json()
    assert body["template"] is None and body["cycle"] is None
    assert body["counts"] == {"remaining": 1, "completed": 0, "total": 1}
    assert body["units"] == []
    assert login("agent@hvh.test").get(_pm(fx, "/sweep")).status_code == 400  # kind required


def test_sweep_counts_rows_filters_and_sorting(app, fx, login):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("101", "204", "205"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    passed_run = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{passed_run}/inspect"), json={"result": "pass"})
    in_progress = start(eng, fx, template_id, units["205"])

    body = eng.get(_pm(fx, "/sweep?kind=guest_room")).get_json()
    assert body["template"]["name"] == "Guest Room Quarterly"
    assert body["cycle"]["ordinal"] == 3 and body["cycle"]["daysLeft"] == 20  # Sep 10 → Sep 30
    assert body["counts"] == {"remaining": 2, "completed": 1, "total": 3}
    by_code = {u["code"]: u for u in body["units"]}
    assert list(by_code) == ["101", "204", "205"]
    assert by_code["204"]["passedThisCycle"] is True and by_code["204"]["currentRun"] is None
    assert by_code["204"]["lastPassedByName"] == "Eli Engineer"
    assert by_code["205"]["currentRun"] == {"id": in_progress["id"], "status": "in_progress",
                                             "startedByUserId": fx.engineer_a.id,
                                             "startedByName": "Eli Engineer"}
    assert by_code["101"]["currentRun"] is None and by_code["101"]["lastPassedAt"] is None

    remaining = eng.get(_pm(fx, "/sweep?kind=guest_room&status=remaining")).get_json()
    assert [u["code"] for u in remaining["units"]] == ["101", "205"]
    completed = eng.get(_pm(fx, "/sweep?kind=guest_room&status=completed")).get_json()
    assert [u["code"] for u in completed["units"]] == ["204"]
    assert [u["code"] for u in eng.get(_pm(fx, "/sweep?kind=guest_room&q=20")).get_json()["units"]] \
        == ["204", "205"]
    by_days = eng.get(_pm(fx, "/sweep?kind=guest_room&sort=days_since_last_pm")).get_json()
    assert [u["code"] for u in by_days["units"]] == ["101", "205", "204"]  # never first
    by_floor = eng.get(_pm(fx, "/sweep?kind=guest_room&sort=floor")).get_json()
    assert [u["code"] for u in by_floor["units"]] == ["101", "204", "205"]


def test_cycle_history_after_a_close(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205", "206"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    run = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{run}/inspect"), json={"result": "pass"})
    with database.session() as db:
        t = db.get(PmTemplate, template_id)
        assert pm_cycles.close_expired(db, t, date(2026, 10, 1)) == 2
        pm_cycles.ensure_open_cycle(db, t, date(2026, 10, 1))
    rows = eng.get(_pm(fx, f"/cycles?templateId={template_id}")).get_json()
    assert [(r["ordinal"], r["status"]) for r in rows] == [(4, "open"), (3, "closed")]
    q3 = rows[1]
    assert (q3["passed"], q3["missed"], q3["total"]) == (1, 2, 3)
    assert q3["daysLeft"] == 0
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_reports.py -q`
Expected: 404s.

- [ ] **Step 2: Write the module**

Create `server/app/domain/pm_reports.py`:

```python
"""Read models for the sweep page, cycle history and (Task 11) compliance (spec §5.3, §5.5).

Everything here is computed in Python from a handful of set queries per property — a hotel has
hundreds of units, not millions — and nothing here issues a query per row.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import pm_cycles, pm_runs
from app.domain.pm_units import natural_key
from app.errors import NotFound
from app.models import MaintainableUnit, PmCycle, PmRun, PmTemplate, Property
from app.schemas.enums import PmCycleStatus, PmRunStatus, PmTemplateMode
from app.schemas.pm import (
    CycleOut,
    SweepCounts,
    SweepCycleOut,
    SweepOut,
    SweepQuery,
    SweepRunBrief,
    SweepTemplateOut,
    SweepUnitOut,
)


def _active_sweep_template(db: Session, property_id: str, unit_kind) -> PmTemplate | None:
    return db.scalar(select(PmTemplate).where(PmTemplate.property_id == property_id,
                                              PmTemplate.mode == PmTemplateMode.sweep,
                                              PmTemplate.unit_kind == unit_kind,
                                              PmTemplate.active.is_(True)))


def sweep(db: Session, property_id: str, query: SweepQuery) -> SweepOut:
    prop = db.get(Property, property_id)
    today = pm_cycles.local_today(prop)
    active_units = list(db.scalars(select(MaintainableUnit).where(
        MaintainableUnit.property_id == property_id, MaintainableUnit.kind == query.kind,
        MaintainableUnit.active.is_(True))).all())
    template = _active_sweep_template(db, property_id, query.kind)
    cycle = pm_cycles.open_cycle(db, template) if template else None
    if template is None or cycle is None:
        return SweepOut(
            template=(SweepTemplateOut(id=template.id, name=template.name,
                                       cadence=template.cadence) if template else None),
            cycle=None,
            counts=SweepCounts(remaining=len(active_units), completed=0,
                               total=len(active_units)),
            units=[])

    unit_ids = [u.id for u in active_units]
    cycle_runs = db.scalars(select(PmRun).where(
        PmRun.cycle_id == cycle.id, PmRun.unit_id.in_(unit_ids or [""]))).all()
    passed_units = {r.unit_id for r in cycle_runs if r.status == PmRunStatus.passed}
    current = {r.unit_id: r for r in cycle_runs
               if r.status in (PmRunStatus.in_progress, PmRunStatus.completed)}
    last_passed = db.scalars(select(PmRun).where(
        PmRun.property_id == property_id, PmRun.status == PmRunStatus.passed,
        PmRun.unit_id.in_(unit_ids or [""])).order_by(PmRun.completed_at, PmRun.id)).all()
    latest = {r.unit_id: r for r in last_passed}  # ascending, so the last write wins
    names = pm_runs.names_for(db, [r.started_by_user_id for r in cycle_runs]
                              + [r.started_by_user_id for r in latest.values()])

    rows: list[SweepUnitOut] = []
    needle = (query.q or "").strip().lower()
    for unit in active_units:
        if needle and needle not in unit.code.lower() and needle not in unit.name.lower():
            continue
        passed = unit.id in passed_units
        if query.status == "remaining" and passed:
            continue
        if query.status == "completed" and not passed:
            continue
        run = current.get(unit.id)
        prev = latest.get(unit.id)
        rows.append(SweepUnitOut(
            id=unit.id, code=unit.code, name=unit.name, floor=unit.floor,
            room_type=unit.room_type,
            last_passed_at=prev.completed_at if prev else None,
            last_passed_by_name=names.get(prev.started_by_user_id or "") if prev else None,
            passed_this_cycle=passed,
            current_run=(SweepRunBrief(id=run.id, status=run.status,
                                       started_by_user_id=run.started_by_user_id,
                                       started_by_name=names.get(run.started_by_user_id or ""))
                         if run else None)))

    if query.sort == "floor":
        rows.sort(key=lambda r: (r.floor is None, r.floor or 0, natural_key(r.code)))
    elif query.sort == "days_since_last_pm":
        # Never passed first, then the longest ago.
        rows.sort(key=lambda r: (r.last_passed_at is not None, r.last_passed_at or 0,
                                 natural_key(r.code)))
    else:
        rows.sort(key=lambda r: natural_key(r.code))

    completed = len(passed_units)
    return SweepOut(
        template=SweepTemplateOut(id=template.id, name=template.name, cadence=template.cadence),
        cycle=SweepCycleOut(id=cycle.id, ordinal=cycle.ordinal, starts_on=cycle.starts_on,
                            ends_on=cycle.ends_on,
                            days_left=max((cycle.ends_on - today).days, 0)),
        counts=SweepCounts(remaining=len(active_units) - completed, completed=completed,
                           total=len(active_units)),
        units=rows)


def cycle_unit_counts(db: Session, cycle: PmCycle) -> tuple[int, int, int]:
    """(passed, missed, total) as *distinct units*, so a run passed after its cycle closed
    cannot make a unit count as both passed and missed."""
    runs = db.execute(select(PmRun.unit_id, PmRun.status).where(PmRun.cycle_id == cycle.id)).all()
    passed = {u for u, s in runs if s == PmRunStatus.passed}
    missed = {u for u, s in runs if s == PmRunStatus.missed} - passed
    return len(passed), len(missed), len(passed | missed)


def cycles(db: Session, property_id: str, template_id: str) -> list[CycleOut]:
    template = db.scalar(select(PmTemplate).where(PmTemplate.id == template_id,
                                                  PmTemplate.property_id == property_id))
    if template is None:
        raise NotFound("Template not found")
    today = pm_cycles.local_today(db.get(Property, property_id))
    rows = db.scalars(select(PmCycle).where(PmCycle.template_id == template.id)
                      .order_by(PmCycle.starts_on.desc())).all()
    out: list[CycleOut] = []
    for cycle in rows:
        passed, missed, total = cycle_unit_counts(db, cycle)
        if cycle.status == PmCycleStatus.open:
            # An open cycle's denominator is its live scope; missed is not yet known.
            total = len(pm_cycles.scope_unit_ids(db, template))
            missed = 0
        out.append(CycleOut(id=cycle.id, template_id=template.id, ordinal=cycle.ordinal,
                            starts_on=cycle.starts_on, ends_on=cycle.ends_on,
                            status=cycle.status,
                            days_left=max((cycle.ends_on - today).days, 0)
                            if cycle.status == PmCycleStatus.open else 0,
                            passed=passed, missed=missed, total=total))
    return out
```

- [ ] **Step 3: Append the routes**

In `server/app/api/pm.py`: add `pm_reports` to the domain import and `SweepQuery` to the schema import. Append:

```python
class _CyclesQuery(CamelModel):
    template_id: str


@bp.get("/sweep")
@require_auth
@require_property
@require_capability("view_pm")
def sweep(property_id: str):
    query = parse_query(SweepQuery)
    with db_session() as db:
        return ok(pm_reports.sweep(db, g.property_id, query))


@bp.get("/cycles")
@require_auth
@require_property
@require_capability("view_pm")
def list_cycles(property_id: str):
    query = parse_query(_CyclesQuery)
    with db_session() as db:
        return ok(pm_reports.cycles(db, g.property_id, query.template_id))
```

with `from app.schemas.common import CamelModel` added to the imports. (`_CyclesQuery` is private to the route module and deliberately not exported to the schema — it is one query-string parameter.)

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_reports.py tests/test_isolation.py -q && ../.venv/Scripts/python.exe -m ruff check .`

```bash
git add server/app/domain/pm_reports.py server/app/api/pm.py server/tests/test_pm_reports.py
git commit -m "feat(server): PM sweep payload and cycle history

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 10: `pm.tick` — roll cycles, expand RRULEs, link work orders

**Files:**
- Create: `server/app/queue/handlers/pm.py`
- Modify: `server/app/queue/jobs.py:12` (`RECURRING`)
- Modify: `server/app/queue/handlers/__init__.py:12` (`MODULES`)
- Modify: `server/app/domain/work_orders.py` (`detail` populates `pm_run_id`)
- Modify: `server/seed/seed.py` (the `ensure_recurring` loop gains `"pm.tick"`)
- Create: `server/tests/test_pm_tick.py`

**Interfaces:**
- Produces: `pm_tick.tick_once(db) -> dict[str, int]` (`{"opened", "missed", "fired"}`), `pm_tick.roll_cycles(db, now)`, `pm_tick.fire_scheduled(db, now)`, `pm_tick.occurrences_between(template, tz, window_end) -> list[datetime]`.
- Consumes: Tasks 5–8.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_pm_tick.py`:

```python
"""The recurring job (spec §4.1) and the scheduled-run lifecycle through the Board."""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import clock
from app.models import PmCycle, PmRun, PmTemplate, WorkOrder
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.queue.handlers.pm import tick_once
from app.schemas.enums import PmCycleStatus, PmRunStatus, WorkOrderStatus
from tests.test_pm_runs import setup_sweep


def _pm(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/pm{rest}"


def test_registered_as_a_recurring_job():
    load_all()
    assert "pm.tick" in HANDLERS and jobs.RECURRING["pm.tick"] == 300


def test_tick_rolls_an_expired_cycle_and_opens_the_next(app, fx, login, database):
    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205"))
    with database.session() as db:
        assert tick_once(db) == {"opened": 0, "missed": 0, "fired": 0}
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db) == {"opened": 1, "missed": 2, "fired": 0}
        cycles = db.scalars(select(PmCycle).where(PmCycle.template_id == template_id)
                            .order_by(PmCycle.starts_on)).all()
        assert [(c.ordinal, c.status) for c in cycles] == [
            (3, PmCycleStatus.closed), (4, PmCycleStatus.open)]
        assert db.scalar(select(func.count()).select_from(PmRun).where(
            PmRun.status == PmRunStatus.missed)) == 2
        assert tick_once(db) == {"opened": 0, "missed": 0, "fired": 0}, "idempotent"


def _scheduled(admin, fx, unit_ids, rrule="FREQ=MONTHLY;INTERVAL=3", dtstart="2026-07-01"):
    res = admin.post(_pm(fx, "/templates"), json={
        "name": "Boiler inspection", "mode": "scheduled", "rrule": rrule,
        "rruleDtstart": dtstart, "departmentId": fx.dept_engineering.id,
        "unitIds": unit_ids,
        "items": [{"label": "Pressure", "itemType": "number", "unit": "psi",
                   "minValue": 10, "maxValue": 30}]})
    assert res.status_code == 201, res.get_json()
    return res.get_json()["id"]


def _units(admin, fx, *codes):
    return [admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                       json={"kind": "equipment", "code": c, "name": c}).get_json()["id"]
            for c in codes]


def test_rrule_fires_once_per_occurrence_per_unit_after_creation_never_before(
        app, fx, login, database):
    admin = login("admin@hvh.test")
    boilers = _units(admin, fx, "BOILER-1", "BOILER-2")
    template_id = _scheduled(admin, fx, boilers)  # created 2026-09-10; Jul 1 is in the past
    with database.session() as db:
        assert db.get(PmTemplate, template_id).last_fired_at == clock.now()
        assert tick_once(db)["fired"] == 0, "no backfill of the July occurrence"
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))  # Oct 1 occurrence has passed
    with database.session() as db:
        assert tick_once(db)["fired"] == 2
        runs = db.scalars(select(PmRun).where(PmRun.template_id == template_id)).all()
        assert {r.status for r in runs} == {PmRunStatus.pending}
        assert {r.unit_id for r in runs} == set(boilers)
        assert all(r.due_at == datetime(2026, 10, 1, 4, 0, tzinfo=UTC) for r in runs)  # EDT
        wos = db.scalars(select(WorkOrder).where(WorkOrder.type == "pm")).all()
        assert len(wos) == 2 and {w.id for w in wos} == {r.work_order_id for r in runs}
        assert wos[0].title.startswith("Boiler inspection — BOILER-")
        assert wos[0].department_id == fx.dept_engineering.id
        assert wos[0].location_type.value == "equipment"
        assert tick_once(db)["fired"] == 0, "the window advanced"
    clock.freeze(datetime(2027, 1, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db)["fired"] == 2


def test_an_inactive_target_unit_is_skipped(app, fx, login, database):
    admin = login("admin@hvh.test")
    b1, b2 = _units(admin, fx, "BOILER-1", "BOILER-2")
    _scheduled(admin, fx, [b1, b2])
    admin.patch(f"/api/p/{fx.property_a.id}/maintainable-units/{b2}", json={"active": False})
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        assert tick_once(db)["fired"] == 1


def test_scheduled_run_drives_its_work_order_start_complete_verify(app, fx, login, database):
    admin = login("admin@hvh.test")
    (boiler,) = _units(admin, fx, "BOILER-1")
    _scheduled(admin, fx, [boiler])
    clock.freeze(datetime(2026, 10, 2, 12, 0, tzinfo=UTC))
    with database.session() as db:
        tick_once(db)
        run_id = db.scalar(select(PmRun.id))
        wo_id = db.scalar(select(PmRun.work_order_id))
    eng = login("engineer@hvh.test")
    detail = eng.get(f"/api/p/{fx.property_a.id}/work-orders/{wo_id}").get_json()
    assert detail["pmRunId"] == run_id and detail["status"] == "open"

    run = eng.get(_pm(fx, f"/runs/{run_id}")).get_json()
    assert run["status"] == "pending" and run["answers"] == []
    res = eng.post(_pm(fx, f"/runs/{run_id}/start"))
    assert res.status_code == 200 and res.get_json()["status"] == "in_progress"
    assert len(res.get_json()["answers"]) == 1
    assert eng.post(_pm(fx, f"/runs/{run_id}/start")).status_code == 409
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.in_progress

    answer = res.get_json()["answers"][0]
    eng.patch(_pm(fx, f"/runs/{run_id}/answers/{answer['id']}"), json={"numberValue": 20})
    assert eng.post(_pm(fx, f"/runs/{run_id}/complete")).status_code == 200
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.complete

    sup = login("supervisor@hvh.test")
    assert sup.post(_pm(fx, f"/runs/{run_id}/inspect"), json={"result": "pass"}).status_code == 200
    with database.session() as db:
        assert db.get(WorkOrder, wo_id).status == WorkOrderStatus.verified
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_tick.py -q`
Expected: `ModuleNotFoundError: app.queue.handlers.pm`.

- [ ] **Step 2: Write the handler**

Create `server/app/queue/handlers/pm.py`:

```python
"""`pm.tick` (spec §4.1): every 300 s, roll sweep cycles and expand scheduled templates.

Both phases are idempotent date-driven scans. The worker retries a failed job, so running twice
must be harmless — and it is: a cycle already open is not reopened, a closed one is not
re-closed, and `last_fired_at` advances only after its occurrences were written.
"""
from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import pm_cycles, pm_runs, pm_units
from app.domain import work_orders as wo_domain
from app.models import MaintainableUnit, PmRun, PmTemplate, PmTemplateUnit, Property
from app.queue.handlers import handler
from app.schemas.enums import PmRunStatus, PmTemplateMode, Priority, WorkOrderType
from app.schemas.work_orders import CreateWorkOrder


def _templates(db: Session, mode: PmTemplateMode) -> list[tuple[PmTemplate, Property]]:
    return list(db.execute(
        select(PmTemplate, Property).join(Property, Property.id == PmTemplate.property_id)
        .where(PmTemplate.mode == mode, PmTemplate.active.is_(True))
        .order_by(PmTemplate.created_at, PmTemplate.id)).all())


def roll_cycles(db: Session, now: datetime) -> tuple[int, int]:
    """Phase A. Close expired windows (freezing missed units), then open today's. Returns
    (cycles opened, missed runs written)."""
    opened = missed = 0
    for template, prop in _templates(db, PmTemplateMode.sweep):
        today = pm_cycles.local_today(prop, now)
        missed += pm_cycles.close_expired(db, template, today)
        if pm_cycles.ensure_open_cycle(db, template, today) is not None:
            opened += 1
    return opened, missed


def occurrences_between(template: PmTemplate, tz: ZoneInfo,
                        window_end: datetime) -> list[datetime]:
    """Occurrences in (last_fired_at, window_end]. dateutil's `between` is exclusive at both
    ends by default, so it is asked for inclusive and the left edge is dropped by hand — the
    occurrence that ended the previous window must not fire twice."""
    if template.last_fired_at is None:
        return []  # stamped at creation (pm_templates.create); a null here is a legacy row
    dtstart = datetime.combine(template.rrule_dtstart, time(0, 0), tzinfo=tz)
    rule = rrulestr(template.rrule, dtstart=dtstart)
    found = rule.between(template.last_fired_at.astimezone(tz), window_end.astimezone(tz),
                         inc=True)
    return [o for o in found if o > template.last_fired_at]


def _create_scheduled_run(db: Session, template: PmTemplate, unit: MaintainableUnit,
                          due_at: datetime) -> PmRun:
    # actor None: the schedule, not a person, raised it. `work_orders.create` tolerates that —
    # reported_by, the created event's user and the audit actor are all nullable.
    wo = wo_domain.create(db, template.property_id, None, CreateWorkOrder(
        title=f"{template.name} — {unit.name}"[:200], type=WorkOrderType.pm,
        priority=Priority.normal, location_type=pm_units.LOCATION_FOR_KIND[unit.kind],
        location_ref=unit.code, department_id=template.department_id, due_at=due_at))
    run = PmRun(property_id=template.property_id, template_id=template.id, unit_id=unit.id,
                work_order_id=wo.id, status=PmRunStatus.pending, due_at=due_at)
    db.add(run)
    db.flush()
    pm_runs.emit(db, run)
    return run


def fire_scheduled(db: Session, now: datetime) -> int:
    """Phase B. Returns the number of runs created."""
    created = 0
    for template, prop in _templates(db, PmTemplateMode.scheduled):
        tz = ZoneInfo(prop.timezone)
        occurrences = occurrences_between(template, tz, now)
        if occurrences:
            units = db.scalars(
                select(MaintainableUnit)
                .join(PmTemplateUnit, PmTemplateUnit.unit_id == MaintainableUnit.id)
                .where(PmTemplateUnit.template_id == template.id,
                       MaintainableUnit.active.is_(True))).all()
            for occurrence in occurrences:
                for unit in units:
                    _create_scheduled_run(db, template, unit, occurrence.astimezone(UTC))
                    created += 1
        template.last_fired_at = now
    db.flush()
    return created


def tick_once(db: Session) -> dict[str, int]:
    now = clock.now()
    opened, missed = roll_cycles(db, now)
    fired = fire_scheduled(db, now)
    return {"opened": opened, "missed": missed, "fired": fired}


@handler("pm.tick")
def pm_tick(db: Session, payload: dict) -> None:
    tick_once(db)
```

(`rrulestr` with an aware `dtstart` yields aware occurrences in the property zone; they are normalised to UTC before hitting `UTCDateTime`, which rejects anything naive.)

- [ ] **Step 3: Wire it in**

`server/app/queue/jobs.py:12`:

```python
RECURRING: dict[str, int] = {"sla.sweep": 30, "snooze.wake": 60, "pm.tick": 300}
```

`server/app/queue/handlers/__init__.py:12`:

```python
MODULES = ("outbound", "mock_delivery", "sla", "snooze", "pms", "pm")
```

`server/seed/seed.py`, the recurring-jobs loop:

```python
        for job_type in ("sla.sweep", "snooze.wake", "pms.tick", "pm.tick"):
            jobs.ensure_recurring(db, job_type)
```

`server/app/domain/work_orders.py`: add `PmRun` to the `from app.models import (...)` list, and in `detail`, replace the final `return WorkOrderDetail(**base, ...)` with:

```python
    pm_run_id = db.scalar(select(PmRun.id).where(PmRun.work_order_id == wo.id))
    return WorkOrderDetail(**base, guest_name=guest_name, room_number=room or wo.location_ref,
                           photos=list_photos(db, wo.id), pm_run_id=pm_run_id,
                           events=[WorkOrderEventOut(
                               id=e.id, user_id=e.user_id,
                               user_name=f"{u.first_name} {u.last_name}" if u else None,
                               type=e.type, from_value=e.from_value, to_value=e.to_value,
                               comment=e.comment, created_at=e.created_at) for e, u in rows])
```

- [ ] **Step 4: Run everything, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .`
Expected: full suite green (`test_queue.py` and `test_seed.py` still pass with the new recurring type).

```bash
git add server/app/queue/handlers/pm.py server/app/queue/jobs.py server/app/queue/handlers/__init__.py server/app/domain/work_orders.py server/seed/seed.py server/tests/test_pm_tick.py
git commit -m "feat(server): pm.tick rolls cycles and expands RRULEs into pm work orders

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 11: Compliance

**Files:**
- Modify: `server/app/domain/pm_reports.py` (append `compliance`)
- Modify: `server/app/api/pm.py` (append one route)
- Modify: `server/tests/test_pm_reports.py` (append)

**Interfaces:**
- Produces: `pm_reports.compliance(db, property_id, ComplianceQuery) -> ComplianceOut`.
- Route: `GET /pm/compliance?from=&to=`, capability `view_property_analytics`.

- [ ] **Step 1: Append the failing tests**

Append to `server/tests/test_pm_reports.py`:

```python


def test_compliance_per_template_cycles_runs_and_inspection_rate(app, fx, login, database):
    from datetime import UTC, datetime

    from app import clock
    from app.queue.handlers.pm import tick_once

    admin = login("admin@hvh.test")
    template_id, units = setup_sweep(admin, fx, codes=("204", "205", "206", "207"))
    eng = login("engineer@hvh.test")
    sup = login("supervisor@hvh.test")
    passed = complete_run(eng, fx, template_id, units["204"])
    sup.post(_pm(fx, f"/runs/{passed}/inspect"), json={"result": "pass"})
    failed = complete_run(eng, fx, template_id, units["205"])
    sup.post(_pm(fx, f"/runs/{failed}/inspect"), json={"result": "fail", "note": "Redo"})
    boiler = admin.post(f"/api/p/{fx.property_a.id}/maintainable-units",
                        json={"kind": "equipment", "code": "B1", "name": "Boiler 1"}).get_json()
    sched = admin.post(_pm(fx, "/templates"), json={
        "name": "Boiler inspection", "mode": "scheduled", "rrule": "FREQ=MONTHLY;INTERVAL=3",
        "rruleDtstart": "2026-07-01", "unitIds": [boiler["id"]],
        "items": [{"label": "Pressure", "itemType": "number"}]}).get_json()["id"]

    clock.freeze(datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    with database.session() as db:
        tick_once(db)  # closes Q3 (3 missed: 205, 206, 207), opens Q4, fires Oct 1 → 1 overdue run

    body = login("manager@hvh.test").get(
        _pm(fx, "/compliance?from=2026-07-01&to=2026-12-31")).get_json()
    by_name = {t["name"]: t for t in body["templates"]}
    rooms = by_name["Guest Room Quarterly"]
    assert rooms["mode"] == "sweep" and rooms["runs"] is None
    q3 = next(c for c in rooms["cycles"] if c["ordinal"] == 3)
    assert (q3["passed"], q3["missed"], q3["total"], q3["onTimePct"]) == (1, 3, 4, 25.0)
    assert rooms["inspectionPassRate"] == 50.0
    boilers = by_name["Boiler inspection"]
    assert boilers["cycles"] == []
    assert boilers["runs"] == {"due": 1, "passed": 0, "failed": 0, "overdue": 1}
    assert boilers["inspectionPassRate"] is None

    assert login("engineer@hvh.test").get(
        _pm(fx, "/compliance?from=2026-07-01&to=2026-12-31")).status_code == 403
    assert login("manager@hvh.test").get(_pm(fx, "/compliance?from=nope&to=2026-12-31")) \
        .status_code == 400
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_pm_reports.py -q -k compliance`
Expected: 404.

- [ ] **Step 2: Append the domain function**

Append to `server/app/domain/pm_reports.py` (and add `from datetime import date, timedelta`, `from app import clock`, `from app.errors import NotFound, ValidationFailed`, and `ComplianceCycleOut, ComplianceOut, ComplianceQuery, ComplianceRunsOut, ComplianceTemplateOut` to the schema import):

```python


def _parse_day(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise ValidationFailed("Dates must be ISO (YYYY-MM-DD)", details={field: "invalid_date"}) \
            from e


def compliance(db: Session, property_id: str, query: ComplianceQuery) -> ComplianceOut:
    """Per template: cycle outcomes for sweeps, due/overdue for schedules, and the inspection
    pass rate over runs inspected in the window (spec §5.5). Percentages are 0–100."""
    prop = db.get(Property, property_id)
    from_day = _parse_day(query.from_, "from")
    to_day = _parse_day(query.to, "to")
    if to_day < from_day:
        raise ValidationFailed("`to` must not precede `from`", details={"to": "before_from"})
    window_start = pm_cycles.local_day_start_utc(prop, from_day)
    window_end = pm_cycles.local_day_start_utc(prop, to_day + timedelta(days=1))
    now = clock.now()

    out: list[ComplianceTemplateOut] = []
    for template in db.scalars(select(PmTemplate).where(PmTemplate.property_id == property_id)
                               .order_by(PmTemplate.name, PmTemplate.id)).all():
        inspected = db.execute(select(PmRun.status).where(
            PmRun.template_id == template.id,
            PmRun.status.in_([PmRunStatus.passed, PmRunStatus.failed]),
            PmRun.inspected_at >= window_start, PmRun.inspected_at < window_end)).all()
        pass_rate = (round(100 * sum(1 for (s,) in inspected if s == PmRunStatus.passed)
                           / len(inspected), 1) if inspected else None)

        if template.mode == PmTemplateMode.sweep:
            cycle_rows = db.scalars(select(PmCycle).where(
                PmCycle.template_id == template.id, PmCycle.starts_on <= to_day,
                PmCycle.ends_on >= from_day).order_by(PmCycle.starts_on)).all()
            cycles_out = []
            for cycle in cycle_rows:
                passed, missed, total = cycle_unit_counts(db, cycle)
                if cycle.status == PmCycleStatus.open:
                    total = len(pm_cycles.scope_unit_ids(db, template))
                    missed = 0
                cycles_out.append(ComplianceCycleOut(
                    ordinal=cycle.ordinal, starts_on=cycle.starts_on, ends_on=cycle.ends_on,
                    status=cycle.status, passed=passed, missed=missed, total=total,
                    on_time_pct=round(100 * passed / total, 1) if total else 0.0))
            out.append(ComplianceTemplateOut(id=template.id, name=template.name,
                                             mode=template.mode, unit_kind=template.unit_kind,
                                             cycles=cycles_out, runs=None,
                                             inspection_pass_rate=pass_rate))
        else:
            runs = db.scalars(select(PmRun).where(
                PmRun.template_id == template.id, PmRun.due_at >= window_start,
                PmRun.due_at < window_end)).all()
            out.append(ComplianceTemplateOut(
                id=template.id, name=template.name, mode=template.mode, unit_kind=None,
                cycles=[],
                runs=ComplianceRunsOut(
                    due=len(runs),
                    passed=sum(1 for r in runs if r.status == PmRunStatus.passed),
                    failed=sum(1 for r in runs if r.status == PmRunStatus.failed),
                    overdue=sum(1 for r in runs if r.due_at < now and r.status in (
                        PmRunStatus.pending, PmRunStatus.in_progress))),
                inspection_pass_rate=pass_rate))
    return ComplianceOut(templates=out)
```

- [ ] **Step 3: Append the route**

In `server/app/api/pm.py`, add `ComplianceQuery` to the schema import and append:

```python
@bp.get("/compliance")
@require_auth
@require_property
@require_capability("view_property_analytics")
def compliance(property_id: str):
    query = parse_query(ComplianceQuery)
    with db_session() as db:
        return ok(pm_reports.compliance(db, g.property_id, query))
```

- [ ] **Step 4: Run, lint, commit**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .`

```bash
git add server/app/domain/pm_reports.py server/app/api/pm.py server/tests/test_pm_reports.py
git commit -m "feat(server): PM compliance report

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 12: Sample data — seed, sample CSV, fixture database

**Files:**
- Create: `server/seed/pm_units.py`
- Create: `server/seed/write_sample_csv.py`
- Create: `fixtures/maintainable_units.sample.csv` (generated)
- Modify: `server/seed/seed.py` (imports, `SeedSummary`, a new section before `# ---- recurring jobs`, the summary)
- Modify: `server/tests/test_seed.py`
- Create: `server/tests/test_pm_sample_csv.py`
- Modify: `server/data/app.db` (reseeded)

**Interfaces:**
- Produces: `seed.pm_units.unit_rows() -> list[dict]` (keys `code, kind, name, floor, room_type, external_id`), `seed.write_sample_csv.render() -> str`.
- Consumes: Tasks 1, 5 (`pm_cycles.window_for`, `local_today`, `local_day_start_utc`).

- [ ] **Step 1: The shared unit rows**

Create `server/seed/pm_units.py`:

```python
"""The maintainable-unit rows the seeder inserts and the sample CSV carries (PM spec §9).

One source, two outputs, so they can never disagree: `seed.seed` inserts these rows, and
`seed.write_sample_csv` writes them in the import format for practising the load. The guest
rooms are exactly the stay grid the seeder already generates (floors 1–6 × 01–20), so every
seeded stay's room_number resolves to a unit.
"""
from __future__ import annotations

# PMS room-type codes for seed.data.ROOM_TYPES, in that order.
ROOM_TYPE_CODES = {
    "King": "KNGN",
    "Queen": "KWHN",
    "Double Queen": "TQNN",
    "Suite": "KSTE",
    "Accessible King": "KACC",
}

COMMON_AREAS: list[tuple[str, str, int | None]] = [
    ("LOBBY", "Lobby", 1),
    ("POOL", "Pool", 1),
    ("FITNESS", "Fitness Room", 2),
    ("LAUNDRY", "Guest Laundry", 2),
    ("BOILER-RM", "Boiler Room", 0),
    ("ELEV-A", "Elevator A", None),
    ("ELEV-B", "Elevator B", None),
    ("STAIR-N", "Stairwell North", None),
    ("STAIR-S", "Stairwell South", None),
    ("DOCK", "Loading Dock", 0),
]

EQUIPMENT: list[tuple[str, str]] = [
    ("POOL-PUMP-1", "Pool pump 1"),
    ("BOILER-1", "Boiler 1"),
    ("BOILER-2", "Boiler 2"),
    ("ICE-2F", "Ice machine 2F"),
    ("ICE-4F", "Ice machine 4F"),
    ("ELEV-MOTOR-A", "Elevator motor A"),
    ("ELEV-MOTOR-B", "Elevator motor B"),
    ("RTU-1", "Rooftop HVAC unit 1"),
]


def _room_type(floor: int, n: int) -> str:
    """Deterministic and plausible: accessible kings by the lifts on 1, corner suites on 6,
    the rest rotating through king / queen / double queen."""
    if floor == 1 and n <= 4:
        return ROOM_TYPE_CODES["Accessible King"]
    if floor == 6 and n in (1, 20):
        return ROOM_TYPE_CODES["Suite"]
    return (ROOM_TYPE_CODES["King"], ROOM_TYPE_CODES["Queen"],
            ROOM_TYPE_CODES["Double Queen"])[n % 3]


def unit_rows() -> list[dict]:
    rows: list[dict] = []
    for floor in range(1, 7):
        for n in range(1, 21):
            code = f"{floor}{n:02d}"
            rows.append({"code": code, "kind": "guest_room", "name": f"Room {code}",
                         "floor": floor, "room_type": _room_type(floor, n), "external_id": None})
    for code, name, floor in COMMON_AREAS:
        rows.append({"code": code, "kind": "common_area", "name": name, "floor": floor,
                     "room_type": None, "external_id": None})
    for code, name in EQUIPMENT:
        rows.append({"code": code, "kind": "equipment", "name": name, "floor": None,
                     "room_type": None, "external_id": None})
    return rows
```

- [ ] **Step 2: The CSV writer and its drift test**

Create `server/seed/write_sample_csv.py`:

```python
"""Writes fixtures/maintainable_units.sample.csv from seed.pm_units.unit_rows().

`python -m seed.write_sample_csv` from server/. tests/test_pm_sample_csv.py fails when the
committed file is stale, the same guard web/src/api/schema.json has.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from seed.pm_units import unit_rows

COLUMNS = ("code", "kind", "name", "floor", "room_type", "external_id")
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "fixtures" / "maintainable_units.sample.csv"


def render() -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in unit_rows():
        writer.writerow({k: "" if row[k] is None else row[k] for k in COLUMNS})
    return buf.getvalue()


def main(out: str | None = None) -> None:
    path = Path(out or DEFAULT_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
```

Create `server/tests/test_pm_sample_csv.py`:

```python
"""fixtures/maintainable_units.sample.csv is generated; it must match its source and import
cleanly (PM spec §9, §12 #1)."""
from pathlib import Path

from app.domain import pm_units
from seed.pm_units import unit_rows
from seed.write_sample_csv import DEFAULT_OUT, render


def test_unit_rows_are_the_stay_grid_plus_areas_and_equipment():
    rows = unit_rows()
    assert len(rows) == 138
    codes = [r["code"] for r in rows if r["kind"] == "guest_room"]
    assert codes[0] == "101" and codes[-1] == "620" and len(codes) == 120
    assert len(set(r["code"] for r in rows)) == 138, "codes are unique"


def test_committed_sample_csv_is_current():
    path = Path(DEFAULT_OUT)
    assert path.exists(), "run: python -m seed.write_sample_csv"
    assert path.read_text(encoding="utf-8") == render(), (
        "fixtures/maintainable_units.sample.csv is stale — re-run python -m seed.write_sample_csv")


def test_sample_csv_imports_cleanly_and_idempotently(database, fx):
    text = Path(DEFAULT_OUT).read_text(encoding="utf-8")
    with database.session() as db:
        first = pm_units.import_csv(db, fx.property_a.id, fx.admin_a.id, text)
        assert (first.created, first.updated, first.errors) == (138, 0, [])
        second = pm_units.import_csv(db, fx.property_a.id, fx.admin_a.id, text)
        assert (second.created, second.updated) == (0, 138)
```

Run: `cd server && ../.venv/Scripts/python.exe -m seed.write_sample_csv && ../.venv/Scripts/python.exe -m pytest tests/test_pm_sample_csv.py -q`
Expected: `wrote …/fixtures/maintainable_units.sample.csv`, then 3 passed. Open the file: 139 lines, first `code,kind,name,floor,room_type,external_id`, second `101,guest_room,Room 101,1,KACC,`.

- [ ] **Step 3: Extend the seeder**

In `server/seed/seed.py`:

Add to the `from app.models import (...)` list: `MaintainableUnit, PmCycle, PmRun, PmRunAnswer, PmRunPhoto, PmTemplate, PmTemplateItem, PmTemplateUnit`. Add to the `from app.schemas.enums import (...)` list: `LocationType, PmCadence, PmCycleStatus, PmItemType, PmRunStatus, PmTemplateMode, PmUnitKind, PmUnitSource`. Add the imports `import base64` (top) and, next to `from seed import data`: `from seed.pm_units import unit_rows` and `from app.domain import pm_cycles`.

Extend `SeedSummary`:

```python
@dataclass
class SeedSummary:
    properties: int
    users: int
    guests: int
    stays: int
    conversations: int
    messages: int
    work_orders: int
    log_entries: int
    maintainable_units: int
    pm_templates: int
    pm_runs: int
```

Add a module-level constant after `PASSWORD`:

```python
# A 1×1 transparent PNG: enough for a seeded run's required photo item to hold a real image
# the checklist page can render, without shipping picture files in the seed.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
```

Insert this section immediately before `# ---- recurring jobs` (it uses `now`, `today`, `rng`, `hvh`, `depts`, `staff`, `eng_staff`, all already defined above it):

```python
        # ---- preventative maintenance (PM spec §9): the inventory, two sweep templates, one
        # scheduled template, and enough runs that every PM screen has something to show.
        units: dict[str, MaintainableUnit] = {}
        for row in unit_rows():
            u = MaintainableUnit(property_id=hvh.id, kind=PmUnitKind(row["kind"]),
                                 code=row["code"], name=row["name"], floor=row["floor"],
                                 room_type=row["room_type"], external_id=row["external_id"],
                                 source=PmUnitSource.manual)
            db.add(u)
            units[u.code] = u
        db.flush()

        def pm_template(name, mode, *, unit_kind=None, cadence=None, rrule=None, dtstart=None,
                        items=(), targets=()):
            t = PmTemplate(property_id=hvh.id, name=name, mode=mode,
                           department_id=depts["engineering"].id, unit_kind=unit_kind,
                           cadence=cadence, rrule=rrule, rrule_dtstart=dtstart,
                           last_fired_at=now if mode == PmTemplateMode.scheduled else None)
            db.add(t)
            db.flush()
            for position, (label, item_type, unit, lo, hi, required) in enumerate(items):
                db.add(PmTemplateItem(template_id=t.id, property_id=hvh.id, position=position,
                                      label=label, item_type=item_type, unit=unit,
                                      min_value=lo, max_value=hi, required=required))
            for code in targets:
                db.add(PmTemplateUnit(template_id=t.id, unit_id=units[code].id,
                                      property_id=hvh.id))
            db.flush()
            return t

        CB, NUM, TXT, PHOTO = (PmItemType.checkbox, PmItemType.number, PmItemType.text,
                               PmItemType.photo)
        rooms_t = pm_template(
            "Guest Room Quarterly", PmTemplateMode.sweep, unit_kind=PmUnitKind.guest_room,
            cadence=PmCadence.quarterly, items=[
                ("HVAC filter replaced", CB, None, None, None, True),
                ("Tap hot-water temperature", NUM, "°F", 100, 120, True),
                ("GFCI outlets tested", CB, None, None, None, True),
                ("Caulk and grout condition", TXT, None, None, None, False),
                ("Bathroom exhaust fan photo", PHOTO, None, None, None, True),
                ("Smoke detector tested", CB, None, None, None, True),
            ])
        areas_t = pm_template(
            "Common Areas Monthly", PmTemplateMode.sweep, unit_kind=PmUnitKind.common_area,
            cadence=PmCadence.monthly, items=[
                ("Lighting fully working", CB, None, None, None, True),
                ("Floor surfaces safe and clean", CB, None, None, None, True),
                ("Notes", TXT, None, None, None, False),
            ])
        local_today = pm_cycles.local_today(hvh, now)
        q_start, q_end, q_ord = pm_cycles.window_for(PmCadence.quarterly, local_today)
        boilers_t = pm_template(
            "Boiler inspection", PmTemplateMode.scheduled, rrule="FREQ=MONTHLY;INTERVAL=3",
            dtstart=q_start, targets=("BOILER-1", "BOILER-2"), items=[
                ("Operating pressure", NUM, "psi", 10, 30, True),
                ("Relief valve tested", CB, None, None, None, True),
                ("Burner flame photo", PHOTO, None, None, None, True),
                ("Notes", TXT, None, None, None, False),
            ])

        # Cycles: this quarter open, last quarter closed; this month open for common areas.
        p_start, p_end, p_ord = pm_cycles.window_for(PmCadence.quarterly,
                                                     q_start - timedelta(days=1))
        current_cycle = PmCycle(property_id=hvh.id, template_id=rooms_t.id, ordinal=q_ord,
                                starts_on=q_start, ends_on=q_end, status=PmCycleStatus.open)
        previous_cycle = PmCycle(property_id=hvh.id, template_id=rooms_t.id, ordinal=p_ord,
                                 starts_on=p_start, ends_on=p_end, status=PmCycleStatus.closed)
        m_start, m_end, m_ord = pm_cycles.window_for(PmCadence.monthly, local_today)
        db.add_all([current_cycle, previous_cycle,
                    PmCycle(property_id=hvh.id, template_id=areas_t.id, ordinal=m_ord,
                            starts_on=m_start, ends_on=m_end, status=PmCycleStatus.open)])
        db.flush()

        room_items = db.scalars(select(PmTemplateItem)
                                .where(PmTemplateItem.template_id == rooms_t.id)
                                .order_by(PmTemplateItem.position)).all()
        sam = staff["sam"]

        def seed_room_run(code, cycle, status, at, *, by=None, inspector=None, note=None):
            """A run with plausible answers. `at` is an aware UTC start time inside the cycle."""
            done = status in (PmRunStatus.completed, PmRunStatus.passed, PmRunStatus.failed)
            run = PmRun(property_id=hvh.id, template_id=rooms_t.id, unit_id=units[code].id,
                        cycle_id=cycle.id, status=status,
                        started_by_user_id=by.id if by else None, started_at=at if by else None,
                        completed_at=at + timedelta(minutes=35) if done else None,
                        inspected_by_user_id=inspector.id if inspector else None,
                        inspected_at=at + timedelta(hours=3) if inspector else None,
                        inspection_note=note, created_at=at, updated_at=at)
            db.add(run)
            db.flush()
            if status == PmRunStatus.missed:
                return run
            for item in room_items:
                a = PmRunAnswer(run_id=run.id, property_id=hvh.id, item_id=item.id)
                if done or rng.random() < 0.5:  # an in-progress run is part-way through
                    if item.item_type == PmItemType.checkbox:
                        a.bool_value = True
                    elif item.item_type == PmItemType.number:
                        a.number_value = float(rng.randint(104, 118))
                    elif item.item_type == PmItemType.text:
                        a.text_value = rng.choice(["Good", "Minor wear, monitored",
                                                   "Resealed tub edge"])
                    elif item.item_type == PmItemType.photo:
                        db.add(PmRunPhoto(run_id=run.id, property_id=hvh.id, item_id=item.id,
                                          uploaded_by_user_id=run.started_by_user_id,
                                          content_type="image/png", byte_size=len(TINY_PNG),
                                          data=TINY_PNG))
                    a.answered_at = at + timedelta(minutes=rng.randint(1, 30))
                db.add(a)
            db.flush()
            return run

        def within(cycle_start, cycle_end):
            """A start time on a random day of the window, never after `now`."""
            last = min(cycle_end, local_today)
            day = cycle_start + timedelta(days=rng.randint(0, max((last - cycle_start).days, 0)))
            at = pm_cycles.local_day_start_utc(hvh, day) + timedelta(hours=rng.randint(8, 16))
            return min(at, now - timedelta(minutes=45))

        room_codes = [c for c, u in units.items() if u.kind == PmUnitKind.guest_room]
        rng.shuffle(room_codes)
        # This quarter: 40 passed, 3 in progress, 4 awaiting inspection, 2 failed (= 49 runs).
        for code in room_codes[:40]:
            seed_room_run(code, current_cycle, PmRunStatus.passed, within(q_start, q_end),
                          by=rng.choice(eng_staff), inspector=sam)
        for code in room_codes[40:43]:
            seed_room_run(code, current_cycle, PmRunStatus.in_progress,
                          now - timedelta(minutes=rng.randint(5, 40)), by=rng.choice(eng_staff))
        for code in room_codes[43:47]:
            seed_room_run(code, current_cycle, PmRunStatus.completed, within(q_start, q_end),
                          by=rng.choice(eng_staff))
        for code, note in zip(room_codes[47:49], ("Fan grille still dusty in the photo.",
                                                  "Smoke detector ticked but not test-pressed.")):
            seed_room_run(code, current_cycle, PmRunStatus.failed, within(q_start, q_end),
                          by=rng.choice(eng_staff), inspector=sam, note=note)
        # Last quarter, frozen: 110 passed, 10 missed.
        rng.shuffle(room_codes)
        for code in room_codes[:110]:
            seed_room_run(code, previous_cycle, PmRunStatus.passed, within(p_start, p_end),
                          by=rng.choice(eng_staff), inspector=sam)
        for code in room_codes[110:]:
            seed_room_run(code, previous_cycle, PmRunStatus.missed,
                          pm_cycles.local_day_start_utc(hvh, p_end + timedelta(days=1)))

        # The boiler schedule's occurrence at the start of this quarter: one pm work order and
        # one pending run per boiler, exactly what pm.tick would have written. last_fired_at is
        # `now`, so the tick will not write them again.
        due = pm_cycles.local_day_start_utc(hvh, q_start)
        for code in ("BOILER-1", "BOILER-2"):
            unit = units[code]
            wo = WorkOrder(property_id=hvh.id, title=f"Boiler inspection — {unit.name}",
                           type=WorkOrderType.pm, priority=Priority.normal,
                           status=WorkOrderStatus.open, location_type=LocationType.equipment,
                           location_ref=unit.code, department_id=depts["engineering"].id,
                           due_at=due, created_at=due, updated_at=due)
            db.add(wo)
            db.flush()
            db.add(WorkOrderEvent(work_order_id=wo.id, property_id=hvh.id, user_id=None,
                                  type=WorkOrderEventType.created, to_value="open",
                                  created_at=due))
            db.add(PmRun(property_id=hvh.id, template_id=boilers_t.id, unit_id=unit.id,
                         work_order_id=wo.id, status=PmRunStatus.pending, due_at=due,
                         created_at=due, updated_at=due))
        db.flush()
```

Extend the summary construction:

```python
            log_entries=db.scalar(select(func.count()).select_from(LogEntry)),
            maintainable_units=db.scalar(select(func.count()).select_from(MaintainableUnit)),
            pm_templates=db.scalar(select(func.count()).select_from(PmTemplate)),
            pm_runs=db.scalar(select(func.count()).select_from(PmRun)),
        )
```

- [ ] **Step 4: Extend the seed tests**

In `server/tests/test_seed.py`, add `MaintainableUnit, PmRun, PmTemplate` to the models import and `PmRunStatus` to the enums import. In `test_seed_matches_spec_counts`, the active-work-order assertion changes — two seeded scheduled-PM work orders are open:

```python
        assert count(WorkOrder, WorkOrder.property_id == hvh.id,
                     WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.assigned,
                                           WorkOrderStatus.in_progress,
                                           WorkOrderStatus.blocked,
                                           WorkOrderStatus.complete])) == 17  # 15 + 2 boiler PMs
```

and add after the log-entry assertions:

```python
        # PM spec §9: 120 rooms + 10 areas + 8 equipment; 49 this quarter, 120 last, 2 boilers.
        assert count(MaintainableUnit, MaintainableUnit.property_id == hvh.id) == 138
        assert count(PmTemplate, PmTemplate.property_id == hvh.id) == 3
        by_status = {s: count(PmRun, PmRun.status == s) for s in PmRunStatus}
        assert by_status == {PmRunStatus.pending: 2, PmRunStatus.in_progress: 3,
                             PmRunStatus.completed: 4, PmRunStatus.passed: 150,
                             PmRunStatus.failed: 2, PmRunStatus.missed: 10}
        assert summary.maintainable_units == 138
        assert summary.pm_templates == 3
        assert summary.pm_runs == count(PmRun)
```

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py tests/test_dev_start.py -q`
Expected: pass.

- [ ] **Step 5: Reseed the fixture database and commit**

The tracked `server/data/app.db` is fixture data; CLAUDE.md says to commit it when the seed genuinely changes, which this does.

Run:
```
cd server && DATABASE_URL="sqlite:///data/app.db" ../.venv/Scripts/python.exe -m seed.seed
```
Expected: prints a `SeedSummary(... maintainable_units=138, pm_templates=3, pm_runs=171)`.

Run the whole backend suite and lint once more:
```
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
```

```bash
git add server/seed/pm_units.py server/seed/write_sample_csv.py server/seed/seed.py fixtures/maintainable_units.sample.csv server/tests/test_seed.py server/tests/test_pm_sample_csv.py server/data/app.db
git commit -m "feat(server): seed the PM inventory, templates and runs; sample units CSV

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 13: Web hooks, query keys and realtime invalidation

**Files:**
- Modify: `web/src/api/queryKeys.ts`
- Modify: `web/src/api/ws.ts:41-105` (two cases)
- Modify: `web/src/api/ws.test.tsx` (append two tests)
- Create: `web/src/api/hooks/pm.ts`

**Interfaces:**
- Produces every hook the pages use: `useUnits`, `useCreateUnit`, `usePatchUnit`, `useImportUnits`, `importReport`, `usePmTemplates`, `useCreatePmTemplate`, `usePatchPmTemplate`, `useSweep`, `usePmCycles`, `usePmRun`, `useStartRun`, `useBeginRun`, `useSaveAnswer`, `useUploadRunPhoto`, `useCompleteRun`, `useInspectRun`, `useInspections`, `useCompliance`. Signatures are in the code below and are what Tasks 14–20 call.

- [ ] **Step 1: Write the failing realtime tests**

Append inside `describe('invalidationsFor', …)` in `web/src/api/ws.test.tsx`:

```ts
  it('refreshes the sweep, the inspection queue and the run for pm.run.changed', () => {
    const keys = invalidationsFor(
      {
        ...base,
        type: 'pm.run.changed',
        payload: { id: 'run-1', unitId: 'u-1', cycleId: 'cy-1', status: 'completed' },
      },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.pmSweepAll('prop-a'))
    expect(keys).toContainEqual(qk.pmInspectionsAll('prop-a'))
    expect(keys).toContainEqual(qk.pmRun('prop-a', 'run-1'))
  })

  it('refreshes the sweep and the cycle history for pm.cycle.rolled', () => {
    const keys = invalidationsFor(
      { ...base, type: 'pm.cycle.rolled', payload: { templateId: 't-1' } },
      'prop-a',
    )
    expect(keys).toContainEqual(qk.pmSweepAll('prop-a'))
    expect(keys).toContainEqual(qk.pmCyclesAll('prop-a'))
  })
```

Run: `cd web && npx vitest run src/api/ws.test.tsx`
Expected: type errors on `qk.pmSweepAll`.

- [ ] **Step 2: Query keys**

Append to the `qk` object in `web/src/api/queryKeys.ts`, before `analyticsOverview`. Every PM key starts `['pm', propertyId, …]` so one prefix reaches all of them:

```ts
  pmAll: (propertyId: string) => ['pm', propertyId] as const,
  pmUnits: (propertyId: string, params: Record<string, string | boolean | null>) =>
    ['pm', propertyId, 'units', params] as const,
  pmUnitsAll: (propertyId: string) => ['pm', propertyId, 'units'] as const,
  pmTemplates: (propertyId: string) => ['pm', propertyId, 'templates'] as const,
  pmSweep: (propertyId: string, params: Record<string, string | null>) =>
    ['pm', propertyId, 'sweep', params] as const,
  pmSweepAll: (propertyId: string) => ['pm', propertyId, 'sweep'] as const,
  pmCycles: (propertyId: string, templateId: string) =>
    ['pm', propertyId, 'cycles', templateId] as const,
  pmCyclesAll: (propertyId: string) => ['pm', propertyId, 'cycles'] as const,
  pmRun: (propertyId: string, id: string) => ['pm', propertyId, 'run', id] as const,
  pmInspections: (propertyId: string, params: Record<string, string | null>) =>
    ['pm', propertyId, 'inspections', params] as const,
  pmInspectionsAll: (propertyId: string) => ['pm', propertyId, 'inspections'] as const,
  pmCompliance: (propertyId: string, from: string, to: string) =>
    ['pm', propertyId, 'compliance', from, to] as const,
```

- [ ] **Step 3: Realtime cases**

In `web/src/api/ws.ts` `invalidationsFor`, before `default:`:

```ts
    case 'pm.run.changed':
      keys.push([...qk.pmSweepAll(propertyId)])
      keys.push([...qk.pmInspectionsAll(propertyId)])
      if (id) keys.push([...qk.pmRun(propertyId, id)])
      break
    case 'pm.cycle.rolled':
      keys.push([...qk.pmSweepAll(propertyId)])
      keys.push([...qk.pmCyclesAll(propertyId)])
      break
```

- [ ] **Step 4: The hooks**

Create `web/src/api/hooks/pm.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AnswerPatch,
  ComplianceOut,
  CycleOut,
  InspectRequest,
  InspectionRowOut,
  PmUnitKind,
  RunOut,
  StartRunRequest,
  SweepOut,
  TemplateIn,
  TemplateOut,
  TemplatePatch,
  UnitImportOut,
  UnitIn,
  UnitOut,
  UnitPatch,
} from '../types'

function qs(params: Record<string, string | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ---- inventory --------------------------------------------------------------------------

export type UnitParams = { kind?: PmUnitKind | null; active?: boolean | null; q?: string | null }

export function useUnits(params: UnitParams = {}) {
  const { propertyId } = useSession()
  const normalised = {
    kind: params.kind ?? null,
    active: params.active ?? null,
    q: params.q ?? null,
  }
  return useQuery<UnitOut[], ApiError>({
    queryKey: qk.pmUnits(propertyId, normalised),
    queryFn: () => api<UnitOut[]>(propertyPath(propertyId, `maintainable-units${qs(normalised)}`)),
  })
}

export function useCreateUnit() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitOut, ApiError, UnitIn>({
    mutationFn: (body) =>
      api<UnitOut>(propertyPath(propertyId, 'maintainable-units'), { method: 'POST', json: body }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

export function usePatchUnit() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitOut, ApiError, UnitPatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<UnitOut>(propertyPath(propertyId, `maintainable-units/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

export function useImportUnits() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<UnitImportOut, ApiError, File>({
    mutationFn: (file) => {
      const form = new FormData()
      form.set('file', file)
      return api<UnitImportOut>(propertyPath(propertyId, 'maintainable-units/import'), {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.pmUnitsAll(propertyId) })
      void client.invalidateQueries({ queryKey: qk.pmSweepAll(propertyId) })
    },
  })
}

/** A rejected import is a 422 IMPORT_REJECTED whose `details` is the whole report. */
export function importReport(error: ApiError | null | undefined): UnitImportOut | null {
  if (!error || error.code !== 'IMPORT_REJECTED') return null
  return error.details as UnitImportOut
}

// ---- templates ---------------------------------------------------------------------------

export function usePmTemplates() {
  const { propertyId } = useSession()
  return useQuery<TemplateOut[], ApiError>({
    queryKey: qk.pmTemplates(propertyId),
    queryFn: () => api<TemplateOut[]>(propertyPath(propertyId, 'pm/templates')),
  })
}

export function useCreatePmTemplate() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TemplateOut, ApiError, TemplateIn>({
    mutationFn: (body) =>
      api<TemplateOut>(propertyPath(propertyId, 'pm/templates'), { method: 'POST', json: body }),
    // Creating a sweep template opens its cycle, so the sweep page is stale too.
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.pmAll(propertyId) }),
  })
}

export function usePatchPmTemplate() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<TemplateOut, ApiError, TemplatePatch & { id: string }>({
    mutationFn: ({ id, ...patch }) =>
      api<TemplateOut>(propertyPath(propertyId, `pm/templates/${id}`), {
        method: 'PATCH',
        json: patch,
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: qk.pmAll(propertyId) }),
  })
}

// ---- sweep, cycles ----------------------------------------------------------------------

export type SweepParams = {
  kind: PmUnitKind
  status?: 'remaining' | 'completed' | null
  q?: string | null
  sort?: string | null
}

export function useSweep(params: SweepParams) {
  const { propertyId } = useSession()
  const normalised = {
    kind: params.kind,
    status: params.status ?? null,
    q: params.q ?? null,
    sort: params.sort ?? null,
  }
  return useQuery<SweepOut, ApiError>({
    queryKey: qk.pmSweep(propertyId, normalised),
    queryFn: () => api<SweepOut>(propertyPath(propertyId, `pm/sweep${qs(normalised)}`)),
  })
}

export function usePmCycles(templateId: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<CycleOut[], ApiError>({
    queryKey: qk.pmCycles(propertyId, templateId ?? ''),
    queryFn: () => api<CycleOut[]>(propertyPath(propertyId, `pm/cycles?templateId=${templateId}`)),
    enabled: Boolean(templateId),
  })
}

// ---- runs --------------------------------------------------------------------------------

export function usePmRun(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<RunOut, ApiError>({
    queryKey: qk.pmRun(propertyId, id ?? ''),
    queryFn: () => api<RunOut>(propertyPath(propertyId, `pm/runs/${id}`)),
    enabled: Boolean(id),
  })
}

/** Every run mutation answers with the whole RunOut; caching it here means the checklist
 *  never renders a stale `missingRequired` between the save and a refetch. */
function useRunMutation<TVars>(
  request: (propertyId: string, vars: TVars) => Promise<RunOut>,
  // `qk.*` return readonly tuples, so the element type must be readonly too.
  alsoInvalidate: (propertyId: string) => readonly (readonly unknown[])[] = () => [],
) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<RunOut, ApiError, TVars>({
    mutationFn: (vars) => request(propertyId, vars),
    onSuccess: (run) => {
      client.setQueryData(qk.pmRun(propertyId, run.id), run)
      for (const key of alsoInvalidate(propertyId)) void client.invalidateQueries({ queryKey: key })
    },
  })
}

export const useStartRun = () =>
  useRunMutation<StartRunRequest>(
    (propertyId, body) =>
      api<RunOut>(propertyPath(propertyId, 'pm/runs'), { method: 'POST', json: body }),
    (propertyId) => [qk.pmSweepAll(propertyId)],
  )

export const useBeginRun = () =>
  useRunMutation<string>(
    (propertyId, runId) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/start`), { method: 'POST' }),
    (propertyId) => [qk.workOrdersAll(propertyId)],
  )

export const useSaveAnswer = () =>
  useRunMutation<{ runId: string; answerId: string; patch: AnswerPatch }>(
    (propertyId, { runId, answerId, patch }) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/answers/${answerId}`), {
        method: 'PATCH',
        json: patch,
      }),
  )

export const useUploadRunPhoto = () =>
  useRunMutation<{ runId: string; file: File; itemId?: string | null }>(
    (propertyId, { runId, file, itemId }) => {
      const form = new FormData()
      form.set('photo', file)
      if (itemId) form.set('itemId', itemId)
      return api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/photos`), {
        method: 'POST',
        body: form,
      })
    },
  )

export const useCompleteRun = () =>
  useRunMutation<string>(
    (propertyId, runId) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/complete`), { method: 'POST' }),
    (propertyId) => [
      qk.pmSweepAll(propertyId),
      qk.pmInspectionsAll(propertyId),
      qk.workOrdersAll(propertyId),
    ],
  )

export const useInspectRun = () =>
  useRunMutation<{ runId: string; body: InspectRequest }>(
    (propertyId, { runId, body }) =>
      api<RunOut>(propertyPath(propertyId, `pm/runs/${runId}/inspect`), {
        method: 'POST',
        json: body,
      }),
    (propertyId) => [
      qk.pmSweepAll(propertyId),
      qk.pmInspectionsAll(propertyId),
      qk.pmCyclesAll(propertyId),
      qk.workOrdersAll(propertyId),
    ],
  )

// ---- inspection queue, compliance --------------------------------------------------------

export type InspectionParams = {
  kind?: PmUnitKind | null
  status: 'available' | 'inspected'
  sort?: 'days_since_last_pm' | 'completed_at' | null
}

export function useInspections(params: InspectionParams) {
  const { propertyId } = useSession()
  const normalised = { kind: params.kind ?? null, status: params.status, sort: params.sort ?? null }
  return useQuery<InspectionRowOut[], ApiError>({
    queryKey: qk.pmInspections(propertyId, normalised),
    queryFn: () =>
      api<InspectionRowOut[]>(propertyPath(propertyId, `pm/inspections${qs(normalised)}`)),
  })
}

export function useCompliance(from: string, to: string) {
  const { propertyId } = useSession()
  return useQuery<ComplianceOut, ApiError>({
    queryKey: qk.pmCompliance(propertyId, from, to),
    queryFn: () =>
      api<ComplianceOut>(propertyPath(propertyId, `pm/compliance?from=${from}&to=${to}`)),
    enabled: Boolean(from && to),
  })
}
```

- [ ] **Step 5: Verify and commit**

Run: `cd web && npx vitest run src/api && npm run lint && npx tsc -b`
Expected: pass, clean.

```bash
git add web/src/api/queryKeys.ts web/src/api/ws.ts web/src/api/ws.test.tsx web/src/api/hooks/pm.ts
git commit -m "feat(web): PM query hooks, keys and realtime invalidation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 14: Sweep page

**Files:**
- Create: `web/src/features/pm/labels.ts`, `web/src/features/pm/labels.test.ts`
- Create: `web/src/features/pm/KindTabs.tsx`
- Create: `web/src/features/pm/SweepPage.tsx`, `web/src/features/pm/SweepPage.test.tsx`
- Modify: `web/src/routes.tsx` (route `pm`)

**Interfaces:**
- Produces: `KIND_LABELS`, `KINDS`, `CADENCE_LABELS`, `ITEM_TYPE_LABELS`, `RUN_STATUS_LABELS`, `isKind(value)`, `ordinal(n)`, `formatDay(iso)`, `formatWindow(a, b)`; `<KindTabs value onChange allowAll?>`.
- Consumes: `useSweep`, `useStartRun` (Task 13).

- [ ] **Step 1: Labels and their test**

Create `web/src/features/pm/labels.ts`:

```ts
import type { PmCadence, PmItemType, PmRunStatus, PmUnitKind } from '../../api/types'

export const KINDS: PmUnitKind[] = ['guest_room', 'common_area', 'equipment']

export const KIND_LABELS: Record<PmUnitKind, string> = {
  guest_room: 'Guest Rooms',
  common_area: 'Common & BOH Areas',
  equipment: 'Equipment',
}

export const CADENCE_LABELS: Record<PmCadence, string> = {
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  semiannual: 'Semiannual',
  annual: 'Annual',
}

export const ITEM_TYPE_LABELS: Record<PmItemType, string> = {
  checkbox: 'Checkbox',
  text: 'Text',
  number: 'Number',
  photo: 'Photo',
}

export const RUN_STATUS_LABELS: Record<PmRunStatus, string> = {
  pending: 'Pending',
  in_progress: 'In progress',
  completed: 'Awaiting inspection',
  passed: 'Passed',
  failed: 'Failed',
  missed: 'Missed',
}

export function isKind(value: string | null | undefined): value is PmUnitKind {
  return KINDS.includes(value as PmUnitKind)
}

const SUFFIX: Record<number, string> = { 1: 'st', 2: 'nd', 3: 'rd' }

/** 1 → 1st, 2 → 2nd, 3 → 3rd, 4 → 4th, 11 → 11th, 12 → 12th, 13 → 13th. */
export function ordinal(n: number): string {
  const mod100 = n % 100
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`
  return `${n}${SUFFIX[n % 10] ?? 'th'}`
}

/** "2026-07-01" → "Jul 01". Parsed as calendar parts, so the viewer's timezone can never shift
 *  a property-local cycle boundary onto the previous day. */
export function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year!, month! - 1, day!).toLocaleDateString('en-US', {
    month: 'short',
    day: '2-digit',
  })
}

export function formatWindow(startsOn: string, endsOn: string): string {
  return `${formatDay(startsOn)} – ${formatDay(endsOn)}`
}
```

Create `web/src/features/pm/labels.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { formatWindow, isKind, ordinal } from './labels'

describe('pm labels', () => {
  it('ordinal handles the teens', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 23].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '23rd',
    ])
  })

  it('formats a cycle window from calendar parts, not instants', () => {
    expect(formatWindow('2026-07-01', '2026-09-30')).toBe('Jul 01 – Sep 30')
  })

  it('isKind narrows', () => {
    expect(isKind('guest_room')).toBe(true)
    expect(isKind('all')).toBe(false)
    expect(isKind(null)).toBe(false)
  })
})
```

- [ ] **Step 2: Kind tabs**

Create `web/src/features/pm/KindTabs.tsx`:

```tsx
import type { PmUnitKind } from '../../api/types'
import { cn } from '../../lib/cn'
import { KINDS, KIND_LABELS } from './labels'

export type KindTab = PmUnitKind | 'all'

export function KindTabs({
  value,
  onChange,
  allowAll,
}: {
  value: KindTab
  onChange: (kind: KindTab) => void
  allowAll?: boolean
}) {
  const options: KindTab[] = allowAll ? ['all', ...KINDS] : KINDS
  return (
    <div role="tablist" className="flex flex-wrap gap-1.5 border-b border-border px-4">
      {options.map((kind) => (
        <button
          key={kind}
          type="button"
          role="tab"
          aria-selected={value === kind}
          onClick={() => onChange(kind)}
          className={cn(
            'inline-flex h-11 items-center px-3.5 text-[13.5px] font-semibold md:h-9',
            value === kind ? 'border-b-2 border-accent text-text' : 'text-text3 hover:text-text',
          )}
        >
          {kind === 'all' ? 'All' : KIND_LABELS[kind]}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Write the failing page test**

Create `web/src/features/pm/SweepPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes, useLocation } from 'react-router-dom'
import type { SweepOut, SweepUnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { SweepPage } from './SweepPage'

function unit(over: Partial<SweepUnitOut>): SweepUnitOut {
  return {
    id: 'u-204', code: '204', name: 'Room 204', floor: 2, roomType: 'KNGN',
    lastPassedAt: null, lastPassedByName: null, passedThisCycle: false, currentRun: null,
    ...over,
  }
}

const SWEEP: SweepOut = {
  template: { id: 't-1', name: 'Guest Room Quarterly', cadence: 'quarterly' },
  cycle: { id: 'cy-3', ordinal: 3, startsOn: '2026-07-01', endsOn: '2026-09-30', daysLeft: 20 },
  counts: { remaining: 3, completed: 1, total: 4 },
  units: [
    unit({ id: 'u-101', code: '101', name: 'Room 101', floor: 1 }),
    unit({ id: 'u-204', code: '204', passedThisCycle: true, lastPassedAt: '2026-08-02T14:00:00Z',
           lastPassedByName: 'Eli Engineer' }),
    unit({ id: 'u-205', code: '205', name: 'Room 205',
           currentRun: { id: 'run-205', status: 'in_progress', startedByUserId: 'u-noah',
                         startedByName: 'Noah Fix' } }),
    unit({ id: 'u-206', code: '206', name: 'Room 206',
           currentRun: { id: 'run-206', status: 'completed', startedByUserId: 'u-eli',
                         startedByName: 'Eli Engineer' } }),
  ],
}

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname + location.search}</div>
}

function serve(sweep: SweepOut, onStart?: () => unknown) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/pm/runs') && init?.method === 'POST') {
      const body = onStart?.() ?? { id: 'run-new', status: 'in_progress' }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 201 }))
    }
    if (url.includes('/pm/sweep')) {
      return Promise.resolve(new Response(JSON.stringify(sweep), { status: 200 }))
    }
    return Promise.resolve(new Response('[]', { status: 200 }))
  })
}

function mount(role: 'agent' | 'dept_staff' | 'admin' = 'dept_staff', route = '/app/pm') {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/pm" element={<SweepPage />} />
        <Route path="/app/pm/runs/:id" element={<div>run page</div>} />
      </Routes>
      <LocationDisplay />
    </SessionProvider>,
    { session: sessionFixture({ role }), route },
  )
}

describe('SweepPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the three tiles from the payload', async () => {
    serve(SWEEP)
    mount()
    expect(await screen.findByText('3')).toBeInTheDocument()
    expect(screen.getByText('Remaining')).toBeInTheDocument()
    expect(screen.getByText('3rd Cycle')).toBeInTheDocument()
    expect(screen.getByText('Jul 01 – Sep 30')).toBeInTheDocument()
    expect(screen.getByText('20 days')).toBeInTheDocument()
    expect(screen.getByText('Completed')).toBeInTheDocument()
  })

  it('shows one action per row from the unit state', async () => {
    serve(SWEEP)
    mount()
    expect(await screen.findByRole('button', { name: 'Start' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Done' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Continue/ })).toHaveTextContent('Noah Fix')
    expect(screen.getByRole('button', { name: 'Awaiting inspection' })).toBeDisabled()
  })

  it('starts a run and lands on it', async () => {
    serve(SWEEP)
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Start' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/pm/runs/run-new'))
    const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(String(post[1]!.body))).toEqual({ templateId: 't-1', unitId: 'u-101' })
  })

  it('follows a 409 to the run somebody else already started', async () => {
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/pm/runs') && init?.method === 'POST') {
        return Promise.resolve(new Response(JSON.stringify({
          error: { code: 'CONFLICT', message: 'Already running', details: { runId: 'run-other' } },
        }), { status: 409 }))
      }
      if (url.includes('/pm/sweep')) return Promise.resolve(new Response(JSON.stringify(SWEEP), { status: 200 }))
      return Promise.resolve(new Response('[]', { status: 200 }))
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Start' }))
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/app/pm/runs/run-other'))
  })

  it('hides Start from a role without perform_pm', async () => {
    serve(SWEEP)
    mount('agent')
    expect(await screen.findByText('Room 101')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start' })).not.toBeInTheDocument()
  })

  it('names the missing template when a kind is unconfigured', async () => {
    serve({ template: null, cycle: null, counts: { remaining: 0, completed: 0, total: 0 }, units: [] })
    mount('admin', '/app/pm?kind=equipment')
    expect(await screen.findByText(/No sweep template for Equipment/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /PM templates/ })).toHaveAttribute('href', '/app/admin/pm-templates')
  })

  it('puts the kind, filter and sort in the URL', async () => {
    serve(SWEEP)
    mount()
    await screen.findByText('Room 101')
    await userEvent.click(screen.getByRole('tab', { name: 'Equipment' }))
    expect(screen.getByTestId('location')).toHaveTextContent('kind=equipment')
    await userEvent.selectOptions(screen.getByLabelText('Show'), 'remaining')
    expect(screen.getByTestId('location')).toHaveTextContent('status=remaining')
  })
})
```

Run: `cd web && npx vitest run src/features/pm`
Expected: `SweepPage` not found.

- [ ] **Step 4: Write the page**

Create `web/src/features/pm/SweepPage.tsx`:

```tsx
import type { ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useStartRun, useSweep } from '../../api/hooks/pm'
import type { PmUnitKind, SweepUnitOut } from '../../api/types'
import { useSession } from '../../auth/SessionContext'
import { Button, EmptyState, Input, Spinner, useToast } from '../../components/ui'
import { cn } from '../../lib/cn'
import { useMediaQuery } from '../../lib/useMediaQuery'
import { KindTabs } from './KindTabs'
import { CADENCE_LABELS, KIND_LABELS, formatWindow, isKind, ordinal } from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'
const HEADING = 'text-xs font-bold uppercase tracking-widest text-text3'

const TILE_TONES = {
  danger: 'bg-dangerBg text-dangerText',
  note: 'bg-noteBg text-noteText',
  ok: 'bg-okBg text-okText',
} as const

function Tile({
  label,
  value,
  sub,
  tone,
}: {
  label: string
  value: string
  sub?: string
  tone: keyof typeof TILE_TONES
}) {
  return (
    <div className={cn('flex min-w-[160px] flex-1 flex-col rounded-card p-4', TILE_TONES[tone])}>
      <span className="text-xs font-bold uppercase tracking-widest opacity-80">{label}</span>
      <span className="mt-1 text-2xl font-bold">{value}</span>
      {sub ? <span className="text-xs opacity-80">{sub}</span> : null}
    </div>
  )
}

function lastPm(unit: SweepUnitOut): string {
  if (!unit.lastPassedAt) return 'Never'
  const when = new Date(unit.lastPassedAt).toLocaleDateString()
  return unit.lastPassedByName ? `${when} · ${unit.lastPassedByName}` : when
}

function csvCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function toCsv(rows: SweepUnitOut[]): string {
  const header = 'code,name,floor,room_type,last_pm,last_pm_by,status'
  const lines = rows.map((u) =>
    [
      u.code, u.name, u.floor, u.roomType, u.lastPassedAt, u.lastPassedByName,
      u.passedThisCycle ? 'done' : u.currentRun?.status ?? 'remaining',
    ].map(csvCell).join(','),
  )
  return [header, ...lines].join('\n') + '\n'
}

function download(filename: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function SweepPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { can } = useSession()
  const toast = useToast()
  const isMobile = useMediaQuery('(max-width: 767px)')

  const kindParam = params.get('kind')
  const kind: PmUnitKind = isKind(kindParam) ? kindParam : 'guest_room'
  const statusParam = params.get('status')
  const status = statusParam === 'remaining' || statusParam === 'completed' ? statusParam : null
  const sort = params.get('sort') ?? 'code'
  const q = params.get('q') ?? ''

  const { data, isPending, error } = useSweep({ kind, status, sort, q })
  const startRun = useStartRun()

  function set(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    setParams(merged)
  }

  function start(unit: SweepUnitOut) {
    if (!data?.template) return
    startRun.mutate(
      { templateId: data.template.id, unitId: unit.id },
      {
        onSuccess: (run) => navigate(`/app/pm/runs/${run.id}`),
        onError: (err) => {
          // Somebody else started this unit first: the 409 names their run, so join it.
          const runId = (err.details as { runId?: string } | undefined)?.runId
          if (err.status === 409 && runId) navigate(`/app/pm/runs/${runId}`)
          else toast(err.message, 'danger')
        },
      },
    )
  }

  const action = (unit: SweepUnitOut) => {
    if (unit.passedThisCycle) return <Button disabled>Done</Button>
    const run = unit.currentRun
    if (run?.status === 'completed') return <Button disabled>Awaiting inspection</Button>
    if (run) {
      return (
        <Button onClick={() => navigate(`/app/pm/runs/${run.id}`)}>
          Continue{run.startedByName ? ` · ${run.startedByName}` : ''}
        </Button>
      )
    }
    if (!can('perform_pm')) return null
    return (
      <Button variant="primary" loading={startRun.isPending} onClick={() => start(unit)}>
        Start
      </Button>
    )
  }

  let body: ReactNode
  if (isPending) {
    body = (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  } else if (error || !data) {
    body = <EmptyState title="Could not load the sweep" hint={error?.message} />
  } else if (!data.template) {
    body = (
      <EmptyState
        title={`No sweep template for ${KIND_LABELS[kind]}`}
        hint="A sweep template says how often every unit of this kind gets its PM and what the checklist is."
        action={
          can('manage_admin') ? (
            <Link to="/app/admin/pm-templates" className="text-sm font-semibold text-accent hover:underline">
              Set one up under PM templates
            </Link>
          ) : null
        }
      />
    )
  } else if (!data.cycle) {
    body = <EmptyState title="No open cycle yet" hint="The next cycle opens on its window's first day." />
  } else if (data.units.length === 0) {
    body = (
      <EmptyState
        title={q || status ? 'Nothing matches' : `No active ${KIND_LABELS[kind].toLowerCase()}`}
        hint={q || status ? 'Clear the search or filter.' : 'Add units under Admin → Maintainable units.'}
      />
    )
  } else if (isMobile) {
    body = (
      <ul className="flex flex-col gap-2 p-4">
        {data.units.map((unit) => (
          <li key={unit.id} className="flex items-center gap-3 rounded-card border border-border2 bg-surface p-3">
            <div className="min-w-0 flex-1">
              <p className="font-mono text-sm font-bold text-roomNum">{unit.code}</p>
              <p className="truncate text-sm">{unit.name}</p>
              <p className="text-xs text-text3">Last PM: {lastPm(unit)}</p>
            </div>
            {action(unit)}
          </li>
        ))}
      </ul>
    )
  } else {
    body = (
      <div className="p-4">
        <table className="w-full">
          <thead>
            <tr>
              {['Unit', 'Floor', 'Last PM', ''].map((head) => (
                <th key={head} className="border-b border-border2 px-3.5 py-2.5 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3">
                  {head}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.units.map((unit) => (
              <tr key={unit.id}>
                <td className="border-b border-border px-3.5 py-3">
                  <span className="font-mono text-sm font-bold text-roomNum">{unit.code}</span>
                  <span className="ml-2 text-sm">{unit.name}</span>
                  {unit.roomType ? <span className="ml-2 text-xs text-text3">({unit.roomType})</span> : null}
                </td>
                <td className="border-b border-border px-3.5 py-3 text-sm">{unit.floor ?? '—'}</td>
                <td className="border-b border-border px-3.5 py-3 text-sm text-text2">{lastPm(unit)}</td>
                <td className="border-b border-border px-3.5 py-3 text-right">{action(unit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">Preventative Maintenance</h1>
        {data?.template ? (
          <span className="text-xs text-text3">
            {data.template.name} · {CADENCE_LABELS[data.template.cadence]}
          </span>
        ) : null}
        {can('view_property_analytics') ? (
          <Link to="/app/pm/compliance" className="ml-auto text-sm font-semibold text-text3 hover:text-text">
            Compliance →
          </Link>
        ) : null}
      </header>

      <KindTabs value={kind} onChange={(next) => set({ kind: next === 'all' ? null : next })} />

      {data?.cycle ? (
        <div className="flex flex-wrap gap-3 p-4">
          <Tile label="Remaining" value={String(data.counts.remaining)} tone="danger" />
          <Tile
            label={`${ordinal(data.cycle.ordinal)} Cycle`}
            value={`${data.cycle.daysLeft} days`}
            sub={formatWindow(data.cycle.startsOn, data.cycle.endsOn)}
            tone="note"
          />
          <Tile label="Completed" value={String(data.counts.completed)} tone="ok" />
        </div>
      ) : null}

      <div className="flex flex-wrap items-end gap-3 border-b border-border px-4 py-3">
        <div className="min-w-[200px] flex-1">
          <label className={HEADING} htmlFor="pm-sweep-q">Search</label>
          <Input
            id="pm-sweep-q"
            className="h-9"
            placeholder="Room, area or equipment"
            value={q}
            onChange={(event) => set({ q: event.target.value })}
          />
        </div>
        <div>
          <label className={HEADING} htmlFor="pm-sweep-status">Show</label>
          <select id="pm-sweep-status" className={SELECT} value={status ?? ''}
                  onChange={(event) => set({ status: event.target.value || null })}>
            <option value="">All</option>
            <option value="remaining">Remaining</option>
            <option value="completed">Completed</option>
          </select>
        </div>
        <div>
          <label className={HEADING} htmlFor="pm-sweep-sort">Sort</label>
          <select id="pm-sweep-sort" className={SELECT} value={sort}
                  onChange={(event) => set({ sort: event.target.value === 'code' ? null : event.target.value })}>
            <option value="code">Unit</option>
            <option value="floor">Floor</option>
            <option value="days_since_last_pm">Days since last PM</option>
          </select>
        </div>
        {can('export') && data?.units.length ? (
          <Button onClick={() => download(`pm-${kind}.csv`, toCsv(data.units))}>Export</Button>
        ) : null}
      </div>

      {body}
    </div>
  )
}
```

Add the route in `web/src/routes.tsx` — import `SweepPage` from `./features/pm/SweepPage` and, after the `log` route:

```tsx
          <Route path="pm" element={<SweepPage />} />
```

- [ ] **Step 5: Verify and commit**

Run: `cd web && npx vitest run src/features/pm && npm run lint && npm run build`

```bash
git add web/src/features/pm/labels.ts web/src/features/pm/labels.test.ts web/src/features/pm/KindTabs.tsx web/src/features/pm/SweepPage.tsx web/src/features/pm/SweepPage.test.tsx web/src/routes.tsx
git commit -m "feat(web): PM sweep page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 15: Checklist page (perform and inspect)

**Files:**
- Create: `web/src/features/pm/ChecklistItem.tsx`
- Create: `web/src/features/pm/RunPage.tsx`, `web/src/features/pm/RunPage.test.tsx`
- Modify: `web/src/routes.tsx` (route `pm/runs/:id`)

**Interfaces:**
- Consumes: `usePmRun`, `useSaveAnswer`, `useUploadRunPhoto`, `useCompleteRun`, `useBeginRun`, `useInspectRun` (Task 13); `RUN_STATUS_LABELS` (Task 14).

- [ ] **Step 1: Write the failing test**

Create `web/src/features/pm/RunPage.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { Role, RunOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RunPage } from './RunPage'

const RUN: RunOut = {
  id: 'run-1', templateId: 't-1', templateName: 'Guest Room Quarterly',
  unitId: 'u-204', unitCode: '204', unitName: 'Room 204', unitKind: 'guest_room',
  cycleId: 'cy-3', workOrderId: null, status: 'in_progress',
  startedByUserId: 'u-eli', startedByName: 'Eli Engineer', startedAt: '2026-09-10T12:00:00Z',
  completedAt: null, inspectedByUserId: null, inspectedByName: null, inspectedAt: null,
  inspectionNote: null, dueAt: null,
  items: [
    { id: 'i-hvac', position: 0, label: 'HVAC filter replaced', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
    { id: 'i-temp', position: 1, label: 'Tap hot-water temperature', itemType: 'number', unit: '°F',
      minValue: 100, maxValue: 120, required: true, active: true },
    { id: 'i-caulk', position: 2, label: 'Caulk condition', itemType: 'text', unit: null,
      minValue: null, maxValue: null, required: false, active: true },
    { id: 'i-fan', position: 3, label: 'Bathroom fan photo', itemType: 'photo', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
  ],
  answers: [
    { id: 'a-hvac', itemId: 'i-hvac', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-temp', itemId: 'i-temp', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-caulk', itemId: 'i-caulk', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-fan', itemId: 'i-fan', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
  ],
  photos: [],
  missingRequired: ['i-hvac', 'i-temp', 'i-fan'],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

/** GET returns `run`; any PATCH/POST returns `after` (or `run`). */
function serve(run: RunOut, after?: RunOut) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/pm/runs/') && init?.method && init.method !== 'GET') return json(after ?? run)
    if (url.includes('/pm/runs/')) return json(run)
    return json([])
  })
}

function mount(role: Role = 'dept_staff') {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/pm/runs/:id" element={<RunPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/pm/runs/run-1' },
  )
}

function patchCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PATCH')
}

describe('RunPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders every item by type and lists what still blocks Complete', async () => {
    serve(RUN)
    mount()
    expect(await screen.findByText('Room 204')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /HVAC filter replaced/ })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /Tap hot-water temperature/ })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Caulk condition/ })).toBeInTheDocument()
    expect(screen.getByLabelText(/Bathroom fan photo/)).toHaveAttribute('type', 'file')
    expect(screen.getByRole('button', { name: 'Complete' })).toBeDisabled()
    expect(screen.getByText(/3 required items still need an answer/)).toBeInTheDocument()
  })

  it('saves a number on blur and shows the out-of-range warning the server returns', async () => {
    const flagged: RunOut = {
      ...RUN,
      answers: RUN.answers.map((a) =>
        a.id === 'a-temp' ? { ...a, numberValue: 122, outOfRange: true, answeredAt: '2026-09-10T12:05:00Z' } : a),
      missingRequired: ['i-hvac', 'i-fan'],
    }
    serve(RUN, flagged)
    mount()
    const field = await screen.findByRole('spinbutton', { name: /Tap hot-water temperature/ })
    await userEvent.type(field, '122')
    await userEvent.tab()
    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(String(patchCalls()[0]![0])).toContain('/pm/runs/run-1/answers/a-temp')
    expect(JSON.parse(String(patchCalls()[0]![1]!.body))).toEqual({ numberValue: 122 })
    expect(await screen.findByText(/Outside 100–120/)).toBeInTheDocument()
    expect(screen.getByText(/2 required items still need an answer/)).toBeInTheDocument()
  })

  it('enables Complete once nothing is missing and posts it', async () => {
    const ready = { ...RUN, missingRequired: [] }
    serve(ready, { ...ready, status: 'completed' })
    mount()
    const button = await screen.findByRole('button', { name: 'Complete' })
    expect(button).toBeEnabled()
    await userEvent.click(button)
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) =>
        String(input).endsWith('/pm/runs/run-1/complete') && init?.method === 'POST')).toBe(true))
    expect(await screen.findByText('Awaiting inspection')).toBeInTheDocument()
  })

  it('is read-only with a Pass/Fail footer for an inspector on a completed run', async () => {
    const completed: RunOut = { ...RUN, status: 'completed', completedAt: '2026-09-10T12:40:00Z', missingRequired: [] }
    serve(completed, { ...completed, status: 'failed' })
    mount('supervisor')
    expect(await screen.findByRole('button', { name: 'Pass' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /HVAC filter replaced/ })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Fail' }))
    const submit = screen.getByRole('button', { name: 'Record failure' })
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByLabelText('What must be redone'), 'Grille still dusty')
    await userEvent.click(submit)
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([input]) => String(input).endsWith('/inspect'))!
      expect(JSON.parse(String(call[1]!.body))).toEqual({ result: 'fail', note: 'Grille still dusty' })
    })
  })

  it('offers only Start PM for a pending scheduled run', async () => {
    serve({ ...RUN, status: 'pending', workOrderId: 'w-9', startedByName: null, answers: [], missingRequired: [] })
    mount()
    expect(await screen.findByRole('button', { name: 'Start PM' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /work order/i })).toHaveAttribute('href', '/app/work-orders/w-9')
  })
})
```

Run: `cd web && npx vitest run src/features/pm/RunPage.test.tsx`
Expected: `RunPage` not found.

- [ ] **Step 2: The item component**

Create `web/src/features/pm/ChecklistItem.tsx`:

```tsx
import { useEffect, useState, type ReactNode } from 'react'
import type { AnswerPatch, RunAnswerOut, RunPhotoOut, TemplateItemOut } from '../../api/types'
import { Input } from '../../components/ui'
import { cn } from '../../lib/cn'

const LABEL = 'text-sm font-semibold'
const HINT = 'text-xs text-text3'

/** One checklist row, rendered by `item.itemType`. Every change is saved as its own PATCH
 *  through `onSave`; nothing is queued locally, so leaving the page mid-room loses nothing. */
export function ChecklistItem({
  item,
  answer,
  photos,
  readOnly,
  missing,
  onSave,
  onUpload,
}: {
  item: TemplateItemOut
  answer?: RunAnswerOut
  photos: RunPhotoOut[]
  readOnly: boolean
  missing: boolean
  onSave: (patch: AnswerPatch) => void
  onUpload: (file: File) => void
}) {
  const inputId = `pm-item-${item.id}`
  const required = item.required ? <span className="text-dangerText"> *</span> : null

  // Text and number are edited locally and saved on blur, so a slow connection does not
  // fight the keyboard. The saved value wins whenever the server answers.
  const [text, setText] = useState(answer?.textValue ?? '')
  const [number, setNumber] = useState(answer?.numberValue === null || answer?.numberValue === undefined ? '' : String(answer.numberValue))
  useEffect(() => setText(answer?.textValue ?? ''), [answer?.textValue])
  useEffect(() => {
    setNumber(answer?.numberValue === null || answer?.numberValue === undefined ? '' : String(answer.numberValue))
  }, [answer?.numberValue])

  const bounds =
    item.minValue !== null && item.minValue !== undefined && item.maxValue !== null && item.maxValue !== undefined
      ? `${item.minValue}–${item.maxValue}`
      : item.minValue !== null && item.minValue !== undefined
        ? `≥ ${item.minValue}`
        : item.maxValue !== null && item.maxValue !== undefined
          ? `≤ ${item.maxValue}`
          : null

  let control: ReactNode
  switch (item.itemType) {
    case 'checkbox':
      control = (
        <label className="flex items-center gap-3">
          <input
            id={inputId}
            type="checkbox"
            className="h-5 w-5"
            checked={answer?.boolValue === true}
            disabled={readOnly}
            onChange={(event) => onSave({ boolValue: event.target.checked })}
          />
          <span className={LABEL}>{item.label}{required}</span>
        </label>
      )
      break
    case 'number':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          <div className="mt-1 flex items-center gap-2">
            <Input
              id={inputId}
              type="number"
              inputMode="decimal"
              step="any"
              className={cn('max-w-[160px]', answer?.outOfRange && 'border-danger text-dangerText')}
              value={number}
              disabled={readOnly}
              onChange={(event) => setNumber(event.target.value)}
              onBlur={() => onSave({ numberValue: number === '' ? null : Number(number) })}
            />
            {item.unit ? <span className="text-sm text-text3">{item.unit}</span> : null}
          </div>
          {bounds ? <p className={HINT}>Expected {bounds}{item.unit ? ` ${item.unit}` : ''}</p> : null}
          {answer?.outOfRange ? (
            <p role="alert" className="mt-1 text-xs font-semibold text-dangerText">
              Outside {bounds} — a work order will be raised when this PM is completed.
            </p>
          ) : null}
        </div>
      )
      break
    case 'text':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          <Input
            id={inputId}
            className="mt-1"
            value={text}
            disabled={readOnly}
            maxLength={2000}
            onChange={(event) => setText(event.target.value)}
            onBlur={() => {
              if ((answer?.textValue ?? '') !== text) onSave({ textValue: text || null })
            }}
          />
        </div>
      )
      break
    case 'photo':
      control = (
        <div>
          <label className={LABEL} htmlFor={inputId}>{item.label}{required}</label>
          {photos.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-2">
              {photos.map((photo) => (
                <a key={photo.id} href={photo.url} target="_blank" rel="noreferrer">
                  <img src={photo.url} alt="" className="h-20 w-20 rounded object-cover" />
                </a>
              ))}
            </div>
          ) : null}
          {readOnly ? null : (
            <input
              id={inputId}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              className="mt-2 block text-sm"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onUpload(file)
                event.target.value = ''
              }}
            />
          )}
        </div>
      )
      break
  }

  return (
    <li className={cn('rounded-card border bg-surface p-4', missing ? 'border-warnText/40' : 'border-border2')}>
      {control}
    </li>
  )
}
```

- [ ] **Step 3: The page**

Create `web/src/features/pm/RunPage.tsx`:

```tsx
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  useBeginRun, useCompleteRun, useInspectRun, usePmRun, useSaveAnswer, useUploadRunPhoto,
} from '../../api/hooks/pm'
import { useSession } from '../../auth/SessionContext'
import { Badge, Button, EmptyState, Spinner, Textarea, useToast } from '../../components/ui'
import { formatClock } from '../../lib/time'
import { ChecklistItem } from './ChecklistItem'
import { RUN_STATUS_LABELS } from './labels'

const STATUS_TONE = {
  pending: 'neutral', in_progress: 'note', completed: 'warn', passed: 'ok', failed: 'danger',
  missed: 'danger',
} as const

export function RunPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useSession()
  const toast = useToast()
  const { data: run, isPending, error } = usePmRun(id)
  const save = useSaveAnswer()
  const upload = useUploadRunPhoto()
  const complete = useCompleteRun()
  const begin = useBeginRun()
  const inspect = useInspectRun()
  const [failing, setFailing] = useState(false)
  const [note, setNote] = useState('')

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !run) return <EmptyState title="Could not load this PM" hint={error?.message} />

  const fail = (err: { message: string }) => toast(err.message, 'danger')
  const readOnly = run.status !== 'in_progress' || !can('perform_pm')
  const canInspect = run.status === 'completed' && can('inspect_pm')
  const missing = new Set(run.missingRequired)
  const missingLabels = run.items.filter((i) => missing.has(i.id)).map((i) => i.label)
  const answerFor = (itemId: string) => run.answers.find((a) => a.itemId === itemId)
  const general = run.photos.filter((p) => !p.itemId)

  const back = run.workOrderId ? (
    <Link to={`/app/work-orders/${run.workOrderId}`} className="text-sm font-semibold text-text3 hover:text-text">
      ← Work order
    </Link>
  ) : (
    <Link to={`/app/pm?kind=${run.unitKind}`} className="text-sm font-semibold text-text3 hover:text-text">
      ← Sweep
    </Link>
  )

  return (
    <div className="h-full overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        {back}
        <span className="font-mono text-lg font-bold text-roomNum">{run.unitCode}</span>
        <h1 className="text-base font-bold">{run.unitName}</h1>
        <Badge tone={STATUS_TONE[run.status]}>{RUN_STATUS_LABELS[run.status]}</Badge>
        <span className="w-full text-xs text-text3 md:ml-auto md:w-auto">
          {run.templateName}
          {run.startedByName ? ` · ${run.startedByName}` : ''}
          {run.startedAt ? ` · started ${formatClock(run.startedAt)}` : ''}
          {run.dueAt ? ` · due ${new Date(run.dueAt).toLocaleDateString()}` : ''}
        </span>
      </header>

      <div className="mx-auto flex max-w-2xl flex-col gap-3 p-4">
        {run.status === 'pending' ? (
          can('perform_pm') ? (
            <EmptyState
              title="This PM is scheduled and waiting to be picked up"
              action={
                <Button variant="primary" loading={begin.isPending}
                        onClick={() => begin.mutate(run.id, { onError: fail })}>
                  Start PM
                </Button>
              }
            />
          ) : (
            <EmptyState title="This PM is scheduled and waiting to be picked up" />
          )
        ) : (
          <ol className="flex flex-col gap-3">
            {run.items.map((item) => (
              <ChecklistItem
                key={item.id}
                item={item}
                answer={answerFor(item.id)}
                photos={run.photos.filter((p) => p.itemId === item.id)}
                readOnly={readOnly}
                missing={missing.has(item.id)}
                onSave={(patch) => {
                  const answer = answerFor(item.id)
                  if (answer) save.mutate({ runId: run.id, answerId: answer.id, patch }, { onError: fail })
                }}
                onUpload={(file) => upload.mutate({ runId: run.id, file, itemId: item.id }, { onError: fail })}
              />
            ))}
          </ol>
        )}

        {run.status !== 'pending' ? (
          <section className="rounded-card border border-border2 bg-surface p-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-text3">Other photos</h2>
            {general.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {general.map((photo) => (
                  <a key={photo.id} href={photo.url} target="_blank" rel="noreferrer">
                    <img src={photo.url} alt="" className="h-20 w-20 rounded object-cover" />
                  </a>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-xs text-text3">None</p>
            )}
            {readOnly ? null : (
              <input
                type="file"
                aria-label="Add a photo"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="mt-2 block text-sm"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (file) upload.mutate({ runId: run.id, file }, { onError: fail })
                  event.target.value = ''
                }}
              />
            )}
          </section>
        ) : null}

        {!readOnly ? (
          <footer className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-4">
            <Button
              variant="primary"
              disabled={missing.size > 0}
              loading={complete.isPending}
              onClick={() => complete.mutate(run.id, { onError: fail })}
            >
              Complete
            </Button>
            {missing.size > 0 ? (
              <p className="text-xs text-text3">
                {missing.size} required item{missing.size === 1 ? '' : 's'} still need{missing.size === 1 ? 's' : ''} an answer: {missingLabels.join(', ')}
              </p>
            ) : (
              <p className="text-xs text-text3">Everything required is answered.</p>
            )}
          </footer>
        ) : null}

        {canInspect ? (
          <footer className="flex flex-col gap-3 rounded-card border border-border2 bg-surface p-4">
            <p className="text-sm font-semibold">Inspection</p>
            {failing ? (
              <>
                <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="pm-fail-note">
                  What must be redone
                </label>
                <Textarea id="pm-fail-note" value={note} maxLength={2000}
                          onChange={(event) => setNote(event.target.value)} />
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    disabled={!note.trim()}
                    loading={inspect.isPending}
                    onClick={() => inspect.mutate({ runId: run.id, body: { result: 'fail', note: note.trim() } }, { onError: fail })}
                  >
                    Record failure
                  </Button>
                  <Button onClick={() => setFailing(false)}>Back</Button>
                </div>
              </>
            ) : (
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  loading={inspect.isPending}
                  onClick={() => inspect.mutate({ runId: run.id, body: { result: 'pass' } }, { onError: fail })}
                >
                  Pass
                </Button>
                <Button variant="danger" onClick={() => setFailing(true)}>Fail</Button>
              </div>
            )}
          </footer>
        ) : null}

        {run.inspectionNote ? (
          <p className="rounded border border-dangerText/40 bg-dangerBg px-3 py-2 text-sm text-dangerText">
            Inspector{run.inspectedByName ? ` (${run.inspectedByName})` : ''}: {run.inspectionNote}
          </p>
        ) : null}
      </div>
    </div>
  )
}
```

Add the route in `web/src/routes.tsx` — import `RunPage` and add after `pm`:

```tsx
          <Route path="pm/runs/:id" element={<RunPage />} />
```

- [ ] **Step 4: Verify and commit**

Run: `cd web && npx vitest run src/features/pm && npm run lint && npm run build`

```bash
git add web/src/features/pm/ChecklistItem.tsx web/src/features/pm/RunPage.tsx web/src/features/pm/RunPage.test.tsx web/src/routes.tsx
git commit -m "feat(web): PM checklist page with inspection mode

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 16: Inspection page

**Files:**
- Create: `web/src/features/pm/InspectionPage.tsx`, `web/src/features/pm/InspectionPage.test.tsx`
- Modify: `web/src/routes.tsx` (route `inspection`, capability-gated; `RequireCapability` widened)

**Interfaces:**
- Consumes: `useInspections` (Task 13), `KindTabs` (Task 14).
- Route: `/app/inspection` (a sibling of `/app/pm`, so the Preventative Maintenance rail entry — which matches the `/app/pm` prefix — does not light on it).

- [ ] **Step 1: Write the failing test**

Create `web/src/features/pm/InspectionPage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { InspectionRowOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { InspectionPage } from './InspectionPage'

const AVAILABLE: InspectionRowOut[] = [
  { runId: 'run-1', unitId: 'u-204', unitCode: '204', unitName: 'Room 204', unitKind: 'guest_room',
    templateName: 'Guest Room Quarterly', completedByName: 'Eli Engineer',
    completedAt: '2026-09-10T12:40:00Z', daysSinceLastPm: 94, status: 'completed',
    inspectedByName: null, inspectedAt: null },
]
const INSPECTED: InspectionRowOut[] = [
  { ...AVAILABLE[0]!, runId: 'run-0', unitCode: '101', unitName: 'Room 101', status: 'passed',
    inspectedByName: 'Sam Super', inspectedAt: '2026-09-09T15:00:00Z' },
  { ...AVAILABLE[0]!, runId: 'run-x', unitCode: '102', unitName: 'Room 102', status: 'failed',
    inspectedByName: 'Sam Super', inspectedAt: '2026-09-09T16:00:00Z' },
]

function serve(available: InspectionRowOut[], inspected: InspectionRowOut[]) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const body = url.includes('status=inspected') ? inspected : available
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/inspection" element={<InspectionPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'supervisor' }), route: '/app/inspection' },
  )
}

describe('InspectionPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows both queue counts and the available rows by default', async () => {
    serve(AVAILABLE, INSPECTED)
    mount()
    expect(await screen.findByRole('tab', { name: 'Available for Inspection 1' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Inspected 2' })).toBeInTheDocument()
    const row = screen.getByRole('link', { name: /Room 204/ })
    expect(row).toHaveAttribute('href', '/app/pm/runs/run-1')
    expect(row).toHaveTextContent('94 days since last PM')
  })

  it('switches to the inspected list with results', async () => {
    serve(AVAILABLE, INSPECTED)
    mount()
    await userEvent.click(await screen.findByRole('tab', { name: 'Inspected 2' }))
    expect(await screen.findByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('Failed')).toBeInTheDocument()
    expect(screen.getAllByText(/Sam Super/)).toHaveLength(2)
  })

  it('has an empty state naming the kind', async () => {
    serve([], [])
    mount()
    await userEvent.click(await screen.findByRole('tab', { name: 'Guest Rooms' }))
    expect(await screen.findByText('No guest rooms PMs are pending for inspection')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: The page**

Create `web/src/features/pm/InspectionPage.tsx`:

```tsx
import { Link, useSearchParams } from 'react-router-dom'
import { useInspections } from '../../api/hooks/pm'
import type { InspectionRowOut, PmUnitKind } from '../../api/types'
import { Badge, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { formatClock } from '../../lib/time'
import { KindTabs } from './KindTabs'
import { KIND_LABELS, RUN_STATUS_LABELS, isKind } from './labels'

const SELECT =
  'h-9 rounded border border-border3 bg-surface2 px-2 text-sm text-text focus:border-accent focus:outline-none'

function Row({ row }: { row: InspectionRowOut }) {
  return (
    <li>
      <Link
        to={`/app/pm/runs/${row.runId}`}
        className="flex flex-wrap items-center gap-3 rounded-card border border-border2 bg-surface p-3 hover:bg-surface2"
      >
        <span className="font-mono text-sm font-bold text-roomNum">{row.unitCode}</span>
        <span className="text-sm font-semibold">{row.unitName}</span>
        <span className="text-xs text-text3">{row.templateName}</span>
        <span className="w-full text-xs text-text3 md:ml-auto md:w-auto">
          {row.completedByName ?? 'Unknown'}
          {row.completedAt ? ` · ${formatClock(row.completedAt)}` : ''}
          {' · '}
          {row.daysSinceLastPm === null || row.daysSinceLastPm === undefined
            ? 'never inspected before'
            : `${row.daysSinceLastPm} days since last PM`}
        </span>
        {row.status !== 'completed' ? (
          <span className="flex items-center gap-2 text-xs text-text3">
            <Badge tone={row.status === 'passed' ? 'ok' : 'danger'}>{RUN_STATUS_LABELS[row.status]}</Badge>
            {row.inspectedByName}
          </span>
        ) : null}
      </Link>
    </li>
  )
}

export function InspectionPage() {
  const [params, setParams] = useSearchParams()
  const kindParam = params.get('kind')
  const kind: PmUnitKind | 'all' = isKind(kindParam) ? kindParam : 'all'
  const tab = params.get('tab') === 'inspected' ? 'inspected' : 'available'
  const sort = params.get('sort') === 'days_since_last_pm' ? 'days_since_last_pm' : 'completed_at'
  const scope = { kind: kind === 'all' ? null : kind, sort }
  const available = useInspections({ ...scope, status: 'available' })
  const inspected = useInspections({ ...scope, status: 'inspected' })
  const current = tab === 'available' ? available : inspected

  function set(next: Record<string, string | null>) {
    const merged = new URLSearchParams(params)
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value)
      else merged.delete(key)
    }
    setParams(merged)
  }

  const subTab = (key: 'available' | 'inspected', label: string, count: number | undefined) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === key}
      onClick={() => set({ tab: key === 'available' ? null : key })}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded px-3 text-sm font-semibold',
        tab === key ? 'bg-accent text-accentText' : 'text-text3 hover:text-text',
      )}
    >
      {label}
      <span className="font-mono text-xs opacity-85">{count ?? '…'}</span>
    </button>
  )

  const kindLabel = kind === 'all' ? '' : `${KIND_LABELS[kind].toLowerCase()} `

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="border-b border-border px-4 py-3">
        <h1 className="text-base font-bold">PM Inspection</h1>
      </header>
      <KindTabs allowAll value={kind} onChange={(next) => set({ kind: next === 'all' ? null : next })} />
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <div role="tablist" className="flex gap-1.5">
          {subTab('available', 'Available for Inspection', available.data?.length)}
          {subTab('inspected', 'Inspected', inspected.data?.length)}
        </div>
        <label className="ml-auto flex items-center gap-2 text-xs font-semibold text-text3">
          Sort
          <select className={SELECT} value={sort}
                  onChange={(event) => set({ sort: event.target.value === 'completed_at' ? null : event.target.value })}>
            <option value="completed_at">Completed</option>
            <option value="days_since_last_pm">Days since last PM</option>
          </select>
        </label>
      </div>

      {current.isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : current.error ? (
        <EmptyState title="Could not load the queue" hint={current.error.message} />
      ) : current.data.length === 0 ? (
        <EmptyState
          title={tab === 'available' ? `No ${kindLabel}PMs are pending for inspection` : `No ${kindLabel}PMs have been inspected`}
        />
      ) : (
        <ul className="flex flex-col gap-2 p-4">
          {current.data.map((row) => (
            <Row key={row.runId} row={row} />
          ))}
        </ul>
      )}
    </div>
  )
}
```

- [ ] **Step 3: The route, and widen the gate**

In `web/src/routes.tsx`, widen `RequireCapability`'s prop from the two-literal union to the real type — import `type Capability` from `./auth/capabilities` and change the prop to `capability: Capability`. Import `InspectionPage` and add after `pm/runs/:id`:

```tsx
          <Route
            path="inspection"
            element={
              <RequireCapability capability="inspect_pm">
                <InspectionPage />
              </RequireCapability>
            }
          />
```

- [ ] **Step 4: Verify and commit**

Run: `cd web && npx vitest run src/features/pm src/routes.test.tsx && npm run lint && npm run build`

```bash
git add web/src/features/pm/InspectionPage.tsx web/src/features/pm/InspectionPage.test.tsx web/src/routes.tsx
git commit -m "feat(web): PM inspection queue

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 17: Compliance page

**Files:**
- Create: `web/src/features/pm/CompliancePage.tsx`, `web/src/features/pm/CompliancePage.test.tsx`
- Modify: `web/src/routes.tsx` (route `pm/compliance`, gated by `view_property_analytics`)

**Interfaces:**
- Consumes: `useCompliance` (Task 13), labels (Task 14).

- [ ] **Step 1: Write the failing test**

Create `web/src/features/pm/CompliancePage.test.tsx`:

```tsx
import { screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ComplianceOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { CompliancePage } from './CompliancePage'

const REPORT: ComplianceOut = {
  templates: [
    { id: 't-1', name: 'Guest Room Quarterly', mode: 'sweep', unitKind: 'guest_room',
      cycles: [
        { ordinal: 2, startsOn: '2026-04-01', endsOn: '2026-06-30', status: 'closed', passed: 110, missed: 10, total: 120, onTimePct: 91.7 },
        { ordinal: 3, startsOn: '2026-07-01', endsOn: '2026-09-30', status: 'open', passed: 40, missed: 0, total: 120, onTimePct: 33.3 },
      ],
      runs: null, inspectionPassRate: 95.2 },
    { id: 't-2', name: 'Boiler inspection', mode: 'scheduled', unitKind: null, cycles: [],
      runs: { due: 2, passed: 1, failed: 0, overdue: 1 }, inspectionPassRate: 100 },
  ],
}

function mount() {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(REPORT), { status: 200 }))
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/pm/compliance" element={<CompliancePage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'manager' }), route: '/app/pm/compliance' },
  )
}

describe('CompliancePage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders a cycle table for sweeps and due/overdue for schedules', async () => {
    mount()
    expect(await screen.findByText('Guest Room Quarterly')).toBeInTheDocument()
    expect(screen.getByText('2nd Cycle')).toBeInTheDocument()
    expect(screen.getByText('91.7%')).toBeInTheDocument()
    expect(screen.getByText('Inspection pass rate 95.2%')).toBeInTheDocument()
    expect(screen.getByText('Boiler inspection')).toBeInTheDocument()
    expect(screen.getByText('1 overdue')).toBeInTheDocument()
  })

  it('asks the server for the chosen window', async () => {
    mount()
    await screen.findByText('Guest Room Quarterly')
    const url = String(vi.mocked(fetch).mock.calls[0]![0])
    expect(url).toMatch(/pm\/compliance\?from=\d{4}-01-01&to=\d{4}-\d{2}-\d{2}$/)
  })
})
```

- [ ] **Step 2: The page**

Create `web/src/features/pm/CompliancePage.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useCompliance } from '../../api/hooks/pm'
import type { ComplianceTemplateOut } from '../../api/types'
import { Badge, EmptyState, Input, Spinner } from '../../components/ui'
import { CADENCE_LABELS, KIND_LABELS, formatWindow, ordinal } from './labels'

const HEADING = 'text-xs font-bold uppercase tracking-widest text-text3'
const TH = 'border-b border-border2 px-3 py-2 text-left text-[11.5px] font-bold uppercase tracking-wider text-text3'
const TD = 'border-b border-border px-3 py-2 text-sm'

function localDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value}%`
}

function TemplateCard({ template }: { template: ComplianceTemplateOut }) {
  return (
    <section className="rounded-card border border-border2 bg-surface p-4">
      <header className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-bold">{template.name}</h2>
        <Badge>{template.mode === 'sweep' ? 'Sweep' : 'Scheduled'}</Badge>
        {template.unitKind ? <span className="text-xs text-text3">{KIND_LABELS[template.unitKind]}</span> : null}
        <span className="ml-auto text-xs text-text3">Inspection pass rate {pct(template.inspectionPassRate)}</span>
      </header>
      {template.mode === 'sweep' ? (
        template.cycles.length === 0 ? (
          <p className="text-xs text-text3">No cycles in this window.</p>
        ) : (
          <table className="w-full">
            <thead>
              <tr>
                {['Cycle', 'Window', 'Passed', 'Missed', 'Total', 'On time'].map((h) => (
                  <th key={h} className={TH}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {template.cycles.map((cycle) => (
                <tr key={cycle.ordinal + cycle.startsOn}>
                  <td className={TD}>
                    {ordinal(cycle.ordinal)} Cycle{cycle.status === 'open' ? <span className="ml-2 text-xs text-text3">open</span> : null}
                  </td>
                  <td className={TD}>{formatWindow(cycle.startsOn, cycle.endsOn)}</td>
                  <td className={`${TD} font-mono`}>{cycle.passed}</td>
                  <td className={`${TD} font-mono`}>{cycle.missed}</td>
                  <td className={`${TD} font-mono`}>{cycle.total}</td>
                  <td className={`${TD} font-mono`}>{pct(cycle.onTimePct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : template.runs ? (
        <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ['Due', template.runs.due], ['Passed', template.runs.passed],
            ['Failed', template.runs.failed], ['Overdue', template.runs.overdue],
          ].map(([label, value]) => (
            <div key={String(label)}>
              <dt className={HEADING}>{label}</dt>
              <dd className="font-mono text-lg font-bold">
                {value} {label === 'Overdue' ? 'overdue' : ''}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  )
}

export function CompliancePage() {
  const now = new Date()
  const [from, setFrom] = useState(`${now.getFullYear()}-01-01`)
  const [to, setTo] = useState(localDay(now))
  const { data, isPending, error } = useCompliance(from, to)

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto">
      <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <Link to="/app/pm" className="text-sm font-semibold text-text3 hover:text-text">← Sweep</Link>
        <h1 className="text-base font-bold">PM Compliance</h1>
        <div className="ml-auto flex items-end gap-2">
          <div>
            <label className={HEADING} htmlFor="pm-from">From</label>
            <Input id="pm-from" type="date" className="h-9" value={from} onChange={(e) => setFrom(e.target.value)} />
          </div>
          <div>
            <label className={HEADING} htmlFor="pm-to">To</label>
            <Input id="pm-to" type="date" className="h-9" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>
      </header>
      {isPending ? (
        <div className="flex justify-center py-8">
          <Spinner />
        </div>
      ) : error || !data ? (
        <EmptyState title="Could not load compliance" hint={error?.message} />
      ) : data.templates.length === 0 ? (
        <EmptyState title="No PM templates yet" />
      ) : (
        <div className="flex flex-col gap-4 p-4">
          {data.templates.map((template) => (
            <TemplateCard key={template.id} template={template} />
          ))}
          <p className="text-xs text-text3">
            Sweep cadences: {data.templates.filter((t) => t.mode === 'sweep').map((t) => t.name).join(', ') || 'none'} ·
            windows are property-local calendar {Object.values(CADENCE_LABELS).join('/').toLowerCase()} periods.
          </p>
        </div>
      )}
    </div>
  )
}
```

(The "Overdue" cell renders as `1 overdue`, which is what the test looks for and what a reader scanning the row wants.)

Add the route in `web/src/routes.tsx` after `pm/runs/:id`:

```tsx
          <Route
            path="pm/compliance"
            element={
              <RequireCapability capability="view_property_analytics">
                <CompliancePage />
              </RequireCapability>
            }
          />
```

- [ ] **Step 3: Verify and commit**

Run: `cd web && npx vitest run src/features/pm && npm run lint && npm run build`

```bash
git add web/src/features/pm/CompliancePage.tsx web/src/features/pm/CompliancePage.test.tsx web/src/routes.tsx
git commit -m "feat(web): PM compliance page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 18: Navigation — rail group and icons

**Files:**
- Modify: `web/src/components/NavIcon.tsx:3-16`
- Modify: `web/src/components/navModel.ts:23-64`
- Modify: `web/src/components/navModel.test.ts` (append)

**Interfaces:**
- Produces: `IconName` gains `'wrench' | 'inspect'`; a **Maintenance** nav group.

- [ ] **Step 1: Write the failing test**

Append to `web/src/components/navModel.test.ts`:

```ts

describe('maintenance group', () => {
  it('shows Preventative Maintenance to view_pm holders and PM Inspection to inspect_pm holders', () => {
    const only = (cap: string) => visibleNavGroups((c) => c === cap)
    expect(only('view_pm').flatMap((g) => g.items).map((i) => i.label)).toContain('Preventative Maintenance')
    expect(only('view_pm').flatMap((g) => g.items).map((i) => i.label)).not.toContain('PM Inspection')
    expect(only('inspect_pm').flatMap((g) => g.items).map((i) => i.label)).toContain('PM Inspection')
  })

  it('lights the PM entry on runs and compliance but not on the inspection queue', () => {
    const pm = item('Preventative Maintenance')
    expect(isNavItemActive(pm, '/app/pm')).toBe(true)
    expect(isNavItemActive(pm, '/app/pm/runs/run-1')).toBe(true)
    expect(isNavItemActive(pm, '/app/pm/compliance')).toBe(true)
    expect(isNavItemActive(pm, '/app/inspection')).toBe(false)
    expect(isNavItemActive(item('PM Inspection'), '/app/inspection')).toBe(true)
  })
})
```

Run: `cd web && npx vitest run src/components/navModel.test.ts`
Expected: the `item()` lookups return `undefined` and the test fails.

- [ ] **Step 2: Icons**

In `web/src/components/NavIcon.tsx`, extend the union and add two paths (lucide's `wrench` and `clipboard-check`, ISC-licensed outline icons drawn on the same 24×24 grid as the existing set):

```ts
export type IconName =
  | 'inbox' | 'board' | 'analytics' | 'alerts' | 'admin' | 'theme' | 'signout' | 'search' | 'log'
  | 'wrench' | 'inspect'
```

```ts
  wrench: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76Z',
  inspect: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2M9 14l2 2 4-4',
```

- [ ] **Step 3: The group**

In `web/src/components/navModel.ts`, insert between the `Overview` and `Insights` groups:

```ts
  {
    heading: 'Maintenance',
    items: [
      // Runs and the compliance tab live under /app/pm, so the prefix lights for all of them.
      // The inspection queue is a sibling at /app/inspection precisely so it does not: two lit
      // entries reads as a bug.
      {
        label: 'Preventative Maintenance',
        to: '/app/pm',
        icon: 'wrench',
        needs: ['view_pm'],
        match: ['/app/pm'],
      },
      { label: 'PM Inspection', to: '/app/inspection', icon: 'inspect', needs: ['inspect_pm'] },
    ],
  },
```

- [ ] **Step 4: Verify and commit**

Run: `cd web && npm test && npm run lint && npm run build`
Expected: green. `AppShell.test.tsx`'s "keeps only the capability-free items" still holds — both new items need a capability, so the group vanishes for a role with none.

```bash
git add web/src/components/NavIcon.tsx web/src/components/navModel.ts web/src/components/navModel.test.ts
git commit -m "feat(web): Maintenance nav group

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 19: Admin — maintainable units and CSV import

**Files:**
- Create: `web/src/features/admin/UnitsAdmin.tsx`, `web/src/features/admin/ImportUnitsDialog.tsx`, `web/src/features/admin/UnitsAdmin.test.tsx`
- Modify: `web/src/components/navModel.ts:69-76` (`ADMIN_SECTIONS`), `web/src/features/admin/AdminPage.tsx` (route)

**Interfaces:**
- Consumes: `useUnits`, `useCreateUnit`, `usePatchUnit`, `useImportUnits`, `importReport` (Task 13); `KindTabs`, labels (Task 14); `AdminTable`, `EditPanel`, `fieldErrors`.

- [ ] **Step 1: Write the failing test**

Create `web/src/features/admin/UnitsAdmin.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { UnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { UnitsAdmin } from './UnitsAdmin'

const UNITS: UnitOut[] = [
  { id: 'u-204', kind: 'guest_room', code: '204', name: 'Room 204', floor: 2, roomType: 'KNGN',
    active: true, source: 'manual', externalId: null, notes: null, createdAt: '2026-09-01T00:00:00Z' },
]

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve(importResponse?: { status: number; body: unknown }) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/import')) return json(importResponse?.body ?? { created: 3, updated: 0, errors: [] }, importResponse?.status ?? 200)
    if (init?.method === 'POST') return json({ ...UNITS[0], id: 'u-new', code: '205' }, 201)
    if (init?.method === 'PATCH') return json({ ...UNITS[0], active: false })
    return json(UNITS)
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <UnitsAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('UnitsAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists units for the selected kind and asks the server for that kind', async () => {
    serve()
    mount()
    expect(await screen.findByText('Room 204')).toBeInTheDocument()
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toContain('maintainable-units?kind=guest_room')
    await userEvent.click(screen.getByRole('tab', { name: 'Equipment' }))
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes('kind=equipment'))).toBe(true))
  })

  it('creates a unit from the panel', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New unit' }))
    await userEvent.type(screen.getByLabelText('Code'), '205')
    await userEvent.type(screen.getByLabelText('Name'), 'Room 205')
    await userEvent.type(screen.getByLabelText('Floor'), '2')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
      expect(JSON.parse(String(post[1]!.body))).toEqual({
        kind: 'guest_room', code: '205', name: 'Room 205', floor: 2, roomType: null,
        externalId: null, notes: null,
      })
    })
  })

  it('shows the per-row report when an import is rejected, and success counts otherwise', async () => {
    serve({
      status: 422,
      body: { error: { code: 'IMPORT_REJECTED', message: 'Import rejected', details: {
        created: 0, updated: 0,
        errors: [{ line: 3, field: 'kind', message: 'must be one of guest_room, common_area, equipment' }],
      } } },
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'Import CSV' }))
    const dialog = screen.getByRole('dialog')
    const file = new File(['code,kind,name,floor,room_type,external_id\n'], 'units.csv', { type: 'text/csv' })
    await userEvent.upload(within(dialog).getByLabelText('CSV file'), file)
    await userEvent.click(within(dialog).getByRole('button', { name: 'Import' }))
    expect(await within(dialog).findByText('Line 3')).toBeInTheDocument()
    expect(within(dialog).getByText(/must be one of/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Nothing was imported/)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: The dialog**

Create `web/src/features/admin/ImportUnitsDialog.tsx`:

```tsx
import { useState } from 'react'
import { importReport, useImportUnits } from '../../api/hooks/pm'
import { Button, Dialog, useToast } from '../../components/ui'

const COLUMNS = 'code,kind,name,floor,room_type,external_id'

/** Upload a CSV of units. A rejection lists every bad row in place — nothing was written, so
 *  the admin fixes the file and tries again without leaving the dialog (PM spec §7.6). */
export function ImportUnitsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const importUnits = useImportUnits()
  const toast = useToast()
  const report = importReport(importUnits.error)

  function close() {
    importUnits.reset()
    setFile(null)
    onClose()
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Import units from CSV"
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!file}
            loading={importUnits.isPending}
            onClick={() => {
              if (!file) return
              importUnits.mutate(file, {
                onSuccess: (result) => {
                  toast(`Imported: ${result.created} created, ${result.updated} updated`)
                  close()
                },
              })
            }}
          >
            Import
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-xs text-text3">
          Header row required, exactly: <code className="font-mono">{COLUMNS}</code>. <code className="font-mono">kind</code> is
          one of guest_room, common_area, equipment. Rows with a code that already exists are updated.
          A sample lives at <code className="font-mono">fixtures/maintainable_units.sample.csv</code>.
        </p>
        <label className="text-xs font-bold uppercase tracking-widest text-text3" htmlFor="units-csv">
          CSV file
        </label>
        <input
          id="units-csv"
          type="file"
          accept=".csv,text/csv"
          className="text-sm"
          onChange={(event) => {
            importUnits.reset()
            setFile(event.target.files?.[0] ?? null)
          }}
        />
        {report ? (
          <div role="alert" className="rounded border border-danger bg-dangerBg p-3 text-xs text-dangerText">
            <p className="mb-2 font-semibold">Nothing was imported. Fix these rows and try again:</p>
            <table className="w-full">
              <tbody>
                {report.errors.map((e, i) => (
                  <tr key={i}>
                    <td className="pr-3 font-mono">Line {e.line}</td>
                    <td className="pr-3 font-mono">{e.field}</td>
                    <td>{e.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : importUnits.error ? (
          <p role="alert" className="text-xs text-dangerText">{importUnits.error.message}</p>
        ) : null}
      </div>
    </Dialog>
  )
}
```

- [ ] **Step 3: The screen**

Create `web/src/features/admin/UnitsAdmin.tsx`:

```tsx
import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateUnit, usePatchUnit, useUnits } from '../../api/hooks/pm'
import type { PmUnitKind, UnitOut } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { KindTabs } from '../pm/KindTabs'
import { KIND_LABELS } from '../pm/labels'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { ImportUnitsDialog } from './ImportUnitsDialog'

type Draft = {
  id?: string
  kind: PmUnitKind
  code: string
  name: string
  floor: string
  roomType: string
  externalId: string
  notes: string
  active: boolean
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

function empty(kind: PmUnitKind): Draft {
  return { kind, code: '', name: '', floor: '', roomType: '', externalId: '', notes: '', active: true }
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

export function UnitsAdmin() {
  const [kind, setKind] = useState<PmUnitKind>('guest_room')
  const { data, isPending, error } = useUnits({ kind })
  const create = useCreateUnit()
  const patch = usePatchUnit()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<UnitOut | null>(null)
  const [importing, setImporting] = useState(false)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)

  const columns: Column<UnitOut>[] = [
    { key: 'code', head: 'Code', mono: true, render: (r) => r.code },
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'floor', head: 'Floor', mono: true, render: (r) => r.floor ?? '—' },
    { key: 'type', head: 'Room type', mono: true, render: (r) => r.roomType ?? '—' },
    { key: 'source', head: 'Source', render: (r) => <Badge>{r.source}</Badge> },
    { key: 'active', head: 'Active', render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>) },
  ]

  function clearFailures() {
    create.reset()
    patch.reset()
  }

  function close() {
    clearFailures()
    setDraft(null)
    setSelected(null)
  }

  function edit(change: Partial<Draft>) {
    if (draft) setDraft({ ...draft, ...change })
  }

  function open(unit: UnitOut) {
    clearFailures()
    setSelected(unit)
    setDraft({
      id: unit.id, kind: unit.kind, code: unit.code, name: unit.name,
      floor: unit.floor === null || unit.floor === undefined ? '' : String(unit.floor),
      roomType: unit.roomType ?? '', externalId: unit.externalId ?? '', notes: unit.notes ?? '',
      active: unit.active,
    })
  }

  function save() {
    if (!draft || !draft.code.trim() || !draft.name.trim()) return
    const body = {
      kind: draft.kind,
      code: draft.code.trim(),
      name: draft.name.trim(),
      floor: draft.floor.trim() === '' ? null : Number(draft.floor),
      roomType: draft.roomType.trim() || null,
      externalId: draft.externalId.trim() || null,
      notes: draft.notes.trim() || null,
    }
    if (draft.id) patch.mutate({ ...body, active: draft.active, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Maintainable units</h1>
          <div className="ml-auto flex gap-2">
            <Button onClick={() => setImporting(true)}>Import CSV</Button>
            <Button
              variant="primary"
              onClick={() => {
                clearFailures()
                setSelected(null)
                setDraft(empty(kind))
              }}
            >
              New unit
            </Button>
          </div>
        </header>
        <KindTabs value={kind} onChange={(next) => next !== 'all' && setKind(next)} />

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load units" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState
              title={`No ${KIND_LABELS[kind].toLowerCase()} yet`}
              hint="Add one, or import the whole inventory from a CSV."
            />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          subjectId={draft.id ?? 'new'}
          title={draft.id ? 'Edit unit' : 'New unit'}
          subtitle={draft.id ? 'Deactivate a retired unit rather than deleting it: its PM history stays attached.' : undefined}
          saving={pending}
          error={failed?.message ?? null}
          onSave={save}
          onCancel={close}
        >
          <div>
            <label className={LABEL} htmlFor="unit-kind">Kind</label>
            <select id="unit-kind" className={SELECT} value={draft.kind}
                    onChange={(e) => edit({ kind: e.target.value as PmUnitKind })}>
              {(Object.keys(KIND_LABELS) as PmUnitKind[]).map((k) => (
                <option key={k} value={k}>{KIND_LABELS[k]}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-code">Code</label>
            <Input id="unit-code" value={draft.code} maxLength={40} onChange={(e) => edit({ code: e.target.value })} />
            <FieldError message={fields.code} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-name">Name</label>
            <Input id="unit-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-floor">Floor</label>
            <Input id="unit-floor" type="number" value={draft.floor} onChange={(e) => edit({ floor: e.target.value })} />
            <FieldError message={fields.floor} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-room-type">Room type code</label>
            <Input id="unit-room-type" value={draft.roomType} maxLength={20} onChange={(e) => edit({ roomType: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-external-id">PMS id</label>
            <Input id="unit-external-id" value={draft.externalId} maxLength={100} onChange={(e) => edit({ externalId: e.target.value })} />
          </div>
          <div>
            <label className={LABEL} htmlFor="unit-notes">Notes</label>
            <Input id="unit-notes" value={draft.notes} onChange={(e) => edit({ notes: e.target.value })} />
          </div>
          {draft.id ? (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
              Active
            </label>
          ) : null}
        </EditPanel>
      ) : null}

      <ImportUnitsDialog open={importing} onClose={() => setImporting(false)} />
    </div>
  )
}
```

- [ ] **Step 4: Wire the section**

In `web/src/components/navModel.ts`, append to `ADMIN_SECTIONS` (after `Property settings`, so `AdminPage.test.tsx`'s first-six ordering holds):

```ts
  { to: '/app/admin/units', label: 'Maintainable units' },
  { to: '/app/admin/pm-templates', label: 'PM templates' },
```

In `web/src/features/admin/AdminPage.tsx`, import `UnitsAdmin` and add inside `<Routes>`:

```tsx
        <Route path="units" element={<UnitsAdmin />} />
```

(`pm-templates` gets its route in Task 20; until then its link renders an empty pane, which is one commit's worth of tolerable.)

- [ ] **Step 5: Verify and commit**

Run: `cd web && npx vitest run src/features/admin && npm run lint && npm run build`

```bash
git add web/src/features/admin/UnitsAdmin.tsx web/src/features/admin/ImportUnitsDialog.tsx web/src/features/admin/UnitsAdmin.test.tsx web/src/components/navModel.ts web/src/features/admin/AdminPage.tsx
git commit -m "feat(web): maintainable units admin with CSV import

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 20: Admin — PM templates and the recurrence builder

**Files:**
- Create: `web/src/features/admin/RecurrenceBuilder.tsx`, `web/src/features/admin/RecurrenceBuilder.test.tsx`
- Create: `web/src/features/admin/PmTemplatesAdmin.tsx`, `web/src/features/admin/PmTemplatesAdmin.test.tsx`
- Modify: `web/src/features/admin/AdminPage.tsx` (route)

**Interfaces:**
- Produces: `<RecurrenceBuilder value onChange>`, `parseSimpleRule(rrule) -> {freq, interval} | null`, `composeSimpleRule(freq, interval) -> string`.
- Consumes: `usePmTemplates`, `useCreatePmTemplate`, `usePatchPmTemplate`, `useUnits` (Task 13); `useDepartments`.

- [ ] **Step 1: Write the failing builder test**

Create `web/src/features/admin/RecurrenceBuilder.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { RecurrenceBuilder, composeSimpleRule, parseSimpleRule } from './RecurrenceBuilder'

/** The builder is a controlled input; a bare mock as `onChange` would leave `value` frozen and
 *  every keystroke would be typed against the stale string. This holds the state like the
 *  admin screen does and records each change. */
function Harness({ initial, onChange }: { initial: string; onChange: (rrule: string) => void }) {
  const [value, setValue] = useState(initial)
  return (
    <RecurrenceBuilder
      value={value}
      onChange={(next) => {
        setValue(next)
        onChange(next)
      }}
    />
  )
}

describe('recurrence rules', () => {
  it('round-trips the simple shape', () => {
    expect(composeSimpleRule('MONTHLY', 3)).toBe('FREQ=MONTHLY;INTERVAL=3')
    expect(composeSimpleRule('WEEKLY', 1)).toBe('FREQ=WEEKLY')
    expect(parseSimpleRule('FREQ=MONTHLY;INTERVAL=3')).toEqual({ freq: 'MONTHLY', interval: 3 })
    expect(parseSimpleRule('FREQ=DAILY')).toEqual({ freq: 'DAILY', interval: 1 })
    expect(parseSimpleRule('FREQ=WEEKLY;BYDAY=MO,WE')).toBeNull()
    expect(parseSimpleRule('')).toEqual({ freq: 'MONTHLY', interval: 1 })
  })

  it('composes from the controls and hands off to the raw field for anything else', async () => {
    const onChange = vi.fn()
    render(<Harness initial="FREQ=MONTHLY;INTERVAL=3" onChange={onChange} />)
    expect(screen.getByLabelText('Every')).toHaveValue(3)
    await userEvent.selectOptions(screen.getByLabelText('Period'), 'YEARLY')
    expect(onChange).toHaveBeenLastCalledWith('FREQ=YEARLY;INTERVAL=3')

    await userEvent.click(screen.getByRole('button', { name: 'Advanced' }))
    await userEvent.clear(screen.getByLabelText('RRULE'))
    await userEvent.type(screen.getByLabelText('RRULE'), 'FREQ=WEEKLY;BYDAY=MO')
    expect(onChange).toHaveBeenLastCalledWith('FREQ=WEEKLY;BYDAY=MO')
  })

  it('disables the controls while the rule is beyond what they can express', () => {
    render(<RecurrenceBuilder value="FREQ=WEEKLY;BYDAY=MO" onChange={() => {}} />)
    expect(screen.getByLabelText('Every')).toBeDisabled()
    expect(screen.getByLabelText('RRULE')).toHaveValue('FREQ=WEEKLY;BYDAY=MO')
  })
})
```

- [ ] **Step 2: The builder**

Create `web/src/features/admin/RecurrenceBuilder.tsx`:

```tsx
import { useState } from 'react'
import { Button, Input } from '../../components/ui'

export type SimpleFreq = 'DAILY' | 'WEEKLY' | 'MONTHLY' | 'YEARLY'
const FREQS: { value: SimpleFreq; label: string }[] = [
  { value: 'DAILY', label: 'days' },
  { value: 'WEEKLY', label: 'weeks' },
  { value: 'MONTHLY', label: 'months' },
  { value: 'YEARLY', label: 'years' },
]
const SIMPLE = /^FREQ=(DAILY|WEEKLY|MONTHLY|YEARLY)(?:;INTERVAL=(\d+))?$/

/** The subset the controls can express: FREQ plus an optional INTERVAL, nothing else.
 *  An empty rule reads as "every 1 month" so a new template starts somewhere sensible. */
export function parseSimpleRule(rrule: string): { freq: SimpleFreq; interval: number } | null {
  if (!rrule.trim()) return { freq: 'MONTHLY', interval: 1 }
  const match = SIMPLE.exec(rrule.trim())
  if (!match) return null
  return { freq: match[1] as SimpleFreq, interval: match[2] ? Number(match[2]) : 1 }
}

export function composeSimpleRule(freq: SimpleFreq, interval: number): string {
  return interval > 1 ? `FREQ=${freq};INTERVAL=${interval}` : `FREQ=${freq}`
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

/** "Every [n] [period]" for the common case, with the raw RRULE behind an Advanced toggle for
 *  everything RFC 5545 can say that the controls cannot. The controls disable themselves
 *  while the rule is one they could not faithfully re-emit. */
export function RecurrenceBuilder({ value, onChange }: { value: string; onChange: (rrule: string) => void }) {
  const simple = parseSimpleRule(value)
  const [advanced, setAdvanced] = useState(simple === null)
  const freq = simple?.freq ?? 'MONTHLY'
  const interval = simple?.interval ?? 1

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-end gap-2">
        <div>
          <label className={LABEL} htmlFor="rrule-interval">Every</label>
          <Input
            id="rrule-interval"
            type="number"
            min={1}
            className="w-20"
            value={interval}
            disabled={simple === null}
            onChange={(e) => onChange(composeSimpleRule(freq, Math.max(1, Number(e.target.value) || 1)))}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="rrule-freq">Period</label>
          <select
            id="rrule-freq"
            className={SELECT}
            value={freq}
            disabled={simple === null}
            onChange={(e) => onChange(composeSimpleRule(e.target.value as SimpleFreq, interval))}
          >
            {FREQS.map((f) => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>
        <Button variant="ghost" onClick={() => setAdvanced((a) => !a)}>Advanced</Button>
      </div>
      {advanced || simple === null ? (
        <div>
          <label className={LABEL} htmlFor="rrule-raw">RRULE</label>
          <Input id="rrule-raw" value={value} maxLength={500} onChange={(e) => onChange(e.target.value)}
                 placeholder="FREQ=MONTHLY;INTERVAL=3" />
          <p className="mt-1 text-xs text-text3">RFC 5545, without the RRULE: prefix. The start date below anchors it.</p>
        </div>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 3: Write the failing screen test**

Create `web/src/features/admin/PmTemplatesAdmin.test.tsx`:

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { TemplateOut, UnitOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { PmTemplatesAdmin } from './PmTemplatesAdmin'

const TEMPLATE: TemplateOut = {
  id: 't-1', name: 'Guest Room Quarterly', mode: 'sweep', departmentId: 'dept-eng', active: true,
  unitKind: 'guest_room', cadence: 'quarterly', rrule: null, rruleDtstart: null, lastFiredAt: null,
  unitIds: [], hasRuns: true, createdAt: '2026-09-01T00:00:00Z',
  items: [
    { id: 'i-1', position: 0, label: 'HVAC filter replaced', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
  ],
}
const BOILER: UnitOut = {
  id: 'u-b1', kind: 'equipment', code: 'BOILER-1', name: 'Boiler 1', floor: null, roomType: null,
  active: true, source: 'manual', externalId: null, notes: null, createdAt: '2026-09-01T00:00:00Z',
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (url.includes('maintainable-units')) return json([BOILER])
    if (init?.method === 'POST') return json({ ...TEMPLATE, id: 't-new' }, 201)
    if (init?.method === 'PATCH') return json(TEMPLATE)
    return json([TEMPLATE])
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <PmTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('PmTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('locks the mode on a template with runs and keeps item types fixed', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByText('Guest Room Quarterly'))
    expect(screen.getByLabelText('Mode')).toBeDisabled()
    expect(screen.getByLabelText('Cadence')).toHaveValue('quarterly')
    expect(screen.getByDisplayValue('HVAC filter replaced')).toBeInTheDocument()
    expect(screen.getByLabelText('Type for item 1')).toBeDisabled()
  })

  it('creates a scheduled template with a composed RRULE, targets and items', async () => {
    serve()
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'Boiler inspection')
    await userEvent.selectOptions(screen.getByLabelText('Mode'), 'scheduled')
    await userEvent.clear(screen.getByLabelText('Every'))
    await userEvent.type(screen.getByLabelText('Every'), '3')
    await userEvent.type(screen.getByLabelText('Starts on'), '2026-07-01')
    await userEvent.click(await screen.findByRole('checkbox', { name: /Boiler 1/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
    await userEvent.type(screen.getByLabelText('Label for item 1'), 'Pressure')
    await userEvent.selectOptions(screen.getByLabelText('Type for item 1'), 'number')
    await userEvent.type(screen.getByLabelText('Unit for item 1'), 'psi')
    await userEvent.type(screen.getByLabelText('Min for item 1'), '10')
    await userEvent.type(screen.getByLabelText('Max for item 1'), '30')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => {
      const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')!
      expect(JSON.parse(String(post[1]!.body))).toEqual({
        name: 'Boiler inspection', mode: 'scheduled', departmentId: null, active: true,
        unitKind: null, cadence: null, rrule: 'FREQ=MONTHLY;INTERVAL=3', rruleDtstart: '2026-07-01',
        unitIds: ['u-b1'],
        items: [{ label: 'Pressure', itemType: 'number', unit: 'psi', minValue: 10, maxValue: 30, required: true }],
      })
    })
  })
})
```

- [ ] **Step 4: The screen**

Create `web/src/features/admin/PmTemplatesAdmin.tsx`:

```tsx
import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreatePmTemplate, usePatchPmTemplate, usePmTemplates, useUnits } from '../../api/hooks/pm'
import { useDepartments } from '../../api/hooks/users'
import type {
  PmCadence, PmItemType, PmTemplateMode, PmUnitKind, TemplateItemIn, TemplateOut,
} from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { CADENCE_LABELS, ITEM_TYPE_LABELS, KIND_LABELS } from '../pm/labels'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { RecurrenceBuilder } from './RecurrenceBuilder'

type ItemDraft = {
  id?: string
  label: string
  itemType: PmItemType
  unit: string
  minValue: string
  maxValue: string
  required: boolean
}

type Draft = {
  id?: string
  name: string
  mode: PmTemplateMode
  departmentId: string
  active: boolean
  unitKind: PmUnitKind
  cadence: PmCadence
  rrule: string
  rruleDtstart: string
  unitIds: string[]
  items: ItemDraft[]
  hasRuns: boolean
}

const EMPTY: Draft = {
  name: '', mode: 'sweep', departmentId: '', active: true, unitKind: 'guest_room',
  cadence: 'quarterly', rrule: 'FREQ=MONTHLY', rruleDtstart: '', unitIds: [], items: [],
  hasRuns: false,
}
const NEW_ITEM: ItemDraft = { label: '', itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true }

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

function toItemIn(item: ItemDraft): TemplateItemIn {
  const number = item.itemType === 'number'
  return {
    ...(item.id ? { id: item.id } : {}),
    label: item.label.trim(),
    itemType: item.itemType,
    unit: number && item.unit.trim() ? item.unit.trim() : null,
    minValue: number && item.minValue.trim() !== '' ? Number(item.minValue) : null,
    maxValue: number && item.maxValue.trim() !== '' ? Number(item.maxValue) : null,
    required: item.required,
  }
}

function fromTemplate(t: TemplateOut): Draft {
  return {
    id: t.id, name: t.name, mode: t.mode, departmentId: t.departmentId ?? '', active: t.active,
    unitKind: t.unitKind ?? 'guest_room', cadence: t.cadence ?? 'quarterly',
    rrule: t.rrule ?? 'FREQ=MONTHLY', rruleDtstart: t.rruleDtstart ?? '', unitIds: [...t.unitIds],
    hasRuns: t.hasRuns,
    items: t.items.map((i) => ({
      id: i.id, label: i.label, itemType: i.itemType, unit: i.unit ?? '',
      minValue: i.minValue === null || i.minValue === undefined ? '' : String(i.minValue),
      maxValue: i.maxValue === null || i.maxValue === undefined ? '' : String(i.maxValue),
      required: i.required,
    })),
  }
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

export function PmTemplatesAdmin() {
  const { data, isPending, error } = usePmTemplates()
  const { data: departments } = useDepartments()
  const { data: units } = useUnits({ active: true })
  const create = useCreatePmTemplate()
  const patch = usePatchPmTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<TemplateOut | null>(null)
  const [unitFilter, setUnitFilter] = useState('')

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)

  const columns: Column<TemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'mode', head: 'Mode', render: (r) => <Badge>{r.mode === 'sweep' ? 'Sweep' : 'Scheduled'}</Badge> },
    {
      key: 'scope', head: 'Scope',
      render: (r) => r.mode === 'sweep'
        ? `${r.unitKind ? KIND_LABELS[r.unitKind] : ''} · ${r.cadence ? CADENCE_LABELS[r.cadence] : ''}`
        : `${r.unitIds.length} unit${r.unitIds.length === 1 ? '' : 's'} · ${r.rrule ?? ''}`,
    },
    { key: 'items', head: 'Items', mono: true, render: (r) => r.items.length },
    { key: 'active', head: 'Active', render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>) },
  ]

  function clearFailures() {
    create.reset()
    patch.reset()
  }

  function close() {
    clearFailures()
    setDraft(null)
    setSelected(null)
  }

  function edit(change: Partial<Draft>) {
    if (draft) setDraft({ ...draft, ...change })
  }

  function editItem(index: number, change: Partial<ItemDraft>) {
    if (!draft) return
    const items = draft.items.map((item, i) => (i === index ? { ...item, ...change } : item))
    setDraft({ ...draft, items })
  }

  function moveItem(index: number, delta: number) {
    if (!draft) return
    const target = index + delta
    if (target < 0 || target >= draft.items.length) return
    const items = [...draft.items]
    ;[items[index], items[target]] = [items[target]!, items[index]!]
    setDraft({ ...draft, items })
  }

  function open(template: TemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const sweep = draft.mode === 'sweep'
    const body = {
      name: draft.name.trim(),
      mode: draft.mode,
      departmentId: draft.departmentId || null,
      active: draft.active,
      unitKind: sweep ? draft.unitKind : null,
      cadence: sweep ? draft.cadence : null,
      rrule: sweep ? null : draft.rrule.trim(),
      rruleDtstart: sweep ? null : draft.rruleDtstart || null,
      unitIds: sweep ? [] : draft.unitIds,
      items: draft.items.map(toItemIn),
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  const filteredUnits = (units ?? []).filter((u) => {
    const needle = unitFilter.trim().toLowerCase()
    return !needle || u.code.toLowerCase().includes(needle) || u.name.toLowerCase().includes(needle)
  })

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">PM templates</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, items: [] })
            }}
          >
            New template
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load templates" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No PM templates" hint="A sweep template covers every unit of a kind on a cadence; a scheduled one raises work orders on a recurrence." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          subjectId={draft.id ?? 'new'}
          title={draft.id ? 'Edit template' : 'New template'}
          subtitle={draft.hasRuns ? 'This template has runs: its mode is fixed and removed items are retired, not deleted.' : undefined}
          saving={pending}
          error={failed?.message ?? null}
          onSave={save}
          onCancel={close}
        >
          <div>
            <label className={LABEL} htmlFor="tpl-name">Name</label>
            <Input id="tpl-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="tpl-mode">Mode</label>
            <select id="tpl-mode" className={SELECT} value={draft.mode} disabled={draft.hasRuns}
                    onChange={(e) => edit({ mode: e.target.value as PmTemplateMode })}>
              <option value="sweep">Sweep — every unit of a kind, each cycle</option>
              <option value="scheduled">Scheduled — work orders on a recurrence</option>
            </select>
            <FieldError message={fields.mode} />
          </div>
          <div>
            <label className={LABEL} htmlFor="tpl-dept">Department</label>
            <select id="tpl-dept" className={SELECT} value={draft.departmentId}
                    onChange={(e) => edit({ departmentId: e.target.value })}>
              <option value="">None</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </div>

          {draft.mode === 'sweep' ? (
            <>
              <div>
                <label className={LABEL} htmlFor="tpl-kind">Unit kind</label>
                <select id="tpl-kind" className={SELECT} value={draft.unitKind}
                        onChange={(e) => edit({ unitKind: e.target.value as PmUnitKind })}>
                  {(Object.keys(KIND_LABELS) as PmUnitKind[]).map((k) => (
                    <option key={k} value={k}>{KIND_LABELS[k]}</option>
                  ))}
                </select>
                <FieldError message={fields.unitKind} />
              </div>
              <div>
                <label className={LABEL} htmlFor="tpl-cadence">Cadence</label>
                <select id="tpl-cadence" className={SELECT} value={draft.cadence}
                        onChange={(e) => edit({ cadence: e.target.value as PmCadence })}>
                  {(Object.keys(CADENCE_LABELS) as PmCadence[]).map((c) => (
                    <option key={c} value={c}>{CADENCE_LABELS[c]}</option>
                  ))}
                </select>
                <FieldError message={fields.cadence} />
              </div>
            </>
          ) : (
            <>
              <RecurrenceBuilder value={draft.rrule} onChange={(rrule) => edit({ rrule })} />
              <FieldError message={fields.rrule} />
              <div>
                <label className={LABEL} htmlFor="tpl-dtstart">Starts on</label>
                <Input id="tpl-dtstart" type="date" value={draft.rruleDtstart}
                       onChange={(e) => edit({ rruleDtstart: e.target.value })} />
                <FieldError message={fields.rruleDtstart} />
              </div>
              <div>
                <p className={LABEL}>Units ({draft.unitIds.length} selected)</p>
                <Input placeholder="Filter units" value={unitFilter} className="mb-2 h-9"
                       onChange={(e) => setUnitFilter(e.target.value)} />
                <ul className="max-h-48 overflow-y-auto rounded border border-border2">
                  {filteredUnits.map((u) => (
                    <li key={u.id}>
                      <label className="flex items-center gap-2 px-2 py-1 text-sm">
                        <input
                          type="checkbox"
                          checked={draft.unitIds.includes(u.id)}
                          onChange={(e) =>
                            edit({
                              unitIds: e.target.checked
                                ? [...draft.unitIds, u.id]
                                : draft.unitIds.filter((id) => id !== u.id),
                            })
                          }
                        />
                        <span className="font-mono text-xs">{u.code}</span> {u.name}
                      </label>
                    </li>
                  ))}
                </ul>
                <FieldError message={fields.unitIds} />
              </div>
            </>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <div>
            <div className="mb-1 flex items-center">
              <p className={LABEL}>Checklist</p>
              <Button className="ml-auto" onClick={() => edit({ items: [...draft.items, { ...NEW_ITEM }] })}>
                Add item
              </Button>
            </div>
            <FieldError message={fields.items} />
            <ol className="flex flex-col gap-2">
              {draft.items.map((item, index) => {
                const n = index + 1
                return (
                  <li key={item.id ?? `new-${index}`} className="rounded border border-border2 p-2">
                    <div className="flex flex-col gap-2">
                      <Input aria-label={`Label for item ${n}`} value={item.label} maxLength={200}
                             placeholder="Label" onChange={(e) => editItem(index, { label: e.target.value })} />
                      <div className="flex gap-2">
                        <select aria-label={`Type for item ${n}`} className={SELECT} value={item.itemType}
                                disabled={Boolean(item.id)}
                                onChange={(e) => editItem(index, { itemType: e.target.value as PmItemType })}>
                          {(Object.keys(ITEM_TYPE_LABELS) as PmItemType[]).map((t) => (
                            <option key={t} value={t}>{ITEM_TYPE_LABELS[t]}</option>
                          ))}
                        </select>
                        <label className="flex items-center gap-1 text-xs">
                          <input type="checkbox" checked={item.required}
                                 onChange={(e) => editItem(index, { required: e.target.checked })} />
                          Required
                        </label>
                      </div>
                      {item.itemType === 'number' ? (
                        <div className="flex gap-2">
                          <Input aria-label={`Unit for item ${n}`} placeholder="Unit" className="w-20" maxLength={16}
                                 value={item.unit} onChange={(e) => editItem(index, { unit: e.target.value })} />
                          <Input aria-label={`Min for item ${n}`} type="number" placeholder="Min" step="any"
                                 value={item.minValue} onChange={(e) => editItem(index, { minValue: e.target.value })} />
                          <Input aria-label={`Max for item ${n}`} type="number" placeholder="Max" step="any"
                                 value={item.maxValue} onChange={(e) => editItem(index, { maxValue: e.target.value })} />
                        </div>
                      ) : null}
                      <div className="flex gap-1">
                        <Button variant="ghost" aria-label={`Move item ${n} up`} onClick={() => moveItem(index, -1)}>↑</Button>
                        <Button variant="ghost" aria-label={`Move item ${n} down`} onClick={() => moveItem(index, 1)}>↓</Button>
                        <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove item ${n}`}
                                onClick={() => edit({ items: draft.items.filter((_, i) => i !== index) })}>
                          Remove
                        </Button>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ol>
          </div>
        </EditPanel>
      ) : null}
    </div>
  )
}
```

In `web/src/features/admin/AdminPage.tsx`, import `PmTemplatesAdmin` and add:

```tsx
        <Route path="pm-templates" element={<PmTemplatesAdmin />} />
```

- [ ] **Step 5: Verify and commit**

Run: `cd web && npx vitest run src/features/admin && npm run lint && npm run build`

```bash
git add web/src/features/admin/RecurrenceBuilder.tsx web/src/features/admin/RecurrenceBuilder.test.tsx web/src/features/admin/PmTemplatesAdmin.tsx web/src/features/admin/PmTemplatesAdmin.test.tsx web/src/features/admin/AdminPage.tsx
git commit -m "feat(web): PM templates admin with recurrence builder

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 21: The Board link to a scheduled PM's checklist

**Files:**
- Modify: `web/src/test/factories.ts:165-167`
- Modify: `web/src/features/board/WorkOrderDetailPage.test.tsx` (append)
- Modify: `web/src/features/board/WorkOrderDetailPage.tsx:102-112`

- [ ] **Step 1: Write the failing test**

In `web/src/test/factories.ts`, `aWorkOrderDetail` gains the new field:

```ts
export function aWorkOrderDetail(over: Partial<WorkOrderDetail> = {}): WorkOrderDetail {
  return {
    ...aWorkOrder(), events: [], photos: [], guestName: 'Sarah Chen', roomNumber: '412',
    pmRunId: null, ...over,
  }
}
```

Append inside `describe('WorkOrderDetailPage', …)` in `WorkOrderDetailPage.test.tsx`:

```tsx
  it('links a scheduled-PM work order to its checklist', async () => {
    serve(aWorkOrderDetail({ type: 'pm', pmRunId: 'run-9' }))
    mount()
    expect(await screen.findByRole('link', { name: 'Open PM checklist' })).toHaveAttribute(
      'href', '/app/pm/runs/run-9')
  })

  it('shows no checklist link on an ordinary work order', async () => {
    serve(aWorkOrderDetail())
    mount()
    await screen.findByText('#w-204')
    expect(screen.queryByRole('link', { name: 'Open PM checklist' })).not.toBeInTheDocument()
  })
```

Run: `cd web && npx vitest run src/features/board/WorkOrderDetailPage.test.tsx`
Expected: the first new test fails.

- [ ] **Step 2: The link**

In `WorkOrderDetailPage.tsx`, inside the Description `<section>`, after the `sourceConversationId` paragraph:

```tsx
            {data.pmRunId ? (
              <p className="mt-3 text-xs text-text3">
                Scheduled preventative maintenance ·{' '}
                <Link to={`/app/pm/runs/${data.pmRunId}`} className="text-accent hover:underline">
                  Open PM checklist
                </Link>
              </p>
            ) : null}
```

- [ ] **Step 3: Verify and commit**

Run: `cd web && npm test && npm run lint && npm run build`
Expected: the whole web suite green.

```bash
git add web/src/test/factories.ts web/src/features/board/WorkOrderDetailPage.test.tsx web/src/features/board/WorkOrderDetailPage.tsx
git commit -m "feat(web): link a scheduled-PM work order to its checklist

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 22: Postgres verification, end-to-end run, spec reconciliation

**Files:**
- Modify: `docs/superpowers/specs/2026-09-19-preventative-maintenance-design.md` (four wording updates)

This task has no code of its own. It is the evidence that the feature works where it will actually run.

- [ ] **Step 1: The migration on PostgreSQL 18**

If the `relay-pg18` container from CLAUDE.md is not running, start it. Then, with a scratch database:

```
docker exec relay-pg18 psql -U relay -d relay_dev -c "DROP DATABASE IF EXISTS relay_pm_test;" -c "CREATE DATABASE relay_pm_test;"
cd server
DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_pm_test" ../.venv/Scripts/python.exe -m alembic upgrade head
DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_pm_test" ../.venv/Scripts/python.exe -m alembic downgrade 0006
DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_pm_test" ../.venv/Scripts/python.exe -m alembic upgrade head
```

Expected: three clean runs, no traceback. Then confirm the CHECK constraint really exists on Postgres:

```
docker exec relay-pg18 psql -U relay -d relay_pm_test -c "\d pm_template"
```

Expected: the table listing ends with `Check constraints:` including `"ck_pm_template_mode_fields"` and `"ck_enum_pmtemplatemode"`.

- [ ] **Step 2: Seed and run the whole app on Postgres**

```
docker exec relay-pg18 psql -U relay -d relay_dev -c "DROP DATABASE IF EXISTS relay_pm_dev;" -c "CREATE DATABASE relay_pm_dev;"
DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_pm_dev" ../.venv/Scripts/python.exe dev_start.py
```

(from `server/`; in a second terminal `cd web && npm run dev`). Expected on the first: `Seeded 2 properties, … work orders.` then `Starting server at http://127.0.0.1:5200`.

Walk the acceptance criteria in the browser as `sam@hvh.test` / `Password123!` (supervisor, Engineering) and `alex@hvh.test` (admin):

1. `/app/pm` — Guest Rooms tab shows Remaining 80 · 3rd Cycle · Completed 40 (the seed's 40 passed of 120), rows with Start / Continue / Awaiting inspection / Done.
2. Start a room, record 122 °F, upload a photo for the fan item, tick the checkboxes, Complete → row shows Awaiting inspection; `/app/board` has a new high-priority maintenance work order for that room; Alerts has a `pm.out_of_range` notification for Sam.
3. `/app/inspection` — the run is queued; Fail with a note → the room is back under Remaining; Pass a second run → Completed increments.
4. `/app/pm/compliance` — last quarter shows 110/10 and this quarter's live numbers.
5. `/app/admin/units` — Import CSV with `fixtures/maintainable_units.sample.csv` → "0 created, 138 updated". Edit one line's `kind` to `gadget`, import again → the dialog lists Line N / kind / the message and nothing changes.
6. `/app/board` — the two seeded `Boiler inspection` work orders; open one → **Open PM checklist** → Start PM → answer → Complete → the work order is Complete; Pass it under `/app/inspection` → Verified.

Anything that does not match is a defect to fix in the task that owns it before continuing — not something to note and move past.

- [ ] **Step 3: Reconcile the spec with what was built**

Four places where the implementation sharpened the spec. Update the spec so it describes the code:

1. **§3.2 / §4.1 `last_fired_at`:** it is stamped `clock.now()` when a scheduled template is created (and whenever its mode, rrule or start date changes); the expansion window is always `(last_fired_at, now]`. Replace §4.1 Phase B steps 1–2 with that rule and delete the "[dtstart, window_end]" case.
2. **§5.3:** replace "Remaining is a `NOT EXISTS` subquery; last passed is a correlated max" with "Remaining, current runs and last-passed are computed in one pass from three set queries per property (active units, runs in the open cycle, passed runs); nothing is queried per row."
3. **§5.4:** a rejected import is `422` with code `IMPORT_REJECTED` and the report as `error.details`, not a bare payload.
4. **§5.5:** `onTimePct` and `inspectionPassRate` are percentages (0–100, one decimal).
5. **§7.1:** the inspection queue lives at `/app/inspection`, a sibling of `/app/pm`, so the Preventative Maintenance rail entry (which matches the `/app/pm` prefix) does not light on it.

```bash
git add docs/superpowers/specs/2026-09-19-preventative-maintenance-design.md
git commit -m "docs: reconcile the PM spec with the implementation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Final full verification**

```
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
cd web && npm test && npm run lint && npm run build
```

Expected: every suite green, both linters clean, the build succeeds. Then hand off through `superpowers:finishing-a-development-branch`. **Pushing `main` to GitHub deploys to production** (CLAUDE.md), and `docker-entrypoint.sh` runs `alembic upgrade head` before gunicorn — so the merge-and-push is the user's call, made after they have seen Steps 1–2 pass.
