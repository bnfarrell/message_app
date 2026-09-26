"""Read side of checklist structure (spec §2.2): per-category progress and the kind on rows."""
from app.domain import ck_instances, ck_templates, ck_views
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistInstanceQuery,
    ChecklistItemIn,
    ChecklistTemplateIn,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistKind, Role
from app.schemas.pm import AnswerPatch
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today


def _night_audit(db, fx, **over):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(**{
        "name": "Night Audit", "department_id": fx.dept_front_desk.id, "schedule": "weekly",
        "shift": "am", "weekdays": 127,
        "categories": [ChecklistCategoryIn(key="a", name="Audit"),
                       ChecklistCategoryIn(key="p", name="Payments"),
                       ChecklistCategoryIn(key="e", name="Empty")],
        "items": [
            ChecklistItemIn(label="Night audit run", item_type="checkbox", category_key="a"),
            ChecklistItemIn(label="Audit total", item_type="number", category_key="a"),
            ChecklistItemIn(label="Card batch closed", item_type="checkbox", category_key="p"),
            ChecklistItemIn(label="Notes", item_type="text", required=False),
        ], **over}))


def _progress(detail):
    return [(c.name, c.done, c.total) for c in detail.categories]


def test_an_unstarted_checklist_shows_every_category_at_zero(database, fx):
    with database.session() as db:
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
        detail = ck_views.detail(db, fx.property_a.id, inst.id)
        # "Empty" holds no items, so it has no heading; "Notes" is ungrouped
        assert _progress(detail) == [("Audit", 0, 2), ("Payments", 0, 1)]
        names = {c.id: c.name for c in detail.categories}
        assert [(i.label, names.get(i.category_id)) for i in detail.items] == [
            ("Night audit run", "Audit"), ("Audit total", "Audit"),
            ("Card batch closed", "Payments"), ("Notes", None)]


def test_progress_counts_answered_items_per_category(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, pid))
        ck_instances.start(db, pid, fx.agent_a.id, Role.agent, inst.id)
        detail = ck_views.detail(db, pid, inst.id)
        answer_for = {a.item_id: a.id for a in detail.answers}
        by_label = {i.label: i.id for i in detail.items}
        for label, patch in (("Night audit run", AnswerPatch(bool_value=True)),
                             ("Notes", AnswerPatch(text_value="Quiet night"))):
            ck_instances.save_answer(db, pid, fx.agent_a.id, Role.agent, inst.id,
                                     answer_for[by_label[label]], patch)
        detail = ck_views.detail(db, pid, inst.id)
        assert _progress(detail) == [("Audit", 1, 2), ("Payments", 0, 1)]
        assert (detail.done, detail.total) == (2, 4)  # the ungrouped answer still counts overall


def test_grouping_follows_edits_but_answers_never_change(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, pid))
        ck_instances.start(db, pid, fx.agent_a.id, Role.agent, inst.id)
        before = ck_views.detail(db, pid, inst.id)
        audit = before.categories[0]
        ck_templates.patch(db, pid, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            categories=[ChecklistCategoryIn(key="a", id=audit.id, name="Audit & reports")]))
        after = ck_views.detail(db, pid, inst.id)
        assert _progress(after) == [("Audit & reports", 0, 2)]  # Payments retired: ungrouped
        assert after.answers == before.answers
        assert [i.id for i in after.items] == [i.id for i in before.items]


def test_rows_carry_the_kind(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx, name="Rounds"), today)
        ck_instances.ensure_instance(db, _night_audit(db, fx, kind="readings"), today)
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery())
        assert {(r.template_name, r.kind) for r in rows} == {
            ("Rounds", ChecklistKind.normal), ("Night Audit", ChecklistKind.readings)}


def test_the_kind_is_on_the_detail_over_http(database, fx, login):
    with database.session() as db:
        inst, _ = ck_instances.ensure_instance(db, _night_audit(db, fx, kind="readings"),
                                               local_today(db, fx.property_a.id))
        iid = inst.id
    body = login("agent@hvh.test").get(
        f"/api/p/{fx.property_a.id}/checklists/instances/{iid}").get_json()
    assert body["kind"] == "readings"
    assert [(c["name"], c["done"], c["total"]) for c in body["categories"]] == [
        ("Audit", 0, 2), ("Payments", 0, 1)]
    assert body["items"][0]["categoryId"] == body["categories"][0]["id"]
