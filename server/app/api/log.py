from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import log, log_templates
from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import ValidationFailed
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFeedQuery,
    LogTemplateIn,
    LogTemplatePatch,
)

bp = Blueprint("log", __name__, url_prefix="/api/p/<property_id>/log-entries")

# Admin → Log templates lives apart from the composer's `/log-entries/templates`: the two lists
# have different capabilities and contents (log templates spec §3.2).
templates_bp = Blueprint("log_templates", __name__,
                         url_prefix="/api/p/<property_id>/log-templates")

# Defined per-api-module by existing convention — app/api/staff_messages.py:47 and
# app/api/work_orders.py:22 each carry their own copy rather than sharing one.
MULTIPART_OVERHEAD_BYTES = 4096


def _reject_oversized_request() -> None:
    """Refuse before Werkzeug buffers the whole multipart body into memory.

    No MAX_CONTENT_LENGTH is configured app-wide, so without this an arbitrarily large
    upload is fully parsed before the truncated read below ever runs. Mirrors
    app/api/staff_messages.py:54.
    """
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})


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
    # Must run BEFORE parse_body: reading the form is what makes Werkzeug buffer the
    # whole multipart body, so a check afterwards is a check after the damage.
    _reject_oversized_request()
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


@bp.get("/templates")
@require_auth
@require_property
@require_capability("post_log")
def usable_templates(property_id: str):
    # A static segment, so it wins over `/<entry_id>` as `/mentionables` does.
    with db_session() as db:
        return ok(log_templates.list_usable(db, g.property_id, g.user.id))


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
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@templates_bp.get("")
@require_auth
@require_property
@require_capability("manage_admin")
def list_templates(property_id: str):
    with db_session() as db:
        return ok(log_templates.list_admin(db, g.property_id))


@templates_bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_template(property_id: str):
    data = parse_body(LogTemplateIn)
    with db_session() as db:
        t = log_templates.create(db, g.property_id, g.user.id, data)
        return ok(log_templates.to_out(db, t), 201)


@templates_bp.patch("/<template_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_template(property_id: str, template_id: str):
    data = parse_body(LogTemplatePatch)
    with db_session() as db:
        t = log_templates.patch(db, g.property_id, g.user.id, template_id, data)
        return ok(log_templates.to_out(db, t))
