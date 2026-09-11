### Task 17: Users & memberships admin, guest detail

**Files:**
- Create: `server/app/api/guests.py`, `server/tests/test_users_admin.py`
- Modify: `server/app/schemas/users.py`, `server/app/domain/users.py`, `server/app/api/users.py`, `server/app/__init__.py`

**Interfaces:**
- Produces: `users.create_staff(db, property_id, actor_user_id, data: CreateStaffRequest) -> StaffUserOut` (creates the account if the email is new, else adds a membership; hashes password), `users.update_staff(db, property_id, actor_user_id, user_id, data: StaffPatch) -> StaffUserOut` (role, department, status, reset password; audit), `users.remove_membership(db, property_id, actor_user_id, user_id)`; `GET /api/p/<id>/guests/<guest_id>` → `GuestDetail` (guest + stays + conversation ids). Schemas: `CreateStaffRequest`, `StaffPatch`, `GuestDetail`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_users_admin.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_users_admin.py -q`
Expected: FAIL with 404/405.

- [ ] **Step 3: Extend schemas, domain, and routes**

Append to `app/schemas/users.py`:
```python
from pydantic import EmailStr, Field

from app.schemas.conversations import GuestOut, StayOut
from app.schemas.enums import UserStatus


class CreateStaffRequest(CamelModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Role
    department_id: str | None = None
    phone: str | None = None


class StaffPatch(CamelModel):
    role: Role | None = None
    department_id: str | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    first_name: str | None = None
    last_name: str | None = None


class GuestDetail(CamelModel):
    guest: GuestOut
    stays: list[StayOut]
    conversation_ids: list[str]
```

Append to `app/domain/users.py` (imports: `hash_password`, `audit`, `Conflict, NotFound, ValidationFailed`, `Department`, `UserStatus`, schemas):
```python
def _staff_out(db: Session, property_id: str, user_id: str) -> StaffUserOut:
    row = db.execute(select(UserAccount, PropertyMembership).join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                     .where(PropertyMembership.property_id == property_id, UserAccount.id == user_id)).first()
    if row is None:
        raise NotFound("User is not a member of this property")
    u, m = row
    return StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name, avatar_url=u.avatar_url,
                        role=m.role, department_id=m.department_id, status=u.status.value)


def _check_department(db: Session, property_id: str, department_id: str | None) -> None:
    if department_id and not db.scalar(select(Department.id).where(Department.id == department_id,
                                                                    Department.property_id == property_id)):
        raise ValidationFailed("Unknown department")


def create_staff(db: Session, property_id: str, actor_user_id: str, data: CreateStaffRequest) -> StaffUserOut:
    _check_department(db, property_id, data.department_id)
    user = db.scalar(select(UserAccount).where(UserAccount.email == data.email.lower()))
    if user is None:
        if not data.password:
            raise ValidationFailed("A password is required for a new account")
        user = UserAccount(email=data.email.lower(), first_name=data.first_name, last_name=data.last_name,
                           phone=data.phone, password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
    if db.scalar(select(PropertyMembership.id).where(PropertyMembership.user_id == user.id,
                                                    PropertyMembership.property_id == property_id)):
        raise Conflict("Already a member of this property")
    db.add(PropertyMembership(user_id=user.id, property_id=property_id, role=data.role, department_id=data.department_id))
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.created", "user_account", user.id,
                 after={"role": data.role.value, "department_id": data.department_id})
    return _staff_out(db, property_id, user.id)


def update_staff(db: Session, property_id: str, actor_user_id: str, user_id: str, data: StaffPatch) -> StaffUserOut:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    u = db.get(UserAccount, user_id)
    before = {"role": m.role.value, "department_id": m.department_id, "status": u.status.value}
    changes = data.model_dump(exclude_unset=True)
    if "department_id" in changes:
        _check_department(db, property_id, changes["department_id"])
        m.department_id = changes["department_id"]
    if data.role is not None:
        m.role = data.role
    if data.status is not None:
        u.status = data.status
    if data.password:
        u.password_hash = hash_password(data.password)
    if data.first_name:
        u.first_name = data.first_name
    if data.last_name:
        u.last_name = data.last_name
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.updated", "user_account", user_id, before=before,
                 after={"role": m.role.value, "department_id": m.department_id, "status": u.status.value,
                        "password_reset": bool(data.password)})
    return _staff_out(db, property_id, user_id)


def remove_membership(db: Session, property_id: str, actor_user_id: str, user_id: str) -> None:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    db.delete(m)
    audit.record(db, property_id, actor_user_id, "membership.removed", "user_account", user_id)
```

Extend `app/api/users.py` with `POST ""` (201), `PATCH /<user_id>`, `DELETE /<user_id>` (204), each `@require_capability("manage_admin")`, calling the three functions above.

`app/api/guests.py`:
```python
from flask import Blueprint, g
from sqlalchemy import select

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import guests
from app.errors import NotFound
from app.models import Conversation, Stay
from app.schemas.conversations import GuestOut, StayOut
from app.schemas.users import GuestDetail

bp = Blueprint("guests", __name__, url_prefix="/api/p/<property_id>/guests")


@bp.get("/<guest_id>")
@require_auth
@require_property
def get_guest(property_id: str, guest_id: str):
    with db_session() as db:
        guest = guests.get(db, g.property_id, guest_id)
        if guest is None:
            raise NotFound("Guest not found")
        stays = db.scalars(select(Stay).where(Stay.guest_id == guest.id).order_by(Stay.arrival_date.desc())).all()
        conv_ids = [*db.scalars(select(Conversation.id).where(Conversation.guest_id == guest.id)).all()]
        return ok(GuestDetail(guest=GuestOut.model_validate(guest), stays=[StayOut.model_validate(s) for s in stays],
                              conversation_ids=conv_ids))
```

Register `guests.bp`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): staff/membership administration and guest detail"
```

---

