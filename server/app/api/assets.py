from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import assets
from app.schemas.content import AssetIn, AssetOut, AssetPatch

bp = Blueprint("assets", __name__, url_prefix="/api/p/<property_id>/assets")


@bp.get("")
@require_auth
@require_property
def list_assets(property_id: str):
    with db_session() as db:
        include_inactive = request.args.get("includeInactive") in ("1", "true")
        return ok(assets.list(db, g.property_id, include_inactive=include_inactive))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_asset(property_id: str):
    with db_session() as db:
        created = assets.create(db, g.property_id, parse_body(AssetIn))
        return ok(AssetOut.model_validate(created), 201)


@bp.patch("/<asset_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_asset(property_id: str, asset_id: str):
    with db_session() as db:
        updated = assets.update(db, g.property_id, asset_id, parse_body(AssetPatch))
        return ok(AssetOut.model_validate(updated))


@bp.delete("/<asset_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_asset(property_id: str, asset_id: str):
    with db_session() as db:
        assets.delete(db, g.property_id, asset_id)
    return no_content()
