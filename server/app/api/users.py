from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("users", __name__, url_prefix="/api/p/<property_id>/users")


@bp.get("")
@require_auth
@require_property
def list_users(property_id: str):
    with db_session() as db:
        return ok(users.list_staff(db, g.property_id))
