from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflict, NotFound
from app.models import Message
from app.queue import jobs
from app.realtime.broadcast import queue_event
from app.schemas.conversations import MessageOut
from app.schemas.enums import DeliveryStatus, Direction


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
