def test_admin_creates_updates_and_removes_staff(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "new@hvh.test", "firstName": "Nora", "lastName": "New",
                               "password": "Password123!", "role": "dept_staff",
                               "departmentId": fx.dept_housekeeping.id})
    assert r.status_code == 201
    u = r.get_json()
    assert u["role"] == "dept_staff" and u["departmentId"] == fx.dept_housekeeping.id
    assert login("new@hvh.test").get("/api/auth/me").status_code == 200
    role_change = admin.patch(f"{base}/{u['id']}", json={"role": "supervisor"})
    assert role_change.get_json()["role"] == "supervisor"
    # Revoking access to THIS property is deleting the membership; disabling the global account
    # is not this endpoint's business (see test_property_admin_cannot_take_over_an_account).
    assert admin.delete(f"{base}/{u['id']}").status_code == 204
    relogin = client.post("/api/auth/login",
                          json={"email": "new@hvh.test", "password": "Password123!"})
    assert relogin.status_code == 200
    assert relogin.get_json()["memberships"] == []
    assert "new@hvh.test" not in {x["email"] for x in admin.get(base).get_json()}


def test_existing_account_gets_membership_not_duplicate(app, fx, login):
    base = f"/api/p/{fx.property_b.id}/users"
    admin_b = login("admin@lsi.test")
    r = admin_b.post(base, json={"email": "agent@hvh.test", "firstName": "Ava", "lastName": "Agent",
                                 "role": "agent"})
    assert r.status_code == 201
    memberships = login("agent@hvh.test").get("/api/auth/me").get_json()["memberships"]
    assert {m["propertyCode"] for m in memberships} == {"HVH", "LSI"}


def test_non_admin_cannot_manage_users(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    mgr = login("manager@hvh.test")
    r = mgr.post(base, json={"email": "x@hvh.test", "firstName": "x", "lastName": "y",
                             "role": "agent"})
    assert r.status_code == 403


def test_guest_detail(app, fx, client, login):
    from tests.factories import inbound

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    agent = login("agent@hvh.test")
    d = agent.get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_inhouse_a.id}").get_json()
    assert d["guest"]["firstName"] == "Sarah" and d["stays"][0]["roomNumber"] == "412"
    assert len(d["conversationIds"]) == 1
    missing = agent.get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_b.id}")
    assert missing.status_code == 404


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
    r = admin.post(base, json={"email": "agent@hvh.test", "firstName": "Ava", "lastName": "Agent",
                               "role": "agent"})
    assert r.status_code == 409
    assert r.get_json()["error"]["code"] == "CONFLICT"


def test_create_staff_requires_password_for_new_account(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "nopass@hvh.test", "firstName": "No", "lastName": "Pass",
                               "role": "agent"})
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_create_staff_rejects_cross_property_department(app, fx, login, database):
    from sqlalchemy import select

    from app.models import Department

    with database.session() as db:
        dept_b = db.scalar(select(Department).where(Department.property_id == fx.property_b.id))

    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "crossdept@hvh.test", "firstName": "Cross",
                               "lastName": "Dept",
                               "password": "Password123!", "role": "dept_staff",
                               "departmentId": dept_b.id})
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


def test_property_admin_cannot_take_over_an_account(app, fx, client, login):
    """The cross-tenant escalation axis, which the "request Property B's URL, expect 403" shape of
    tests/test_isolation.py structurally cannot reach: every request below is to Property A's own
    URL, authorised by a real membership at Property A.

    `UserAccount` is global, and `create_staff` deliberately attaches an *existing* account to
    your property by email (an intended feature — see
    test_existing_account_gets_membership_not_duplicate). If the property-scoped PATCH could also
    write global account columns, an admin at A could add a stranger's account to A, reset its
    password, and then sign in as them at every *other* property that account belongs to. Three
    requests, none of them to a Property B URL.
    """
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")  # admin at A only

    # Step 1 stands: attaching the existing regional account (a manager at B) to A is allowed.
    added = admin.post(base, json={"email": "regional@group.test", "firstName": "Riley",
                                   "lastName": "Regional", "role": "agent"})
    assert added.status_code == 201
    victim_id = added.get_json()["id"]

    # Step 2 must not: password and status are global UserAccount columns.
    pwned = admin.patch(f"{base}/{victim_id}", json={"password": "Pwned123!"})
    assert pwned.status_code == 400, "a property-scoped PATCH reset a global password"
    assert pwned.get_json()["error"]["code"] == "VALIDATION_FAILED"
    disabled = admin.patch(f"{base}/{victim_id}", json={"status": "disabled"})
    assert disabled.status_code == 400, "a property-scoped PATCH disabled a global account"

    # Step 3 therefore cannot happen: the attacker's password does not work...
    assert client.post("/api/auth/login", json={"email": "regional@group.test",
                                                "password": "Pwned123!"}).status_code == 401
    # ...and the victim still has their own account and their Property B access.
    me = login("regional@group.test").get("/api/auth/me").get_json()
    assert {m["propertyCode"] for m in me["memberships"]} == {"HVH", "LSI"}

    # The membership fields the endpoint does own still work, and are all it can reach.
    assert admin.patch(f"{base}/{victim_id}",
                       json={"role": "supervisor"}).get_json()["role"] == "supervisor"


def test_staff_patch_rejects_every_global_account_field(app, fx, login):
    admin = login("admin@hvh.test")
    base = f"/api/p/{fx.property_a.id}/users/{fx.agent_a.id}"
    for field, value in (("password", "Pwned123!"), ("status", "disabled"),
                         ("firstName", "Mallory"), ("lastName", "Malory")):
        r = admin.patch(base, json={field: value})
        assert r.status_code == 400, f"{field} is still writable through a property-scoped URL"


def test_last_admin_cannot_be_demoted_or_removed(app, fx, login):
    """A property must keep someone who can `manage_admin`, or it is locked out of its own
    administration with no in-app remedy."""
    base = f"/api/p/{fx.property_b.id}/users"
    admin_b = login("admin@lsi.test")  # the only manage_admin membership at B
    demote = admin_b.patch(f"{base}/{fx.admin_b.id}", json={"role": "manager"})
    assert demote.status_code == 409 and demote.get_json()["error"]["code"] == "CONFLICT"
    assert admin_b.delete(f"{base}/{fx.admin_b.id}").status_code == 409

    # With a second admin in place, both are allowed again.
    assert admin_b.post(base, json={"email": "admin2@lsi.test", "firstName": "Bo",
                                    "lastName": "Second", "password": "Password123!",
                                    "role": "admin"}).status_code == 201
    assert admin_b.delete(f"{base}/{fx.admin_b.id}").status_code == 204


def test_last_admin_guard_counts_corporate_and_allows_admin_to_admin_moves(app, fx, login):
    """Property A has an admin and a corporate member, both of which hold `manage_admin`; the
    guard must count both, and must not block a change that keeps the capability."""
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    assert admin.patch(f"{base}/{fx.admin_a.id}",
                       json={"role": "corporate"}).status_code == 200
    # corporate_a is now the other manage_admin holder; removing it is still allowed.
    assert admin.delete(f"{base}/{fx.corporate_a.id}").status_code == 204
    # ...but the last one standing is not.
    assert admin.delete(f"{base}/{fx.admin_a.id}").status_code == 409
