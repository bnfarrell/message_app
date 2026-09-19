from flask import Blueprint, g

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_property
from app.domain import staff_messages
from app.schemas.staff_messages import CreateStaffConversationRequest, StaffDirectoryEntryOut

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


@directory_bp.get("/staff-directory")
@require_auth
@require_property
def get_directory(property_id: str):
    with db_session() as db:
        return ok(staff_messages.directory(db, g.property_id, g.user.id))
