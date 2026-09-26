"""Housekeeping routes (spec §4.1). Every route: auth + property + a capability."""
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import hk_assignments, hk_photos, hk_transitions, hk_views
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import ValidationFailed
from app.schemas.enums import HkStatus
from app.schemas.housekeeping import (
    HkAssignRequest,
    HkInspectRequest,
    HkMarkDirtyRequest,
    HkReorderRequest,
    HkStatusRequest,
)

bp = Blueprint("housekeeping", __name__, url_prefix="/api/p/<property_id>/housekeeping")

# Defined per-api-module by existing convention (app/api/log.py, app/api/pm.py).
MULTIPART_OVERHEAD_BYTES = 4096


def _read_photo() -> bytes:
    """Mirrors app/api/pm.py: refuse before Werkzeug buffers the body, then read cap + 1."""
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    upload = request.files.get("photo")
    if upload is None:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    return upload.read(MAX_PHOTO_BYTES + 1)


@bp.get("/board")
@require_auth
@require_property
@require_capability("view_housekeeping")
def board(property_id: str):
    with db_session() as db:
        return ok(hk_views.board(db, g.property_id))


@bp.get("/my-rooms")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def my_rooms(property_id: str):
    with db_session() as db:
        return ok(hk_views.my_rooms(db, g.property_id, g.user.id))


@bp.get("/inspections")
@require_auth
@require_property
@require_capability("inspect_housekeeping")
def inspections(property_id: str):
    with db_session() as db:
        return ok(hk_views.inspections(db, g.property_id))


@bp.get("/rooms/<room_id>")
@require_auth
@require_property
@require_capability("view_housekeeping")
def room_detail(property_id: str, room_id: str):
    with db_session() as db:
        return ok(hk_views.room_detail(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/mark-dirty")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def mark_dirty(property_id: str, room_id: str):
    data = parse_body(HkMarkDirtyRequest)
    with db_session() as db:
        hk_transitions.mark_dirty(db, g.property_id, g.user.id, room_id, data.note)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/rush")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def set_rush(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.set_rush(db, g.property_id, g.user.id, room_id, True)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.delete("/rooms/<room_id>/rush")
@require_auth
@require_property
@require_capability("mark_room_dirty")
def clear_rush(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.set_rush(db, g.property_id, g.user.id, room_id, False)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/status")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def set_status(property_id: str, room_id: str):
    data = parse_body(HkStatusRequest)
    with db_session() as db:
        hk_transitions.set_room_status(db, g.property_id, g.user.id, room_id,
                                       HkStatus(data.status), data.note)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/rooms/<room_id>/self-assign-start")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def self_assign_start(property_id: str, room_id: str):
    with db_session() as db:
        hk_transitions.self_assign_start(db, g.property_id, g.user.id, room_id)
        return ok(hk_views.room_row(db, g.property_id, room_id))


@bp.post("/assignments")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def assign(property_id: str):
    data = parse_body(HkAssignRequest)
    with db_session() as db:
        out = hk_assignments.assign(db, g.property_id, g.user.id, data.room_ids,
                                    data.housekeeper_user_id)
        return ok([hk_views.assignment_out(db, a) for a in out], 201)


@bp.post("/assignments/reorder")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def reorder(property_id: str):
    data = parse_body(HkReorderRequest)
    with db_session() as db:
        out = hk_assignments.reorder(db, g.property_id, g.user.id, data.housekeeper_user_id,
                                     data.assignment_ids)
        return ok([hk_views.assignment_out(db, a) for a in out])


@bp.delete("/assignments/<assignment_id>")
@require_auth
@require_property
@require_capability("manage_housekeeping")
def unassign(property_id: str, assignment_id: str):
    with db_session() as db:
        room = hk_assignments.unassign(db, g.property_id, g.user.id, assignment_id)
        return ok(hk_views.room_row(db, g.property_id, room.id))


@bp.post("/assignments/<assignment_id>/start")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def start(property_id: str, assignment_id: str):
    with db_session() as db:
        a = hk_transitions.start(db, g.property_id, g.user.id, g.membership.role, assignment_id)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/complete")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def complete(property_id: str, assignment_id: str):
    with db_session() as db:
        a = hk_transitions.complete(db, g.property_id, g.user.id, g.membership.role,
                                    assignment_id)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/inspect")
@require_auth
@require_property
@require_capability("inspect_housekeeping")
def inspect(property_id: str, assignment_id: str):
    data = parse_body(HkInspectRequest)
    with db_session() as db:
        a = hk_transitions.inspect(db, g.property_id, g.user.id, assignment_id, data.result,
                                   data.note)
        return ok(hk_views.room_row(db, g.property_id, a.room_id))


@bp.post("/assignments/<assignment_id>/photos")
@require_auth
@require_property
@require_capability("perform_housekeeping")
def add_photo(property_id: str, assignment_id: str):
    data = _read_photo()
    with db_session() as db:
        photo = hk_photos.attach(db, g.property_id, g.user.id, g.membership.role, assignment_id,
                                 data=data)
        room_id = hk_assignments.get(db, g.property_id, photo.assignment_id).room_id
        return ok(hk_views.room_detail(db, g.property_id, room_id), 201)


@bp.get("/assignments/<assignment_id>/photos/<photo_id>")
@require_auth
@require_property
@require_capability("view_housekeeping")
def get_photo(property_id: str, assignment_id: str, photo_id: str):
    with db_session() as db:
        photo = hk_photos.get_photo(db, g.property_id, assignment_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })
