# Shift Checklists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship per-department, per-shift checklists with typed readings — generated on a weekly
schedule or started on demand, claimable or assignable, missed when their shift ends, with
out-of-range readings raising work orders — reusing preventative maintenance's typed-item logic.

**Architecture:** Five new tables (`checklist_template`, `checklist_template_item`,
`checklist_instance`, `checklist_answer`, `checklist_photo`) in migration `0009`. PM's answer
rules move into one shared module, `app/domain/typed_items.py`, that both features call; PM's
wire models (`TemplateItemIn/Out`, `AnswerPatch`, `RunAnswerOut`, `RunPhotoOut`) are reused so
PM's `ChecklistItem` React component renders checklist rows unchanged. A stateless
`checklist.tick` generates today's instances and marks ended ones missed.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · pytest; Vite +
React + TypeScript + TanStack Query + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-25-shift-checklists-design.md` — read it before any
task. Where this plan is more precise than the spec, "Spec clarifications" says so.

## Global Constraints

- Python by explicit path only: `cd server && ../.venv/Scripts/python.exe -m pytest -q`. Bare
  `python` is a silent Windows Store stub.
- Lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` — line length 100.
- Frontend: `cd web && npm test && npm run lint && npm run build` — all three clean.
- Engine-portable SQL only: no JSON filtering, no partial indexes, no Postgres-only functions;
  pin NULL ordering with `.nulls_last()` where it matters.
- Every enum column through `enum_type()`; in migrations through the local `_enum()` helper.
- Times from `app.clock.now()` (aware UTC). Property-local dates through
  `pm_cycles.local_today` and the new `shifts` helpers — never a UTC date.
- `ValidationFailed` is HTTP 400 `VALIDATION_FAILED`; `TransitionError` / `Conflict` are 409.
- API models subclass `CamelModel`; checklist-specific models are prefixed `Checklist`.
- After any schema change: `cd server && ../.venv/Scripts/python.exe -m
  app.schemas.export_json_schema`, then `cd web && npm run gen:types`, then re-export the new
  names from `web/src/api/types.ts`. Never hand-edit the generated files.
- `server/app/auth/permissions.py` and `web/src/auth/capabilities.ts` change in the same
  commit; every new capability includes `Role.admin`.
- SQLite enforces foreign keys (`PRAGMA foreign_keys = 1`).
- Commit after every task, message ending with a `Co-Authored-By:` trailer naming the model that
  wrote it. **Do not push** until Task 16 — pushing `main` deploys to production.

## Spec clarifications (decided while planning)

1. **The tick never generates an instance whose shift window has already ended.** Otherwise a
   mid-afternoon deploy (or a template created at 16:00) would produce today's AM instance and
   the same pass would mark it missed — a "miss" nobody could have prevented.
2. **Checklist work orders use `location_type = other`** with no location ref; the title carries
   the reading and the checklist name (`"Pool pH 8.1 out of range (7.2–7.8) — Engineering AM
   Rounds"`), built by the shared `typed_items.out_of_range_title`.
3. **`weekdays` bit 0 is Monday … bit 6 is Sunday** (Python's `date.weekday()`), valid range
   1–127.
4. **Progress on a list row = satisfied items / total items**, using the shared "is answered"
   rule (a required checkbox must be ticked; a photo item needs a photo). Before an instance is
   started it counts the template's active items, with 0 satisfied.
5. **`_boundary` moves from `app/domain/log.py` into the new `app/domain/shifts.py`** as the
   public `boundary(raw, key)`, and `log.py` imports it — one parser for shift boundaries, not two.
6. **Seed determinism:** the seed never relies on the time of day for anything `test_seed`
   asserts. It plants yesterday's instances directly through `ck_instances.ensure_instance` and
   asserts only those; today's instances depend on when the seed runs and are not asserted.

## Review Focus

1. **A shift boundary edited in Property settings while instances exist** — existing instances
   must be judged against the *current* boundaries without crashing, and an instance must never be
   missed before the (new) end of its shift. → Task 4 (`test_window_follows_edited_boundaries`)
   and Task 7 (`test_missed_uses_current_boundaries`).
2. **A template deactivated or edited mid-shift** — today's already-generated instance stays and a
   started instance keeps its item snapshot. → Task 6 (`test_editing_a_template_never_changes_a_started_instance`),
   Task 7 (`test_deactivated_template_keeps_todays_instance`).
3. **Two people start the same open instance at once** (double tap, two staff) — the second must
   get a 409, not a second set of answers. → Task 6 (`test_starting_twice_is_a_409`).
4. **A staff member with no department** (managers, admins) — can see every department's
   checklists and act on them via the supervisor exemption; a `dept_staff` from another department
   cannot. → Task 6 (`test_other_department_staff_are_refused`), Task 8 (`test_list_without_department_filter_shows_all`).
5. **A required photo item** — Complete stays blocked until a photo carrying that item's id
   exists, and a general (no-item) photo does not satisfy it. → Task 6
   (`test_required_photo_item_needs_its_own_photo`).

## File map

**Server — create:** `app/domain/typed_items.py`, `app/domain/shifts.py`,
`app/models/checklists.py`, `alembic/versions/0009_shift_checklists.py`,
`app/domain/ck_templates.py`, `app/domain/ck_instances.py`, `app/domain/ck_photos.py`,
`app/domain/ck_tick.py`, `app/domain/ck_views.py`, `app/schemas/checklists.py`,
`app/api/checklists.py`, `app/queue/handlers/checklists.py`; tests `tests/ck_helpers.py`,
`test_typed_items.py`, `test_shifts.py`, `test_ck_models.py`, `test_ck_permissions.py`,
`test_ck_templates.py`, `test_ck_instances.py`, `test_ck_tick.py`, `test_ck_views.py`,
`test_ck_api.py`.

**Server — modify:** `app/domain/pm_runs.py`, `app/domain/pm_templates.py`, `app/domain/log.py`,
`app/schemas/enums.py`, `app/models/__init__.py`, `app/auth/permissions.py`, `app/__init__.py`,
`app/queue/jobs.py`, `app/queue/handlers/__init__.py`, `app/schemas/export_json_schema.py`,
`seed/seed.py`, `tests/test_models.py`, `tests/test_schema_export.py`, `tests/test_seed.py`,
`data/app.db`.

**Web — create:** `api/hooks/checklists.ts`, `features/admin/ItemListEditor.tsx` (+test),
`features/admin/ChecklistTemplatesAdmin.tsx` (+test), `features/checklists/labels.ts`,
`features/checklists/ChecklistsPage.tsx` (+test), `features/checklists/ChecklistRunPage.tsx`
(+test).

**Web — modify:** `auth/capabilities.ts` (+test), `api/queryKeys.ts`, `api/ws.ts` (+test),
`api/types.ts`, `components/navModel.ts` (+test), `components/NavIcon.tsx`, `routes.tsx`,
`features/admin/AdminPage.tsx`, `features/admin/PmTemplatesAdmin.tsx`, and any test that
enumerates nav entries (e.g. `components/CommandPalette.test.tsx`).

---

### Task 1: Extract the typed-item rules from PM

**Files:**
- Create: `server/app/domain/typed_items.py`
- Modify: `server/app/domain/pm_runs.py` (`save_answer`, `missing_required`, `_escalation_targets`,
  `_fmt`, the title in `_raise_out_of_range`, and remove `VALUE_COLUMN`/`WIRE_NAME`)
- Modify: `server/app/domain/pm_templates.py` (`_sync_items` → shared)
- Test: `server/tests/test_typed_items.py`

**Interfaces:**
- Produces (in `app.domain.typed_items`): `VALUE_COLUMN`, `WIRE_NAME`,
  `apply_answer(item, answer, data: AnswerPatch) -> None`,
  `is_answered(item, answer, photographed: set[str]) -> bool`,
  `sync_items(db, item_model: type, template, items: list[TemplateItemIn]) -> None`,
  `escalation_targets(db, property_id: str, department_id: str | None) -> list[str]`,
  `fmt(value: float | None) -> str`, `out_of_range_title(item, answer, where: str) -> str`.
  Items and answers are duck-typed: any object with PM's item columns (`item_type`, `label`,
  `unit`, `min_value`, `max_value`, `required`, `id`) and answer columns (`bool_value`,
  `text_value`, `number_value`, `out_of_range`, `answered_at`).

- [ ] **Step 1: Write the failing test** — `server/tests/test_typed_items.py`:

```python
"""The typed-item rules PM and shift checklists share (checklists spec §2.2)."""
from types import SimpleNamespace

import pytest

from app.domain import typed_items
from app.errors import ValidationFailed
from app.schemas.enums import PmItemType
from app.schemas.pm import AnswerPatch


def item(item_type, **kw):
    base = dict(id="i1", label="Pool pH", item_type=item_type, unit=None, min_value=None,
                max_value=None, required=True)
    base.update(kw)
    return SimpleNamespace(**base)


def answer():
    return SimpleNamespace(bool_value=None, text_value=None, number_value=None,
                           out_of_range=False, answered_at=None)


def test_number_answer_flags_out_of_range_exclusive_of_the_bounds():
    it = item(PmItemType.number, min_value=7.2, max_value=7.8)
    a = answer()
    typed_items.apply_answer(it, a, AnswerPatch(number_value=7.8))
    assert (a.number_value, a.out_of_range) == (7.8, False)
    assert a.answered_at is not None  # a unit test: the clock is not frozen here
    typed_items.apply_answer(it, a, AnswerPatch(number_value=8.1))
    assert a.out_of_range is True
    typed_items.apply_answer(it, a, AnswerPatch(number_value=None))
    assert (a.out_of_range, a.answered_at) == (False, None)


def test_text_is_trimmed_and_blank_means_unanswered():
    a = answer()
    typed_items.apply_answer(item(PmItemType.text), a, AnswerPatch(text_value="   "))
    assert (a.text_value, a.answered_at) == (None, None)


def test_the_wrong_field_for_the_type_is_refused():
    with pytest.raises(ValidationFailed):
        typed_items.apply_answer(item(PmItemType.checkbox), answer(),
                                 AnswerPatch(number_value=1))


def test_a_photo_item_cannot_be_answered_by_patch():
    with pytest.raises(ValidationFailed):
        typed_items.apply_answer(item(PmItemType.photo), answer(), AnswerPatch(bool_value=True))


def test_is_answered_per_type():
    a = answer()
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is False
    a.bool_value = False
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is False  # must be ticked
    a.bool_value = True
    assert typed_items.is_answered(item(PmItemType.checkbox), a, set()) is True
    assert typed_items.is_answered(item(PmItemType.photo), answer(), {"i1"}) is True
    assert typed_items.is_answered(item(PmItemType.photo), answer(), set()) is False


def test_out_of_range_title_names_the_reading_and_where():
    it = item(PmItemType.number, unit="", min_value=7.2, max_value=7.8)
    a = answer()
    a.number_value = 8.1
    assert typed_items.out_of_range_title(it, a, "Engineering AM Rounds") == \
        "Pool pH 8.1 out of range (7.2–7.8) — Engineering AM Rounds"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_typed_items.py -q`
Expected: FAIL — `ImportError: cannot import name 'typed_items'`.

- [ ] **Step 3: Create `server/app/domain/typed_items.py`** by moving, not rewriting:

```python
"""Typed checklist items shared by preventative maintenance and shift checklists.

Items and answers are duck-typed: PmTemplateItem / ChecklistTemplateItem and PmRunAnswer /
ChecklistAnswer carry the same columns, so one set of rules serves both — a fix here fixes both.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import ValidationFailed
from app.models import PropertyMembership, UserAccount
from app.schemas.enums import PmItemType, Role, UserStatus
from app.schemas.pm import AnswerPatch, TemplateItemIn

VALUE_COLUMN: dict[PmItemType, str] = {
    PmItemType.checkbox: "bool_value",
    PmItemType.text: "text_value",
    PmItemType.number: "number_value",
}
WIRE_NAME = {"bool_value": "boolValue", "text_value": "textValue", "number_value": "numberValue"}


def apply_answer(item: Any, answer: Any, data: AnswerPatch) -> None:
    """Validate a typed answer and write it onto `answer`, stamping answered_at and out_of_range."""
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


def is_answered(item: Any, answer: Any, photographed: set[str]) -> bool:
    """A required checkbox must be ticked, not merely answered; a photo item is satisfied by a
    photo carrying its id."""
    if item.item_type == PmItemType.checkbox:
        return answer.bool_value is True
    if item.item_type == PmItemType.text:
        return bool(answer.text_value)
    if item.item_type == PmItemType.number:
        return answer.number_value is not None
    return item.id in photographed
```

Then move `_sync_items` from `pm_templates.py` here **verbatim** as
`sync_items(db: Session, item_model: type, template: Any, items: list[TemplateItemIn]) -> None`,
replacing every `PmTemplateItem` with `item_model` (the query becomes
`select(item_model).where(item_model.template_id == template.id)` and the constructor
`item_model(template_id=..., ...)`). Keep its docstring and its "pushed past the live range"
comment. Move `_escalation_targets` here verbatim as `escalation_targets` and `_fmt` as `fmt`,
and add:

```python
def out_of_range_title(item: Any, answer: Any, where: str) -> str:
    return (f"{item.label} {fmt(answer.number_value)}{item.unit or ''} out of range "
            f"({fmt(item.min_value)}–{fmt(item.max_value)}) — {where}")[:200]
```

- [ ] **Step 4: Point PM at the shared module**

`pm_runs.py`: delete `VALUE_COLUMN`, `WIRE_NAME`, `_escalation_targets`, `_fmt`. In
`save_answer`, replace everything from `column = VALUE_COLUMN.get(...)` through the
`out_of_range` assignment with `typed_items.apply_answer(item, answer, data)` (keep the status
check, the answer lookup, `db.flush()` and `return answer`). In `missing_required`, replace the
if/elif chain with `if not typed_items.is_answered(item, answer, photographed): missing.append(item.id)`.
In `_raise_out_of_range`, use `typed_items.escalation_targets(...)` and
`title = typed_items.out_of_range_title(item, answer, unit.name)`.
`pm_templates.py`: delete `_sync_items`; both call sites become
`typed_items.sync_items(db, PmTemplateItem, t, data.items)`. Drop imports this leaves unused.

- [ ] **Step 5: Run the new tests and PM's whole suite**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_typed_items.py tests/test_pm_runs.py tests/test_pm_templates.py tests/test_pm_inspection.py tests/test_pm_tick.py tests/test_pm_reports.py -q`
Expected: PASS — PM behaviour unchanged. Then the full server suite and ruff.

- [ ] **Step 6: Commit**

```bash
git add server/app/domain/typed_items.py server/app/domain/pm_runs.py server/app/domain/pm_templates.py server/tests/test_typed_items.py
git commit -m "refactor(pm): extract typed-item rules into a shared module"
```

---

### Task 2: Enums, models and migration `0009`

**Files:**
- Modify: `server/app/schemas/enums.py` (append), `server/app/models/__init__.py`,
  `server/tests/test_models.py` (`EXPECTED_TABLES`)
- Create: `server/app/models/checklists.py`, `server/alembic/versions/0009_shift_checklists.py`
- Test: `server/tests/test_ck_models.py`

