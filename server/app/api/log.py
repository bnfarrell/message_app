from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import log
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import ValidationFailed
from app.schemas.log import CreateLogEntryRequest, LogFeedQuery

bp = Blueprint("log", __name__, url_prefix="/api/p/<property_id>/log-entries")


def _photo_from_request() -> tuple[bytes, str] | None:
    upload = request.files.get("photo")
    if upload is None:
        return None
    body = upload.read(MAX_PHOTO_BYTES + 1)
    if len(body) > MAX_PHOTO_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    content_type = sniff_image_type(body)
    if content_type is None:
        raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                               details={"photo": "unsupported_image_type"})
    return body, content_type


@bp.get("")
@require_auth
@require_property
@require_capability("view_log")
def list_entries(property_id: str):
    query = parse_query(LogFeedQuery)
    with db_session() as db:
        return ok(log.feed(db, g.property_id, g.user.id, query))


@bp.post("")
@require_auth
@require_property
@require_capability("post_log")
def create_entry(property_id: str):
    data = parse_body(CreateLogEntryRequest)
    photo = _photo_from_request()
    with db_session() as db:
        entry = log.create(db, g.property_id, g.user.id, data, photo=photo)
        return ok(log.get_out(db, g.property_id, g.user.id, entry.id), 201)


@bp.get("/mentionables")
@require_auth
@require_property
@require_capability("view_log")
def mentionables(property_id: str):
    with db_session() as db:
        return ok(log.mentionables(db, g.property_id))


@bp.get("/<entry_id>")
@require_auth
@require_property
@require_capability("view_log")
def get_entry(property_id: str, entry_id: str):
    with db_session() as db:
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.post("/<entry_id>/ack")
@require_auth
@require_property
@require_capability("view_log")
def ack_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.acknowledge(db, g.property_id, g.user.id, entry_id)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.post("/<entry_id>/pin")
@require_auth
@require_property
@require_capability("pin_log_entry")
def pin_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.set_pinned(db, g.property_id, g.user.id, entry_id, True)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.delete("/<entry_id>/pin")
@require_auth
@require_property
@require_capability("pin_log_entry")
def unpin_entry(property_id: str, entry_id: str):
    with db_session() as db:
        log.set_pinned(db, g.property_id, g.user.id, entry_id, False)
        return ok(log.get_out(db, g.property_id, g.user.id, entry_id))


@bp.get("/<entry_id>/photo")
@require_auth
@require_property
@require_capability("view_log")
def get_entry_photo(property_id: str, entry_id: str):
    with db_session() as db:
        body, content_type = log.get_photo(db, g.property_id, entry_id)
    return Response(body, mimetype=content_type,
                    headers={"Cache-Control": "private, max-age=86400"})
