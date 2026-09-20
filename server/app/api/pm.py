"""Preventative maintenance routes (spec §5.2). Templates here; runs, inspection and reports
are appended by later tasks."""
from flask import Blueprint, Response, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_inspection, pm_reports, pm_runs, pm_templates
from app.domain.work_orders import MAX_PHOTO_BYTES
from app.errors import ValidationFailed
from app.schemas.common import CamelModel
from app.schemas.pm import (
    AnswerPatch,
    ComplianceQuery,
    InspectionQuery,
    InspectRequest,
    StartRunRequest,
    SweepQuery,
    TemplateIn,
    TemplatePatch,
)

bp = Blueprint("pm", __name__, url_prefix="/api/p/<property_id>/pm")


@bp.get("/templates")
@require_auth
@require_property
@require_capability("view_pm")
def list_templates(property_id: str):
    with db_session() as db:
        return ok(pm_templates.list_templates(db, g.property_id))


@bp.post("/templates")
@require_auth
@require_property
@require_capability("manage_admin")
def create_template(property_id: str):
    data = parse_body(TemplateIn)
    with db_session() as db:
        t = pm_templates.create(db, g.property_id, g.user.id, data)
        return ok(pm_templates.to_out(db, t), 201)


@bp.patch("/templates/<template_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_template(property_id: str, template_id: str):
    data = parse_body(TemplatePatch)
    with db_session() as db:
        t = pm_templates.patch(db, g.property_id, g.user.id, template_id, data)
        return ok(pm_templates.to_out(db, t))


# Defined per-api-module by existing convention (app/api/log.py:14).
MULTIPART_OVERHEAD_BYTES = 4096


def _read_photo() -> bytes:
    """Mirrors app/api/log.py: refuse before Werkzeug buffers the body, then read cap + 1."""
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(
            f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
            details={"photo": "file_too_large"})
    upload = request.files.get("photo")
    if upload is None:
        raise ValidationFailed("A photo file is required", details={"photo": "required"})
    return upload.read(MAX_PHOTO_BYTES + 1)


@bp.post("/runs")
@require_auth
@require_property
@require_capability("perform_pm")
def start_run(property_id: str):
    data = parse_body(StartRunRequest)
    with db_session() as db:
        run = pm_runs.start(db, g.property_id, g.user.id, data)
        return ok(pm_runs.to_out(db, run), 201)


@bp.get("/runs/<run_id>")
@require_auth
@require_property
@require_capability("view_pm")
def get_run(property_id: str, run_id: str):
    with db_session() as db:
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)))


@bp.post("/runs/<run_id>/start")
@require_auth
@require_property
@require_capability("perform_pm")
def begin_run(property_id: str, run_id: str):
    with db_session() as db:
        run = pm_runs.begin_pending(db, g.property_id, g.user.id, run_id)
        return ok(pm_runs.to_out(db, run))


@bp.patch("/runs/<run_id>/answers/<answer_id>")
@require_auth
@require_property
@require_capability("perform_pm")
def save_answer(property_id: str, run_id: str, answer_id: str):
    """Returns the whole run, so the client gets `missingRequired` refreshed in the same round
    trip as the answer it just saved."""
    data = parse_body(AnswerPatch)
    with db_session() as db:
        pm_runs.save_answer(db, g.property_id, g.user.id, run_id, answer_id, data)
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)))


@bp.post("/runs/<run_id>/photos")
@require_auth
@require_property
@require_capability("perform_pm")
def add_run_photo(property_id: str, run_id: str):
    """multipart/form-data: a `photo` part and an optional `itemId` field naming a photo item."""
    data = _read_photo()
    item_id = request.form.get("itemId") or None
    with db_session() as db:
        pm_runs.attach_photo(db, g.property_id, g.user.id, run_id, data=data, item_id=item_id)
        return ok(pm_runs.to_out(db, pm_runs.get(db, g.property_id, run_id)), 201)


@bp.get("/runs/<run_id>/photos/<photo_id>")
@require_auth
@require_property
@require_capability("view_pm")
def get_run_photo(property_id: str, run_id: str, photo_id: str):
    with db_session() as db:
        photo = pm_runs.get_photo(db, g.property_id, run_id, photo_id)
        body, content_type = photo.data, photo.content_type
    return Response(body, mimetype=content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })


@bp.post("/runs/<run_id>/complete")
@require_auth
@require_property
@require_capability("perform_pm")
def complete_run(property_id: str, run_id: str):
    with db_session() as db:
        run = pm_runs.complete(db, g.property_id, g.user.id, run_id)
        return ok(pm_runs.to_out(db, run))


@bp.get("/inspections")
@require_auth
@require_property
@require_capability("inspect_pm")
def list_inspections(property_id: str):
    query = parse_query(InspectionQuery)
    with db_session() as db:
        return ok(pm_inspection.queue(db, g.property_id, query))


@bp.post("/runs/<run_id>/inspect")
@require_auth
@require_property
@require_capability("inspect_pm")
def inspect_run(property_id: str, run_id: str):
    data = parse_body(InspectRequest)
    with db_session() as db:
        run = pm_inspection.inspect(db, g.property_id, g.user.id, run_id, data)
        return ok(pm_runs.to_out(db, run))


class _CyclesQuery(CamelModel):
    template_id: str


@bp.get("/sweep")
@require_auth
@require_property
@require_capability("view_pm")
def sweep(property_id: str):
    query = parse_query(SweepQuery)
    with db_session() as db:
        return ok(pm_reports.sweep(db, g.property_id, query))


@bp.get("/cycles")
@require_auth
@require_property
@require_capability("view_pm")
def list_cycles(property_id: str):
    query = parse_query(_CyclesQuery)
    with db_session() as db:
        return ok(pm_reports.cycles(db, g.property_id, query.template_id))


@bp.get("/compliance")
@require_auth
@require_property
@require_capability("view_property_analytics")
def compliance(property_id: str):
    query = parse_query(ComplianceQuery)
    with db_session() as db:
        return ok(pm_reports.compliance(db, g.property_id, query))
