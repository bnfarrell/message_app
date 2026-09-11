from flask import Blueprint, g

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import users
from app.schemas.users import CreateStaffRequest, StaffPatch

bp = Blueprint("users", __name__, url_prefix="/api/p/<property_id>/users")


@bp.get("")
@require_auth
@require_property
def list_users(property_id: str):
    with db_session() as db:
        return ok(users.list_staff(db, g.property_id))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_user(property_id: str):
    data = parse_body(CreateStaffRequest)
    with db_session() as db:
        return ok(users.create_staff(db, g.property_id, g.user.id, data), 201)


@bp.patch("/<user_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_user(property_id: str, user_id: str):
    data = parse_body(StaffPatch)
    with db_session() as db:
        return ok(users.update_staff(db, g.property_id, g.user.id, user_id, data))


@bp.delete("/<user_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_user(property_id: str, user_id: str):
    with db_session() as db:
        users.remove_membership(db, g.property_id, g.user.id, user_id)
        return no_content()
