"""Categories and kind on checklist templates (checklist structure spec §2, §3.2)."""
import pytest
from sqlalchemy import select

from app.domain import ck_instances, ck_templates
from app.errors import ValidationFailed
from app.models import ChecklistAnswer, ChecklistTemplateCategory
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistItemIn,
    ChecklistTemplateIn,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistKind, Role
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

CATEGORIES = [ChecklistCategoryIn(key="audit", name="Audit"),
              ChecklistCategoryIn(key="pay", name="Payments")]
ITEMS = [
    ChecklistItemIn(label="Night audit run", item_type="checkbox", category_key="audit"),
    ChecklistItemIn(label="Card batch closed", item_type="checkbox", category_key="pay"),
    ChecklistItemIn(label="Notes", item_type="text", required=False),
]


def _create(db, fx, **over):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(**{
        "name": "Night Audit", "department_id": fx.dept_front_desk.id, "schedule": "on_demand",
        "categories": CATEGORIES, "items": ITEMS, **over}))


def _patch(db, fx, t, **fields):
    return ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                              ChecklistTemplatePatch(**fields))


def _grouping(out):
    names = {c.id: c.name for c in out.categories}
    return [(i.label, names.get(i.category_id)) for i in out.items]


def _again(out, **over):
    """The saved template as a patch body: categories keyed by id, items by their category."""
    categories = [ChecklistCategoryIn(key=c.id, id=c.id, name=c.name) for c in out.categories]
    items = [ChecklistItemIn(id=i.id, label=i.label, item_type=i.item_type,
                             required=i.required, category_key=i.category_id)
             for i in out.items]
    return {"categories": categories, "items": items, **over}


def test_create_saves_categories_in_order_and_groups_the_items(database, fx):
    with database.session() as db:
        out = ck_templates.to_out(db, _create(db, fx))
        assert [(c.name, c.position) for c in out.categories] == [("Audit", 0), ("Payments", 1)]
        assert _grouping(out) == [("Night audit run", "Audit"), ("Card batch closed", "Payments"),
                                  ("Notes", None)]


def test_kind_defaults_to_normal_and_round_trips(database, fx):
    with database.session() as db:
        assert ck_templates.to_out(db, make_template(db, fx)).kind == ChecklistKind.normal
        t = _create(db, fx, kind="readings")
        assert ck_templates.to_out(db, t).kind == ChecklistKind.readings
        _patch(db, fx, t, kind="normal")
        assert ck_templates.to_out(db, t).kind == ChecklistKind.normal
        _patch(db, fx, t, name="Night Audit 2")  # kind not sent: unchanged
        assert ck_templates.to_out(db, t).kind == ChecklistKind.normal


def test_patch_renames_reorders_adds_removes_and_moves_items(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        audit, pay = out.categories
        run, batch, notes = out.items
        _patch(db, fx, t, categories=[
            ChecklistCategoryIn(key="p", id=pay.id, name="Payments & cards"),
            ChecklistCategoryIn(key="new", name="Reports"),
        ], items=[
            ChecklistItemIn(id=run.id, label=run.label, item_type="checkbox", category_key="new"),
            ChecklistItemIn(id=batch.id, label=batch.label, item_type="checkbox",
                            category_key="p"),
            ChecklistItemIn(id=notes.id, label="Notes", item_type="text", required=False,
                            category_key="p"),
        ])
        after = ck_templates.to_out(db, t)
        assert [(c.name, c.position) for c in after.categories] == [
            ("Payments & cards", 0), ("Reports", 1)]
        assert after.categories[0].id == pay.id  # updated in place, not recreated
        assert _grouping(after) == [("Night audit run", "Reports"),
                                    ("Card batch closed", "Payments & cards"),
                                    ("Notes", "Payments & cards")]
        retired = db.get(ChecklistTemplateCategory, audit.id)
        assert retired.active is False  # soft-deleted, never removed


def test_removing_a_category_leaves_its_items_ungrouped(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        _patch(db, fx, t, categories=[ChecklistCategoryIn(key="pay", id=out.categories[1].id,
                                                          name="Payments")])
        assert _grouping(ck_templates.to_out(db, t)) == [
            ("Night audit run", None), ("Card batch closed", "Payments"), ("Notes", None)]


def test_patching_items_alone_keeps_categories_and_resolves_saved_ids(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        body = _again(out)
        _patch(db, fx, t, items=[*body["items"][:2], ChecklistItemIn(
            id=out.items[2].id, label="Notes", item_type="text", required=False,
            category_key=out.categories[0].id)])
        after = ck_templates.to_out(db, t)
        assert [c.name for c in after.categories] == ["Audit", "Payments"]
        assert _grouping(after)[2] == ("Notes", "Audit")


def test_patching_categories_alone_keeps_item_assignments(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        _patch(db, fx, t, categories=_again(out)["categories"][::-1])  # reorder only
        after = ck_templates.to_out(db, t)
        assert [c.name for c in after.categories] == ["Payments", "Audit"]
        assert _grouping(after) == _grouping(out)


@pytest.mark.parametrize("categories, items, details", [
    (CATEGORIES, [ChecklistItemIn(label="x", item_type="checkbox", category_key="nope")],
     {"items": "unknown_category"}),
    ([ChecklistCategoryIn(key="a", name="   ")], ITEMS[2:], {"categories": "required"}),
    ([ChecklistCategoryIn(key="a", name="A"), ChecklistCategoryIn(key="a", name="B")],
     ITEMS[2:], {"categories": "duplicate"}),
    ([ChecklistCategoryIn(key="a", id="00000000-0000-0000-0000-000000000000", name="A")],
     ITEMS[2:], {"categories": "unknown_category"}),
])
def test_bad_categories_are_400s_and_write_nothing(database, fx, categories, items, details):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as refused:
            _create(db, fx, categories=categories, items=items)
        assert refused.value.details == details
        assert ck_templates.list_templates(db, fx.property_a.id) == []


def test_a_category_of_another_template_is_unknown(database, fx):
    with database.session() as db:
        other = ck_templates.to_out(db, _create(db, fx, name="Other"))
        t = _create(db, fx)
        with pytest.raises(ValidationFailed) as refused:
            _patch(db, fx, t, categories=[ChecklistCategoryIn(
                key="x", id=other.categories[0].id, name="Audit")])
        assert refused.value.details == {"categories": "unknown_category"}
        assert ck_templates.to_out(db, t).categories[0].id != other.categories[0].id


def test_editing_categories_never_changes_a_started_checklists_answers(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        inst = ck_instances.start_on_demand(db, fx.property_a.id, fx.agent_a.id, Role.agent,
                                            t.id)
        before = {(a.item_id, a.bool_value) for a in db.scalars(
            select(ChecklistAnswer).where(ChecklistAnswer.instance_id == inst.id)).all()}
        first = ck_templates.to_out(db, t).items[0]
        _patch(db, fx, t, categories=[], items=[ChecklistItemIn(
            id=first.id, label=first.label, item_type="checkbox")])
        after = {(a.item_id, a.bool_value) for a in db.scalars(
            select(ChecklistAnswer).where(ChecklistAnswer.instance_id == inst.id)).all()}
        assert after == before and len(after) == 3


def test_an_old_checklist_still_saves_without_categories(database, fx):
    """Regression: the shipped create/patch path (PM's item model, no categories) is unchanged."""
    with database.session() as db:
        t = make_template(db, fx)
        assert ck_templates.to_out(db, t).categories == []
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
        assert inst.template_id == t.id
