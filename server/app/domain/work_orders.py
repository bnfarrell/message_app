from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, draft_prompts, notifications
from app.domain import conversations as conv_domain
from app.errors import Forbidden, NotFound, TransitionError, ValidationFailed
from app.models import (
    Conversation,
    Department,
    Guest,
    Message,
    PropertyMembership,
    Stay,
    UserAccount,
    WorkOrder,
    WorkOrderEvent,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    DepartmentType,
    Direction,
    LocationType,
    Priority,
    Role,
    WorkOrderEventType,
    WorkOrderStatus,
    WorkOrderType,
)
from app.schemas.work_orders import (
    CreateWorkOrder,
    WorkOrderDetail,
    WorkOrderEventOut,
    WorkOrderOut,
    WorkOrderPrefill,
)

S = WorkOrderStatus
TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    S.open: {S.assigned, S.in_progress, S.cancelled},
    S.assigned: {S.in_progress, S.open, S.cancelled},
    S.in_progress: {S.blocked, S.complete, S.cancelled},
    S.blocked: {S.in_progress, S.cancelled},
    S.complete: {S.verified, S.in_progress},
    S.verified: set(),
    S.cancelled: set(),
}
OPEN_STATUSES = [S.open, S.assigned, S.in_progress, S.blocked, S.complete]

DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "engineering": ("ac", "a/c", "air", "heat", "hvac", "hot", "cold", "leak", "toilet", "shower",
                    "drain", "light", "bulb", "tv", "remote", "wifi", "door", "lock", "broken",
                    "not working", "elevator", "noise", "outlet", "plug"),
    "housekeeping": ("towel", "towels", "pillow", "sheets", "linen", "clean", "dirty", "trash",
                     "vacuum", "amenities", "shampoo", "soap", "toilet paper", "housekeeping",
                     "turndown"),
    "front_desk": ("checkout", "check out", "check-in", "late", "early", "bill", "folio", "charge",
                   "reservation", "key", "parking", "valet", "wake", "luggage"),
}
TYPE_FOR_DEPARTMENT = {"engineering": WorkOrderType.maintenance,
                       "housekeeping": WorkOrderType.housekeeping,
                       "front_desk": WorkOrderType.guest_request}


def assert_transition(from_: WorkOrderStatus, to: WorkOrderStatus) -> None:
    if to not in TRANSITIONS.get(from_, set()):
        raise TransitionError(f"Cannot move a work order from {from_.value} to {to.value}")


def guess_department_type(text: str) -> str | None:
    import re

    t = text.lower()
    # word boundaries: "ac" must not match "back"
    scores = {dept: sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", t))
              for dept, kws in DEPARTMENT_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def get(db: Session, property_id: str, work_order_id: str) -> WorkOrder:
    wo = db.scalar(select(WorkOrder).where(WorkOrder.id == work_order_id,
                                            WorkOrder.property_id == property_id))
    if wo is None:
        raise NotFound("Work order not found")
    return wo


def _event(db: Session, wo: WorkOrder, user_id: str | None, type: WorkOrderEventType,
           from_value: str | None = None, to_value: str | None = None,
           comment: str | None = None) -> None:
    db.add(WorkOrderEvent(work_order_id=wo.id, property_id=wo.property_id, user_id=user_id,
                          type=type, from_value=from_value, to_value=to_value, comment=comment))


def _emit(db: Session, wo: WorkOrder, type: str) -> None:
    queue_event(db, wo.property_id, type,
                WorkOrderOut.model_validate(wo).model_dump(mode="json", by_alias=True))


def _validate_refs(db: Session, property_id: str, department_id: str | None,
                   assigned_user_id: str | None) -> None:
    if department_id and not db.scalar(select(Department.id).where(
            Department.id == department_id, Department.property_id == property_id)):
        raise ValidationFailed("Unknown department")
    if assigned_user_id and not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id,
            PropertyMembership.user_id == assigned_user_id)):
        raise ValidationFailed("Assignee is not a member of this property")


