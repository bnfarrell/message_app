from flask import Blueprint, g

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import properties
from app.schemas.properties import PropertySettingsPatch

bp = Blueprint("properties", __name__, url_prefix="/api/p/<property_id>/settings")


@bp.get("")
@require_auth
@require_property
def get_settings(property_id: str):
    with db_session() as db:
        return ok(properties.settings(db, g.property_id))


@bp.patch("")
@require_auth
@require_property
@require_capability("manage_admin")
def update_settings(property_id: str):
    with db_session() as db:
        return ok(properties.update_settings(db, g.property_id, parse_body(PropertySettingsPatch)))
