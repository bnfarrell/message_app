from datetime import datetime, time, timezone

from flask import Blueprint, g, request

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import analytics
from app.errors import Forbidden, ValidationFailed

bp = Blueprint("analytics", __name__, url_prefix="/api/p/<property_id>/analytics")


def _parse(name: str, end_of_day: bool = False) -> datetime | None:
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as e:
        raise ValidationFailed(f"{name} must be an ISO date or datetime") from e
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), time.max if end_of_day and len(raw) == 10 else dt.time(), tzinfo=timezone.utc)
    return dt


@bp.get("/overview")
@require_auth
@require_property
@require_capability("view_property_analytics")
def overview(property_id: str):
    with db_session() as db:
        return ok(analytics.overview(db, g.property_id, _parse("from"), _parse("to", end_of_day=True)))


@bp.get("/agents")
@require_auth
@require_property
def agents(property_id: str):
    role = g.membership.role
    if has_capability(role, "view_property_analytics"):
        only = None
    elif has_capability(role, "view_own_stats"):
        only = g.user.id
    else:
        raise Forbidden("Your role cannot view analytics")
    with db_session() as db:
        return ok(analytics.agents(db, g.property_id, _parse("from"), _parse("to", end_of_day=True), only_user_id=only))
