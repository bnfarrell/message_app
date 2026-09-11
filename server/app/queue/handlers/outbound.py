from __future__ import annotations

from sqlalchemy.orm import Session

from app.channels.registry import get_sms_adapter
from app.domain import messages
from app.models import Conversation, Guest, Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("outbound.send")
def outbound_send(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None or msg.delivery_status != DeliveryStatus.queued:
        return  # already handled or retried; idempotent
    conv = db.get(Conversation, msg.conversation_id)
    guest = db.get(Guest, conv.guest_id)
    adapter = get_sms_adapter()
    try:
        result = adapter.send(db, guest.phone_e164, msg.body, message_id=msg.id)
    except Exception as exc:
        # Provider threw: mark failed and return normally so this write commits with the job.
        # Re-raising would have the session rolled back by Database.session(), silently discarding
        # the failure and leaving the message stuck at queued forever. No automatic backoff retry
        # for transient provider errors in Phase 1: recovery is the visible failed state plus
        # messages.retry(), which re-enqueues the job.
        messages.update_delivery_status(db, msg.property_id, msg.id, DeliveryStatus.failed,
                                        error_code="ADAPTER_ERROR", error_message=repr(exc)[:500])
        return
    msg.provider_message_id = result.provider_message_id
    db.flush()
