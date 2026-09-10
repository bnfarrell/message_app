from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.db import get_db
from app.domain import audit, consent
from app.domain import conversations as conv_domain
from app.domain.redaction import redact
from app.errors import Conflict, NotFound, ValidationFailed
from app.models import Conversation, DigitalAsset, Guest, Message, WorkOrder
from app.queue import jobs
from app.realtime.broadcast import queue_event
from app.schemas.conversations import MessageOut
from app.schemas.enums import (
    AuthorType,
    Channel,
    DeliveryStatus,
    Direction,
    DraftPromptStatus,
    SmsConsentStatus,
)


def _get(db: Session, property_id: str, message_id: str) -> Message:
    m = db.scalar(select(Message).where(Message.id == message_id, Message.property_id == property_id))
    if m is None:
        raise NotFound("Message not found")
    return m


# The trusted boundary for the forward-only invariant: queued -> sent -> delivered may only move
# forward (a stale/replayed provider callback must not revert a later status). failed/undelivered
# are terminal-from-anywhere and sit outside this list, so e.g. queued -> failed still applies.
_FORWARD_ORDER = [DeliveryStatus.queued, DeliveryStatus.sent, DeliveryStatus.delivered]


def update_delivery_status(db: Session, property_id: str, message_id: str, status: DeliveryStatus, *,
                           provider_message_id: str | None = None, error_code: str | None = None,
                           error_message: str | None = None) -> Message:
    m = _get(db, property_id, message_id)
    if (status in _FORWARD_ORDER and m.delivery_status in _FORWARD_ORDER
            and _FORWARD_ORDER.index(status) <= _FORWARD_ORDER.index(m.delivery_status)):
        return m  # backward or no-op transition: ignore, no write, no event
    m.delivery_status = status
    if provider_message_id:
        m.provider_message_id = provider_message_id
    if status == DeliveryStatus.delivered:
        m.delivered_at = clock.now()
    if status in (DeliveryStatus.failed, DeliveryStatus.undelivered):
        m.provider_error_code = error_code
        m.provider_error_message = error_message
    db.flush()
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m


def retry(db: Session, property_id: str, message_id: str) -> Message:
    m = _get(db, property_id, message_id)
    if m.direction != Direction.outbound or m.delivery_status not in (
        DeliveryStatus.failed, DeliveryStatus.undelivered
    ):
        raise Conflict("Only failed outbound messages can be retried")
    m.delivery_status = DeliveryStatus.queued
    m.provider_error_code = None
    m.provider_error_message = None
    m.provider_message_id = None
    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m


MAX_BODY = 1600


def send(db: Session, property_id: str, conversation_id: str, body: str, *,
         author_user_id: str | None, author_type: AuthorType = AuthorType.staff,
         digital_asset_id: str | None = None, draft_prompt_id: str | None = None,
         allow_opt_out_confirmation: bool = False, ip: str | None = None,
         user_agent: str | None = None) -> Message:
    """THE outbound path. Every message to a guest goes through here (design.md §9.1)."""
    body = (body or "").strip()
    if not body:
        raise ValidationFailed("Message body is empty")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"Message body exceeds {MAX_BODY} characters")

    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        # The caller's session will roll back when ConsentError propagates, so the audit row gets its own
        # session. Nothing has been written in `db` yet at this point, so SQLite WAL allows the second writer.
        with get_db().session() as audit_db:
            audit.record(audit_db, property_id, author_user_id, "message.rejected_opted_out", "conversation",
                         conv.id, after={"body_length": len(body)}, ip=ip, user_agent=user_agent)
    consent.assert_can_send(guest, allow_opt_out_confirmation=allow_opt_out_confirmation)

    if digital_asset_id:
        asset = db.scalar(select(DigitalAsset).where(DigitalAsset.id == digital_asset_id,
                                                     DigitalAsset.property_id == property_id))
        if asset is None:
            raise ValidationFailed("Unknown digital asset")
        body = f"{body} /a/{asset.short_code}"
        asset.send_count += 1

    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.outbound,
                author_type=author_type, author_user_id=author_user_id, channel=Channel.sms,
                body=body, digital_asset_id=digital_asset_id, delivery_status=DeliveryStatus.queued,
                sent_at=now)
    db.add(m)

    conv.last_staff_message_at = now
    conv.sla_due_at = None
    conv.sla_breach_notified_at = None
    if conv.first_response_seconds is None and conv.last_guest_message_at is not None \
            and author_type == AuthorType.staff:
        conv.first_response_seconds = int((now - conv.last_guest_message_at).total_seconds())

    if draft_prompt_id:
        from app.models import DraftPrompt

        dp = db.scalar(select(DraftPrompt).where(DraftPrompt.id == draft_prompt_id,
                                                 DraftPrompt.property_id == property_id,
                                                 DraftPrompt.conversation_id == conv.id))
        if dp is not None and dp.status == DraftPromptStatus.pending:
            dp.status = DraftPromptStatus.sent
            dp.resolved_at = now
            dp.resolved_by_user_id = author_user_id
            wo = db.get(WorkOrder, dp.work_order_id)
            if wo is not None:
                wo.guest_notified_at = now

    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    audit.record(db, property_id, author_user_id, "message.sent", "message", m.id,
                 after={"conversation_id": conv.id, "length": len(body)}, ip=ip, user_agent=user_agent)
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    conv_domain.touch_updated(db, conv)
    return m


def record_inbound(db: Session, property_id: str, conv: Conversation, body: str,
                   provider_message_id: str, *, start_sla: bool = True) -> Message:
    clean, redacted = redact(body)
    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.inbound,
                author_type=AuthorType.guest, channel=Channel.sms, body=clean, redacted=redacted,
                delivery_status=DeliveryStatus.delivered, provider_message_id=provider_message_id,
                sent_at=now, delivered_at=now)
    db.add(m)
    conv.last_guest_message_at = now
    if start_sla:
        conv.sla_due_at = now + timedelta(minutes=conv_domain.sla_minutes(db, property_id))
        conv.sla_breach_notified_at = None
    db.flush()
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m
