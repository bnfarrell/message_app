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
