"""Shift checklist routes (checklists spec §4.2, §4.3). Every route: auth + property + a
capability."""
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import ck_instances, ck_library, ck_photos, ck_templates, ck_views
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import ValidationFailed
from app.schemas.checklists import (
    ChecklistAssignRequest,
    ChecklistCommentPatch,
    ChecklistInstanceQuery,
    ChecklistLibraryImport,
    ChecklistMissedQuery,
    ChecklistTemplateIn,
    ChecklistTemplatePatch,
)
from app.schemas.pm import AnswerPatch

bp = Blueprint("checklists", __name__, url_prefix="/api/p/<property_id>/checklists")

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


@bp.get("/templates")
@require_auth
@require_property
@require_capability("view_checklists")
def list_templates(property_id: str):
    with db_session() as db:
        return ok(ck_templates.list_templates(db, g.property_id))


@bp.post("/templates")
@require_auth
@require_property
@require_capability("manage_admin")
def create_template(property_id: str):
    data = parse_body(ChecklistTemplateIn)
    with db_session() as db:
        t = ck_templates.create(db, g.property_id, g.user.id, data)
        return ok(ck_templates.to_out(db, t), 201)


@bp.patch("/templates/<template_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_template(property_id: str, template_id: str):
    data = parse_body(ChecklistTemplatePatch)
    with db_session() as db:
        t = ck_templates.patch(db, g.property_id, g.user.id, template_id, data)
        return ok(ck_templates.to_out(db, t))


@bp.get("/library")
@require_auth
@require_property
@require_capability("manage_admin")
def library(property_id: str):
    return ok(ck_library.list_entries())


@bp.post("/library/<key>/import")
@require_auth
@require_property
@require_capability("manage_admin")
def import_from_library(property_id: str, key: str):
    data = parse_body(ChecklistLibraryImport)
    with db_session() as db:
        t = ck_library.import_entry(db, g.property_id, g.user.id, key, data)
        return ok(ck_templates.to_out(db, t), 201)


@bp.post("/templates/<template_id>/start")
@require_auth
@require_property
@require_capability("perform_checklists")
def start_on_demand(property_id: str, template_id: str):
    with db_session() as db:
        inst = ck_instances.start_on_demand(db, g.property_id, g.user.id, g.membership.role,
                                            template_id)
        return ok(ck_views.detail(db, g.property_id, inst.id), 201)


@bp.get("/instances")
@require_auth
@require_property
@require_capability("view_checklists")
def list_instances(property_id: str):
    query = parse_query(ChecklistInstanceQuery)
    with db_session() as db:
        return ok(ck_views.list_instances(db, g.property_id, query))


@bp.get("/instances/<instance_id>")
@require_auth
@require_property
@require_capability("view_checklists")
def instance_detail(property_id: str, instance_id: str):
    with db_session() as db:
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.post("/instances/<instance_id>/assign")
@require_auth
@require_property
@require_capability("manage_checklists")
def assign(property_id: str, instance_id: str):
    data = parse_body(ChecklistAssignRequest)
    with db_session() as db:
        ck_instances.assign(db, g.property_id, g.user.id, instance_id, data.user_id)
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.post("/instances/<instance_id>/start")
@require_auth
@require_property
@require_capability("perform_checklists")
def start(property_id: str, instance_id: str):
    with db_session() as db:
        ck_instances.start(db, g.property_id, g.user.id, g.membership.role, instance_id)
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.post("/instances/<instance_id>/complete")
@require_auth
@require_property
@require_capability("perform_checklists")
def complete(property_id: str, instance_id: str):
    with db_session() as db:
        ck_instances.complete(db, g.property_id, g.user.id, g.membership.role, instance_id)
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.patch("/instances/<instance_id>")
@require_auth
@require_property
@require_capability("perform_checklists")
def set_comment(property_id: str, instance_id: str):
    data = parse_body(ChecklistCommentPatch)
    with db_session() as db:
        ck_instances.set_comment(db, g.property_id, g.user.id, g.membership.role, instance_id,
                                 data.comment)
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.patch("/instances/<instance_id>/answers/<answer_id>")
@require_auth
@require_property
@require_capability("perform_checklists")
def save_answer(property_id: str, instance_id: str, answer_id: str):
    data = parse_body(AnswerPatch)
    with db_session() as db:
        ck_instances.save_answer(db, g.property_id, g.user.id, g.membership.role, instance_id,
                                 answer_id, data)
        return ok(ck_views.detail(db, g.property_id, instance_id))


@bp.post("/instances/<instance_id>/photos")
@require_auth
@require_property
@require_capability("perform_checklists")
def add_photo(property_id: str, instance_id: str):
    data = _read_photo()
    item_id = request.form.get("itemId") or None
    with db_session() as db:
        ck_photos.attach(db, g.property_id, g.user.id, g.membership.role, instance_id,
                         data=data, item_id=item_id)
        return ok(ck_views.detail(db, g.property_id, instance_id), 201)


@bp.get("/instances/<instance_id>/photos/<photo_id>")
@require_auth
@require_property
@require_capability("view_checklists")
def get_photo(property_id: str, instance_id: str, photo_id: str):
    with db_session() as db:
        photo = ck_photos.get_photo(db, g.property_id, instance_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@bp.get("/missed")
@require_auth
@require_property
@require_capability("view_property_analytics")
def missed(property_id: str):
    query = parse_query(ChecklistMissedQuery)
    with db_session() as db:
        return ok(ck_views.missed(db, g.property_id, query))
