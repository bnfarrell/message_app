"""Checklist templates (checklists spec §2.1, §3.4)."""
import pytest

from app.domain import ck_templates
from app.errors import ValidationFailed
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplatePatch
from app.schemas.pm import TemplateItemIn
from tests.ck_helpers import ITEMS, make_template


def test_create_weekly_template_with_items(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift.value, out.weekdays) == ("weekly", "am", 127)
        assert [i.label for i in out.items] == [i.label for i in ITEMS]
        assert out.department_name == "Engineering"


def test_weekly_needs_shift_and_weekdays_and_on_demand_neither(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed):
            ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                name="x", department_id=fx.dept_engineering.id, schedule="weekly",
                shift="am", weekdays=None, items=ITEMS))
        with pytest.raises(ValidationFailed):
            ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                name="x", department_id=fx.dept_engineering.id, schedule="on_demand",
                shift="pm", items=ITEMS))


def test_department_must_belong_to_the_property(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed):
        make_template(db, fx, department_id="00000000-0000-0000-0000-000000000000")


def test_patch_switches_to_on_demand_and_retires_removed_items(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        first = ck_templates.to_out(db, t).items[0]
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="on_demand", shift=None, weekdays=None,
            items=[TemplateItemIn(id=first.id, label=first.label, item_type="checkbox")]))
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift, out.weekdays) == ("on_demand", None, None)
        assert [i.label for i in out.items] == [first.label]  # active items only
