from flask import Blueprint, g

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_property
from app.domain import staff_messages
from app.schemas.staff_messages import (
    CreateStaffConversationRequest,
    SendStaffMessageRequest,
    StaffDirectoryEntryOut,
    StaffMessageOut,
)

bp = Blueprint("staff_messages", __name__, url_prefix="/api/p/<property_id>/staff-conversations")
directory_bp = Blueprint("staff_directory", __name__, url_prefix="/api/p/<property_id>")


@bp.get("")
@require_auth
@require_property
def list_conversations(property_id: str):
    with db_session() as db:
        return ok(staff_messages.list_conversations_for_user(db, g.property_id, g.user.id))


@bp.post("")
@require_auth
@require_property
def create_conversation(property_id: str):
    data = parse_body(CreateStaffConversationRequest)
    with db_session() as db:
        conv, created = staff_messages.create_conversation(db, g.property_id, g.user.id, data)
        out = staff_messages.detail(db, g.property_id, conv.id, g.user.id)
        return ok(out, 201 if created else 200)


@bp.get("/<conversation_id>")
@require_auth
@require_property
def get_conversation(property_id: str, conversation_id: str):
    with db_session() as db:
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
def send_message(property_id: str, conversation_id: str):
    data = parse_body(SendStaffMessageRequest)
    with db_session() as db:
        msg = staff_messages.send_message(db, g.property_id, conversation_id, g.user.id,
                                          body=data.body)
        author = g.user
        return ok(StaffMessageOut(id=msg.id, conversation_id=msg.conversation_id,
                                  author_user_id=msg.author_user_id,
                                  author_name=f"{author.first_name} {author.last_name}",
                                  body=msg.body, photo_url=None, created_at=msg.created_at), 201)


@bp.post("/<conversation_id>/read")
@require_auth
@require_property
def mark_read(property_id: str, conversation_id: str):
    with db_session() as db:
        staff_messages.mark_read(db, g.property_id, conversation_id, g.user.id)
    return no_content()


@directory_bp.get("/staff-directory")
@require_auth
@require_property
def get_directory(property_id: str):
    with db_session() as db:
        return ok(staff_messages.directory(db, g.property_id, g.user.id))
