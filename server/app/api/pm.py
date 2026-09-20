"""Preventative maintenance routes (spec §5.2). Templates here; runs, inspection and reports
are appended by later tasks."""
from flask import Blueprint, g

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import pm_templates
from app.schemas.pm import TemplateIn, TemplatePatch

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
