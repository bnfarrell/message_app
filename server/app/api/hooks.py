from flask import Blueprint, request

from app.api._util import db_session, no_content
from app.channels import inbound
from app.channels.registry import get_sms_adapter
from app.errors import NotFound, Unauthorized
from app.ratelimit import rate_limited, webhook_limiter

bp = Blueprint("hooks", __name__, url_prefix="/api/hooks")


@bp.post("/sms/inbound")
@rate_limited(webhook_limiter)
def sms_inbound():
    adapter = get_sms_adapter()
    if not adapter.verify_inbound(request):
        raise Unauthorized("Bad webhook signature")
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    msg = adapter.parse_inbound(payload)
    with db_session() as db:
        prop = inbound.property_for_number(db, msg.to)
        if prop is None:
            raise NotFound("No property uses that number")
        inbound.handle(db, prop.id, msg)
    return no_content()
