from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import NotFound
from app.models import Conversation, Guest, Property, Stay
from app.realtime.broadcast import queue_event
from app.schemas.enums import Channel, ConversationStatus


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
