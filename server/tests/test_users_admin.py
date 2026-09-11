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


def test_non_admin_cannot_update_staff(app, fx, login):
    mgr = login("manager@hvh.test")
    r = mgr.patch(f"/api/p/{fx.property_a.id}/users/{fx.agent_a.id}", json={"role": "supervisor"})
    assert r.status_code == 403


def test_non_admin_cannot_remove_membership(app, fx, login):
    mgr = login("manager@hvh.test")
    r = mgr.delete(f"/api/p/{fx.property_a.id}/users/{fx.agent_a.id}")
    assert r.status_code == 403


def test_create_staff_conflict_when_already_member(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "agent@hvh.test", "firstName": "Ava", "lastName": "Agent", "role": "agent"})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CONFLICT"


def test_create_staff_requires_password_for_new_account(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "nopass@hvh.test", "firstName": "No", "lastName": "Pass", "role": "agent"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_staff_rejects_cross_property_department(app, fx, login, database):
    from sqlalchemy import select

    from app.models import Department

    with database.session() as db:
        dept_b = db.scalar(select(Department).where(Department.property_id == fx.property_b.id))

    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "crossdept@hvh.test", "firstName": "Cross", "lastName": "Dept",
                               "password": "Password123!", "role": "dept_staff", "departmentId": dept_b.id})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_staff_survives_concurrent_account_insert_race(app, fx, database, monkeypatch):
    """Mirrors test_find_or_create_by_phone_survives_concurrent_insert_race (test_guests_stays.py):
    force create_staff's initial email lookup to miss while a competing account with the same
    email already exists, so the INSERT hits the UniqueConstraint and the except IntegrityError
    branch must recover by re-querying and attaching the membership to the winning account
    instead of erroring or creating a duplicate."""
    from sqlalchemy import select

    from app.domain import users as users_domain
    from app.models import UserAccount
    from app.schemas.enums import Role
    from app.schemas.users import CreateStaffRequest

    email = "race@hvh.test"
    with database.session() as db:
        winner = UserAccount(email=email, first_name="Race", last_name="Winner",
                             password_hash=users_domain.hash_password("Password123!"))
        db.add(winner)
        db.flush()
        winner_id = winner.id

        real_scalar = db.scalar
        calls = {"n": 0}

        def flaky_scalar(stmt, *a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return None  # pretend the winning insert isn't visible yet (the race window)
            return real_scalar(stmt, *a, **kw)

        monkeypatch.setattr(db, "scalar", flaky_scalar)

        data = CreateStaffRequest(email=email, first_name="Ignored", last_name="Ignored",
                                  password="Password123!", role=Role.agent)
        out = users_domain.create_staff(db, fx.property_a.id, fx.admin_a.id, data)
        dupes = db.scalars(select(UserAccount).where(UserAccount.email == email)).all()

    assert calls["n"] >= 2, "the except IntegrityError branch never ran"
    assert out.id == winner_id
    assert len(dupes) == 1
