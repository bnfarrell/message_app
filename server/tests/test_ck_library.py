"""The starter checklist library and its import (checklist structure spec §3.3, §3.4)."""
import pytest

from app.domain import ck_library, ck_templates
from app.errors import NotFound, ValidationFailed
from app.models import Department
from app.schemas.checklists import ChecklistLibraryImport
from app.schemas.enums import ChecklistKind, DepartmentType, PmItemType

READING_LIMIT = 10 ** 8  # Numeric(10, 2): PostgreSQL overflows at |x| >= 10^8


def _lib(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists/library{rest}"


def test_the_library_holds_the_six_starter_checklists():
    assert [(e.key, e.kind, e.department_type) for e in ck_library.LIBRARY] == [
        ("front_desk_am", ChecklistKind.normal, DepartmentType.front_desk),
        ("front_desk_pm", ChecklistKind.normal, DepartmentType.front_desk),
        ("night_audit", ChecklistKind.normal, DepartmentType.front_desk),
        ("pool_spa", ChecklistKind.readings, DepartmentType.engineering),
        ("boiler_rounds", ChecklistKind.readings, DepartmentType.engineering),
        ("linen_par", ChecklistKind.normal, DepartmentType.housekeeping),
    ]
    assert len(ck_library.BY_KEY["night_audit"].categories) == 7


@pytest.mark.parametrize("entry", ck_library.LIBRARY, ids=lambda e: e.key)
def test_every_entry_is_valid_input_for_create(database, fx, entry):
    assert len(set(entry.categories)) == len(entry.categories)
    for category in entry.categories:
        assert 0 < len(category) <= 120
        assert any(i.category == category for i in entry.items), f"{category} has no items"
    for item in entry.items:
        assert item.category is None or item.category in entry.categories, item.label
        bounds = [b for b in (item.min_value, item.max_value) if b is not None]
        assert item.item_type == PmItemType.number or not (bounds or item.unit), item.label
        assert all(abs(b) < READING_LIMIT for b in bounds), item.label
        if len(bounds) == 2:
            assert item.min_value <= item.max_value, item.label
        assert item.unit is None or len(item.unit) <= 16, item.label
    with database.session() as db:
        t = ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, entry.key,
                                    ChecklistLibraryImport(department_id=fx.dept_engineering.id))
        out = ck_templates.to_out(db, t)
        assert (out.name, out.kind, out.schedule.value) == (entry.name, entry.kind,
                                                             "unscheduled")
        assert [c.name for c in out.categories] == list(entry.categories)
        names = {c.id: c.name for c in out.categories}
        assert [(i.label, i.item_type, i.unit, i.min_value, i.max_value, i.required,
                 names.get(i.category_id)) for i in out.items] == [
            (i.label, i.item_type, i.unit, i.min_value, i.max_value, i.required, i.category)
            for i in entry.items]


def test_the_list_summarises_each_entry():
    entries = {e.key: e for e in ck_library.list_entries()}
    am = entries["front_desk_am"]
    assert (am.name, am.item_count) == ("Front Desk AM Opening", 7)
    assert [(c.name, c.item_count) for c in am.categories] == [
        ("Cash & drawer", 2), ("Systems", 3), ("Lobby", 2)]
    assert entries["pool_spa"].categories == []


def test_import_takes_a_name_and_twice_gives_two_copies(database, fx):
    with database.session() as db:
        pid, fd = fx.property_a.id, fx.dept_front_desk.id
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd))
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd, name="Night Audit B"))
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd, name="   "))
        assert sorted(t.name for t in ck_templates.list_templates(db, pid)) == [
            "Night Audit", "Night Audit", "Night Audit B"]


def test_unknown_key_and_foreign_department(database, fx):
    with database.session() as db:
        with pytest.raises(NotFound):
            ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, "nope",
                                    ChecklistLibraryImport(department_id=fx.dept_front_desk.id))
        other = Department(property_id=fx.property_b.id, name="Engineering",
                           type=DepartmentType.engineering)
        db.add(other)
        db.flush()
        with pytest.raises(ValidationFailed) as refused:
            ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, "pool_spa",
                                    ChecklistLibraryImport(department_id=other.id))
        assert refused.value.details == {"departmentId": "unknown"}


def test_library_routes(app, fx, login):
    admin = login("admin@hvh.test")
    listed = admin.get(_lib(fx)).get_json()
    assert [e["key"] for e in listed][:1] == ["front_desk_am"]
    assert listed[0]["departmentType"] == "front_desk"
    assert listed[0]["categories"][0] == {"name": "Cash & drawer", "itemCount": 2}
    res = admin.post(_lib(fx, "/pool_spa/import"), json={"departmentId": fx.dept_engineering.id})
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert (body["name"], body["kind"], body["schedule"], len(body["items"])) == (
        "Pool & Spa Readings", "readings", "unscheduled", 5)
    assert admin.post(_lib(fx, "/nope/import"),
                      json={"departmentId": fx.dept_engineering.id}).status_code == 404
    assert admin.post(_lib(fx, "/pool_spa/import"), json={}).status_code == 400


def test_library_needs_manage_admin(app, fx, login):
    for email in ("agent@hvh.test", "supervisor@hvh.test", "manager@hvh.test"):
        c = login(email)
        assert c.get(_lib(fx)).status_code == 403, email
        assert c.post(_lib(fx, "/pool_spa/import"),
                      json={"departmentId": fx.dept_engineering.id}).status_code == 403, email
    assert login("corporate@hvh.test").get(_lib(fx)).status_code == 200
