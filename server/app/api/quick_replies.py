from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import conversations, quick_replies
from app.schemas.content import (
    PreviewRequest,
    QuickReplyIn,
    QuickReplyOut,
    QuickReplyPatch,
    RenderRequest,
)

bp = Blueprint("quick_replies", __name__, url_prefix="/api/p/<property_id>/quick-replies")


@bp.get("")
@require_auth
@require_property
def list_quick_replies(property_id: str):
    with db_session() as db:
        return ok(quick_replies.list(db, g.property_id, q=request.args.get("q"),
                                     department_id=request.args.get("dept"),
                                     include_inactive=request.args.get("includeInactive")
                                     in ("1", "true")))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_quick_reply(property_id: str):
    with db_session() as db:
        created = quick_replies.create(db, g.property_id, parse_body(QuickReplyIn))
        return ok(QuickReplyOut.model_validate(created), 201)


@bp.patch("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        patch = parse_body(QuickReplyPatch)
        updated = quick_replies.update(db, g.property_id, quick_reply_id, patch)
        return ok(QuickReplyOut.model_validate(updated))


@bp.delete("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        quick_replies.delete(db, g.property_id, quick_reply_id)
    return no_content()


@bp.post("/<quick_reply_id>/render")
@require_auth
@require_property
@require_capability("reply")
def render_quick_reply(property_id: str, quick_reply_id: str):
    body = parse_body(RenderRequest)
    with db_session() as db:
        conversations.get_for_viewer(db, g.property_id, body.conversation_id, g.membership.role,
                                     g.user.id, g.membership.department_id)
        return ok(quick_replies.render(db, g.property_id, quick_reply_id, body.conversation_id,
                                       g.user.id))


@bp.get("/variables")
@require_auth
@require_property
def list_variables(property_id: str):
    """The authoritative `{{variable}}` list (ruling D68), so the client never hardcodes it."""
    return ok(list(quick_replies.VARIABLES))


@bp.post("/preview")
@require_auth
@require_property
@require_capability("manage_admin")
def preview_quick_reply(property_id: str):
    """Read-only sibling of /render for the admin editor: arbitrary body text, no usage_count
    bump, and gated on the screen's own capability so `corporate` is not locked out."""
    body = parse_body(PreviewRequest)
    with db_session() as db:
        if body.conversation_id:
            conversations.get_for_viewer(db, g.property_id, body.conversation_id,
                                         g.membership.role, g.user.id, g.membership.department_id)
        return ok(quick_replies.preview(db, g.property_id, body.body, body.conversation_id,
                                        g.user.id))
