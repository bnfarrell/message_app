from flask import Blueprint, request
from sqlalchemy import select

from app.api._util import db_session, no_content
from app.channels import inbound
from app.channels.registry import get_sms_adapter
from app.domain import messages
from app.errors import NotFound, Unauthorized
from app.models import Message
from app.ratelimit import rate_limited, webhook_limiter
from app.schemas.enums import DeliveryStatus

bp = Blueprint("hooks", __name__, url_prefix="/api/hooks")

# Twilio MessageStatus values that move our state machine. queued/accepted/sending/scheduled are
# still "queued" to us, and read/canceled/receiving/received never apply to an outbound SMS.
_TWILIO_STATUS = {
    "sent": DeliveryStatus.sent,
    "delivered": DeliveryStatus.delivered,
    "undelivered": DeliveryStatus.undelivered,
    "failed": DeliveryStatus.failed,
}


def _verified_payload() -> dict:
    adapter = get_sms_adapter()
    if not adapter.verify_inbound(request):
        raise Unauthorized("Bad webhook signature")
    return request.form.to_dict() if request.form else (request.get_json(silent=True) or {})


@bp.post("/sms/inbound")
@rate_limited(webhook_limiter)
def sms_inbound():
    payload = _verified_payload()
    msg = get_sms_adapter().parse_inbound(payload)
    with db_session() as db:
        prop = inbound.property_for_number(db, msg.to)
        if prop is None:
            raise NotFound("No property uses that number")
        inbound.handle(db, prop.id, msg)
    return no_content()


@bp.post("/sms/status")
@rate_limited(webhook_limiter)
def sms_status():
    payload = _verified_payload()
    status = _TWILIO_STATUS.get(payload.get("MessageStatus", ""))
    if status is None:
        return no_content()
    with db_session() as db:
        # MessageSid is globally unique, so no property scoping is needed to find the row; the
        # domain call re-checks property_id and owns the forward-only ordering invariant.
        m = db.scalar(select(Message).where(
            Message.provider_message_id == payload.get("MessageSid", "")))
        if m is None:
            return no_content()  # Twilio never retries status callbacks; nothing to gain from 4xx
        messages.update_delivery_status(db, m.property_id, m.id, status,
                                        error_code=payload.get("ErrorCode"),
                                        error_message=payload.get("ErrorMessage"))
    return no_content()
