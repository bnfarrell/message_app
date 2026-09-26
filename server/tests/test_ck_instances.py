"""Instance lifecycle (checklists spec §3.3)."""
import pytest
from sqlalchemy import select

from app.domain import ck_instances, ck_photos, ck_templates
from app.errors import Forbidden, TransitionError, ValidationFailed
from app.models import ChecklistAnswer, ChecklistTemplateItem, Notification, WorkOrder
from app.schemas.checklists import ChecklistTemplatePatch
from app.schemas.enums import ChecklistStatus, Role, Shift
from app.schemas.pm import AnswerPatch, TemplateItemIn
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _open(db, fx, **kw):
    t = make_template(db, fx, **kw)
    inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
    return t, inst


def _answers(db, inst):
    return {item.label: ans for ans, item in db.execute(
        select(ChecklistAnswer, ChecklistTemplateItem)
        .join(ChecklistTemplateItem, ChecklistTemplateItem.id == ChecklistAnswer.item_id)
        .where(ChecklistAnswer.instance_id == inst.id)).all()}


def _fill(db, fx, inst, ph=7.4):
    a = _answers(db, inst)
    pid, eli = fx.property_a.id, fx.engineer_a.id
    ck_instances.save_answer(db, pid, eli, Role.dept_staff, inst.id,
                             a["Skimmer baskets emptied"].id, AnswerPatch(bool_value=True))
    ck_instances.save_answer(db, pid, eli, Role.dept_staff, inst.id, a["Pool pH"].id,
                             AnswerPatch(number_value=ph))
    item_id = a["Plant room photo"].item_id
    ck_photos.attach(db, pid, eli, Role.dept_staff, inst.id, data=PNG, item_id=item_id)


def test_ensure_instance_is_idempotent(database, fx):
    with database.session() as db:
        t, inst = _open(db, fx)
        again, created = ck_instances.ensure_instance(db, t, inst.due_date)
        assert (again.id, created, inst.slot, inst.shift) == (inst.id, False, 0, Shift.am)


def test_start_claims_and_snapshots_the_items(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert (inst.status, inst.assigned_user_id, inst.started_by_user_id) == (
            ChecklistStatus.in_progress, fx.engineer_a.id, fx.engineer_a.id)
        assert len(_answers(db, inst)) == 4


def test_starting_twice_is_a_409(database, fx):
    """Review focus 3."""
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        with pytest.raises(TransitionError):
            ck_instances.start(db, fx.property_a.id, fx.supervisor_a.id, Role.supervisor,
                               inst.id)


def test_other_department_staff_are_refused(database, fx):
    """Review focus 4: a housekeeper can't run Engineering's rounds; a manager (no department)
    can, through the supervisor exemption."""
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(Forbidden):
            ck_instances.start(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff,
                               inst.id)
        ck_instances.start(db, fx.property_a.id, fx.manager_a.id, Role.manager, inst.id)


def test_assign_requires_a_department_member_and_notifies(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(ValidationFailed):
            ck_instances.assign(db, fx.property_a.id, fx.supervisor_a.id, inst.id,
                                fx.housekeeper_a.id)
        ck_instances.assign(db, fx.property_a.id, fx.supervisor_a.id, inst.id, fx.engineer_a.id)
        assert inst.assigned_user_id == fx.engineer_a.id
        assert db.scalar(select(Notification.type).where(
            Notification.user_id == fx.engineer_a.id)) == "checklist.assigned"


def test_required_photo_item_needs_its_own_photo(database, fx):
    """Review focus 5: a general photo does not satisfy a photo item."""
    with database.session() as db:
        _, inst = _open(db, fx)
        pid = fx.property_a.id
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        a = _answers(db, inst)
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id,
                                 a["Skimmer baskets emptied"].id, AnswerPatch(bool_value=True))
        ck_instances.save_answer(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id,
                                 a["Pool pH"].id, AnswerPatch(number_value=7.4))
        ck_photos.attach(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id, data=PNG,
                         item_id=None)
        with pytest.raises(ValidationFailed) as e:
            ck_instances.complete(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert e.value.details == {"missingItemIds": [a["Plant room photo"].item_id]}


def test_complete_raises_one_work_order_per_out_of_range_reading(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        pid = fx.property_a.id
        ck_instances.start(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        _fill(db, fx, inst, ph=8.1)
        ck_instances.complete(db, pid, fx.engineer_a.id, Role.dept_staff, inst.id)
        assert inst.status is ChecklistStatus.complete
        titles = db.scalars(select(WorkOrder.title)).all()
        assert titles == ["Pool pH 8.1 out of range (7.2–7.8) — Engineering AM Rounds"]
        assert db.scalar(select(Notification.user_id).where(
            Notification.type == "checklist.out_of_range")) == fx.supervisor_a.id


def test_complete_is_refused_unless_in_progress(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        with pytest.raises(TransitionError):
            ck_instances.complete(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff,
                                  inst.id)


def test_on_demand_runs_twice_and_takes_the_current_shift(database, fx):
    # FROZEN 2026-09-10 12:00 UTC = 08:00 New York → the AM shift of Sep 10.
    with database.session() as db:
        t = make_template(db, fx, name="Power Outage", schedule="on_demand")
        one = ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                           Role.dept_staff, t.id)
        two = ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                           Role.dept_staff, t.id)
        assert one.id != two.id
        assert (one.shift, one.slot, one.status) == (Shift.am, None, ChecklistStatus.in_progress)


def test_editing_a_template_never_changes_a_started_instance(database, fx):
    """Review focus 2."""
    with database.session() as db:
        t, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            items=[TemplateItemIn(label="Something new", item_type="checkbox")]))
        assert sorted(_answers(db, inst)) == sorted(
            ["Skimmer baskets emptied", "Pool pH", "Notes", "Plant room photo"])


def test_comment_is_saved_trimmed(database, fx):
    with database.session() as db:
        _, inst = _open(db, fx)
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
        ck_instances.set_comment(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff,
                                 inst.id, "  Boiler 2 noisy, keep an eye  ")
        assert inst.comment == "Boiler 2 noisy, keep an eye"


def test_each_mutation_emits_one_event(database, fx, events):
    with database.session() as db:
        _, inst = _open(db, fx)
    events.clear()
    with database.session() as db:
        ck_instances.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, inst.id)
    ck = [e for e in events if e.type == ck_instances.EVENT]
    assert len(ck) == 1 and ck[0].payload == {"ids": [inst.id]}
