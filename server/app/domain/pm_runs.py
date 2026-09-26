"""PM runs: start, answer, photograph, complete (spec §3.6–3.8, §4.2, §4.3)."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications, pm_cycles, pm_templates, pm_units, typed_items
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
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    Priority,
    WorkOrderStatus,
    WorkOrderType,
)
from app.schemas.pm import AnswerPatch, RunAnswerOut, RunOut, RunPhotoOut, StartRunRequest
from app.schemas.work_orders import CreateWorkOrder


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
    typed_items.apply_answer(item, answer, data)
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
        if not typed_items.is_answered(item, answer, photographed):
            missing.append(item.id)
    return missing


def _raise_out_of_range(db: Session, run: PmRun, actor_user_id: str) -> list[WorkOrder]:
    rows = db.execute(select(PmRunAnswer, PmTemplateItem)
                      .join(PmTemplateItem, PmTemplateItem.id == PmRunAnswer.item_id)
                      .where(PmRunAnswer.run_id == run.id, PmRunAnswer.out_of_range.is_(True))
                      .order_by(PmTemplateItem.position)).all()
    if not rows:
        return []
    template = db.get(PmTemplate, run.template_id)
    unit = db.get(MaintainableUnit, run.unit_id)
    targets = [t for t in typed_items.escalation_targets(db, run.property_id,
                                                         template.department_id)
               if t != actor_user_id]
    created: list[WorkOrder] = []
    for answer, item in rows:
        title = typed_items.out_of_range_title(item, answer, unit.name)
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
