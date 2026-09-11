import pytest

from app.schemas.enums import Role, WorkOrderType


def test_departments_lists_only_this_property(app, fx, login):
    c = login("agent@hvh.test")
    res = c.get(f"/api/p/{fx.property_a.id}/departments")
    assert res.status_code == 200
    names = sorted(d["name"] for d in res.get_json())
    assert names == ["Engineering", "Front Desk", "Housekeeping"]


def test_users_lists_staff_with_roles(app, fx, login):
    c = login("agent@hvh.test")
    res = c.get(f"/api/p/{fx.property_a.id}/users")
    assert res.status_code == 200
    rows = {u["email"]: u for u in res.get_json()}
    assert rows["engineer@hvh.test"]["role"] == "dept_staff"
    assert rows["engineer@hvh.test"]["departmentId"] == fx.dept_engineering.id
    assert "admin@lsi.test" not in rows
    assert "passwordHash" not in rows["engineer@hvh.test"]


def _make_department(admin, fx, **overrides) -> dict:
    body = {"name": "Spa", "type": "spa"} | overrides
    res = admin.post(f"/api/p/{fx.property_a.id}/departments", json=body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_department_create_patch_and_delete(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/departments"
    admin = login("admin@hvh.test")
    d = _make_department(admin, fx, escalation_minutes=30)
    assert d["type"] == "spa" and d["escalationMinutes"] == 30 and d["active"] is True

    assert d["id"] in [x["id"] for x in login("agent@hvh.test").get(base).get_json()]

    for field, value in (("name", "Spa & Wellness"), ("type", "other"),
                         ("escalationMinutes", 45), ("active", False)):
        res = admin.patch(f"{base}/{d['id']}", json={field: value})
        assert res.status_code == 200, res.get_json()
        assert res.get_json()[field] == value
    patched = admin.patch(f"{base}/{d['id']}", json={}).get_json()
    assert patched == {"id": d["id"], "name": "Spa & Wellness", "type": "other",
                       "escalationMinutes": 45, "active": False}

    assert admin.delete(f"{base}/{d['id']}").status_code == 204
    assert admin.delete(f"{base}/{d['id']}").status_code == 404
    assert d["id"] not in [x["id"] for x in admin.get(base).get_json()]


def test_department_writes_require_manage_admin(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/departments"
    admin = login("admin@hvh.test")
    d = _make_department(admin, fx)
    for c in (login("agent@hvh.test"), login("manager@hvh.test")):
        assert c.get(base).status_code == 200  # reads stay open to every member
        assert c.post(base, json={"name": "Valet", "type": "valet"}).status_code == 403
        assert c.patch(f"{base}/{d['id']}", json={"name": "x"}).status_code == 403
        assert c.delete(f"{base}/{d['id']}").status_code == 403
    corporate = login("corporate@hvh.test")  # manage_admin = {admin, corporate}
    assert corporate.patch(f"{base}/{d['id']}", json={"name": "Spa 2"}).status_code == 200


def test_department_validation_and_cross_property_scope(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/departments"
    admin = login("admin@hvh.test")
    assert admin.post(base, json={"name": "", "type": "spa"}).status_code == 400
    assert admin.post(base, json={"name": "Spa", "type": "sauna"}).status_code == 400
    assert admin.post(base, json={"name": "Spa", "type": "spa",
                                  "escalationMinutes": 0}).status_code == 400
    # a department of property B is invisible here, not merely unauthorised
    b_dept = login("admin@lsi.test").get(
        f"/api/p/{fx.property_b.id}/departments").get_json()[0]
    assert admin.patch(f"{base}/{b_dept['id']}", json={"name": "x"}).status_code == 404
    assert admin.delete(f"{base}/{b_dept['id']}").status_code == 404


def _ref_membership(db, fx, dept_id):
    from app.models import PropertyMembership, UserAccount

    u = UserAccount(email="spa@hvh.test", first_name="Sal", last_name="Spa")
    db.add(u)
    db.flush()
    db.add(PropertyMembership(user_id=u.id, property_id=fx.property_a.id, role=Role.dept_staff,
                              department_id=dept_id))


def _ref_quick_reply(db, fx, dept_id):
    from app.models import QuickReply

    db.add(QuickReply(property_id=fx.property_a.id, department_id=dept_id, shortcut="/spa",
                      title="Spa hours", body="The spa is open until 8pm."))


def _ref_digital_asset(db, fx, dept_id):
    from app.models import DigitalAsset

    db.add(DigitalAsset(property_id=fx.property_a.id, department_id=dept_id, name="Spa menu",
                        url="https://example.test/spa.pdf", short_code="spa123"))


def _ref_conversation(db, fx, dept_id):
    from tests.factories import make_conversation

    make_conversation(db, fx, assigned_department_id=dept_id)


def _ref_work_order(db, fx, dept_id):
    from app.models import WorkOrder

    db.add(WorkOrder(property_id=fx.property_a.id, title="Fix the sauna",
                     type=WorkOrderType.maintenance, department_id=dept_id))


@pytest.mark.parametrize("add_reference", [
    _ref_membership, _ref_quick_reply, _ref_digital_asset, _ref_conversation, _ref_work_order,
], ids=["membership", "quick_reply", "digital_asset", "conversation", "work_order"])
def test_department_delete_is_refused_while_anything_references_it(app, fx, database, login,
                                                                   add_reference):
    """Every nullable FK to department.id must block the delete. Phase 1 has no soft delete and
    no ON DELETE behaviour, so a delete that went through would orphan the reference."""
    base = f"/api/p/{fx.property_a.id}/departments"
    admin = login("admin@hvh.test")
    d = _make_department(admin, fx)
    with database.session() as db:
        add_reference(db, fx, d["id"])

    res = admin.delete(f"{base}/{d['id']}")
    assert res.status_code == 409, res.get_json()
    assert "deactivate" in res.get_json()["error"]["message"]
    assert d["id"] in [x["id"] for x in admin.get(base).get_json()]

    # deactivating is the documented escape hatch and must still work
    assert admin.patch(f"{base}/{d['id']}", json={"active": False}).get_json()["active"] is False
