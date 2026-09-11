def test_admin_creates_updates_and_removes_staff(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "new@hvh.test", "firstName": "Nora", "lastName": "New",
                               "password": "Password123!", "role": "dept_staff", "departmentId": fx.dept_housekeeping.id})
    assert r.status_code == 201
    u = r.get_json()
    assert u["role"] == "dept_staff" and u["departmentId"] == fx.dept_housekeeping.id
    assert login("new@hvh.test").get("/api/auth/me").status_code == 200
    assert admin.patch(f"{base}/{u['id']}", json={"role": "supervisor"}).get_json()["role"] == "supervisor"
    assert admin.patch(f"{base}/{u['id']}", json={"status": "disabled"}).get_json()["status"] == "disabled"
    assert client.post("/api/auth/login", json={"email": "new@hvh.test", "password": "Password123!"}).status_code == 401
    assert admin.delete(f"{base}/{u['id']}").status_code == 204
    assert "new@hvh.test" not in {x["email"] for x in admin.get(base).get_json()}


def test_existing_account_gets_membership_not_duplicate(app, fx, login):
    base = f"/api/p/{fx.property_b.id}/users"
    admin_b = login("admin@lsi.test")
    r = admin_b.post(base, json={"email": "agent@hvh.test", "firstName": "Ava", "lastName": "Agent", "role": "agent"})
    assert r.status_code == 201
    memberships = login("agent@hvh.test").get("/api/auth/me").get_json()["memberships"]
    assert {m["propertyCode"] for m in memberships} == {"HVH", "LSI"}


def test_non_admin_cannot_manage_users(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    mgr = login("manager@hvh.test")
    assert mgr.post(base, json={"email": "x@hvh.test", "firstName": "x", "lastName": "y", "role": "agent"}).status_code == 403


def test_guest_detail(app, fx, client, login):
    from tests.factories import inbound

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    d = login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_inhouse_a.id}").get_json()
    assert d["guest"]["firstName"] == "Sarah" and d["stays"][0]["roomNumber"] == "412"
    assert len(d["conversationIds"]) == 1
    assert login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_b.id}").status_code == 404
