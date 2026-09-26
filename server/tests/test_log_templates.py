"""Log templates: admin create/patch and the audience rule (log templates spec §2.1, §3.1)."""
import pytest

from app.domain import log_templates
from app.errors import Forbidden, NotFound, ValidationFailed
from app.schemas.log import LogTemplateFieldIn, LogTemplatePatch, MentionRef
from tests.log_template_helpers import FIELDS, field_ids, front_desk, make_template


def test_create_round_trips_fields_in_order_and_the_audience(database, fx):
    with database.session() as db:
        out = log_templates.to_out(db, make_template(db, fx, audience=front_desk(fx)))
        assert (out.name, out.shift.value, out.active, out.used_count) == (
            "Night Audit", "overnight", True, 0)
        assert [(f.label, f.field_type.value, f.required) for f in out.fields] == [
            (f.label, f.field_type.value, f.required) for f in FIELDS]
        assert [f.position for f in out.fields] == [0, 1, 2, 3, 4]
        assert [(r.type.value, r.id) for r in out.audience] == [
            ("department", fx.dept_front_desk.id)]


def test_new_templates_are_appended_in_position_order(database, fx):
    with database.session() as db:
        first = make_template(db, fx, name="AM Checklist", shift="am")
        second = make_template(db, fx, name="PM Checklist", shift="pm")
        assert (first.position, second.position) == (0, 1)


def test_patch_renames_reorders_and_soft_deletes_a_missing_field(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
            name="Night Audit v2", shift=None, fields=[
                LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy %",
                                   field_type="percent"),
                LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals actual",
                                   field_type="integer", required=False),
            ]))
        out = log_templates.to_out(db, t)
        assert (out.name, out.shift) == ("Night Audit v2", None)
        assert [(f.label, f.required) for f in out.fields] == [("Occupancy %", True),
                                                             ("Arrivals actual", False)]
        assert set(field_ids(db, t)) == {"Occupancy %", "Arrivals actual"}  # active only


def test_a_saved_fields_type_never_changes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        with pytest.raises(ValidationFailed) as e:
            log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
                fields=[LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy",
                                           field_type="integer")]))
        assert e.value.details == {"fields": "type_change"}


def test_unknown_and_duplicate_field_ids_are_refused(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        occ = field_ids(db, t)["Occupancy"]
        for fields, reason in (
                ([LogTemplateFieldIn(id="00000000-0000-0000-0000-000000000000", label="x",
                                     field_type="integer")], "unknown_field"),
                ([LogTemplateFieldIn(id=occ, label="a", field_type="percent"),
                  LogTemplateFieldIn(id=occ, label="b", field_type="percent")],
                 "duplicate_field")):
            with pytest.raises(ValidationFailed) as e:
                log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                                    LogTemplatePatch(fields=fields))
            assert e.value.details == {"fields": reason}


def test_blank_name_or_label_is_refused(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, name="   ")
        assert e.value.details == {"name": "required"}
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, fields=[LogTemplateFieldIn(label="  ",
                                                             field_type="integer")])
        assert e.value.details == {"fields": "required"}


def test_audience_is_replaced_wholesale_and_repeats_collapse(database, fx):
    """Review focus 4: a repeat and a ref kept across a save must not hit the unique key."""
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        eli = MentionRef(type="user", id=fx.engineer_a.id)
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
            audience=[eli, eli, *front_desk(fx)]))
        assert {(r.type.value, r.id) for r in log_templates.to_out(db, t).audience} == {
            ("user", fx.engineer_a.id), ("department", fx.dept_front_desk.id)}
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                            LogTemplatePatch(audience=[]))
        assert log_templates.to_out(db, t).audience == []


def test_audience_must_belong_to_the_property(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, audience=[MentionRef(type="user", id=fx.agent_b.id)])
        assert e.value.details == {"audience": "unknown_user"}
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, audience=[
                MentionRef(type="department", id="00000000-0000-0000-0000-000000000000")])
        assert e.value.details == {"audience": "unknown_department"}


def test_a_template_of_another_property_is_not_found(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        with pytest.raises(NotFound):
            log_templates.get(db, fx.property_b.id, t.id)


@pytest.mark.parametrize("who,allowed", [
    ("agent_a", True),         # front desk: a member of the listed department
    ("engineer_a", False),     # another department
    ("supervisor_a", False),   # supervisors are not exempt (spec §3.1)
    ("manager_a", True), ("admin_a", True), ("corporate_a", True),  # exempt roles
])
def test_the_audience_rule(database, fx, who, allowed):
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        user_id = getattr(fx, who).id
        if allowed:
            log_templates.assert_can_use(db, fx.property_a.id, user_id, t)
        else:
            with pytest.raises(Forbidden):
                log_templates.assert_can_use(db, fx.property_a.id, user_id, t)


def test_a_listed_user_may_use_it_and_an_empty_audience_means_everyone(database, fx):
    with database.session() as db:
        shared = make_template(db, fx, audience=[MentionRef(type="user", id=fx.engineer_a.id)])
        log_templates.assert_can_use(db, fx.property_a.id, fx.engineer_a.id, shared)
        everyone = make_template(db, fx, name="General")
        log_templates.assert_can_use(db, fx.property_a.id, fx.housekeeper_a.id, everyone)
        with pytest.raises(Forbidden):  # a member of another property never can
            log_templates.assert_can_use(db, fx.property_a.id, fx.agent_b.id, everyone)
