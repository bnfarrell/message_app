from __future__ import annotations

from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation, Guest, Message
from app.schemas.enums import AuthorType, Channel, ConversationStatus, DeliveryStatus, Direction


def make_conversation(db: Session, fx, guest: Guest | None = None, **overrides) -> Conversation:
    guest = guest or fx.guest_inhouse_a
    stay_id = fx.stay_inhouse_a.id if guest.id == fx.guest_inhouse_a.id else None
    c = Conversation(property_id=guest.property_id, guest_id=guest.id, stay_id=stay_id,
                     status=ConversationStatus.open, channel_primary=Channel.sms)
    for k, v in overrides.items():
        setattr(c, k, v)
    db.add(c)
    db.flush()
    return c


def make_message(db: Session, conversation: Conversation, *, direction: Direction, body: str,
                 **overrides) -> Message:
    m = Message(
        conversation_id=conversation.id, property_id=conversation.property_id, direction=direction,
        author_type=AuthorType.guest if direction == Direction.inbound else AuthorType.staff,
        channel=Channel.sms, body=body,
        delivery_status=(DeliveryStatus.delivered
                        if direction == Direction.inbound else DeliveryStatus.queued),
        sent_at=clock.now(),
    )
    for k, v in overrides.items():
        setattr(m, k, v)
    db.add(m)
    db.flush()
    return m


def inbound(client, fx, from_phone: str, body: str, to: str | None = None, sid: str | None = None):
    import uuid

    return client.post(
        "/api/hooks/sms/inbound",
        data={"From": from_phone, "To": to or fx.property_a.sms_number, "Body": body,
              "MessageSid": sid or f"SM{uuid.uuid4().hex[:10]}"},
        headers={"X-Mock-Secret": "dev"},
    )
