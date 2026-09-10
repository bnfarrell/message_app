from flask import Blueprint, g

from app.api._util import client_meta, db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import messages
from app.schemas.conversations import MessageOut, SendMessageRequest

bp = Blueprint("conversations", __name__, url_prefix="/api/p/<property_id>/conversations")


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
@require_capability("reply")
def send_message(property_id: str, conversation_id: str):
    body = parse_body(SendMessageRequest)
    ip, ua = client_meta()
    with db_session() as db:
        m = messages.send(db, g.property_id, conversation_id, body.body, author_user_id=g.user.id,
                          digital_asset_id=body.digital_asset_id, draft_prompt_id=body.draft_prompt_id,
                          ip=ip, user_agent=ua)
        return ok(MessageOut.model_validate(m), 201)
