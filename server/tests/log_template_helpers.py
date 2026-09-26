"""Shared set-up for the log-template tests."""
from __future__ import annotations

from app.domain import log_templates
from app.schemas.log import LogTemplateFieldIn, LogTemplateIn, MentionRef

FIELDS = [
    LogTemplateFieldIn(label="Arrivals actual", field_type="integer"),
    LogTemplateFieldIn(label="Occupancy", field_type="percent"),
    LogTemplateFieldIn(label="ADR", field_type="decimal", required=False),
    LogTemplateFieldIn(label="Duty manager", field_type="short_text", required=False),
    LogTemplateFieldIn(label="Handover", field_type="long_text", required=False),
]


def make_template(db, fx, *, name="Night Audit", shift="overnight", fields=None,
                  audience=None, active=True):
    """Created through the domain as `fx.admin_a`. `audience` is a list of MentionRef."""
    return log_templates.create(db, fx.property_a.id, fx.admin_a.id, LogTemplateIn(
        name=name, shift=shift, active=active, fields=fields or FIELDS,
        audience=audience or []))


def front_desk(fx) -> list[MentionRef]:
    return [MentionRef(type="department", id=fx.dept_front_desk.id)]


def field_ids(db, template) -> dict[str, str]:
    """Active field id by label."""
    return {f.label: f.id for f in log_templates.active_fields(db, template.id)}
