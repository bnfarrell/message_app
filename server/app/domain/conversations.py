from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.domain import audit, notifications
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Conversation,
    Department,
    DraftPrompt,
    Guest,
    Message,
    Property,
    PropertyMembership,
    ResolutionCategory,
    Stay,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.conversations import (
    ConversationDetail,
    ConversationPatch,
    ConversationSummary,
    DraftPromptOut,
    GuestOut,
    GuestThread,
    GuestThreadMessage,
    MessageOut,
    StayOut,
    WorkOrderBrief,
)
from app.schemas.enums import Channel, ConversationStatus, DraftPromptStatus, Role, WorkOrderStatus


def get(db: Session, property_id: str, conversation_id: str) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                             Conversation.property_id == property_id))
    if c is None:
        raise NotFound("Conversation not found")
    return c


def _setting(db: Session, property_id: str, key: str, default: int) -> int:
    settings = db.scalar(select(Property.settings).where(Property.id == property_id)) or {}
    return int(settings.get(key, default))


def sla_minutes(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "sla_minutes", 15)


def auto_resolve_hours(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "auto_resolve_hours", 4)


def find_or_create_for_guest(db: Session, property_id: str, guest: Guest,
                             stay: Stay | None = None) -> tuple[Conversation, bool]:
    """Returns the guest's single live conversation, reopening an archived one if that is all there is."""
    c = db.scalar(
        select(Conversation).where(Conversation.property_id == property_id,
                                   Conversation.guest_id == guest.id)
        .order_by(Conversation.updated_at.desc())
    )
    if c is None:
        c = Conversation(property_id=property_id, guest_id=guest.id, stay_id=stay.id if stay else None,
                         status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(c)
        db.flush()
        return c, True
    if c.status == ConversationStatus.archived:
        c.status = ConversationStatus.open
        c.archived_at = None
        c.resolution_category_id = None
    elif c.status == ConversationStatus.snoozed:
        c.status = ConversationStatus.open
        c.snoozed_until = None
    if stay and c.stay_id != stay.id:
        c.stay_id = stay.id
    db.flush()
    return c, False


def touch_updated(db: Session, c: Conversation) -> None:
    c.updated_at = clock.now()
    queue_event(db, c.property_id, "conversation.updated", {"id": c.id})


OPEN_WO = [WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress, WorkOrderStatus.blocked]


def _open_wo_exists():
    return exists().where(WorkOrder.source_conversation_id == Conversation.id, WorkOrder.status.in_(OPEN_WO))


def _resolved_condition(db: Session, property_id: str):
    """Spec §4 'Resolved': open, quiet for N hours, no open work order — and answered, so an ignored
    guest can never fall out of the queue (a refinement of the spec wording)."""
    cutoff = clock.now() - timedelta(hours=auto_resolve_hours(db, property_id))
    return and_(Conversation.status == ConversationStatus.open,
                Conversation.last_guest_message_at.isnot(None),
                Conversation.last_guest_message_at < cutoff,
                ~_unanswered_expr(),
                ~_open_wo_exists())


def _unanswered_expr():
    return and_(Conversation.last_guest_message_at.isnot(None),
                or_(Conversation.last_staff_message_at.is_(None),
                    Conversation.last_staff_message_at < Conversation.last_guest_message_at))


def viewer_scope(q, viewer_role: Role, viewer_user_id: str, viewer_department_id: str | None):
    if viewer_role == Role.dept_staff:
        if viewer_department_id is None:
            return q.where(Conversation.assigned_user_id == viewer_user_id)
        return q.where(or_(Conversation.assigned_user_id == viewer_user_id,
                           Conversation.assigned_department_id == viewer_department_id))
    return q


def list(db: Session, property_id: str, *, filter: str, viewer_user_id: str, viewer_role: Role,
         viewer_department_id: str | None, dept: str | None = None, limit: int = 50,
         offset: int = 0) -> list[ConversationSummary]:  # noqa: A001 — mirrors the API name
    now = clock.now()
    resolved = _resolved_condition(db, property_id)
    q = (select(Conversation).where(Conversation.property_id == property_id)
         .options(selectinload(Conversation.guest), selectinload(Conversation.stay)))
    if filter == "all":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved)
    elif filter == "mine":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved,
                    Conversation.assigned_user_id == viewer_user_id)
    elif filter == "unassigned":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved,
                    Conversation.assigned_user_id.is_(None), Conversation.assigned_department_id.is_(None))
    elif filter == "overdue":
        q = q.where(Conversation.status == ConversationStatus.open, Conversation.sla_due_at.isnot(None),
                    Conversation.sla_due_at < now)
    elif filter == "resolved":
        q = q.where(resolved)
    elif filter == "archived":
        q = q.where(Conversation.status == ConversationStatus.archived)
    elif filter == "snoozed":
        q = q.where(Conversation.status == ConversationStatus.snoozed)
    else:
        raise ValidationFailed(f"Unknown filter {filter!r}")
    if dept:
        q = q.where(Conversation.assigned_department_id == dept)
    q = viewer_scope(q, viewer_role, viewer_user_id, viewer_department_id)
    q = q.order_by(case((_unanswered_expr(), 0), else_=1),
                   Conversation.last_guest_message_at.asc().nulls_last(),
                   Conversation.updated_at.desc()).limit(limit).offset(offset)
    rows = db.scalars(q).all()
    return [_summary(db, c) for c in rows]


