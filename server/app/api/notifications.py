from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok
from app.auth.decorators import require_auth, require_property
from app.domain import notifications
from app.errors import NotFound
from app.schemas.notifications import UnreadCount

bp = Blueprint("notifications", __name__, url_prefix="/api/p/<property_id>/notifications")


@bp.get("")
@require_auth
@require_property
def list_notifications(property_id: str):
    unread = request.args.get("unread") in ("1", "true")
    with db_session() as db:
        return ok(notifications.list_for_user(db, g.property_id, g.user.id, unread_only=unread))


@bp.get("/unread-count")
@require_auth
@require_property
def unread(property_id: str):
    with db_session() as db:
        return ok(UnreadCount(count=notifications.unread_count(db, g.property_id, g.user.id)))


@bp.post("/<notification_id>/read")
@require_auth
@require_property
def mark_read(property_id: str, notification_id: str):
    with db_session() as db:
        if not notifications.mark_read(db, g.property_id, g.user.id, notification_id):
            raise NotFound("Notification not found")
    return no_content()


@bp.post("/read-all")
@require_auth
@require_property
def mark_all(property_id: str):
    with db_session() as db:
        notifications.mark_all_read(db, g.property_id, g.user.id)
    return no_content()
