"""`checklist.tick` (checklists spec §3.2): every 5 minutes, stateless and idempotent. It never
records "I ran today" — it asks what ought to exist and what has ended."""
from __future__ import annotations

from sqlalchemy import select, update
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
                # Conditional on still being live: between the select above and this write,
                # someone may have just completed the instance. The status predicate makes
                # that a no-op instead of overwriting a just-completed instance as missed.
                result = db.execute(update(ChecklistInstance).where(
                    ChecklistInstance.id == inst.id,
                    ChecklistInstance.status.in_(ck_instances.LIVE))
                    .values(status=ChecklistStatus.missed))
                if result.rowcount:
                    changed.append(inst.id)
                    missed += 1
        db.flush()
        ck_instances.emit(db, prop.id, changed)
    return {"generated": generated, "missed": missed}
