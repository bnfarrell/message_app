from flask import Blueprint, g

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import users
from app.schemas.users import DepartmentIn, DepartmentOut, DepartmentPatch

bp = Blueprint("departments", __name__, url_prefix="/api/p/<property_id>/departments")


@bp.get("")
@require_auth
@require_property
def list_departments(property_id: str):
    """Deliberately ungated: department pickers all over the product read this list."""
    with db_session() as db:
        return ok(users.list_departments(db, g.property_id))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_department(property_id: str):
    with db_session() as db:
        created = users.create_department(db, g.property_id, parse_body(DepartmentIn))
        return ok(DepartmentOut.model_validate(created), 201)


@bp.patch("/<department_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_department(property_id: str, department_id: str):
    with db_session() as db:
        updated = users.update_department(db, g.property_id, department_id,
                                          parse_body(DepartmentPatch))
        return ok(DepartmentOut.model_validate(updated))


@bp.delete("/<department_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_department(property_id: str, department_id: str):
    with db_session() as db:
        users.delete_department(db, g.property_id, department_id)
    return no_content()
