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
