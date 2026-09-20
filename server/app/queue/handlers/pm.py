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
