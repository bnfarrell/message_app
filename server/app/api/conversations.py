from flask import Blueprint, g
from sqlalchemy import select

from app.api._util import client_meta, db_session, no_content, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import conversations, draft_prompts, messages, notes
from app.errors import NotFound
from app.models import Message
from app.schemas.conversations import (
    ConversationPatch, CreateNoteRequest, ListQuery, MessageOut, SendMessageRequest,
)

bp = Blueprint("conversations", __name__, url_prefix="/api/p/<property_id>/conversations")


def _viewer():
    m = g.membership
    return dict(viewer_user_id=g.user.id, viewer_role=m.role, viewer_department_id=m.department_id)


@bp.get("")
@require_auth
@require_property
def list_conversations(property_id: str):
    q = parse_query(ListQuery)
    with db_session() as db:
        return ok(conversations.list(db, g.property_id, filter=q.filter, dept=q.dept, limit=q.limit,
                                     offset=q.offset, **_viewer()))


@bp.get("/<conversation_id>")
@require_auth
@require_property
def get_conversation(property_id: str, conversation_id: str):
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        return ok(conversations.detail(db, g.property_id, conversation_id))


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
@require_capability("reply")
def send_message(property_id: str, conversation_id: str):
    body = parse_body(SendMessageRequest)
    ip, ua = client_meta()
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        m = messages.send(db, g.property_id, conversation_id, body.body, author_user_id=g.user.id,
                          digital_asset_id=body.digital_asset_id, draft_prompt_id=body.draft_prompt_id,
                          ip=ip, user_agent=ua)
        return ok(MessageOut.model_validate(m), 201)


@bp.post("/<conversation_id>/messages/<message_id>/retry")
@require_auth
@require_property
@require_capability("reply")
def retry_message(property_id: str, conversation_id: str, message_id: str):
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        target = db.scalar(select(Message).where(Message.id == message_id,
                                                  Message.property_id == g.property_id))
        if target is None or target.conversation_id != conversation_id:
            raise NotFound("Message not found")
        m = messages.retry(db, g.property_id, message_id)
        return ok(MessageOut.model_validate(m))


@bp.post("/<conversation_id>/notes")
@require_auth
@require_property
@require_capability("add_note")
def add_note(property_id: str, conversation_id: str):
    body = parse_body(CreateNoteRequest)
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        n = notes.create(db, g.property_id, conversation_id, g.user.id, body.body)
        out = [x for x in notes.list_for(db, g.property_id, conversation_id) if x.id == n.id][0]
        return ok(out, 201)


@bp.patch("/<conversation_id>")
@require_auth
@require_property
@require_capability("assign")
def patch_conversation(property_id: str, conversation_id: str):
    changes = parse_body(ConversationPatch)
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        conversations.patch(db, g.property_id, conversation_id, g.user.id, changes,
                            can_archive=has_capability(g.membership.role, "archive"))
        return ok(conversations.detail(db, g.property_id, conversation_id))


@bp.post("/<conversation_id>/draft-prompts/<prompt_id>/dismiss")
@require_auth
@require_property
@require_capability("reply")
def dismiss_prompt(property_id: str, conversation_id: str, prompt_id: str):
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        draft_prompts.dismiss(db, g.property_id, conversation_id, prompt_id, g.user.id)
    return no_content()
