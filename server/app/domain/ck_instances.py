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
