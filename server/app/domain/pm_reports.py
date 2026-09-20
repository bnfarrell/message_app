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
