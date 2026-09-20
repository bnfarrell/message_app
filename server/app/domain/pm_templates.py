"""PM templates (spec §3.2–3.4, §4.5, §7.1)."""
from __future__ import annotations

import re
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


_TOO_FINE_FREQUENCIES = {"SECONDLY", "MINUTELY", "HOURLY"}


def validate_rrule(rrule: str) -> None:
    try:
        rrulestr(rrule, dtstart=datetime(2026, 1, 1, tzinfo=UTC))
    except (ValueError, TypeError, KeyError) as e:
        raise ValidationFailed("Invalid recurrence rule",
                               details={"rrule": "invalid_rrule"}) from e
    # Sub-daily frequencies pass rrulestr but mint runs faster than any tick interval could
    # sanely process (`fire_scheduled` caps nothing per tick).
    frequencies = {m.upper() for m in re.findall(r"FREQ=(\w+)", rrule, re.IGNORECASE)}
    if frequencies & _TOO_FINE_FREQUENCIES:
        raise ValidationFailed("Recurrence must be daily or coarser",
                               details={"rrule": "frequency_too_fine"})


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
    seen_ids: set[str] = set()
    for data in items:
        if data.id:
            if data.id in seen_ids:
                raise ValidationFailed("Duplicate item id", details={"items": "duplicate_item"})
            seen_ids.add(data.id)
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
    retired = [row for row in existing.values() if row.id not in keep]
    for n, row in enumerate(retired):
        # Pushed past the live range so a retired item never shares a position with a kept one —
        # historical runs render their answers `order_by(position)`.
        row.active = False
        row.position = 1000 + n
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
    schedule_changed = any(k in changes and changes[k] != before[k]
                           for k in ("mode", "rrule", "rrule_dtstart"))
    reactivated = before.get("active") is False and changes.get("active") is True
    if merged["mode"] == PmTemplateMode.scheduled and (schedule_changed or reactivated):
        # A changed schedule restarts from now, never backfills; a template reactivated after
        # being dormant must do the same, or `pm.tick` expands the whole dormant window at once.
        t.last_fired_at = clock.now()
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
