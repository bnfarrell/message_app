from flask import Blueprint, g

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import categories
from app.schemas.content import CategoryIn, CategoryOut, CategoryPatch

bp = Blueprint("categories", __name__, url_prefix="/api/p/<property_id>/resolution-categories")


@bp.get("")
@require_auth
@require_property
def list_categories(property_id: str):
    with db_session() as db:
        return ok(categories.list_tree(db, g.property_id))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_category(property_id: str):
    with db_session() as db:
        created = categories.create(db, g.property_id, parse_body(CategoryIn))
        return ok(CategoryOut.model_validate(created), 201)


@bp.patch("/<category_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_category(property_id: str, category_id: str):
    with db_session() as db:
        updated = categories.update(db, g.property_id, category_id, parse_body(CategoryPatch))
        return ok(CategoryOut.model_validate(updated))


@bp.delete("/<category_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_category(property_id: str, category_id: str):
    with db_session() as db:
        categories.delete(db, g.property_id, category_id)
    return no_content()
