"""Shared set-up for the shift-checklist tests."""
from __future__ import annotations

from app.domain import ck_templates
from app.schemas.checklists import ChecklistTemplateIn
from app.schemas.pm import TemplateItemIn

ITEMS = [
    TemplateItemIn(label="Skimmer baskets emptied", item_type="checkbox"),
    TemplateItemIn(label="Pool pH", item_type="number", unit="", min_value=7.2, max_value=7.8),
    TemplateItemIn(label="Notes", item_type="text", required=False),
    TemplateItemIn(label="Plant room photo", item_type="photo"),
]


def make_template(db, fx, *, name="Engineering AM Rounds", department_id=None,
                  schedule="weekly", shift="am", weekdays=127, items=None):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
        name=name, department_id=department_id or fx.dept_engineering.id, schedule=schedule,
        shift=shift if schedule == "weekly" else None,
        weekdays=weekdays if schedule == "weekly" else None, items=items or ITEMS))