def _last_preview(db: Session, conversation_id: str) -> str | None:
    body = db.scalar(select(Message.body).where(Message.conversation_id == conversation_id)
                     .order_by(Message.sent_at.desc()).limit(1))
    return body[:140] if body else None


def _open_wo_count(db: Session, conversation_id: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkOrder).where(
        WorkOrder.source_conversation_id == conversation_id, WorkOrder.status.in_(OPEN_WO))) or 0


def _summary(db: Session, c: Conversation) -> ConversationSummary:
    unanswered = bool(c.last_guest_message_at and (c.last_staff_message_at is None
                                                    or c.last_staff_message_at < c.last_guest_message_at))
    return ConversationSummary(
        id=c.id, status=c.status, guest=GuestOut.model_validate(c.guest),
        room_number=c.stay.room_number if c.stay else None,
        assigned_user_id=c.assigned_user_id, assigned_department_id=c.assigned_department_id,
        channel_primary=c.channel_primary, last_guest_message_at=c.last_guest_message_at,
        last_staff_message_at=c.last_staff_message_at, last_message_preview=_last_preview(db, c.id),
        sla_due_at=c.sla_due_at, unanswered=unanswered, open_work_order_count=_open_wo_count(db, c.id),
        snoozed_until=c.snoozed_until,
    )


def assert_viewer_can_see(c: Conversation, viewer_role: Role, viewer_user_id: str,
                          viewer_department_id: str | None) -> None:
    if viewer_role == Role.dept_staff and not (
        c.assigned_user_id == viewer_user_id or c.assigned_department_id == viewer_department_id
    ):
        raise Forbidden("This conversation belongs to another department")


def detail(db: Session, property_id: str, conversation_id: str) -> ConversationDetail:
    from app.domain import notes as notes_domain

    c = get(db, property_id, conversation_id)
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.sent_at)).all()
    wos = db.scalars(select(WorkOrder).where(WorkOrder.source_conversation_id == c.id)
                     .order_by(WorkOrder.created_at.desc())).all()
    prompts = db.execute(select(DraftPrompt, WorkOrder.title).join(WorkOrder, WorkOrder.id == DraftPrompt.work_order_id)
                         .where(DraftPrompt.conversation_id == c.id, DraftPrompt.status == DraftPromptStatus.pending)
                         .order_by(DraftPrompt.created_at)).all()
    return ConversationDetail(
        id=c.id, status=c.status, guest=GuestOut.model_validate(c.guest),
        stay=StayOut.model_validate(c.stay) if c.stay else None,
        assigned_user_id=c.assigned_user_id, assigned_department_id=c.assigned_department_id,
        channel_primary=c.channel_primary, last_guest_message_at=c.last_guest_message_at,
        last_staff_message_at=c.last_staff_message_at, first_response_seconds=c.first_response_seconds,
        sla_due_at=c.sla_due_at, snoozed_until=c.snoozed_until,
        resolution_category_id=c.resolution_category_id, archived_at=c.archived_at,
        messages=[MessageOut.model_validate(m) for m in msgs],
        notes=notes_domain.list_for(db, property_id, c.id),
        work_orders=[WorkOrderBrief.model_validate(w) for w in wos],
        draft_prompts=[DraftPromptOut(id=p.id, work_order_id=p.work_order_id, work_order_title=title,
                                      body=p.body, status=p.status, created_at=p.created_at)
                       for p, title in prompts],
    )


