from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications
from app.domain.users import active_members_of_department
from app.errors import ValidationFailed
from app.models import (
    Conversation,
    Department,
    LogEntry,
    LogEntryMention,
    LogEntryPhoto,
    Property,
    PropertyMembership,
    UserAccount,
    WorkOrder,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import MentionTargetType, Shift, UserStatus
from app.schemas.log import CreateLogEntryRequest, MentionRef

# Spec §3.3. Overridable per property via settings["shift_boundaries"].
DEFAULT_SHIFT_BOUNDARIES = {"am": "07:00", "pm": "15:00", "overnight": "23:00"}


def _boundary(raw: dict, key: str) -> time:
    value = raw.get(key) or DEFAULT_SHIFT_BOUNDARIES[key]
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute))


def shift_for(prop: Property, at: datetime) -> Shift:
    """Which shift `at` falls in, on the property's own clock.

    Computed once at creation and then stored, so editing the boundaries later does not
    retroactively relabel history (spec §3.3). Overnight is the window that wraps midnight,
    which is why this is a three-way comparison rather than a sorted bisect.
    """
    if at.tzinfo is None:
        raise ValueError("shift_for requires an aware datetime")
    raw = (prop.settings or {}).get("shift_boundaries") or {}
    am, pm, overnight = (_boundary(raw, k) for k in ("am", "pm", "overnight"))
    local = at.astimezone(ZoneInfo(prop.timezone)).time()
    if am <= local < pm:
        return Shift.am
    if pm <= local < overnight:
        return Shift.pm
    return Shift.overnight


def _assert_member(db: Session, property_id: str, user_id: str) -> None:
    if not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id,
            PropertyMembership.user_id == user_id)):
        raise ValidationFailed("That person is not a member of this property")


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if not db.scalar(select(Department.id).where(Department.property_id == property_id,
                                                 Department.id == department_id)):
        raise ValidationFailed("That department is not part of this property")


def _validate_refs(db: Session, property_id: str, refs: list[MentionRef]) -> None:
    for ref in refs:
        if ref.type == MentionTargetType.user:
            _assert_member(db, property_id, ref.id)
        else:
            _assert_department(db, property_id, ref.id)


def resolve_audience(db: Session, property_id: str, refs: list[MentionRef]) -> list[str]:
    """Flatten mention refs to concrete active user ids, de-duplicated, order preserved."""
    out: list[str] = []
    for ref in refs:
        if ref.type == MentionTargetType.user:
            out.append(ref.id)
        else:
            out.extend(active_members_of_department(db, property_id, ref.id))
    active = set(db.scalars(
        select(UserAccount.id).where(UserAccount.id.in_(out or [""]),
                                     UserAccount.status == UserStatus.active)).all())
    return [uid for uid in dict.fromkeys(out) if uid in active]


def create(db: Session, property_id: str, author_user_id: str,
           data: CreateLogEntryRequest,
           photo: tuple[bytes, str] | None = None) -> LogEntry:
    prop = db.get(Property, property_id)
    if data.department_id:
        _assert_department(db, property_id, data.department_id)
    _validate_refs(db, property_id, data.mentions)
    _validate_refs(db, property_id, data.ack_audience)
    if data.linked_work_order_id and not db.scalar(select(WorkOrder.id).where(
            WorkOrder.id == data.linked_work_order_id,
            WorkOrder.property_id == property_id)):
        raise ValidationFailed("That work order is not part of this property")
    if data.linked_conversation_id and not db.scalar(select(Conversation.id).where(
            Conversation.id == data.linked_conversation_id,
            Conversation.property_id == property_id)):
        raise ValidationFailed("That conversation is not part of this property")

    body = data.body.strip()
    if not body:
        raise ValidationFailed("A log entry needs a body")

    expected = [uid for uid in resolve_audience(db, property_id, data.ack_audience)
                if uid != author_user_id] if data.requires_ack else []

    entry = LogEntry(
        property_id=property_id,
        author_user_id=author_user_id,
        department_id=data.department_id,
        shift=shift_for(prop, clock.now()),
        body=body,
        # An audience that resolves to nobody would render "0 of 0 acknowledged", which is
        # not a claim about anything (spec §3.2).
        requires_ack=bool(expected),
        ack_expected=expected,
        linked_work_order_id=data.linked_work_order_id,
        linked_conversation_id=data.linked_conversation_id,
    )
    db.add(entry)
    db.flush()

    for position, ref in enumerate(data.mentions):
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=property_id,
                               type=ref.type, target_id=ref.id, position=position))
    if photo is not None:
        body_bytes, content_type = photo
        db.add(LogEntryPhoto(log_entry_id=entry.id, property_id=property_id,
                             uploaded_by_user_id=author_user_id,
                             content_type=content_type, byte_size=len(body_bytes),
                             data=body_bytes))
    db.flush()

    author = db.get(UserAccount, author_user_id)
    mentioned = [uid for uid in resolve_audience(db, property_id, data.mentions)
                 if uid != author_user_id]
    notifications.notify_users(
        db, property_id, mentioned, "log.mention",
        f"{author.first_name} mentioned you in the hotel log",
        body=entry.body[:140], entity_type="log_entry", entity_id=entry.id)
    # Somebody asked to acknowledge who was not also mentioned still needs telling.
    notifications.notify_users(
        db, property_id, [uid for uid in expected if uid not in set(mentioned)],
        "log.ack_requested",
        f"{author.first_name} needs you to acknowledge a log entry",
        body=entry.body[:140], entity_type="log_entry", entity_id=entry.id)

    audit.record(db, property_id, author_user_id, "log_entry.created", "log_entry", entry.id,
                 after={"shift": entry.shift.value, "requires_ack": entry.requires_ack})
    queue_event(db, property_id, "log.entry.created", {"id": entry.id})
    return entry
