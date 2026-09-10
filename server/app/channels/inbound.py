from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.domain import consent, guests, messages, notifications, stays
from app.domain import conversations as conv_domain
from app.models import Conversation, Message, Property
from app.realtime.broadcast import queue_event
from app.schemas.enums import AuthorType, SmsConsentStatus


@dataclass
class InboundResult:
    conversation: Conversation
    message: Message
    created_conversation: bool
    keyword: str | None


def property_for_number(db: Session, to_number: str) -> Property | None:
    return db.scalar(select(Property).where(Property.sms_number == guests.normalize_phone(to_number)))


def handle(db: Session, property_id: str, msg: InboundMessage) -> InboundResult:
    existing = db.scalar(select(Message).where(Message.property_id == property_id,
                                               Message.provider_message_id == msg.provider_message_id))
    if existing is not None:
        conv = db.get(Conversation, existing.conversation_id)
        return InboundResult(conv, existing, False, None)

    guest, _ = guests.find_or_create_by_phone(db, property_id, msg.from_)
    if guest.sms_consent_status == SmsConsentStatus.unknown:
        consent.opt_in(db, guest, "inbound_sms")

    stay = stays.find_in_house_for_guest(db, property_id, guest.id)
    conv, created = conv_domain.find_or_create_for_guest(db, property_id, guest, stay)

    keyword = consent.classify_keyword(msg.body)
    message = messages.record_inbound(db, property_id, conv, msg.body, msg.provider_message_id,
                                      start_sla=keyword is None)

    prop = db.get(Property, property_id)
    if keyword == "stop":
        consent.opt_out(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, consent.STOP_CONFIRMATION(prop.name),
                      author_user_id=None, author_type=AuthorType.system,
                      allow_opt_out_confirmation=True)
    elif keyword == "start":
        consent.opt_in(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, f"You're resubscribed to {prop.name} messages.",
                      author_user_id=None, author_type=AuthorType.system)
    elif keyword == "help":
        help_text = (prop.settings or {}).get("help_text") or f"{prop.name}: reply to this number."
        messages.send(db, property_id, conv.id, help_text, author_user_id=None,
                      author_type=AuthorType.system, allow_opt_out_confirmation=True)
    else:
        name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or guest.phone_e164
        room = f" · {stay.room_number}" if stay and stay.room_number else ""
        notifications.notify_user_or_department(
            db, property_id, user_id=conv.assigned_user_id, department_id=conv.assigned_department_id,
            type="message.inbound", title=f"{name}{room}", body=message.body[:140],
            entity_type="conversation", entity_id=conv.id)

    queue_event(db, property_id, "conversation.created" if created else "conversation.updated",
                {"id": conv.id})
    return InboundResult(conv, message, created, keyword)