def create(db: Session, property_id: str, actor_user_id: str, data: CreateWorkOrder) -> WorkOrder:
    _validate_refs(db, property_id, data.department_id, data.assigned_user_id)
    if data.source_conversation_id:
        conv_domain.get(db, property_id, data.source_conversation_id)
    wo = WorkOrder(property_id=property_id, title=data.title.strip(), description=data.description,
                   type=data.type, priority=data.priority, location_type=data.location_type,
                   location_ref=data.location_ref,
                   department_id=data.department_id, assigned_user_id=data.assigned_user_id,
                   reported_by_user_id=actor_user_id,
                   source_conversation_id=data.source_conversation_id,
                   source_message_id=data.source_message_id, due_at=data.due_at,
                   status=S.assigned if data.assigned_user_id else S.open)
    db.add(wo)
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.created, to_value=wo.status.value)
    if wo.assigned_user_id:
        notifications.create(db, property_id, wo.assigned_user_id, "work_order.assigned",
                             f"Assigned: {wo.title}", body=wo.location_ref,
                             entity_type="work_order", entity_id=wo.id)
    elif wo.department_id:
        notifications.notify_user_or_department(db, property_id, user_id=None,
                                                department_id=wo.department_id,
                                                type="work_order.created",
                                                title=f"New work order: {wo.title}",
                                                body=wo.location_ref, entity_type="work_order",
                                                entity_id=wo.id)
    audit.record(db, property_id, actor_user_id, "work_order.created", "work_order", wo.id,
                 after={"title": wo.title, "source_conversation_id": wo.source_conversation_id})
    _emit(db, wo, "work_order.created")
    if wo.source_conversation_id:
        queue_event(db, property_id, "conversation.updated", {"id": wo.source_conversation_id})
    return wo


def prefill_from_conversation(db: Session, property_id: str,
                              conversation_id: str) -> WorkOrderPrefill:
    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    inbound = db.scalars(select(Message).where(Message.conversation_id == conv.id,
                                                Message.direction == Direction.inbound)
                         .order_by(Message.sent_at.desc(), Message.id.desc()).limit(3)).all()
    last = inbound[0] if inbound else None
    title = ((last.body.strip().splitlines() or ["Guest request"])[0][:120]
            if last else "Guest request")
    description = "\n".join(m.body for m in reversed(inbound))
    dept_type = guess_department_type(description)
    dept_id = None
    if dept_type:
        dept_id = db.scalar(select(Department.id).where(
            Department.property_id == property_id,
            Department.type == DepartmentType(dept_type)))
    name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or None
    return WorkOrderPrefill(
        title=title, description=description,
        type=TYPE_FOR_DEPARTMENT.get(dept_type, WorkOrderType.guest_request),
        priority=Priority.normal, location_type=LocationType.room if stay else LocationType.other,
        location_ref=stay.room_number if stay else None, department_id=dept_id, guest_name=name,
        source_conversation_id=conv.id, source_message_id=last.id if last else None)


def transition(db: Session, property_id: str, work_order_id: str, actor_user_id: str,
               to: WorkOrderStatus, comment: str | None = None) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    assert_transition(wo.status, to)
    now = clock.now()
    frm = wo.status
    wo.status = to
    if to == S.in_progress and wo.started_at is None:
        wo.started_at = now
    if to == S.complete:
        wo.completed_at = now
    if to == S.verified:
        wo.verified_at = now
    if wo.assigned_user_id == actor_user_id and wo.acknowledged_at is None:
        wo.acknowledged_at = now
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.status_changed, from_value=frm.value,
           to_value=to.value, comment=comment)
    audit.record(db, property_id, actor_user_id, "work_order.transition", "work_order", wo.id,
                 before={"status": frm.value}, after={"status": to.value})
    _emit(db, wo, "work_order.updated")
    if to == S.complete:
        draft_prompts.create_for_completion(db, wo)
    if wo.source_conversation_id:
        queue_event(db, property_id, "conversation.updated", {"id": wo.source_conversation_id})
    return wo


def assign(db: Session, property_id: str, work_order_id: str, actor_user_id: str, *,
           user_id: str | None = None, department_id: str | None = None,
           clear: bool = False) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    _validate_refs(db, property_id, department_id, user_id)
    before = wo.assigned_user_id
    if clear:
        wo.assigned_user_id = None
        if wo.status == S.assigned:
            wo.status = S.open
    if department_id:
        wo.department_id = department_id
    if user_id:
        wo.assigned_user_id = user_id
        wo.acknowledged_at = None
        if wo.status == S.open:
            wo.status = S.assigned
        if user_id != actor_user_id:
            notifications.create(db, property_id, user_id, "work_order.assigned",
                                 f"Assigned: {wo.title}", body=wo.location_ref,
                                 entity_type="work_order", entity_id=wo.id)
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.assigned, from_value=before,
           to_value=wo.assigned_user_id)
    _emit(db, wo, "work_order.updated")
    return wo