def guest_thread(db: Session, property_id: str, phone: str) -> GuestThread:
    """Guest-facing shape. Queries only `message` — internal_note is never touched here."""
    from app.domain.guests import find_by_phone

    prop = db.get(Property, property_id)
    guest = find_by_phone(db, property_id, phone)
    msgs: list[Message] = []
    if guest:
        msgs = db.scalars(
            select(Message).join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.guest_id == guest.id, Message.property_id == property_id)
            .order_by(Message.sent_at)
        ).all()
    return GuestThread(phone=guest.phone_e164 if guest else phone, property_name=prop.name,
                       messages=[GuestThreadMessage(id=m.id, direction=m.direction, body=m.body,
                                                    sent_at=m.sent_at, delivery_status=m.delivery_status)
                                 for m in msgs])


def patch(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
          changes: ConversationPatch, *, can_archive: bool) -> Conversation:
    c = get(db, property_id, conversation_id)
    before = {"status": c.status.value, "assigned_user_id": c.assigned_user_id,
              "assigned_department_id": c.assigned_department_id}
    if changes.clear_assignment:
        c.assigned_user_id = None
        c.assigned_department_id = None
    if changes.assigned_user_id is not None:
        if not db.scalar(select(PropertyMembership.id).where(PropertyMembership.property_id == property_id,
                                                              PropertyMembership.user_id == changes.assigned_user_id)):
            raise ValidationFailed("Assignee is not a member of this property")
        c.assigned_user_id = changes.assigned_user_id
        if changes.assigned_user_id != actor_user_id:
            notifications.create(db, property_id, changes.assigned_user_id, "conversation.assigned",
                                 "Conversation assigned to you", entity_type="conversation", entity_id=c.id)
    if changes.assigned_department_id is not None:
        if not db.scalar(select(Department.id).where(Department.id == changes.assigned_department_id,
                                                     Department.property_id == property_id)):
            raise ValidationFailed("Unknown department")
        c.assigned_department_id = changes.assigned_department_id
        c.assigned_user_id = None if changes.assigned_user_id is None else c.assigned_user_id
    category_supplied = "resolution_category_id" in changes.model_fields_set
    if category_supplied and changes.resolution_category_id is not None:
        if not db.scalar(select(ResolutionCategory.id).where(
                ResolutionCategory.id == changes.resolution_category_id,
                ResolutionCategory.property_id == property_id)):
            raise ValidationFailed("Unknown resolution category")
    if changes.status is not None:
        if changes.status == ConversationStatus.archived:
            if not can_archive:
                raise Forbidden("Your role cannot archive conversations")
            c.status = ConversationStatus.archived
            c.archived_at = clock.now()
            if category_supplied:
                c.resolution_category_id = changes.resolution_category_id
        elif changes.status == ConversationStatus.snoozed:
            if changes.snoozed_until is None:
                raise ValidationFailed("snoozedUntil is required to snooze")
            c.status = ConversationStatus.snoozed
            c.snoozed_until = changes.snoozed_until
        elif changes.status == ConversationStatus.open:
            c.status = ConversationStatus.open
            c.archived_at = None
            c.snoozed_until = None
    elif category_supplied:
        c.resolution_category_id = changes.resolution_category_id
    db.flush()
    after = {"status": c.status.value, "assigned_user_id": c.assigned_user_id,
             "assigned_department_id": c.assigned_department_id}
    audit.record(db, property_id, actor_user_id, "conversation.patched", "conversation", c.id,
                 before=before, after=after)
    queue_event(db, property_id, "conversation.assigned" if before["assigned_user_id"] != after["assigned_user_id"]
                or before["assigned_department_id"] != after["assigned_department_id"] else "conversation.updated",
                {"id": c.id})
    return c
