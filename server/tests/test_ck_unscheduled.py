"""The `unscheduled` schedule (checklist structure spec §1.2, §2.2): no shift, no days, never
generated, never started on demand. conftest freezes Thu 2026-09-10 12:00 UTC (AM in New York)."""
import pytest
from sqlalchemy import func, select

from app.domain import ck_instances, ck_templates, ck_tick
from app.errors import TransitionError, ValidationFailed
from app.models import ChecklistInstance
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplatePatch
from app.schemas.enums import Role
from tests.ck_helpers import ITEMS, make_template


def test_unscheduled_takes_no_shift_or_days(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift, out.weekdays) == ("unscheduled", None, None)
        for shift, weekdays in (("am", None), (None, 127)):
            with pytest.raises(ValidationFailed) as refused:
                ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                    name="x", department_id=fx.dept_engineering.id, schedule="unscheduled",
                    shift=shift, weekdays=weekdays, items=ITEMS))
            assert refused.value.details == {"shift": "not_allowed"}


def test_the_tick_never_generates_an_unscheduled_template(database, fx):
    with database.session() as db:
        make_template(db, fx, name="Every day")  # weekly, AM, every day: the tick's control
        someday = make_template(db, fx, name="Someday", schedule="unscheduled")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}
        assert db.scalar(select(func.count()).select_from(ChecklistInstance).where(
            ChecklistInstance.template_id == someday.id)) == 0


def test_an_unscheduled_template_cannot_be_started_on_demand(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        with pytest.raises(TransitionError):
            ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                         Role.dept_staff, t.id)


def test_scheduling_it_later_is_an_ordinary_schedule_edit(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        with pytest.raises(ValidationFailed) as refused:  # weekly still needs shift + days
            ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                               ChecklistTemplatePatch(schedule="weekly"))
        assert refused.value.details == {"weekdays": "required"}
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="weekly", shift="pm", weekdays=0b0011111))
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift.value, out.weekdays) == ("weekly", "pm", 31)
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="unscheduled", shift=None, weekdays=None))
        assert ck_templates.to_out(db, t).schedule.value == "unscheduled"


def test_unscheduled_over_http(database, fx, login):
    admin = login("admin@hvh.test")
    base = f"/api/p/{fx.property_a.id}/checklists"
    res = admin.post(f"{base}/templates", json={
        "name": "Deep clean", "departmentId": fx.dept_engineering.id, "schedule": "unscheduled",
        "items": [{"label": "Done", "itemType": "checkbox"}]})
    assert res.status_code == 201, res.get_json()
    assert (res.get_json()["schedule"], res.get_json()["shift"]) == ("unscheduled", None)
    started = login("engineer@hvh.test").post(f"{base}/templates/{res.get_json()['id']}/start")
    assert started.status_code == 409
