"""Read models for the sweep page, cycle history and (Task 11) compliance (spec §5.3, §5.5).

Everything here is computed in Python from a handful of set queries per property — a hotel has
hundreds of units, not millions — and nothing here issues a query per row.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import pm_cycles, pm_runs
from app.domain.pm_units import natural_key
from app.errors import NotFound, ValidationFailed
from app.models import MaintainableUnit, PmCycle, PmRun, PmTemplate, Property
from app.schemas.enums import PmCycleStatus, PmRunStatus, PmTemplateMode
from app.schemas.pm import (
    ComplianceCycleOut,
    ComplianceOut,
    ComplianceQuery,
    ComplianceRunsOut,
    ComplianceTemplateOut,
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