def comment(db: Session, property_id: str, work_order_id: str, actor_user_id: str,
           text: str) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    _event(db, wo, actor_user_id, WorkOrderEventType.commented, comment=text.strip())
    wo.updated_at = clock.now()
    _emit(db, wo, "work_order.updated")
    return wo


def set_priority(db: Session, property_id: str, work_order_id: str, actor_user_id: str,
                 priority: Priority) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    before = wo.priority
    wo.priority = priority
    _event(db, wo, actor_user_id, WorkOrderEventType.priority_changed, from_value=before.value,
           to_value=priority.value)
    _emit(db, wo, "work_order.updated")
    return wo


def list(db: Session, property_id: str, *, status: str | None = None,
         type: WorkOrderType | None = None,
         dept: str | None = None, assignee: str | None = None, mine_user_id: str | None = None,
         include_closed: bool = False) -> list[WorkOrderOut]:
    # `from __future__ import annotations` keeps this annotation lazy, and the def statement binds
    # the module-level name `list` only after the signature is built, so the annotation means
    # builtins.list.
    q = select(WorkOrder).where(WorkOrder.property_id == property_id)
    if status:
        try:
            statuses = [S(s) for s in status.split(",") if s]
        except ValueError as e:
            raise ValidationFailed(f"Unknown status in filter: {e}") from e
        q = q.where(WorkOrder.status.in_(statuses))
    elif not include_closed:
        q = q.where(WorkOrder.status.in_(OPEN_STATUSES))
    if type:
        q = q.where(WorkOrder.type == type)
    if dept:
        q = q.where(WorkOrder.department_id == dept)
    if assignee:
        q = q.where(WorkOrder.assigned_user_id == assignee)
    if mine_user_id:
        q = q.where(WorkOrder.assigned_user_id == mine_user_id)
    rows = db.scalars(q.order_by(WorkOrder.created_at.desc(), WorkOrder.id.desc())).all()
    return [WorkOrderOut.model_validate(w) for w in rows]


def _can_see_conversation(conv: Conversation, viewer_role: Role, viewer_user_id: str,
                          viewer_department_id: str | None) -> bool:
    try:
        conv_domain.assert_viewer_can_see(conv, viewer_role, viewer_user_id, viewer_department_id)
    except Forbidden:
        return False
    return True


def detail(db: Session, property_id: str, work_order_id: str, *, viewer_role: Role,
           viewer_user_id: str, viewer_department_id: str | None) -> WorkOrderDetail:
    """Work orders are property-wide by design (design.md §3.2 has no work-order-viewing
    capability), but `guest_name` and `room_number` here are read *through*
    `source_conversation_id` — so a dept_staff viewer who is 403'd from that conversation must
    not receive them back from this route instead. The viewer arguments are required, not
    optional, so a new caller cannot fail open by forgetting them.
    """
    wo = get(db, property_id, work_order_id)
    rows = db.execute(select(WorkOrderEvent, UserAccount)
                      .outerjoin(UserAccount, UserAccount.id == WorkOrderEvent.user_id)
                      .where(WorkOrderEvent.work_order_id == wo.id)
                      .order_by(WorkOrderEvent.created_at)).all()
    guest_name = room = None
    if wo.source_conversation_id:
        conv = db.get(Conversation, wo.source_conversation_id)
        if conv and _can_see_conversation(conv, viewer_role, viewer_user_id,
                                          viewer_department_id):
            g = db.get(Guest, conv.guest_id)
            guest_name = f"{g.first_name or ''} {g.last_name or ''}".strip() or g.phone_e164
            st = db.get(Stay, conv.stay_id) if conv.stay_id else None
            room = st.room_number if st else None
    base = WorkOrderOut.model_validate(wo).model_dump()
    return WorkOrderDetail(**base, guest_name=guest_name, room_number=room or wo.location_ref,
                           events=[WorkOrderEventOut(
                               id=e.id, user_id=e.user_id,
                               user_name=f"{u.first_name} {u.last_name}" if u else None,
                               type=e.type, from_value=e.from_value, to_value=e.to_value,
                               comment=e.comment, created_at=e.created_at) for e, u in rows])
