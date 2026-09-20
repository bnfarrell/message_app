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
        # DESC + NULLS LAST pinned explicitly (see pm_reports.sweep): SQLite sorts NULLs
        # first on ASC, PostgreSQL last, so `previous[0]` must not depend on the engine.
        .order_by(PmRun.completed_at.desc().nulls_last(), PmRun.id.desc())).all()
    out: list[InspectionRowOut] = []
    for run, unit, template in rows:
        previous = [p for p in previous_all if p.unit_id == unit.id and p.id != run.id]
        days = ((today - pm_cycles.local_today(prop, previous[0].completed_at)).days
                if previous and previous[0].completed_at else None)
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
