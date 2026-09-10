from sqlalchemy.orm import Session

from app.domain import messages
from app.models import Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("mock.delivery_status")
def mock_delivery_status(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None:
        return
    target = DeliveryStatus(payload["status"])
    # A retry resets the message to queued and clears provider_message_id before scheduling a new
    # sequence; a stale job from the superseded send must not touch the message it no longer
    # describes. The forward-only ordering invariant lives in messages.update_delivery_status,
    # which is the trusted boundary for it.
    if msg.provider_message_id is None:
        return  # message was reset by a retry after this job was scheduled
    messages.update_delivery_status(db, msg.property_id, msg.id, target,
                                    error_code=payload.get("error_code"),
                                    error_message=payload.get("error_message"))
