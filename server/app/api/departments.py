from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("departments", __name__, url_prefix="/api/p/<property_id>/departments")


@bp.get("")
@require_auth
@require_property
def list_departments(property_id: str):
    with db_session() as db:
        return ok(users.list_departments(db, g.property_id))