**Interfaces:**
- Produces: enums `ChecklistSchedule` (`weekly`, `on_demand`), `ChecklistStatus` (`open`,
  `in_progress`, `complete`, `missed`); models `ChecklistTemplate`, `ChecklistTemplateItem`,
  `ChecklistInstance`, `ChecklistAnswer`, `ChecklistPhoto` exported from `app.models`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_models.py` — add to `EXPECTED_TABLES`:
`"checklist_template", "checklist_template_item", "checklist_instance", "checklist_answer",
"checklist_photo",`.

`server/tests/test_ck_models.py`:

```python
"""Shift-checklist schema (checklists spec §2, §6)."""
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import ChecklistInstance, ChecklistTemplate
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx, **kw):
    t = ChecklistTemplate(property_id=fx.property_a.id, name="AM Rounds",
                          department_id=fx.dept_engineering.id, **kw)
    db.add(t)
    db.flush()
    return t


def test_weekly_template_needs_a_shift_and_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=None)
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=0)


def test_on_demand_template_has_neither_shift_nor_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.on_demand, shift=Shift.am, weekdays=None)
    with database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.on_demand, shift=None, weekdays=None)


def _instance(db, t, slot):
    db.add(ChecklistInstance(property_id=t.property_id, template_id=t.id,
                             due_date=date(2026, 9, 10), shift=Shift.am, slot=slot,
                             status=ChecklistStatus.open))
    db.flush()


def test_scheduled_slot_is_unique_but_on_demand_slots_repeat(database, fx):
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.weekly, shift=Shift.am, weekdays=127)
        _instance(db, t, None)
        _instance(db, t, None)  # NULLs are distinct: on-demand may repeat
        _instance(db, t, 0)
        tid = t.id
    with pytest.raises(IntegrityError), database.session() as db:
        _instance(db, db.get(ChecklistTemplate, tid), 0)


