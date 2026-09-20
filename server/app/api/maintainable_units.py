from flask import Blueprint, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_units
from app.errors import ValidationFailed
from app.schemas.pm import MAX_IMPORT_BYTES, UnitIn, UnitListQuery, UnitPatch

bp = Blueprint("maintainable_units", __name__,
               url_prefix="/api/p/<property_id>/maintainable-units")

MULTIPART_OVERHEAD_BYTES = 4096


@bp.get("")
@require_auth
@require_property
@require_capability("view_pm")
def list_units(property_id: str):
    query = parse_query(UnitListQuery)
    with db_session() as db:
        return ok(pm_units.list_units(db, g.property_id, query))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_unit(property_id: str):
    data = parse_body(UnitIn)
    with db_session() as db:
        unit = pm_units.create(db, g.property_id, g.user.id, data)
        return ok(pm_units.to_out(unit), 201)


@bp.patch("/<unit_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_unit(property_id: str, unit_id: str):
    data = parse_body(UnitPatch)
    with db_session() as db:
        unit = pm_units.patch(db, g.property_id, g.user.id, unit_id, data)
        return ok(pm_units.to_out(unit))


@bp.post("/import")
@require_auth
@require_property
@require_capability("manage_admin")
def import_units(property_id: str):
    """multipart/form-data with a `file` part. 200 with counts on success; the domain raises
    ImportRejected (422, report in `error.details`) with nothing written otherwise (spec §5.4)."""
    # Before request.files: reading it is what makes Werkzeug buffer the whole body.
    if (request.content_length or 0) > MAX_IMPORT_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed("The file must be 1 MB or smaller",
                               details={"file": "file_too_large"})
    upload = request.files.get("file")
    if upload is None:
        raise ValidationFailed("A CSV file is required", details={"file": "required"})
    raw = upload.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise ValidationFailed("The file must be 1 MB or smaller",
                               details={"file": "file_too_large"})
    try:
        text = raw.decode("utf-8-sig")  # Excel writes a BOM; tolerate it
    except UnicodeDecodeError as e:
        raise ValidationFailed("The file must be UTF-8 text",
                               details={"file": "not_utf8"}) from e
    with db_session() as db:
        return ok(pm_units.import_csv(db, g.property_id, g.user.id, text))