def test_0009_downgrades_and_reupgrades(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    assert "checklist_instance" in sa.inspect(engine).get_table_names()
    command.downgrade(cfg, "0008")
    assert "checklist_template" not in sa.inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert "checklist_photo" in sa.inspect(engine).get_table_names()
    engine.dispose()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_models.py tests/test_models.py -q`
Expected: FAIL — `ImportError` / missing tables.

- [ ] **Step 3: Append the enums** to `server/app/schemas/enums.py`:

```python
class ChecklistSchedule(StrEnum):
    weekly = "weekly"
    on_demand = "on_demand"


class ChecklistStatus(StrEnum):
    open = "open"
    in_progress = "in_progress"
    complete = "complete"
    missed = "missed"
```

- [ ] **Step 4: Create `server/app/models/checklists.py`**

```python
"""Shift checklists (checklists spec §2). Items and answers carry exactly PM's typed columns so
app.domain.typed_items serves both features."""
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
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.models.pm import READING
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, PmItemType, Shift


class ChecklistTemplate(TimestampMixin, Base):
    __tablename__ = "checklist_template"
    __table_args__ = (
        CheckConstraint(
            "(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
            "AND weekdays > 0) OR "
            "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)",
            name="ck_checklist_template_schedule_fields",
        ),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[str] = mapped_column(ForeignKey("department.id"), nullable=False)
    schedule: Mapped[ChecklistSchedule] = mapped_column(enum_type(ChecklistSchedule),
                                                        nullable=False)
    shift: Mapped[Shift | None] = mapped_column(enum_type(Shift))
    # Bit 0 = Monday … bit 6 = Sunday (date.weekday()); an integer, not JSON, for portability.
    weekdays: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChecklistTemplateItem(TimestampMixin, Base):
    """PM's item columns exactly; soft-deleted via `active` so old answers keep their item."""

    __tablename__ = "checklist_template_item"
    template_id: Mapped[str] = mapped_column(ForeignKey("checklist_template.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type: Mapped[PmItemType] = mapped_column(enum_type(PmItemType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    min_value: Mapped[float | None] = mapped_column(READING)
    max_value: Mapped[float | None] = mapped_column(READING)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChecklistInstance(TimestampMixin, Base):
    """`slot` is 0 on scheduled instances and NULL on on-demand ones: the unique key below makes
    generation idempotent while NULLs (distinct on both engines) let on-demand runs repeat."""

    __tablename__ = "checklist_instance"
    __table_args__ = (
        UniqueConstraint("template_id", "due_date", "shift", "slot",
                         name="uq_checklist_instance_slot"),
        Index("ix_checklist_instance_property_due", "property_id", "due_date"),
        Index("ix_checklist_instance_property_status", "property_id", "status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False)
    template_id: Mapped[str] = mapped_column(ForeignKey("checklist_template.id"), nullable=False,
                                             index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[Shift] = mapped_column(enum_type(Shift), nullable=False)
    slot: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ChecklistStatus] = mapped_column(
        enum_type(ChecklistStatus), default=ChecklistStatus.open, nullable=False)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    completed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    comment: Mapped[str | None] = mapped_column(Text)


class ChecklistAnswer(TimestampMixin, Base):
    __tablename__ = "checklist_answer"
    __table_args__ = (
        UniqueConstraint("instance_id", "item_id", name="uq_checklist_answer_instance_item"),
    )
    instance_id: Mapped[str] = mapped_column(ForeignKey("checklist_instance.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("checklist_template_item.id"), nullable=False)
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(READING)
    out_of_range: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ChecklistPhoto(TimestampMixin, Base):
    """Bytes in the table, `data` deferred and NOT NULL — as every photo table."""

    __tablename__ = "checklist_photo"
    instance_id: Mapped[str] = mapped_column(ForeignKey("checklist_instance.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("checklist_template_item.id"))
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
```

Export all five from `app/models/__init__.py` (import line + `__all__`, alphabetical).

- [ ] **Step 5: Create `server/alembic/versions/0009_shift_checklists.py`** in 0008's style —
revision `"0009"`, down `"0008"`, the same `_enum()` / `_timestamps()` helpers. Enum constraint
names: `ck_enum_checklistschedule`, `ck_enum_shift`, `ck_enum_pmitemtype`,
`ck_enum_checkliststatus` (reusing a name on a different table is fine — 0008 does it). Tables
in FK order `checklist_template` → `checklist_template_item` → `checklist_instance` →
`checklist_answer` → `checklist_photo`, each column exactly as the model (nullability included —
`checklist_photo.data` is `nullable=False`; `number_value`/`min_value`/`max_value` are
`sa.Numeric(10, 2, asdecimal=False)`), with the model's CHECK, unique constraints and named
indexes, plus a `batch_op.f("ix_<table>_<col>")` index for every `index=True` column. No backfill.
`downgrade()` drops the five tables children-first.

- [ ] **Step 6: Verify the migration matches the models**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_models.py tests/test_models.py -q` → PASS.
Then check drift with a throwaway script (do not commit it):

```bash
cd server && ../.venv/Scripts/python.exe -c "
from app.db import run_migrations, Base; import app.models, sqlalchemy as sa, tempfile, os
from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata
p=os.path.join(tempfile.mkdtemp(),'d.db'); u='sqlite:///'+p.replace(os.sep,'/'); run_migrations(u)
e=sa.create_engine(u); print([d for d in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata) if 'checklist' in str(d)])"
```

Expected: `[]`. Fix any difference in the migration, then run the full server suite and ruff.

- [ ] **Step 7: Commit**

```bash
git add server/app/schemas/enums.py server/app/models/checklists.py server/app/models/__init__.py server/alembic/versions/0009_shift_checklists.py server/tests/test_ck_models.py server/tests/test_models.py
git commit -m "feat(checklists): models and migration 0009"
```

---

### Task 3: Capabilities (server and web, same commit)

**Files:** Modify `server/app/auth/permissions.py`, `web/src/auth/capabilities.ts`
(+ `capabilities.test.ts`). Test: `server/tests/test_ck_permissions.py`.

**Interfaces:** Produces `view_checklists`, `perform_checklists`, `manage_checklists`.

- [ ] **Step 1: Write the failing server test** — `server/tests/test_ck_permissions.py`:

```python
"""Checklists spec §4.3. Every one includes admin — test_isolation.py demands it."""
from app.auth.permissions import CAPABILITIES, STAFF, has_capability
from app.schemas.enums import Role


def test_checklist_capabilities_match_the_spec():
    assert CAPABILITIES["view_checklists"] == STAFF
    assert CAPABILITIES["perform_checklists"] == {Role.agent, Role.dept_staff, Role.supervisor,
                                                  Role.manager, Role.admin}
    assert CAPABILITIES["manage_checklists"] == {Role.supervisor, Role.manager, Role.admin}
    for cap in ("view_checklists", "perform_checklists", "manage_checklists"):
        assert has_capability(Role.admin, cap), cap
    assert not has_capability(Role.corporate, "perform_checklists")
    assert not has_capability(Role.dept_staff, "manage_checklists")
```

- [ ] **Step 2: Write the failing web test** — append to `web/src/auth/capabilities.test.ts`:

```ts
describe('checklist capabilities', () => {
  it('mirrors server/app/auth/permissions.py', () => {
    expect(hasCapability('corporate', 'view_checklists')).toBe(true)
    expect(hasCapability('agent', 'perform_checklists')).toBe(true)
    expect(hasCapability('corporate', 'perform_checklists')).toBe(false)
    expect(hasCapability('dept_staff', 'manage_checklists')).toBe(false)
    expect(hasCapability('supervisor', 'manage_checklists')).toBe(true)
    for (const cap of ['view_checklists', 'perform_checklists', 'manage_checklists'] as const) {
      expect(hasCapability('admin', cap)).toBe(true)
    }
  })
})
```

- [ ] **Step 3: Run both to verify they fail**, then implement:

`permissions.py`, inside `CAPABILITIES` after the housekeeping block:

```python
    # Shift checklists (checklists spec §4.3). All include admin, as above. Front desk (agent)
    # performs its own opening/closing checklists.
    "view_checklists": STAFF,
    "perform_checklists": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager,
                           Role.admin},
    "manage_checklists": {Role.supervisor, Role.manager, Role.admin},
```

`capabilities.ts`: add the three names to the `Capability` union and

```ts
  view_checklists: STAFF,
  perform_checklists: ['agent', 'dept_staff', 'supervisor', 'manager', 'admin'],
  manage_checklists: ['supervisor', 'manager', 'admin'],
```

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_permissions.py tests/test_isolation.py -q`
and `cd web && npx vitest run src/auth/capabilities.test.ts && npm run lint` → PASS.

- [ ] **Step 5: Commit (all four files together)**

```bash
git add server/app/auth/permissions.py server/tests/test_ck_permissions.py web/src/auth/capabilities.ts web/src/auth/capabilities.test.ts
git commit -m "feat(checklists): capabilities, mirrored server and web"
```

---

### Task 4: Shift windows

**Files:** Create `server/app/domain/shifts.py`; modify `server/app/domain/log.py`; test
`server/tests/test_shifts.py`.

**Interfaces:**
- Produces (in `app.domain.shifts`): `boundary(raw: dict, key: str) -> time` (moved from
  `log._boundary`), `shift_window(prop, day: date, shift: Shift) -> tuple[datetime, datetime]`
  (aware UTC), `current_shift(prop, at: datetime) -> tuple[date, Shift]`.

- [ ] **Step 1: Write the failing test** — `server/tests/test_shifts.py`:

```python
"""Shift windows (checklists spec §3.1). HVH is New York (EDT = UTC-4 until 2026-11-01), LSI
Chicago. Default boundaries: am 07:00, pm 15:00, overnight 23:00."""
from datetime import UTC, date, datetime

from app.domain import shifts
from app.models import Property
from app.schemas.enums import Shift


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_default_windows(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        d = date(2026, 9, 10)
        assert shifts.shift_window(p, d, Shift.am) == (utc(2026, 9, 10, 11), utc(2026, 9, 10, 19))
        assert shifts.shift_window(p, d, Shift.pm) == (utc(2026, 9, 10, 19), utc(2026, 9, 11, 3))
        assert shifts.shift_window(p, d, Shift.overnight) == (utc(2026, 9, 11, 3),
                                                              utc(2026, 9, 11, 11))


def test_current_shift_after_midnight_is_the_previous_days_overnight(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        assert shifts.current_shift(p, utc(2026, 9, 11, 6)) == (date(2026, 9, 10),
                                                                Shift.overnight)
        assert shifts.current_shift(p, utc(2026, 9, 11, 12)) == (date(2026, 9, 11), Shift.am)


def test_window_follows_edited_boundaries(database, fx):
    """Review focus 1: boundaries are read at call time, never cached."""
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        p.settings = {**(p.settings or {}),
                      "shift_boundaries": {"am": "06:00", "pm": "14:00", "overnight": "22:00"}}
        db.flush()
        assert shifts.shift_window(p, date(2026, 9, 10), Shift.am) == (utc(2026, 9, 10, 10),
                                                                       utc(2026, 9, 10, 18))


def test_overnight_across_the_dst_change_has_its_true_length(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        start, end = shifts.shift_window(p, date(2026, 10, 31), Shift.overnight)
        assert (start, end) == (utc(2026, 11, 1, 3), utc(2026, 11, 1, 12))  # 9 hours, not 8


def test_each_property_uses_its_own_zone(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_b.id)
        assert shifts.shift_window(p, date(2026, 9, 10), Shift.am) == (utc(2026, 9, 10, 12),
                                                                       utc(2026, 9, 10, 20))
```

- [ ] **Step 2: Run to verify it fails** (`ImportError`).

- [ ] **Step 3: Implement `server/app/domain/shifts.py`**

```python
"""Shift windows (checklists spec §3.1), on the same configurable boundaries as the hotel log's
shift_for. Boundaries are read from settings on every call, so an edit applies immediately."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Property
from app.schemas.enums import Shift

DEFAULT_SHIFT_BOUNDARIES = {"am": "07:00", "pm": "15:00", "overnight": "23:00"}


def boundary(raw: dict, key: str) -> time:
    value = raw.get(key) or DEFAULT_SHIFT_BOUNDARIES[key]
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute))


def _raw(prop: Property) -> dict:
    return (prop.settings or {}).get("shift_boundaries") or {}


def _at(prop: Property, day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=ZoneInfo(prop.timezone)).astimezone(UTC)


def shift_window(prop: Property, day: date, shift: Shift) -> tuple[datetime, datetime]:
    """`day` is the date the shift starts; overnight ends at the next morning's am boundary."""
    raw = _raw(prop)
    am, pm, overnight = boundary(raw, "am"), boundary(raw, "pm"), boundary(raw, "overnight")
    if shift is Shift.am:
        return _at(prop, day, am), _at(prop, day, pm)
    if shift is Shift.pm:
        return _at(prop, day, pm), _at(prop, day, overnight)
    return _at(prop, day, overnight), _at(prop, day + timedelta(days=1), am)


def current_shift(prop: Property, at: datetime) -> tuple[date, Shift]:
    """The shift `at` falls in, and the date that shift started (02:00 → yesterday's overnight)."""
    from app.domain.log import shift_for  # local import: log imports `boundary` from here
    shift = shift_for(prop, at)
    local = at.astimezone(ZoneInfo(prop.timezone))
    day = local.date()
    if shift is Shift.overnight and local.time() < boundary(_raw(prop), "am"):
        day -= timedelta(days=1)
    return day, shift
```

In `server/app/domain/log.py`: delete `DEFAULT_SHIFT_BOUNDARIES` and `_boundary`, add
`from app.domain.shifts import DEFAULT_SHIFT_BOUNDARIES, boundary` and replace `_boundary(` with
`boundary(`. (If anything else imports `log.DEFAULT_SHIFT_BOUNDARIES`, the re-import keeps it
working — grep to confirm.)

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_shifts.py tests/test_log_shift.py tests/test_log_api.py -q` → PASS; full suite + ruff.

- [ ] **Step 5: Commit**

```bash
git add server/app/domain/shifts.py server/app/domain/log.py server/tests/test_shifts.py
git commit -m "feat(checklists): shift windows on the hotel's configured boundaries"
```

---

### Task 5: Templates (`ck_templates`) and the checklist wire models

**Files:** Create `server/app/schemas/checklists.py`, `server/app/domain/ck_templates.py`,
`server/tests/ck_helpers.py`; test `server/tests/test_ck_templates.py`.

**Interfaces:**
- Produces schemas: `ChecklistTemplateIn`, `ChecklistTemplatePatch`, `ChecklistTemplateOut`,
  `ChecklistInstanceRowOut`, `ChecklistInstanceOut`, `ChecklistAssignRequest`,
  `ChecklistCommentPatch`, `ChecklistInstanceQuery`, `ChecklistMissedQuery` (defined here; the
  instance/row ones are filled by Task 8).
- Produces (in `app.domain.ck_templates`): `get(db, pid, tid)`, `active_items(db, tid)`,
  `to_out(db, t) -> ChecklistTemplateOut`, `list_templates(db, pid)`,
  `create(db, pid, actor_id, data) -> ChecklistTemplate`,
  `patch(db, pid, actor_id, tid, data) -> ChecklistTemplate`.
- Produces test helpers (`tests/ck_helpers.py`): `make_template(db, fx, *, name, department_id,
  schedule="weekly", shift="am", weekdays=127, items=None) -> ChecklistTemplate` (via
  `ck_templates.create`, actor `fx.admin_a`), `ITEMS` (a checkbox, a required number 7.2–7.8
  "Pool pH", an optional text, a required photo).

- [ ] **Step 1: Write the wire models** — `server/app/schemas/checklists.py`:

```python
"""Shift-checklist wire models (checklists spec §4). Items, answers and photos reuse PM's models
so PM's ChecklistItem component renders checklist rows unchanged."""
from datetime import date, datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut, TemplateItemIn, TemplateItemOut


class ChecklistTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    department_id: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool = True
    items: list[TemplateItemIn] = Field(min_length=1, max_length=100)


class ChecklistTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    department_id: str | None = None
    schedule: ChecklistSchedule | None = None
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool | None = None
    items: list[TemplateItemIn] | None = Field(default=None, min_length=1, max_length=100)


class ChecklistTemplateOut(CamelModel):
    id: str
    name: str
    department_id: str
    department_name: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = None
    active: bool
    items: list[TemplateItemOut]


class ChecklistInstanceRowOut(CamelModel):
    id: str
    template_id: str
    template_name: str
    department_id: str
    department_name: str
    due_date: date
    shift: Shift
    on_demand: bool
    status: ChecklistStatus
    assigned_user_id: str | None = None
    assigned_name: str | None = None
    completed_by_name: str | None = None
    done: int
    total: int
    out_of_range_count: int


class ChecklistInstanceOut(ChecklistInstanceRowOut):
    started_by_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    comment: str | None = None
    items: list[TemplateItemOut]
    answers: list[RunAnswerOut]
    photos: list[RunPhotoOut]
    missing_required: list[str]


class ChecklistAssignRequest(CamelModel):
    user_id: str | None = None


class ChecklistCommentPatch(CamelModel):
    comment: str | None = Field(default=None, max_length=4000)


class ChecklistInstanceQuery(CamelModel):
    # `day`, not `date`: a field named after its own type shadows it inside the class body.
    day: date | None = None
    department_id: str | None = None
    status: ChecklistStatus | None = None


class ChecklistMissedQuery(CamelModel):
    days: int = Field(default=7, ge=1, le=90)
```

- [ ] **Step 2: Write the helpers and the failing test**

`server/tests/ck_helpers.py`:

```python
"""Shared set-up for the shift-checklist tests."""
from __future__ import annotations

from app.domain import ck_templates
from app.schemas.checklists import ChecklistTemplateIn
from app.schemas.pm import TemplateItemIn

ITEMS = [
    TemplateItemIn(label="Skimmer baskets emptied", item_type="checkbox"),
    TemplateItemIn(label="Pool pH", item_type="number", unit="", min_value=7.2, max_value=7.8),
    TemplateItemIn(label="Notes", item_type="text", required=False),
    TemplateItemIn(label="Plant room photo", item_type="photo"),
]


def make_template(db, fx, *, name="Engineering AM Rounds", department_id=None,
                  schedule="weekly", shift="am", weekdays=127, items=None):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
        name=name, department_id=department_id or fx.dept_engineering.id, schedule=schedule,
        shift=shift if schedule == "weekly" else None,
        weekdays=weekdays if schedule == "weekly" else None, items=items or ITEMS))
```

`server/tests/test_ck_templates.py`:

```python
"""Checklist templates (checklists spec §2.1, §3.4)."""
import pytest

from app.domain import ck_templates
from app.errors import ValidationFailed
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplatePatch
from app.schemas.pm import TemplateItemIn
from tests.ck_helpers import ITEMS, make_template


def test_create_weekly_template_with_items(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift.value, out.weekdays) == ("weekly", "am", 127)
        assert [i.label for i in out.items] == [i.label for i in ITEMS]
        assert out.department_name == "Engineering"


def test_weekly_needs_shift_and_weekdays_and_on_demand_neither(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                name="x", department_id=fx.dept_engineering.id, schedule="weekly",
                shift="am", weekdays=None, items=ITEMS))
        with pytest.raises(ValidationFailed):
            ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                name="x", department_id=fx.dept_engineering.id, schedule="on_demand",
                shift="pm", items=ITEMS))


def test_department_must_belong_to_the_property(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed):
        make_template(db, fx, department_id="00000000-0000-0000-0000-000000000000")


def test_patch_switches_to_on_demand_and_retires_removed_items(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        first = ck_templates.to_out(db, t).items[0]
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="on_demand", shift=None, weekdays=None,
            items=[TemplateItemIn(id=first.id, label=first.label, item_type="checkbox")]))
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift, out.weekdays) == ("on_demand", None, None)
        assert [i.label for i in out.items] == [first.label]  # active items only
```

- [ ] **Step 3: Run to verify it fails**, then implement `server/app/domain/ck_templates.py`:

```python
"""Checklist templates (checklists spec §2.1, §3.4). Items sync through the same shared rules as
PM templates: replace-by-list, soft deletes, an item's type never changes."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, typed_items
from app.errors import NotFound, ValidationFailed
from app.models import ChecklistTemplate, ChecklistTemplateItem, Department
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplateOut, ChecklistTemplatePatch
from app.schemas.enums import ChecklistSchedule
from app.schemas.pm import TemplateItemOut


def get(db: Session, property_id: str, template_id: str) -> ChecklistTemplate:
    t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.id == template_id,
                                                  ChecklistTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Checklist template not found")
    return t


def active_items(db: Session, template_id: str) -> list[ChecklistTemplateItem]:
    return list(db.scalars(select(ChecklistTemplateItem).where(
        ChecklistTemplateItem.template_id == template_id,
        ChecklistTemplateItem.active.is_(True)).order_by(ChecklistTemplateItem.position)).all())


def to_out(db: Session, t: ChecklistTemplate) -> ChecklistTemplateOut:
    dept = db.get(Department, t.department_id)
    return ChecklistTemplateOut(
        id=t.id, name=t.name, department_id=t.department_id, department_name=dept.name,
        schedule=t.schedule, shift=t.shift, weekdays=t.weekdays, active=t.active,
        items=[TemplateItemOut.model_validate(i, from_attributes=True)
               for i in active_items(db, t.id)])


def list_templates(db: Session, property_id: str) -> list[ChecklistTemplateOut]:
    rows = db.scalars(select(ChecklistTemplate).where(ChecklistTemplate.property_id == property_id)
                      .order_by(ChecklistTemplate.name, ChecklistTemplate.id)).all()
    return [to_out(db, t) for t in rows]


def _validate_schedule(schedule, shift, weekdays) -> None:
    if schedule == ChecklistSchedule.weekly and (shift is None or not weekdays):
        raise ValidationFailed("A weekly checklist needs a shift and at least one day",
                               details={"weekdays": "required"})
    if schedule == ChecklistSchedule.on_demand and (shift is not None or weekdays is not None):
        raise ValidationFailed("An on-demand checklist has no shift or days — it takes the shift "
                               "it is started in", details={"shift": "not_allowed"})


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if db.scalar(select(Department.id).where(Department.id == department_id,
                                             Department.property_id == property_id)) is None:
        raise ValidationFailed("Unknown department", details={"departmentId": "unknown"})


def create(db: Session, property_id: str, actor_id: str,
           data: ChecklistTemplateIn) -> ChecklistTemplate:
    _validate_schedule(data.schedule, data.shift, data.weekdays)
    _assert_department(db, property_id, data.department_id)
    t = ChecklistTemplate(property_id=property_id, name=data.name.strip(),
                          department_id=data.department_id, schedule=data.schedule,
                          shift=data.shift, weekdays=data.weekdays, active=data.active)
    db.add(t)
    db.flush()
    typed_items.sync_items(db, ChecklistTemplateItem, t, data.items)
    audit.record(db, property_id, actor_id, "checklist_template.created", "checklist_template",
                 t.id, after={"name": t.name})
    return t


def patch(db: Session, property_id: str, actor_id: str, template_id: str,
          data: ChecklistTemplatePatch) -> ChecklistTemplate:
    t = get(db, property_id, template_id)
    provided = data.model_dump(exclude_unset=True)
    schedule = provided.get("schedule", t.schedule)
    shift = provided["shift"] if "shift" in provided else t.shift
    weekdays = provided["weekdays"] if "weekdays" in provided else t.weekdays
    _validate_schedule(schedule, shift, weekdays)
    if "department_id" in provided:
        _assert_department(db, property_id, data.department_id)
        t.department_id = data.department_id
    if "name" in provided:
        t.name = data.name.strip()
    if "active" in provided:
        t.active = data.active
    t.schedule, t.shift, t.weekdays = schedule, shift, weekdays
    db.flush()
    if data.items is not None:
        typed_items.sync_items(db, ChecklistTemplateItem, t, data.items)
    audit.record(db, property_id, actor_id, "checklist_template.updated", "checklist_template",
                 t.id, after={"fields": sorted(provided)})
    return t
```

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_templates.py -q` → PASS; full suite + ruff.

- [ ] **Step 5: Commit**

```bash
git add server/app/schemas/checklists.py server/app/domain/ck_templates.py server/tests/ck_helpers.py server/tests/test_ck_templates.py
git commit -m "feat(checklists): templates sharing PM's item rules"
```

---

### Task 6: Instance lifecycle (`ck_instances`) and photos (`ck_photos`)

**Files:** Create `server/app/domain/ck_instances.py`, `server/app/domain/ck_photos.py`; test
`server/tests/test_ck_instances.py`.

**Interfaces:**
- Consumes: `ck_templates.get/active_items`, `typed_items.*`, `shifts.current_shift`,
  `work_orders.create`, `notifications.notify_users`.
- Produces (in `app.domain.ck_instances`): `EVENT = "checklist.instances.changed"`, `LIVE`,
  `emit(db, pid, ids)`, `get(db, pid, iid)`, `ensure_instance(db, template, day) ->
  tuple[ChecklistInstance, bool]`, `is_member(db, pid, user_id, department_id) -> bool`,
  `require_actor(db, inst, template, actor_id, role)`, `assign(db, pid, actor_id, iid, user_id)`,
  `start(db, pid, actor_id, role, iid)`, `start_on_demand(db, pid, actor_id, role, tid)`,
  `save_answer(db, pid, actor_id, role, iid, answer_id, data: AnswerPatch)`,
  `set_comment(db, pid, actor_id, role, iid, comment)`, `missing_required(db, inst) -> list[str]`,
  `complete(db, pid, actor_id, role, iid)`.
- Produces (in `app.domain.ck_photos`): `attach(db, pid, actor_id, role, iid, *, data: bytes,
  item_id: str | None)`, `get_photo(db, pid, iid, photo_id)`, `photo_url(pid, iid, photo_id)`,
  `photos_for(db, iid) -> list[ChecklistPhoto]`.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_ck_instances.py`:

```python
"""Instance lifecycle (checklists spec §3.3)."""
import pytest
from sqlalchemy import select

from app.domain import ck_instances, ck_photos, ck_templates
from app.errors import Forbidden, TransitionError, ValidationFailed
from app.models import ChecklistAnswer, ChecklistTemplateItem, Notification, WorkOrder
from app.schemas.checklists import ChecklistTemplatePatch
from app.schemas.enums import ChecklistStatus, Role, Shift
from app.schemas.pm import AnswerPatch, TemplateItemIn
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _open(db, fx, **kw):
    t = make_template(db, fx, **kw)
    inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
    return t, inst


def _answers(db, inst):
    return {item.label: ans for ans, item in db.execute(
        select(ChecklistAnswer, ChecklistTemplateItem)
        .join(ChecklistTemplateItem, ChecklistTemplateItem.id == ChecklistAnswer.item_id)
        .where(ChecklistAnswer.instance_id == inst.id)).all()}


def _fill(db, fx, inst, ph=7.4):
    a = _answers(db, inst)
    pid, eli = fx.property_a.id, fx.engineer_a.id
    ck_instances.save_answer(db, pid, eli, Role.dept_staff, inst.id,
                             a["Skimmer baskets emptied"].id, AnswerPatch(bool_value=True))
    ck_instances.save_answer(db, pid, eli, Role.dept_staff, inst.id, a["Pool pH"].id,
                             AnswerPatch(number_value=ph))
    item_id = a["Plant room photo"].item_id
    ck_photos.attach(db, pid, eli, Role.dept_staff, inst.id, data=PNG, item_id=item_id)


def test_ensure_instance_is_idempotent(database, fx):
    with database.session() as db:
        t, inst = _open(db, fx)
        again, created = ck_instances.ensure_instance(db, t, inst.due_date)
        assert (again.id, created, inst.slot, inst.shift) == (inst.id, False, 0, Shift.am)


def test_start_claims_and_snapshots_the_items(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert (inst.status, inst.assigned_user_id, inst.started_by_user_id) == (
            ChecklistStatus.in_progress, fx.engineer_a.id, fx.engineer_a.id)
        assert len(_answers(db, inst)) == 4


def test_starting_twice_is_a_409(database, fx):
    """Review focus 3."""
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        with pytest.raises(TransitionError):
            ck_instances.start(db, fx.property_a.id, fx.supervisor_a.id, Role.supervisor,
                               inst.id)


def test_other_department_staff_are_refused(database, fx):
    """Review focus 4: a housekeeper can't run Engineering's rounds; a manager (no department)
    can, through the supervisor exemption."""
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(Forbidden):
            ck_instances.start(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                               inst.id)
        ck_instances.start(db, fx.property_a.id, fx.manager_a.id, Role.manager, inst.id)


def test_assign_requires_a_department_member_and_notifies(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(ValidationFailed):
            ck_instances.assign(db, fx.property_a.id, fx.supervisor_a.id, inst.id,
                                fx.housekeeper_a.id)
        ck_instances.assign(db, fx.property_a.id, fx.supervisor_a.id, inst.id, fx.engineer_a.id)
        assert inst.assigned_user_id == fx.engineer_a.id
        assert db.scalar(select(Notification.type).where(
            Notification.user_id == fx.engineer_a.id)) == "checklist.assigned"


def test_required_photo_item_needs_its_own_photo(database, fx):
    """Review focus 5: a general photo does not satisfy a photo item."""
    with database.session() as db:
        _, inst = _open(db, fx)
        pid = fx.property_a.id
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        a = _answers(db, inst)
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id,
                                 a["Skimmer baskets emptied"].id, AnswerPatch(bool_value=True))
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id,
                                 a["Pool pH"].id, AnswerPatch(number_value=7.4))
        ck_photos.attach(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id, data=PNG,
                         item_id=None)
        with pytest.raises(ValidationFailed) as e:
            ck_instances.complete(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert e.value.details == {"missingItemIds": [a["Plant room photo"].item_id]}


def test_complete_raises_one_work_order_per_out_of_range_reading(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        pid = fx.property_a.id
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        _fill(db, fx, inst, ph=8.1)
        ck_instances.complete(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert inst.status is ChecklistStatus.complete
        titles = db.scalars(select(WorkOrder.title)).all()
        assert titles == ["Pool pH 8.1 out of range (7.2–7.8) — Engineering AM Rounds"]
        assert db.scalar(select(Notification.type).where(
            Notification.user_id == fx.supervisor_a.id)) == "checklist.out_of_range"


def test_complete_is_refused_unless_in_progress(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(TransitionError):
            ck_instances.complete(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff,
                                  inst.id)


def test_on_demand_runs_twice_and_takes_the_current_shift(database, fx):
    # FROZEN 2026-09-10 12:00 UTC = 08:00 New York → the AM shift of Sep 10.
    with database.session() as db:
        t = make_template(db, fx, name="Power Outage", schedule="on_demand")
        one = ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                           Role.dept_staff, t.id)
        two = ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                           Role.dept_staff, t.id)
        assert one.id != two.id
        assert (one.shift, one.slot, one.status) == (Shift.am, None, ChecklistStatus.in_progress)


def test_editing_a_template_never_changes_a_started_instance(database, fx):
    """Review focus 2."""
    with database.session() as db:
        t, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            items=[TemplateItemIn(label="Something new", item_type="checkbox")]))
        assert sorted(_answers(db, inst)) == sorted(
            ["Skimmer baskets emptied", "Pool pH", "Notes", "Plant room photo"])


def test_comment_is_saved_trimmed(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        ck_instances.set_comment(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff,
                                 inst.id, "  Boiler 2 noisy, keep an eye  ")
        assert inst.comment == "Boiler 2 noisy, keep an eye"


def test_each_mutation_emits_one_event(database, fx, events):
    with database.session() as db:
        _, inst = _open(db, fx)
    events.clear()
    with database.session() as db:
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
    ck = [e for e in events if e.type == ck_instances.EVENT]
    assert len(ck) == 1 and ck[0].payload == {"ids": [inst.id]}
```

- [ ] **Step 2: Run to verify they fail** (`ImportError`).

- [ ] **Step 3: Implement `server/app/domain/ck_instances.py`**

```python
"""Checklist instances (checklists spec §3.3): assign, start/claim, answers, comment, complete.
Anything not implemented here is a 409."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.permissions import has_capability
from app.domain import audit, ck_templates, notifications, shifts, typed_items
from app.domain import work_orders as wo_domain
from app.errors import Forbidden, NotFound, TransitionError, ValidationFailed
from app.models import (
    ChecklistAnswer,
    ChecklistInstance,
    ChecklistPhoto,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Property,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    ChecklistSchedule,
    ChecklistStatus,
    LocationType,
    Priority,
    Role,
    UserStatus,
    WorkOrderType,
)
from app.schemas.pm import AnswerPatch
from app.schemas.work_orders import CreateWorkOrder

EVENT = "checklist.instances.changed"
LIVE = (ChecklistStatus.open, ChecklistStatus.in_progress)


def emit(db: Session, property_id: str, ids: list[str]) -> None:
    """The one place checklists call queue_event (spec §3.5)."""
    unique = list(dict.fromkeys(ids))
    if unique:
        queue_event(db, property_id, EVENT, {"ids": unique})


def get(db: Session, property_id: str, instance_id: str) -> ChecklistInstance:
    inst = db.scalar(select(ChecklistInstance).where(ChecklistInstance.id == instance_id,
                                                     ChecklistInstance.property_id == property_id))
    if inst is None:
        raise NotFound("Checklist not found")
    return inst


def ensure_instance(db: Session, template: ChecklistTemplate,
                    day: date) -> tuple[ChecklistInstance, bool]:
    """The scheduled instance for (template, day): created if missing. slot 0 + the unique key
    make this idempotent."""
    inst = db.scalar(select(ChecklistInstance).where(
        ChecklistInstance.template_id == template.id, ChecklistInstance.due_date == day,
        ChecklistInstance.shift == template.shift, ChecklistInstance.slot == 0))
    if inst is not None:
        return inst, False
    inst = ChecklistInstance(property_id=template.property_id, template_id=template.id,
                             due_date=day, shift=template.shift, slot=0,
                             status=ChecklistStatus.open)
    db.add(inst)
    db.flush()
    return inst, True


def is_member(db: Session, property_id: str, user_id: str, department_id: str) -> bool:
    return db.scalar(
        select(PropertyMembership.id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.user_id == user_id,
               PropertyMembership.department_id == department_id,
               UserAccount.status == UserStatus.active)) is not None


def require_actor(db: Session, inst: ChecklistInstance, template: ChecklistTemplate,
                  actor_id: str, role: Role) -> None:
    if (has_capability(role, "manage_checklists") or inst.assigned_user_id == actor_id
            or is_member(db, inst.property_id, actor_id, template.department_id)):
        return
    raise Forbidden("Only this checklist's department can work on it")


def _require_in_progress(inst: ChecklistInstance) -> None:
    if inst.status != ChecklistStatus.in_progress:
        raise TransitionError("This checklist is not in progress")


def _load(db: Session, property_id: str, instance_id: str):
    inst = get(db, property_id, instance_id)
    return inst, db.get(ChecklistTemplate, inst.template_id)


def assign(db: Session, property_id: str, actor_id: str, instance_id: str,
           user_id: str | None) -> ChecklistInstance:
    inst, template = _load(db, property_id, instance_id)
    if inst.status not in LIVE:
        raise TransitionError("Only an open or in-progress checklist can be assigned")
    if user_id is not None and not is_member(db, property_id, user_id, template.department_id):
        raise ValidationFailed("That person is not an active member of this checklist's "
                               "department", details={"userId": "not_in_department"})
    inst.assigned_user_id = user_id
    db.flush()
    if user_id and user_id != actor_id:
        notifications.notify_users(db, property_id, [user_id], "checklist.assigned",
                                   f"Checklist assigned: {template.name}",
                                   entity_type="checklist_instance", entity_id=inst.id)
    emit(db, property_id, [inst.id])
    return inst


def _begin(db: Session, inst: ChecklistInstance, actor_id: str) -> None:
    inst.status = ChecklistStatus.in_progress
    inst.started_by_user_id = actor_id
    inst.started_at = clock.now()
    if inst.assigned_user_id is None:
        inst.assigned_user_id = actor_id  # claim
    for item in ck_templates.active_items(db, inst.template_id):
        db.add(ChecklistAnswer(instance_id=inst.id, property_id=inst.property_id,
                               item_id=item.id))
    db.flush()
    emit(db, inst.property_id, [inst.id])


def start(db: Session, property_id: str, actor_id: str, role: Role,
          instance_id: str) -> ChecklistInstance:
    inst, template = _load(db, property_id, instance_id)
    require_actor(db, inst, template, actor_id, role)
    if inst.status != ChecklistStatus.open:
        raise TransitionError("Only an open checklist can be started")
    _begin(db, inst, actor_id)
    return inst


def start_on_demand(db: Session, property_id: str, actor_id: str, role: Role,
                    template_id: str) -> ChecklistInstance:
    """On-demand instances take the shift they are started in (spec §3.3)."""
    template = ck_templates.get(db, property_id, template_id)
    if template.schedule != ChecklistSchedule.on_demand or not template.active:
        raise TransitionError("Only an active on-demand checklist can be started this way")
    if not (has_capability(role, "manage_checklists")
            or is_member(db, property_id, actor_id, template.department_id)):
        raise Forbidden("Only this checklist's department can start it")
    day, shift = shifts.current_shift(db.get(Property, property_id), clock.now())
    inst = ChecklistInstance(property_id=property_id, template_id=template.id, due_date=day,
                             shift=shift, slot=None, status=ChecklistStatus.open)
    db.add(inst)
    db.flush()
    _begin(db, inst, actor_id)
    return inst


def save_answer(db: Session, property_id: str, actor_id: str, role: Role, instance_id: str,
                answer_id: str, data: AnswerPatch) -> ChecklistAnswer:
    inst, template = _load(db, property_id, instance_id)
    require_actor(db, inst, template, actor_id, role)
    _require_in_progress(inst)
    answer = db.scalar(select(ChecklistAnswer).where(ChecklistAnswer.id == answer_id,
                                                     ChecklistAnswer.instance_id == inst.id))
    if answer is None:
        raise NotFound("Answer not found")
    typed_items.apply_answer(db.get(ChecklistTemplateItem, answer.item_id), answer, data)
    db.flush()
    emit(db, property_id, [inst.id])
    return answer


def set_comment(db: Session, property_id: str, actor_id: str, role: Role, instance_id: str,
                comment: str | None) -> ChecklistInstance:
    inst, template = _load(db, property_id, instance_id)
    require_actor(db, inst, template, actor_id, role)
    _require_in_progress(inst)
    inst.comment = (comment or "").strip() or None
    db.flush()
    emit(db, property_id, [inst.id])
    return inst


def missing_required(db: Session, inst: ChecklistInstance) -> list[str]:
    rows = db.execute(select(ChecklistAnswer, ChecklistTemplateItem)
                      .join(ChecklistTemplateItem,
                            ChecklistTemplateItem.id == ChecklistAnswer.item_id)
                      .where(ChecklistAnswer.instance_id == inst.id,
                             ChecklistTemplateItem.required.is_(True))
                      .order_by(ChecklistTemplateItem.position)).all()
    photographed = set(db.scalars(select(ChecklistPhoto.item_id).where(
        ChecklistPhoto.instance_id == inst.id, ChecklistPhoto.item_id.is_not(None))).all())
    return [item.id for answer, item in rows
            if not typed_items.is_answered(item, answer, photographed)]


def _raise_out_of_range(db: Session, inst: ChecklistInstance, template: ChecklistTemplate,
                        actor_id: str) -> list[WorkOrder]:
    rows = db.execute(select(ChecklistAnswer, ChecklistTemplateItem)
                      .join(ChecklistTemplateItem,
                            ChecklistTemplateItem.id == ChecklistAnswer.item_id)
                      .where(ChecklistAnswer.instance_id == inst.id,
                             ChecklistAnswer.out_of_range.is_(True))
                      .order_by(ChecklistTemplateItem.position)).all()
    if not rows:
        return []
    targets = [t for t in typed_items.escalation_targets(db, inst.property_id,
                                                         template.department_id)
               if t != actor_id]
    created: list[WorkOrder] = []
    for answer, item in rows:
        title = typed_items.out_of_range_title(item, answer, template.name)
        wo = wo_domain.create(db, inst.property_id, actor_id, CreateWorkOrder(
            title=title,
            description=(f"Recorded on the {template.name} checklist "
                         f"({inst.due_date.isoformat()}, {inst.shift.value} shift)."),
            type=WorkOrderType.maintenance, priority=Priority.high,
            location_type=LocationType.other, department_id=template.department_id))
        notifications.notify_users(db, inst.property_id, targets, "checklist.out_of_range",
                                   f"Out of range: {item.label} on {template.name}",
                                   body=title[:140], entity_type="work_order", entity_id=wo.id)
        created.append(wo)
    return created


def complete(db: Session, property_id: str, actor_id: str, role: Role,
             instance_id: str) -> ChecklistInstance:
    inst, template = _load(db, property_id, instance_id)
    require_actor(db, inst, template, actor_id, role)
    _require_in_progress(inst)
    missing = missing_required(db, inst)
    if missing:
        raise ValidationFailed("Answer every required item first",
                               details={"missingItemIds": missing})
    raised = _raise_out_of_range(db, inst, template, actor_id)
    inst.status = ChecklistStatus.complete
    inst.completed_by_user_id = actor_id
    inst.completed_at = clock.now()
    db.flush()
    audit.record(db, property_id, actor_id, "checklist_instance.completed",
                 "checklist_instance", inst.id,
                 after={"work_orders_raised": [w.id for w in raised]})
    emit(db, property_id, [inst.id])
    return inst
```

- [ ] **Step 4: Implement `server/app/domain/ck_photos.py`** — mirror `hk_photos.py` exactly
(size cap `MAX_PHOTO_BYTES`, `sniff_image_type`, the same three error messages and detail codes,
`audit.record(... "checklist.photo_attached" ...)`), with these differences: the guard is
`ck_instances.require_actor(db, inst, template, actor_id, role)` then
`if inst.status != ChecklistStatus.in_progress: raise TransitionError("Photos can only be added
while the checklist is in progress")`; an `item_id`, when given, must name a `photo`-type
`ChecklistTemplateItem` of the instance's template (else `ValidationFailed("That item does not
take a photo", details={"itemId": "not_a_photo_item"})`); it ends with
`ck_instances.emit(db, property_id, [inst.id])`; `photo_url(property_id, instance_id, photo_id)`
returns `f"/api/p/{property_id}/checklists/instances/{instance_id}/photos/{photo_id}"`;
`photos_for(db, instance_id)` returns the instance's photos ordered by `created_at, id`;
`get_photo` is scoped by property **and** instance.

- [ ] **Step 5: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_instances.py -q` → PASS; full suite + ruff.

- [ ] **Step 6: Commit**

```bash
git add server/app/domain/ck_instances.py server/app/domain/ck_photos.py server/tests/test_ck_instances.py
git commit -m "feat(checklists): instance lifecycle, out-of-range work orders, photos"
```

---

### Task 7: The tick

**Files:** Create `server/app/domain/ck_tick.py`, `server/app/queue/handlers/checklists.py`;
modify `server/app/queue/handlers/__init__.py` (`MODULES`), `server/app/queue/jobs.py`
(`RECURRING`); test `server/tests/test_ck_tick.py`.

**Interfaces:** Produces `ck_tick.tick(db) -> dict[str, int]` (`"generated"`, `"missed"`); job
`"checklist.tick"` every 300 s.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_ck_tick.py`:

```python
"""checklist.tick (checklists spec §3.2; plan clarification 1). FROZEN = Thu 2026-09-10 12:00
UTC = 08:00 New York (AM shift, window 11:00–19:00 UTC)."""
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import clock
from app.domain import ck_instances, ck_tick
from app.models import ChecklistInstance, ChecklistTemplate, Property
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.schemas.enums import ChecklistStatus, Role
from tests.ck_helpers import make_template

THU = 1 << 3


def _count(db):
    return db.scalar(select(func.count()).select_from(ChecklistInstance))


def test_registered_every_five_minutes():
    load_all()
    assert "checklist.tick" in HANDLERS and jobs.RECURRING["checklist.tick"] == 300


def test_generates_on_the_templates_weekdays_only_and_idempotently(database, fx, events):
    with database.session() as db:
        make_template(db, fx, name="Thursday", weekdays=THU)
        make_template(db, fx, name="Monday", weekdays=1)
        make_template(db, fx, name="Whenever", schedule="on_demand")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}
    events.clear()
    with database.session() as db:
        assert ck_tick.tick(db) == {"generated": 0, "missed": 0}
        assert _count(db) == 1
    assert [e for e in events if e.type == ck_instances.EVENT] == []


def test_never_generates_an_already_ended_shift(database, fx):
    """Clarification 1: at 20:00 UTC the AM window (ends 19:00 UTC) is over."""
    clock.freeze(datetime(2026, 9, 10, 20, 0, tzinfo=UTC))
    with database.session() as db:
        make_template(db, fx, shift="am")
        make_template(db, fx, name="PM", shift="pm")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}


def test_marks_missed_exactly_when_the_window_ends(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
    clock.freeze(datetime(2026, 9, 10, 18, 59, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0
    clock.freeze(datetime(2026, 9, 10, 19, 0, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 1
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.missed


def test_complete_instances_are_left_alone(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        inst = db.scalar(select(ChecklistInstance))
        inst.status = ChecklistStatus.complete
    clock.freeze(datetime(2026, 9, 10, 23, 0, tzinfo=UTC))
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0


def test_missed_uses_current_boundaries(database, fx):
    """Review focus 1: moving the pm boundary later extends an in-flight AM instance."""
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        p = db.get(Property, fx.property_a.id)
        p.settings = {**(p.settings or {}), "shift_boundaries": {"pm": "16:00"}}
    clock.freeze(datetime(2026, 9, 10, 19, 30, tzinfo=UTC))  # past 15:00 local, before 16:00
    with database.session() as db:
        assert ck_tick.tick(db)["missed"] == 0


def test_deactivated_template_keeps_todays_instance(database, fx):
    """Review focus 2."""
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        db.scalar(select(ChecklistTemplate)).active = False
    with database.session() as db:
        ck_tick.tick(db)
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.open


def test_a_partly_answered_instance_is_frozen_as_missed(database, fx):
    with database.session() as db:
        make_template(db, fx)
        ck_tick.tick(db)
        inst = db.scalar(select(ChecklistInstance))
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
    clock.freeze(datetime(2026, 9, 10, 19, 0, tzinfo=UTC))
    with database.session() as db:
        ck_tick.tick(db)
        assert db.scalar(select(ChecklistInstance.status)) is ChecklistStatus.missed
```

- [ ] **Step 2: Run to verify they fail**, then implement `server/app/domain/ck_tick.py`:

```python
"""`checklist.tick` (checklists spec §3.2): every 5 minutes, stateless and idempotent. It never
records "I ran today" — it asks what ought to exist and what has ended."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import ck_instances, pm_cycles, shifts
from app.models import ChecklistInstance, ChecklistTemplate, Property
from app.schemas.enums import ChecklistSchedule, ChecklistStatus


def tick(db: Session) -> dict[str, int]:
    generated = missed = 0
    now = clock.now()
    for prop in db.scalars(select(Property).order_by(Property.id)).all():
        changed: list[str] = []
        today = pm_cycles.local_today(prop)
        bit = 1 << today.weekday()
        templates = db.scalars(select(ChecklistTemplate).where(
            ChecklistTemplate.property_id == prop.id, ChecklistTemplate.active.is_(True),
            ChecklistTemplate.schedule == ChecklistSchedule.weekly)).all()
        for template in templates:
            if not (template.weekdays or 0) & bit:
                continue
            if now >= shifts.shift_window(prop, today, template.shift)[1]:
                continue  # plan clarification 1: never born already missed
            inst, created = ck_instances.ensure_instance(db, template, today)
            if created:
                changed.append(inst.id)
                generated += 1
        live = db.scalars(select(ChecklistInstance).where(
            ChecklistInstance.property_id == prop.id,
            ChecklistInstance.status.in_(ck_instances.LIVE))).all()
        for inst in live:
            if now >= shifts.shift_window(prop, inst.due_date, inst.shift)[1]:
                inst.status = ChecklistStatus.missed
                changed.append(inst.id)
                missed += 1
        db.flush()
        ck_instances.emit(db, prop.id, changed)
    return {"generated": generated, "missed": missed}
```

`server/app/queue/handlers/checklists.py`:

```python
"""`checklist.tick` (checklists spec §3.2): every 300 s. Idempotent, so a retried job is harmless."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain import ck_tick
from app.queue.handlers import handler


@handler("checklist.tick")
def checklist_tick(db: Session, payload: dict) -> None:
    ck_tick.tick(db)
```

Append `"checklists"` to `MODULES` in `handlers/__init__.py`; add `"checklist.tick": 300` to
`RECURRING` in `jobs.py` (wrap under 100 columns).

- [ ] **Step 3: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_tick.py tests/test_queue.py -q` → PASS; full suite + ruff.

- [ ] **Step 4: Commit**

```bash
git add server/app/domain/ck_tick.py server/app/queue/handlers/checklists.py server/app/queue/handlers/__init__.py server/app/queue/jobs.py server/tests/test_ck_tick.py
git commit -m "feat(checklists): stateless tick generating today's instances and marking misses"
```

---

### Task 8: Read models (`ck_views`)

**Files:** Create `server/app/domain/ck_views.py`; test `server/tests/test_ck_views.py`.

**Interfaces:** Produces `list_instances(db, pid, query: ChecklistInstanceQuery) ->
list[ChecklistInstanceRowOut]`, `detail(db, pid, iid) -> ChecklistInstanceOut`,
`missed(db, pid, query: ChecklistMissedQuery) -> list[ChecklistInstanceRowOut]`.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_ck_views.py`:

```python
"""Read models (checklists spec §4.2; plan clarification 4)."""
from datetime import timedelta

from app.domain import ck_instances, ck_photos, ck_views
from app.schemas.checklists import ChecklistInstanceQuery, ChecklistMissedQuery
from app.schemas.enums import ChecklistStatus, Role
from app.schemas.pm import AnswerPatch
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def test_list_rows_progress_and_shift_order(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        pm_t = make_template(db, fx, name="PM Walk", shift="pm")
        am_t = make_template(db, fx, name="AM Rounds", shift="am")
        am, _ = ck_instances.ensure_instance(db, am_t, today)
        ck_instances.ensure_instance(db, pm_t, today)
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, am.id)
        answer = next(a for a in ck_views.detail(db, pid, am.id).answers)
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, am.id, answer.id,
                                 AnswerPatch(bool_value=True))
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery())
        assert [r.template_name for r in rows] == ["AM Rounds", "PM Walk"]
        assert (rows[0].done, rows[0].total, rows[0].assigned_name) == (1, 4, "Eli Engineer")
        assert (rows[1].done, rows[1].total, rows[1].status) == (0, 4, ChecklistStatus.open)


def test_list_filters_by_department(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx), today)
        ck_instances.ensure_instance(db, make_template(
            db, fx, name="Desk Opening", department_id=fx.dept_front_desk.id), today)
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery(
            department_id=fx.dept_front_desk.id))
        assert [r.template_name for r in rows] == ["Desk Opening"]


def test_list_without_department_filter_shows_all(database, fx):
    """Review focus 4: people with no department see every department's checklists."""
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx), today)
        ck_instances.ensure_instance(db, make_template(
            db, fx, name="Desk Opening", department_id=fx.dept_front_desk.id), today)
        assert len(ck_views.list_instances(db, pid, ChecklistInstanceQuery())) == 2


def test_detail_carries_items_answers_photos_and_missing(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        inst, _ = ck_instances.ensure_instance(db, make_template(db, fx), today)
        before = ck_views.detail(db, pid, inst.id)
        assert (len(before.items), before.answers, before.missing_required) == (4, [], [])
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        photo_item = next(i for i in before.items if i.item_type.value == "photo")
        ck_photos.attach(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id, data=PNG,
                         item_id=photo_item.id)
        after = ck_views.detail(db, pid, inst.id)
        assert len(after.answers) == 4 and len(after.photos) == 1
        assert after.photos[0].url.endswith(f"/photos/{after.photos[0].id}")
        assert photo_item.id not in after.missing_required and len(after.missing_required) == 2


def test_missed_lists_the_last_n_days_newest_first(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        t = make_template(db, fx)
        for back in (1, 3, 10):
            inst, _ = ck_instances.ensure_instance(db, t, today - timedelta(days=back))
            inst.status = ChecklistStatus.missed
        db.flush()
        rows = ck_views.missed(db, pid, ChecklistMissedQuery(days=7))
        assert [r.due_date for r in rows] == [today - timedelta(days=1),
                                             today - timedelta(days=3)]
```

- [ ] **Step 2: Run to verify they fail**, then implement `server/app/domain/ck_views.py`:

```python
"""Checklist read models (checklists spec §4.2, §4.4)."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import ck_instances, ck_photos, ck_templates, pm_cycles, typed_items
from app.domain.pm_runs import names_for
from app.models import (
    ChecklistAnswer,
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateItem,
    Department,
    Property,
)
from app.schemas.checklists import (
    ChecklistInstanceOut,
    ChecklistInstanceQuery,
    ChecklistInstanceRowOut,
    ChecklistMissedQuery,
)
from app.schemas.enums import ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut, TemplateItemOut

SHIFT_ORDER = {Shift.am: 0, Shift.pm: 1, Shift.overnight: 2}


def _answered_rows(db: Session, inst: ChecklistInstance):
    return db.execute(select(ChecklistAnswer, ChecklistTemplateItem)
                      .join(ChecklistTemplateItem,
                            ChecklistTemplateItem.id == ChecklistAnswer.item_id)
                      .where(ChecklistAnswer.instance_id == inst.id)
                      .order_by(ChecklistTemplateItem.position)).all()


def _progress(db: Session, inst: ChecklistInstance) -> tuple[int, int, int]:
    """(done, total, out_of_range) — clarification 4. An unstarted instance counts the template's
    active items; a started one its own snapshot."""
    rows = _answered_rows(db, inst)
    if not rows:
        return 0, len(ck_templates.active_items(db, inst.template_id)), 0
    photographed = {p.item_id for p in ck_photos.photos_for(db, inst.id) if p.item_id}
    done = sum(typed_items.is_answered(item, answer, photographed) for answer, item in rows)
    return done, len(rows), sum(answer.out_of_range for answer, _ in rows)


def _row_fields(db: Session, inst, template, dept, names) -> dict:
    done, total, oor = _progress(db, inst)
    return dict(
        id=inst.id, template_id=template.id, template_name=template.name,
        department_id=dept.id, department_name=dept.name, due_date=inst.due_date,
        shift=inst.shift, on_demand=inst.slot is None, status=inst.status,
        assigned_user_id=inst.assigned_user_id,
        assigned_name=names.get(inst.assigned_user_id or ""),
        completed_by_name=names.get(inst.completed_by_user_id or ""),
        done=done, total=total, out_of_range_count=oor)


def _joined(property_id: str):
    return (select(ChecklistInstance, ChecklistTemplate, Department)
            .join(ChecklistTemplate, ChecklistTemplate.id == ChecklistInstance.template_id)
            .join(Department, Department.id == ChecklistTemplate.department_id)
            .where(ChecklistInstance.property_id == property_id))


def _rows(db: Session, triples) -> list[ChecklistInstanceRowOut]:
    names = names_for(db, [i.assigned_user_id for i, _, _ in triples]
                      + [i.completed_by_user_id for i, _, _ in triples])
    return [ChecklistInstanceRowOut(**_row_fields(db, i, t, d, names)) for i, t, d in triples]


def list_instances(db: Session, property_id: str,
                   query: ChecklistInstanceQuery) -> list[ChecklistInstanceRowOut]:
    day = query.day or pm_cycles.local_today(db.get(Property, property_id))
    stmt = _joined(property_id).where(ChecklistInstance.due_date == day)
    if query.department_id:
        stmt = stmt.where(ChecklistTemplate.department_id == query.department_id)
    if query.status:
        stmt = stmt.where(ChecklistInstance.status == query.status)
    triples = sorted(db.execute(stmt).all(),
                     key=lambda r: (SHIFT_ORDER[r[0].shift], r[1].name, r[0].created_at))
    return _rows(db, triples)


def missed(db: Session, property_id: str,
           query: ChecklistMissedQuery) -> list[ChecklistInstanceRowOut]:
    since = pm_cycles.local_today(db.get(Property, property_id)) - timedelta(days=query.days)
    triples = sorted(db.execute(_joined(property_id).where(
        ChecklistInstance.status == ChecklistStatus.missed,
        ChecklistInstance.due_date >= since)).all(),
        key=lambda r: (-r[0].due_date.toordinal(), SHIFT_ORDER[r[0].shift], r[1].name))
    return _rows(db, triples)


def detail(db: Session, property_id: str, instance_id: str) -> ChecklistInstanceOut:
    inst = ck_instances.get(db, property_id, instance_id)
    template = db.get(ChecklistTemplate, inst.template_id)
    dept = db.get(Department, template.department_id)
    names = names_for(db, [inst.assigned_user_id, inst.completed_by_user_id,
                           inst.started_by_user_id])
    rows = _answered_rows(db, inst)
    items = [item for _, item in rows] or ck_templates.active_items(db, template.id)
    photos = ck_photos.photos_for(db, inst.id)
    return ChecklistInstanceOut(
        **_row_fields(db, inst, template, dept, names),
        started_by_name=names.get(inst.started_by_user_id or ""), started_at=inst.started_at,
        completed_at=inst.completed_at, comment=inst.comment,
        items=[TemplateItemOut.model_validate(i, from_attributes=True) for i in items],
        answers=[RunAnswerOut.model_validate(a, from_attributes=True) for a, _ in rows],
        photos=[RunPhotoOut(id=p.id, item_id=p.item_id, content_type=p.content_type,
                            byte_size=p.byte_size, uploaded_by_user_id=p.uploaded_by_user_id,
                            url=ck_photos.photo_url(property_id, inst.id, p.id),
                            created_at=p.created_at) for p in photos],
        missing_required=(ck_instances.missing_required(db, inst)
                          if inst.status == ChecklistStatus.in_progress else []))
```

- [ ] **Step 3: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_views.py -q` → PASS; full suite + ruff.

- [ ] **Step 4: Commit**

```bash
git add server/app/domain/ck_views.py server/tests/test_ck_views.py
git commit -m "feat(checklists): read models for the list, detail and missed views"
```

---

### Task 9: API blueprint and schema export

**Files:** Create `server/app/api/checklists.py`; modify `server/app/__init__.py`,
`server/app/schemas/export_json_schema.py`, `server/tests/test_schema_export.py`; regenerate
`web/src/api/schema.json`, `web/src/api/types.generated.ts`; modify `web/src/api/types.ts`;
test `server/tests/test_ck_api.py`.

**Interfaces:** The HTTP surface of spec §4.2 at `/api/p/<property_id>/checklists`; answer PATCH
and photo POST return the updated `ChecklistInstanceOut` (like PM's run endpoints); start,
complete, assign, comment return `ChecklistInstanceOut`; POST templates returns 201.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_ck_api.py`:

```python
"""The checklists HTTP surface (checklists spec §4.2, §4.3)."""
import io

from app.domain import ck_instances
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _ck(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists{rest}"


def _instance(database, fx):
    with database.session() as db:
        inst, _ = ck_instances.ensure_instance(db, make_template(db, fx),
                                               local_today(db, fx.property_a.id))
        return inst.id


def test_the_whole_loop_over_http(database, fx, login):
    iid = _instance(database, fx)
    eli = login("engineer@hvh.test")
    body = eli.post(_ck(fx, f"/instances/{iid}/start")).get_json()
    assert body["status"] == "in_progress"
    by_label = {i["label"]: i for i in body["items"]}
    answer_for = {a["itemId"]: a for a in body["answers"]}
    for label, patch in (("Skimmer baskets emptied", {"boolValue": True}),
                         ("Pool pH", {"numberValue": 8.1})):
        res = eli.patch(_ck(fx, f"/instances/{iid}/answers/"
                                f"{answer_for[by_label[label]['id']]['id']}"), json=patch)
        assert res.status_code == 200, res.get_json()
    up = eli.post(_ck(fx, f"/instances/{iid}/photos"),
                  data={"photo": (io.BytesIO(PNG), "p.png", "image/png"),
                        "itemId": by_label["Plant room photo"]["id"]},
                  content_type="multipart/form-data")
    assert up.status_code == 201, up.get_json()
    assert eli.get(up.get_json()["photos"][0]["url"]).data == PNG
    assert eli.patch(_ck(fx, f"/instances/{iid}"),
                     json={"comment": "Pool pH high"}).get_json()["comment"] == "Pool pH high"
    done = eli.post(_ck(fx, f"/instances/{iid}/complete")).get_json()
    assert (done["status"], done["outOfRangeCount"]) == ("complete", 1)


def test_capabilities(database, fx, login):
    iid = _instance(database, fx)
    corp = login("corporate@hvh.test")
    assert corp.get(_ck(fx, "/instances")).status_code == 200
    assert corp.post(_ck(fx, f"/instances/{iid}/start")).status_code == 403
    assert login("engineer@hvh.test").post(_ck(fx, f"/instances/{iid}/assign"),
                                           json={"userId": None}).status_code == 403
    assert login("agent@hvh.test").get(_ck(fx, "/missed")).status_code == 403
    assert login("manager@hvh.test").get(_ck(fx, "/missed")).status_code == 200


def test_other_department_gets_403_from_the_domain(database, fx, login):
    iid = _instance(database, fx)
    assert login("housekeeper@hvh.test").post(
        _ck(fx, f"/instances/{iid}/start")).status_code == 403


def test_create_template_and_start_on_demand(database, fx, login):
    admin = login("admin@hvh.test")
    res = admin.post(_ck(fx, "/templates"), json={
        "name": "Power Outage", "departmentId": fx.dept_engineering.id, "schedule": "on_demand",
        "items": [{"label": "Generator started", "itemType": "checkbox"}]})
    assert res.status_code == 201, res.get_json()
    started = login("engineer@hvh.test").post(_ck(fx, f"/templates/{res.get_json()['id']}/start"))
    assert started.status_code == 201 and started.get_json()["onDemand"] is True


def test_instances_of_another_property_are_404(database, fx, login):
    with database.session() as db:
        from app.models import ChecklistTemplate
        t = ChecklistTemplate(property_id=fx.property_b.id, name="B", schedule="on_demand",
                              department_id=fx.dept_front_desk.id)
        db.add(t)
        db.flush()
        tid = t.id
    assert login("admin@hvh.test").post(_ck(fx, f"/templates/{tid}/start")).status_code == 404
```

Append to the tuple in `test_schema_export.py::test_export_contains_the_public_models`:
`"ChecklistTemplateIn", "ChecklistTemplateOut", "ChecklistInstanceRowOut",
"ChecklistInstanceOut", "ChecklistAssignRequest"`.

- [ ] **Step 2: Run to verify they fail** (404s / missing schema names).

- [ ] **Step 3: Create `server/app/api/checklists.py`**, following `app/api/housekeeping.py`'s
shape exactly (decorator order, `db_session()`, `ok(...)`, a per-module
`MULTIPART_OVERHEAD_BYTES` + `_read_photo()` copied from it). Routes and bodies:

| route | cap | body |
|---|---|---|
| `GET /templates` | view_checklists | `ok(ck_templates.list_templates(db, g.property_id))` |
| `POST /templates` | manage_admin | `parse_body(ChecklistTemplateIn)` → `ok(ck_templates.to_out(db, ck_templates.create(...)), 201)` |
| `PATCH /templates/<template_id>` | manage_admin | `parse_body(ChecklistTemplatePatch)` → `ok(to_out(...))` |
| `POST /templates/<template_id>/start` | perform_checklists | `inst = ck_instances.start_on_demand(db, g.property_id, g.user.id, g.membership.role, template_id)` → `ok(ck_views.detail(db, g.property_id, inst.id), 201)` |
| `GET /instances` | view_checklists | `parse_query(ChecklistInstanceQuery)` → `ok(ck_views.list_instances(...))` |
| `GET /instances/<instance_id>` | view_checklists | `ok(ck_views.detail(...))` |
| `POST /instances/<instance_id>/assign` | manage_checklists | `parse_body(ChecklistAssignRequest)` → `ck_instances.assign(db, pid, g.user.id, instance_id, data.user_id)` → detail |
| `POST /instances/<instance_id>/start` | perform_checklists | `ck_instances.start(..., g.membership.role, instance_id)` → detail |
| `POST /instances/<instance_id>/complete` | perform_checklists | `ck_instances.complete(...)` → detail |
| `PATCH /instances/<instance_id>` | perform_checklists | `parse_body(ChecklistCommentPatch)` → `set_comment(...)` → detail |
| `PATCH /instances/<instance_id>/answers/<answer_id>` | perform_checklists | `parse_body(AnswerPatch)` → `save_answer(...)` → detail |
| `POST /instances/<instance_id>/photos` | perform_checklists | `_read_photo()`, `item_id = request.form.get("itemId") or None` → `ck_photos.attach(...)` → `ok(detail, 201)` |
| `GET /instances/<instance_id>/photos/<photo_id>` | view_checklists | bytes, same headers as housekeeping's photo GET |
| `GET /missed` | view_property_analytics | `parse_query(ChecklistMissedQuery)` → `ok(ck_views.missed(...))` |

Register it in `server/app/__init__.py` after `housekeeping.bp`. Add `checklists` to
`export_json_schema.py`'s imports and `MODULES`, regenerate
(`cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema && cd ../web && npm run gen:types`),
and re-export from `web/src/api/types.ts`: `ChecklistAssignRequest, ChecklistCommentPatch,
ChecklistInstanceOut, ChecklistInstanceQuery, ChecklistInstanceRowOut, ChecklistMissedQuery,
ChecklistSchedule, ChecklistStatus, ChecklistTemplateIn, ChecklistTemplateOut,
ChecklistTemplatePatch, Shift` (skip any already exported).

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_api.py tests/test_schema_export.py tests/test_isolation.py -q`
→ PASS (isolation counts the 14 new rules automatically). Full server suite + ruff;
`cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add server/app/api/checklists.py server/app/__init__.py server/app/schemas/export_json_schema.py server/tests/test_ck_api.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts
git commit -m "feat(checklists): API blueprint and schema export"
```

---

### Task 10: Sample data

**Files:** Modify `server/seed/seed.py`, `server/tests/test_seed.py`; regenerate
`server/data/app.db`.

**Interfaces:** `SeedSummary.checklist_templates`, `SeedSummary.checklist_instances`.

- [ ] **Step 1: Write the failing assertions** — in `test_seed_matches_spec_counts`, after the
housekeeping block (import `ChecklistInstance`, `ChecklistTemplate`, `ChecklistStatus`,
`pm_cycles`, `timedelta`):

```python
        # shift checklists (spec §5) — yesterday's planted instances only (clarification 6)
        yesterday = pm_cycles.local_today(hvh) - timedelta(days=1)
        assert count(ChecklistTemplate, ChecklistTemplate.property_id == hvh.id) == 5
        assert count(ChecklistInstance, ChecklistInstance.due_date == yesterday,
                     ChecklistInstance.status == ChecklistStatus.complete) == 2
        assert count(ChecklistInstance, ChecklistInstance.due_date == yesterday,
                     ChecklistInstance.status == ChecklistStatus.missed) == 1
        assert count(WorkOrder, WorkOrder.title.like("Pool pH 8.1 out of range%")) == 1
    assert summary.checklist_templates == 5
```

- [ ] **Step 2: Run to verify it fails.**

- [ ] **Step 3: Implement** — `SeedSummary` gains `checklist_templates: int` and
`checklist_instances: int` (counted from the database like its neighbours). Imports:
`ck_instances, ck_photos, ck_templates, ck_tick, shifts` from `app.domain`; `ChecklistAnswer,
ChecklistTemplateItem` from `app.models`; `ChecklistStatus, PmItemType` from enums;
`ChecklistTemplateIn` from `app.schemas.checklists`; `AnswerPatch, TemplateItemIn` from
`app.schemas.pm`. Add `"checklist.tick"` to the `ensure_recurring` tuple. Just before
`# ---- recurring jobs`, after the housekeeping block:

```python
        # ---- shift checklists (checklists spec §5). Through the domain. Yesterday's instances
        # are planted directly so test_seed never depends on the time of day (plan
        # clarification 6); today's depend on when the seed runs and are not asserted.
        def ck_template(name, dept, schedule, shift, weekdays, items):
            return ck_templates.create(db, hvh.id, staff["alex"].id, ChecklistTemplateIn(
                name=name, department_id=depts[dept].id, schedule=schedule, shift=shift,
                weekdays=weekdays, items=[TemplateItemIn(**i) for i in items]))

        every_day, mon_wed_fri = 0b1111111, 0b0010101
        fd_open = ck_template("Front Desk AM Opening", "front_desk", "weekly", "am", every_day, [
            {"label": "Cash drawer counted", "item_type": "number", "unit": "$",
             "min_value": 150, "max_value": 250},
            {"label": "Lobby walk-through done", "item_type": "checkbox"},
            {"label": "Key encoder tested", "item_type": "checkbox"}])
        ck_template("Front Desk Overnight Night Audit", "front_desk", "weekly", "overnight",
                    every_day, [
                        {"label": "Night audit run", "item_type": "checkbox"},
                        {"label": "Credit card batch closed", "item_type": "checkbox"},
                        {"label": "Audit report", "item_type": "photo"}])
        rounds = ck_template("Engineering AM Rounds", "engineering", "weekly", "am", every_day, [
            {"label": "Pool free chlorine", "item_type": "number", "unit": "ppm",
             "min_value": 1.0, "max_value": 3.0},
            {"label": "Pool pH", "item_type": "number", "unit": "", "min_value": 7.2,
             "max_value": 7.8},
            {"label": "Boiler supply temp", "item_type": "number", "unit": "°F",
             "min_value": 140, "max_value": 180}])
        linen = ck_template("Housekeeping PM Linen Par", "housekeeping", "weekly", "pm",
                            mon_wed_fri, [
                                {"label": "King sheet sets", "item_type": "number",
                                 "unit": "sets", "min_value": 40},
                                {"label": "Bath towels", "item_type": "number", "min_value": 120},
                                {"label": "Linen room tidy", "item_type": "checkbox"}])
        ck_template("Engineering Power Outage Response", "engineering", "on_demand", None, None, [
            {"label": "Generator started", "item_type": "checkbox"},
            {"label": "Elevators checked for trapped guests", "item_type": "checkbox"},
            {"label": "Notes", "item_type": "text", "required": False}])

        value_field = {PmItemType.checkbox: "bool_value", PmItemType.text: "text_value",
                       PmItemType.number: "number_value"}

        def run_checklist(inst, actor, role, values):
            ck_instances.start(db, hvh.id, actor.id, role, inst.id)
            for answer, item in db.execute(
                    select(ChecklistAnswer, ChecklistTemplateItem)
                    .join(ChecklistTemplateItem,
                          ChecklistTemplateItem.id == ChecklistAnswer.item_id)
                    .where(ChecklistAnswer.instance_id == inst.id)).all():
                if item.label in values:
                    ck_instances.save_answer(
                        db, hvh.id, actor.id, role, inst.id, answer.id,
                        AnswerPatch(**{value_field[item.item_type]: values[item.label]}))

        yesterday = pm_cycles.local_today(hvh) - timedelta(days=1)
        for template, actor, role, values in (
                (fd_open, staff["marcus"], Role.agent,
                 {"Cash drawer counted": 200, "Lobby walk-through done": True,
                  "Key encoder tested": True}),
                (rounds, staff["eli"], Role.dept_staff,
                 {"Pool free chlorine": 2.1, "Pool pH": 8.1, "Boiler supply temp": 162})):
            inst, _ = ck_instances.ensure_instance(db, template, yesterday)
            run_checklist(inst, actor, role, values)
            ck_instances.complete(db, hvh.id, actor.id, role, inst.id)  # pH 8.1 → work order
            window_start, _ = shifts.shift_window(hvh, yesterday, inst.shift)
            inst.started_at = window_start + timedelta(minutes=40)
            inst.completed_at = window_start + timedelta(minutes=65)
        abandoned, _ = ck_instances.ensure_instance(db, linen, yesterday)
        run_checklist(abandoned, staff["hana"], Role.dept_staff, {"King sheet sets": 44})
        ck_tick.tick(db)  # yesterday's PM window is over → missed; today's generated
        today_rounds, _ = ck_instances.ensure_instance(db, rounds, pm_cycles.local_today(hvh))
        if today_rounds.status == ChecklistStatus.open:
            ck_instances.start(db, hvh.id, staff["noah"].id, Role.dept_staff, today_rounds.id)
        db.flush()
```

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py tests/test_dev_start.py -q` → PASS.

- [ ] **Step 5: Regenerate** `cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('sqlite:///data/app.db', reset=True))"` — the summary shows `checklist_templates=5`.

- [ ] **Step 6: Full suite + ruff, commit (including `app.db`)**

```bash
git add server/seed/seed.py server/tests/test_seed.py server/data/app.db
git commit -m "feat(checklists): seed templates, a completed day and a missed check"
```

---

### Task 11: Web data layer

**Files:** Modify `web/src/api/queryKeys.ts`, `web/src/api/ws.ts` (+`ws.test.tsx`); create
`web/src/api/hooks/checklists.ts`.

**Interfaces:** `qk.ckAll`, `qk.ckTemplates`, `qk.ckInstances(p, params)`, `qk.ckInstancesAll`,
`qk.ckInstance(p, id)`, `qk.ckMissedAll`; hooks `useChecklistTemplates`,
`useCreateChecklistTemplate`, `usePatchChecklistTemplate` (`{ id, ...patch }`),
`useChecklistInstances({ day?, departmentId? })`, `useChecklistInstance(id | undefined)`,
`useMissedChecklists(enabled: boolean)`, `useAssignChecklist` (`{ instanceId, userId }`),
`useStartChecklist` (id), `useStartOnDemand` (templateId → `ChecklistInstanceOut`),
`useSaveChecklistAnswer` (`{ instanceId, answerId, patch }`), `useSetChecklistComment`
(`{ instanceId, comment }`), `useCompleteChecklist` (id), `useUploadChecklistPhoto`
(`{ instanceId, file, itemId? }`).

- [ ] **Step 1: Failing test** — in `ws.test.tsx`, with the file's `base`:

```ts
  it('refreshes the checklist list, the missed view and each instance for checklist.instances.changed', () => {
    expect(invalidationsFor({ ...base, type: 'checklist.instances.changed', payload: { ids: ['i-1'] } }, 'prop-a'))
      .toEqual([['ck', 'prop-a', 'instances'], ['ck', 'prop-a', 'missed'], ['ck', 'prop-a', 'instance', 'i-1']])
  })
```

- [ ] **Step 2: Run to verify it fails**, then add to `queryKeys.ts`:

```ts
  ckAll: (propertyId: string) => ['ck', propertyId] as const,
  ckTemplates: (propertyId: string) => ['ck', propertyId, 'templates'] as const,
  ckInstances: (propertyId: string, params: Record<string, string | null>) =>
    ['ck', propertyId, 'instances', params] as const,
  ckInstancesAll: (propertyId: string) => ['ck', propertyId, 'instances'] as const,
  ckInstance: (propertyId: string, id: string) => ['ck', propertyId, 'instance', id] as const,
  ckMissedAll: (propertyId: string) => ['ck', propertyId, 'missed'] as const,
```

and to `ws.ts` `invalidationsFor`, before `default:`:

```ts
    case 'checklist.instances.changed': {
      keys.push([...qk.ckInstancesAll(propertyId)])
      keys.push([...qk.ckMissedAll(propertyId)])
      const ids = event.payload['ids']
      if (Array.isArray(ids)) {
        for (const value of ids) {
          const instanceId = str(value)
          if (instanceId) keys.push([...qk.ckInstance(propertyId, instanceId)])
        }
      }
      break
    }
```

- [ ] **Step 3: Create `web/src/api/hooks/checklists.ts`** — structured exactly like
`web/src/api/hooks/housekeeping.ts` (a `ckPath(p, rest)` helper over
`propertyPath(p, \`checklists/${rest}\`)`, query hooks, and a `useCkMutation` helper whose
`onSuccess` invalidates `qk.ckAll(propertyId)`), plus a local `qs(params)` copied from
`hooks/pm.ts`:

```ts
export type InstanceParams = { day?: string | null; departmentId?: string | null }

export function useChecklistInstances(params: InstanceParams = {}) {
  const { propertyId } = useSession()
  const normalised = { day: params.day ?? null, departmentId: params.departmentId ?? null }
  return useQuery<ChecklistInstanceRowOut[], ApiError>({
    queryKey: qk.ckInstances(propertyId, normalised),
    queryFn: () => api<ChecklistInstanceRowOut[]>(ckPath(propertyId, `instances${qs(normalised)}`)),
  })
}

export function useChecklistInstance(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<ChecklistInstanceOut, ApiError>({
    queryKey: qk.ckInstance(propertyId, id ?? ''),
    queryFn: () => api<ChecklistInstanceOut>(ckPath(propertyId, `instances/${id}`)),
    enabled: Boolean(id),
  })
}

export function useMissedChecklists(enabled: boolean) {
  const { propertyId } = useSession()
  return useQuery<ChecklistInstanceRowOut[], ApiError>({
    queryKey: qk.ckMissedAll(propertyId),
    queryFn: () => api<ChecklistInstanceRowOut[]>(ckPath(propertyId, 'missed?days=7')),
    enabled,
  })
}

export const useSaveChecklistAnswer = () =>
  useCkMutation<{ instanceId: string; answerId: string; patch: AnswerPatch }, ChecklistInstanceOut>(
    (p, { instanceId, answerId, patch }) =>
      api(ckPath(p, `instances/${instanceId}/answers/${answerId}`), { method: 'PATCH', json: patch }),
  )

export const useUploadChecklistPhoto = () =>
  useCkMutation<{ instanceId: string; file: File; itemId?: string | null }, ChecklistInstanceOut>(
    (p, { instanceId, file, itemId }) => {
      const form = new FormData()
      form.set('photo', file)
      if (itemId) form.set('itemId', itemId)
      return api(ckPath(p, `instances/${instanceId}/photos`), { method: 'POST', body: form })
    },
  )
```

and, in the same style: `useChecklistTemplates` (GET `templates`), `useCreateChecklistTemplate`
(POST `templates`), `usePatchChecklistTemplate` (PATCH `templates/${id}`), `useAssignChecklist`
(POST `instances/${instanceId}/assign`, json `{ userId }`), `useStartChecklist` (POST
`instances/${id}/start`), `useStartOnDemand` (POST `templates/${templateId}/start`),
`useSetChecklistComment` (PATCH `instances/${instanceId}`, json `{ comment }`),
`useCompleteChecklist` (POST `instances/${id}/complete`).

- [ ] **Step 4: Run** `cd web && npx vitest run src/api/ws.test.tsx && npm run lint && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/queryKeys.ts web/src/api/ws.ts web/src/api/ws.test.tsx web/src/api/hooks/checklists.ts
git commit -m "feat(checklists): web query keys, realtime invalidation and hooks"
```

---

### Task 12: Extract the shared item editor

**Files:** Create `web/src/features/admin/ItemListEditor.tsx` (+`ItemListEditor.test.tsx`);
modify `web/src/features/admin/PmTemplatesAdmin.tsx`.

**Interfaces:** Produces `ItemDraft` (type), `NEW_ITEM`, `toItemIn(item: ItemDraft):
TemplateItemIn`, `itemDraftFrom(item: TemplateItemOut): ItemDraft`, and
`ItemListEditor({ items, onChange, error }: { items: ItemDraft[]; onChange: (items: ItemDraft[])
=> void; error?: string })`.

- [ ] **Step 1: Failing test** — `web/src/features/admin/ItemListEditor.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { ItemListEditor, type ItemDraft } from './ItemListEditor'

function Harness({ initial = [] as ItemDraft[] }) {
  const [items, setItems] = useState(initial)
  return (
    <>
      <ItemListEditor items={items} onChange={setItems} />
      <output data-testid="labels">{items.map((i) => i.label).join('|')}</output>
    </>
  )
}

const saved: ItemDraft = { id: 'i-1', label: 'Pool pH', itemType: 'number', unit: '',
  minValue: '7.2', maxValue: '7.8', required: true }

describe('ItemListEditor', () => {
  it('adds an item and shows bounds only for numbers', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Add item' }))
    await user.type(screen.getByLabelText('Label for item 1'), 'Boiler temp')
    expect(screen.queryByLabelText('Min for item 1')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Type for item 1'), 'number')
    expect(screen.getByLabelText('Min for item 1')).toBeInTheDocument()
    expect(screen.getByTestId('labels')).toHaveTextContent('Boiler temp')
  })

  it('locks the type of a saved item, and reorders and removes', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[saved, { ...saved, id: 'i-2', label: 'Chlorine' }]} />)
    expect(screen.getByLabelText('Type for item 1')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Chlorine|Pool pH')
    await user.click(screen.getByRole('button', { name: 'Remove item 1' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Pool pH')
  })
})
```

- [ ] **Step 2: Run to verify it fails**, then create `ItemListEditor.tsx` by **moving** from
`PmTemplatesAdmin.tsx`: the `ItemDraft` type, `NEW_ITEM`, `toItemIn`, the item half of
`fromTemplate` as `itemDraftFrom`, the `LABEL`/`SELECT` class strings it uses, the `FieldError`
component, and the whole `<div>` block from `<p className={LABEL}>Checklist</p>` through the
closing `</ol></div>`, with `editItem`/`moveItem` rewritten against props:

```tsx
export function ItemListEditor({ items, onChange, error }: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
  error?: string
}) {
  const editItem = (index: number, change: Partial<ItemDraft>) =>
    onChange(items.map((item, i) => (i === index ? { ...item, ...change } : item)))
  const moveItem = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= items.length) return
    const next = [...items]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }
  // …the moved JSX, with `draft.items` → `items`, `edit({ items: X })` → `onChange(X)`,
  // and `<FieldError message={fields.items} />` → `<FieldError message={error} />`.
}
```

In `PmTemplatesAdmin.tsx`, delete the moved pieces, import them from `./ItemListEditor`, build
`items` with `itemDraftFrom` inside `fromTemplate`, and render
`<ItemListEditor items={draft.items} onChange={(items) => edit({ items })} error={fields.items} />`
where the block was. Keep `FieldError` in PM if other fields still use it (export it from
`ItemListEditor.tsx` and import it back rather than keeping two copies).

- [ ] **Step 3: Run** `cd web && npx vitest run src/features/admin && npm run lint && npm run build` → PASS (PM admin tests unchanged and green).

- [ ] **Step 4: Commit**

```bash
git add web/src/features/admin/ItemListEditor.tsx web/src/features/admin/ItemListEditor.test.tsx web/src/features/admin/PmTemplatesAdmin.tsx
git commit -m "refactor(admin): extract the typed item editor for reuse"
```

---

### Task 13: Admin — checklist templates

**Files:** Create `web/src/features/admin/ChecklistTemplatesAdmin.tsx` (+test),
`web/src/features/checklists/labels.ts`; modify `web/src/features/admin/AdminPage.tsx`,
`web/src/components/navModel.ts` (`ADMIN_SECTIONS`).

**Interfaces:** Produces `labels.ts` exports `SHIFT_LABELS: Record<Shift, string>` (`AM` / `PM`
/ `Overnight`), `STATUS_LABELS: Record<ChecklistStatus, string>` (`Open` / `In progress` /
`Complete` / `Missed`), `STATUS_TONE` (Badge tone per status: neutral / note / ok / danger),
`WEEKDAYS: string[]` (`['Mon','Tue','Wed','Thu','Fri','Sat','Sun']`), and
`weekdayLabel(mask: number | null | undefined): string` ("Every day", "Mon, Wed, Fri", "—").

- [ ] **Step 1: Failing test** — `web/src/features/admin/ChecklistTemplatesAdmin.test.tsx`
(same harness and fetch-stub pattern as `PmTemplatesAdmin.test.tsx`):

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (init?.method === 'POST') return json({ id: 't-new' }, 201)
    return json([])
  })
}

function posted() {
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')
  return post ? JSON.parse(String(post[1]!.body)) : undefined
}

async function startNew(name: string) {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
  await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
  await userEvent.type(screen.getByLabelText('Name'), name)
  await userEvent.selectOptions(await screen.findByLabelText('Department'), 'dept-eng')
}

async function addCheckbox(label: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
  await userEvent.type(screen.getByLabelText('Label for item 1'), label)
}

describe('ChecklistTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('creates a weekly template with the chosen days as a bitmask', async () => {
    await startNew('AM Rounds')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sat' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sun' }))
    await addCheckbox('Skimmers')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toEqual({
      name: 'AM Rounds', departmentId: 'dept-eng', schedule: 'weekly', shift: 'am',
      weekdays: 0b0011111, active: true,
      items: [{ label: 'Skimmers', itemType: 'checkbox', unit: null, minValue: null,
                maxValue: null, required: true }],
    }))
  })

  it('sends no shift or days for an on-demand template', async () => {
    await startNew('Outage')
    await userEvent.click(screen.getByRole('radio', { name: 'On demand' }))
    expect(screen.queryByLabelText('Shift')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Mon' })).not.toBeInTheDocument()
    await addCheckbox('Generator started')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toMatchObject(
      { schedule: 'on_demand', shift: null, weekdays: null }))
  })
})
```

- [ ] **Step 2: Run to verify it fails**, then implement.

`labels.ts` — the constants above; `weekdayLabel` returns `'Every day'` for 127, `'—'` for
null/0, else the matching `WEEKDAYS` joined with `', '`.

`ChecklistTemplatesAdmin.tsx` — same skeleton as `PmTemplatesAdmin` (header with "New template",
`AdminTable` of templates, `EditPanel` for the draft, `fieldErrors` for field messages). Columns:
Name · Department · Schedule (`On demand`, or `${SHIFT_LABELS[shift]} · ${weekdayLabel(weekdays)}`)
· Items (count) · Active. Draft fields: `name`, `departmentId` (a `<select aria-label="Department">`
from `useDepartments()`), `schedule` (two radio inputs labelled `Weekly` / `On demand`), when
weekly a `<select aria-label="Shift">` (AM/PM/Overnight) and seven checkboxes labelled by
`WEEKDAYS` (default all ticked), `active`, and `<ItemListEditor>`. Save builds:

```ts
const body: ChecklistTemplateIn = {
  name: draft.name.trim(), departmentId: draft.departmentId, schedule: draft.schedule,
  shift: draft.schedule === 'weekly' ? draft.shift : null,
  weekdays: draft.schedule === 'weekly'
    ? draft.days.reduce((mask, on, i) => (on ? mask | (1 << i) : mask), 0) : null,
  active: draft.active, items: draft.items.map(toItemIn),
}
```

and calls `useCreateChecklistTemplate` or `usePatchChecklistTemplate` (`{ id, ...body }`).
Editing an existing template derives `days` from its mask (`(mask >> i) & 1`).

Wire it in: `ADMIN_SECTIONS` gains `{ to: '/app/admin/checklist-templates', label: 'Checklist
templates' }` after PM templates; `AdminPage.tsx` gains
`<Route path="checklist-templates" element={<ChecklistTemplatesAdmin />} />`.

- [ ] **Step 3: Run** `cd web && npx vitest run src/features/admin && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/admin/ChecklistTemplatesAdmin.tsx web/src/features/admin/ChecklistTemplatesAdmin.test.tsx web/src/features/admin/AdminPage.tsx web/src/components/navModel.ts web/src/features/checklists/labels.ts
git commit -m "feat(checklists): admin editor for checklist templates"
```

---

### Task 14: Checklists page and nav

**Files:** Create `web/src/features/checklists/ChecklistsPage.tsx` (+test); modify
`web/src/components/navModel.ts` (+test), `web/src/components/NavIcon.tsx`,
`web/src/routes.tsx`, and any test that enumerates nav entries.

**Interfaces:** `ChecklistsPage` at `/app/checklists`.

- [ ] **Step 1: Failing tests**

`navModel.test.ts`:

```ts
  it('puts Checklists in Overview after Log', () => {
    const overview = NAV_GROUPS.find((g) => g.heading === 'Overview')!
    const labels = overview.items.map((i) => i.label)
    expect(labels.indexOf('Checklists')).toBe(labels.indexOf('Log') + 1)
    const item = overview.items.find((i) => i.label === 'Checklists')!
    expect(isNavItemActive(item, '/app/checklists/abc')).toBe(true)
  })
```

`web/src/features/checklists/ChecklistsPage.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ChecklistInstanceRowOut, ChecklistTemplateOut, Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistsPage } from './ChecklistsPage'

function row(over: Partial<ChecklistInstanceRowOut>): ChecklistInstanceRowOut {
  return {
    id: 'i-am', templateId: 't-am', templateName: 'Engineering AM Rounds',
    departmentId: 'dept-eng', departmentName: 'Engineering', dueDate: '2026-09-10', shift: 'am',
    onDemand: false, status: 'open', assignedUserId: null, assignedName: null,
    completedByName: null, done: 0, total: 3, outOfRangeCount: 0, ...over,
  }
}

const TODAY = [
  row({}),
  row({ id: 'i-pm', templateId: 't-pm', templateName: 'Engineering PM Walk', shift: 'pm',
        status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer', done: 2,
        total: 5, outOfRangeCount: 1 }),
]
const ON_DEMAND: ChecklistTemplateOut = {
  id: 't-out', name: 'Power Outage', departmentId: 'dept-eng', departmentName: 'Engineering',
  schedule: 'on_demand', shift: null, weekdays: null, active: true, items: [],
}
const MISSED = [row({ id: 'i-old', dueDate: '2026-09-09', status: 'missed',
                      templateName: 'Housekeeping PM Linen Par' })]

const calls: { url: string; method: string }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    calls.push({ url, method })
    const body = url.includes('/departments') ? [aDepartment()]
      : url.includes('staff-directory') ? []
      : url.includes('/checklists/missed') ? MISSED
      : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND]
      : method === 'POST' ? { ...row({}), id: url.includes('/templates/') ? 'i-new' : 'i-am' }
      : TODAY
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
}

function mount(role: Role) {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/checklists" element={<ChecklistsPage />} />
        <Route path="/app/checklists/:id" element={<p>checklist page</p>} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role, departmentId: 'dept-eng' }), route: '/app/checklists' },
  )
}

describe('ChecklistsPage', () => {
  beforeEach(() => {
    calls.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('groups today by shift with progress and an out-of-range flag', async () => {
    mount('dept_staff')
    await screen.findByText('Engineering PM Walk')
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent))
      .toEqual(['AM', 'PM'])
    const pm = screen.getByText('Engineering PM Walk').closest('li')!
    expect(within(pm).getByText('2 / 5')).toBeInTheDocument()
    expect(within(pm).getByText('Eli Engineer')).toBeInTheDocument()
    expect(within(pm).getByText('1 out of range')).toBeInTheDocument()
  })

  it('asks the server for my department by default', async () => {
    mount('dept_staff')
    await screen.findByText('Engineering AM Rounds')
    expect(calls.some((c) => c.url.includes('/checklists/instances')
      && c.url.includes('departmentId=dept-eng'))).toBe(true)
  })

  it('starts an open checklist and opens it', async () => {
    const user = userEvent.setup()
    mount('dept_staff')
    const am = (await screen.findByText('Engineering AM Rounds')).closest('li')!
    await user.click(within(am).getByRole('button', { name: 'Start' }))
    expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/instances/i-am/start')))
      .toBe(true)
    expect(await screen.findByText('checklist page')).toBeInTheDocument()
  })

  it('shows Assign only to supervisors and the Missed tab only to managers', async () => {
    const staff = mount('dept_staff')
    await screen.findByText('Engineering AM Rounds')
    expect(screen.queryByLabelText('Assign Engineering AM Rounds')).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Missed' })).not.toBeInTheDocument()
    staff.unmount()

    const sup = mount('supervisor')
    expect(await screen.findByLabelText('Assign Engineering AM Rounds')).toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: 'Missed' })).not.toBeInTheDocument()
    sup.unmount()

    const user = userEvent.setup()
    mount('manager')
    await user.click(await screen.findByRole('tab', { name: 'Missed' }))
    expect(await screen.findByText('Housekeeping PM Linen Par')).toBeInTheDocument()
  })

  it('starts an on-demand checklist from the menu', async () => {
    const user = userEvent.setup()
    mount('dept_staff')
    await user.selectOptions(await screen.findByLabelText('Start a checklist'), 't-out')
    await waitFor(() => expect(calls.some(
      (c) => c.method === 'POST' && c.url.endsWith('/templates/t-out/start'))).toBe(true))
    expect(await screen.findByText('checklist page')).toBeInTheDocument()
  })
})
```

(If the generated `ChecklistTemplateOut` / `ChecklistInstanceRowOut` make some fields optional,
keep the literal objects as written — extra explicit `null`s are valid.)

- [ ] **Step 2: Run to verify they fail**, then implement.

`NavIcon.tsx`: add `'checklist'` with path
`'M9 11l2 2 4-4M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1Z'`.
`navModel.ts` Overview group, right after Log:
`{ label: 'Checklists', to: '/app/checklists', icon: 'checklist', needs: ['view_checklists'], match: ['/app/checklists'] },`
Update any test that enumerates Overview/command-palette entries to include `'Checklists'`.

`ChecklistsPage.tsx`:
- Department filter: a `<select aria-label="Department">` from `useDepartments()` with an "All
  departments" option; initial value `membership.departmentId ?? ''`; passes
  `departmentId: value || null` to `useChecklistInstances`.
- Tabs (`role="tablist"`, like PM's InspectionPage): **Today**, and **Missed** only when
  `can('view_property_analytics')`.
- Today: rows grouped by `shift` in AM → PM → Overnight order, each group an `<h2>` with
  `SHIFT_LABELS[shift]`; empty groups not rendered; `EmptyState title="No checklists today"`
  when none. A card (`<li>`): template name, department, `<Badge tone={STATUS_TONE[s]}>`,
  assignee name or "Unassigned", `${done} / ${total}`, and `N out of range` when
  `outOfRangeCount > 0`. Actions: **Start** (status `open`, when `can('perform_checklists')`) →
  `useStartChecklist` then `navigate(\`/app/checklists/${id}\`)`; **Continue** / **View**
  (otherwise) → a link to `/app/checklists/${id}`; **Assign** (when
  `can('manage_checklists')` and status `open`/`in_progress`) → a small inline `<select
  aria-label={\`Assign ${templateName}\`}>` of department members (from `useStaffDirectory()`
  in `api/hooks/staffMessages.ts`, filtered by `departmentId`) plus "Unassigned", calling
  `useAssignChecklist`.
- **Start a checklist**: a `<select aria-label="Start a checklist">` of active on-demand
  templates (from `useChecklistTemplates()`, filtered to `schedule === 'on_demand'` and — unless
  the user has `manage_checklists` — to their department); choosing one calls
  `useStartOnDemand` and navigates to the created instance.
- Missed tab: `useMissedChecklists(can('view_property_analytics'))`, a list of date · shift ·
  department · template · assignee.
- Every mutation's error renders inline as `<p role="alert" className="text-sm text-dangerText">`.

`routes.tsx`: `<Route path="checklists" element={<RequireCapability capability="view_checklists"><ChecklistsPage /></RequireCapability>} />`.

- [ ] **Step 3: Run** `cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/checklists/ChecklistsPage.tsx web/src/features/checklists/ChecklistsPage.test.tsx web/src/components/navModel.ts web/src/components/navModel.test.ts web/src/components/NavIcon.tsx web/src/routes.tsx
git commit -m "feat(checklists): today's checklists page with claim, assign and missed"
```

(Add any nav-enumeration test files you had to update to the `git add`.)

---

### Task 15: The checklist page

**Files:** Create `web/src/features/checklists/ChecklistRunPage.tsx` (+test); modify
`web/src/routes.tsx`.

**Interfaces:** `ChecklistRunPage` at `/app/checklists/:id`, rendering rows with
`features/pm/ChecklistItem.tsx` unchanged.

- [ ] **Step 1: Failing test** — `web/src/features/checklists/ChecklistRunPage.test.tsx`.
Before writing it, open `web/src/features/pm/ChecklistItem.tsx` and confirm the accessible name
of a checkbox row's input (it is labelled by `item.label`, id `pm-item-<id>`); the test below
relies on `getByRole('checkbox', { name: /Skimmers/ })`.

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ChecklistInstanceOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistRunPage } from './ChecklistRunPage'

const BASE: ChecklistInstanceOut = {
  id: 'i-1', templateId: 't-1', templateName: 'Engineering AM Rounds', departmentId: 'dept-eng',
  departmentName: 'Engineering', dueDate: '2026-09-10', shift: 'am', onDemand: false,
  status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
  completedByName: null, done: 0, total: 2, outOfRangeCount: 0, startedByName: 'Eli Engineer',
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null,
  items: [
    { id: 'it-chk', position: 0, label: 'Skimmers', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
    { id: 'it-ph', position: 1, label: 'Pool pH', itemType: 'number', unit: '', minValue: 7.2,
      maxValue: 7.8, required: true, active: true },
  ],
  answers: [
    { id: 'a-chk', itemId: 'it-chk', boolValue: null, textValue: null, numberValue: null,
      outOfRange: false, answeredAt: null },
    { id: 'a-ph', itemId: 'it-ph', boolValue: null, textValue: null, numberValue: 7.4,
      outOfRange: false, answeredAt: '2026-09-10T11:40:00Z' },
  ],
  photos: [],
  missingRequired: ['it-chk'],
}

let instance: ChecklistInstanceOut = BASE
let patchStatus = 200
const writes: { url: string; method: string; body: unknown }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (method !== 'GET') {
      writes.push({ url: String(input), method,
                    body: init?.body ? JSON.parse(String(init.body)) : null })
      if (patchStatus !== 200) {
        return Promise.resolve(new Response(JSON.stringify({ error: {
          code: 'INVALID_TRANSITION', message: 'This checklist is not in progress' } }),
          { status: patchStatus }))
      }
    }
    return Promise.resolve(new Response(JSON.stringify(instance), { status: 200 }))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/checklists/:id" element={<ChecklistRunPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'dept_staff', departmentId: 'dept-eng' }),
      route: '/app/checklists/i-1' },
  )
}

describe('ChecklistRunPage', () => {
  beforeEach(() => {
    instance = BASE
    patchStatus = 200
    writes.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('saves an answer as it is entered', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('checkbox', { name: /Skimmers/ }))
    await waitFor(() => expect(writes).toContainEqual({
      url: '/api/p/prop-a/checklists/instances/i-1/answers/a-chk', method: 'PATCH',
      body: { boolValue: true } }))
  })

  it('keeps Complete disabled and lists what is missing', async () => {
    mount()
    expect(await screen.findByRole('button', { name: 'Complete' })).toBeDisabled()
    expect(screen.getByText(/Still to do: Skimmers/)).toBeInTheDocument()
  })

  it('saves the handover comment', async () => {
    const user = userEvent.setup()
    mount()
    await user.type(await screen.findByLabelText('Handover note'), 'Boiler 2 noisy')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(writes).toContainEqual({
      url: '/api/p/prop-a/checklists/instances/i-1', method: 'PATCH',
      body: { comment: 'Boiler 2 noisy' } }))
  })

  it('is read-only once missed', async () => {
    instance = { ...BASE, status: 'missed', missingRequired: [] }
    mount()
    expect(await screen.findByText('Missed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Skimmers/ })).toBeDisabled()
  })

  it('shows a failed save inline', async () => {
    patchStatus = 409
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('checkbox', { name: /Skimmers/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This checklist is not in progress')
  })
})
```

- [ ] **Step 2: Run to verify it fails**, then implement `ChecklistRunPage.tsx` on
`features/pm/RunPage.tsx`'s layout: a header (← Checklists link, template name, `STATUS_LABELS`
badge, department · shift · date, started-by / completed-by with `formatClock`); the items via
`<ChecklistItem item answer photos readOnly missing onSave onUpload />` where
`onSave = (patch) => save.mutate({ instanceId, answerId: answerFor(item.id)!.id, patch })` and
`onUpload = (file) => upload.mutate({ instanceId, file, itemId: item.id })`; a general photo
input; a **Handover note** `<Textarea aria-label="Handover note">` with a **Save note** button
(`useSetChecklistComment`); and **Complete** (`variant="primary"`, disabled while
`missingRequired.length > 0`, with "Still to do: …" listing the missing labels) calling
`useCompleteChecklist`. `readOnly = status !== 'in_progress' || !can('perform_checklists')`; an
`open` instance shows a **Start** button instead of the items' inputs. Every mutation's error
renders inline (`role="alert"`) rather than as a toast.

`routes.tsx`: `<Route path="checklists/:id" element={<RequireCapability capability="view_checklists"><ChecklistRunPage /></RequireCapability>} />`.

- [ ] **Step 3: Run** `cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/checklists/ChecklistRunPage.tsx web/src/features/checklists/ChecklistRunPage.test.tsx web/src/routes.tsx
git commit -m "feat(checklists): the checklist page, reusing PM's item component"
```

---

### Task 16: Postgres verification, full check, deploy

- [ ] **Step 1: Everything green locally** — server pytest + ruff; web test + lint + build;
regenerate the schema/types and confirm `git status --short web/src/api` shows nothing.

- [ ] **Step 2: Migrate a Postgres 18 database** (Docker Desktop must be running; start it
from `C:\Users\bryan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe` if `docker info`
fails):

```bash
docker rm -f relay-pg18 2>/dev/null; docker run -d --name relay-pg18 -e POSTGRES_PASSWORD=relaydev -e POSTGRES_USER=relay -e POSTGRES_DB=relay_test -p 55432:5432 postgres:18
# wait for: docker exec relay-pg18 pg_isready -U relay
cd server && export DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_test"
../.venv/Scripts/python.exe -m alembic upgrade head
../.venv/Scripts/python.exe -m alembic downgrade 0008
docker exec relay-pg18 psql -U relay -d relay_test -c "\dt checklist*"   # → no relations
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_test -c "\dt checklist*"   # → five tables
```

Also prove the NULL-distinct unique key on Postgres:

```bash
docker exec -i relay-pg18 psql -U relay -d relay_test <<'SQL'
INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at) VALUES ('p1','P','PPP','UTC','USD','{}',now(),now());
INSERT INTO department (id,property_id,name,type,escalation_minutes,active,created_at,updated_at) VALUES ('d1','p1','Eng','engineering',15,true,now(),now());
INSERT INTO checklist_template (id,property_id,name,department_id,schedule,active,created_at,updated_at) VALUES ('t1','p1','T','d1','on_demand',true,now(),now());
INSERT INTO checklist_instance (id,property_id,template_id,due_date,shift,slot,status,created_at,updated_at) VALUES ('a','p1','t1','2026-09-10','am',NULL,'open',now(),now()),('b','p1','t1','2026-09-10','am',NULL,'open',now(),now());
SQL
```

Expected: both instance rows insert (on-demand repeats are allowed).

- [ ] **Step 3: Run the whole app on Postgres** — drop/create `relay_dev`, run
`DATABASE_URL=".../relay_dev" .venv/Scripts/python.exe server/dev_start.py` in the background,
wait for `/api/health`, log in as `eli@hvh.test` / `Password123!`, and
`GET /api/p/<pid>/checklists/instances` and `/templates`: templates = 5; then log in as
`morgan@hvh.test` and `GET /checklists/missed` returns the missed linen check. Run
`ck_tick.tick` once against Postgres (as the housekeeping re-check did) and confirm it returns a
dict without error. Stop the server.

- [ ] **Step 4: Ask the user before pushing** — show `git log --oneline origin/main..HEAD`.
Pushing `main` deploys to production.

- [ ] **Step 5: After approval,** `git push origin main`, then verify on Railway: the deployment
for the new head reaches SUCCESS with reason `deploy`; its log shows `==> alembic upgrade head`
before `==> gunicorn`; `/api/health` is ok; and from inside the container
`SELECT version_num FROM alembic_version` returns `0009` and the five `checklist_*` tables exist
(empty — production is never seeded).

