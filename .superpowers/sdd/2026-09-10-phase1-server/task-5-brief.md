### Task 5: First property-scoped routes + the automated property-isolation suite (§11.1 #9)

**Files:**
- Create: `server/app/schemas/users.py`, `server/app/domain/users.py`, `server/app/api/departments.py`, `server/app/api/users.py`, `server/tests/test_isolation.py`, `server/tests/test_departments_users.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `GET /api/p/<property_id>/departments`, `GET /api/p/<property_id>/users`; `DepartmentOut`, `StaffUserOut`; `domain.users.list_departments(db, property_id)`, `list_staff(db, property_id)`, `members_of_department(db, property_id, department_id) -> list[str]`; the isolation test that auto-discovers every `/api/p/<property_id>/...` rule.
- Consumes: Task 4 decorators and `_util`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_departments_users.py`:
```python
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
```

`server/tests/test_isolation.py`:
```python
"""design.md §11.1 #9: a member of Property A gets 403 on every Property B resource.

Enumerates every rule under /api/p/<property_id> so new routes are covered automatically.
"""
import re

SKIP_METHODS = {"HEAD", "OPTIONS"}
DUMMY_ID = "00000000-0000-0000-0000-000000000000"


def property_rules(app):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/p/<property_id>"):
            for method in sorted(rule.methods - SKIP_METHODS):
                yield rule, method


def build_path(rule, property_id: str) -> str:
    path = rule.rule.replace("<property_id>", property_id)
    return re.sub(r"<[^>]+>", DUMMY_ID, path)  # 403 must fire before any lookup


def test_route_enumeration_finds_routes(app):
    assert len(list(property_rules(app))) >= 2


def test_member_of_a_gets_403_on_every_b_route(app, fx, login):
    c = login("admin@hvh.test")  # admin at A, no membership at B
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_b.id), method=method, json={})
        if res.status_code != 403:
            failures.append((method, rule.rule, res.status_code))
    assert not failures, f"routes reachable across properties: {failures}"


def test_admin_of_a_is_not_403_on_own_property(app, fx, login):
    """Guards the previous test against vacuity: the same routes must not 403 for a member."""
    c = login("admin@hvh.test")
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_a.id), method=method, json={})
        if res.status_code == 403:
            failures.append((method, rule.rule))
    assert not failures, f"admin blocked on own property: {failures}"


def test_anonymous_gets_401_on_every_property_route(app, fx, client):
    for rule, method in property_rules(app):
        res = client.open(build_path(rule, fx.property_a.id), method=method, json={})
        assert res.status_code == 401, (method, rule.rule, res.status_code)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_isolation.py tests/test_departments_users.py -q`
Expected: FAIL — enumeration finds 0 routes; the others get 404.

- [ ] **Step 3: Write schemas and domain**

`server/app/schemas/users.py`:
```python
from app.schemas.common import CamelModel
from app.schemas.enums import DepartmentType, Role


class DepartmentOut(CamelModel):
    id: str
    name: str
    type: DepartmentType
    escalation_minutes: int
    active: bool


class StaffUserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None
    status: str
```

`server/app/domain/users.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, PropertyMembership, UserAccount
from app.schemas.users import DepartmentOut, StaffUserOut


def list_departments(db: Session, property_id: str) -> list[DepartmentOut]:
    rows = db.scalars(
        select(Department).where(Department.property_id == property_id).order_by(Department.name)
    ).all()
    return [DepartmentOut.model_validate(d) for d in rows]


def list_staff(db: Session, property_id: str) -> list[StaffUserOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id)
        .order_by(UserAccount.first_name, UserAccount.last_name)
    ).all()
    return [
        StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
                     avatar_url=u.avatar_url, role=m.role, department_id=m.department_id,
                     status=u.status.value)
        for u, m in rows
    ]


def members_of_department(db: Session, property_id: str, department_id: str) -> list[str]:
    return list(
        db.scalars(
            select(PropertyMembership.user_id).where(
                PropertyMembership.property_id == property_id,
                PropertyMembership.department_id == department_id,
            )
        ).all()
    )
```

- [ ] **Step 4: Write the blueprints and register them**

`server/app/api/departments.py`:
```python
from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("departments", __name__, url_prefix="/api/p/<property_id>/departments")


@bp.get("")
@require_auth
@require_property
def list_departments(property_id: str):
    with db_session() as db:
        return ok(users.list_departments(db, g.property_id))
```

`server/app/api/users.py`:
```python
from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("users", __name__, url_prefix="/api/p/<property_id>/users")


@bp.get("")
@require_auth
@require_property
def list_users(property_id: str):
    with db_session() as db:
        return ok(users.list_staff(db, g.property_id))
```

In `create_app`, extend the import to `from app.api import auth, departments, health, users` and register `departments.bp` and `users.bp`. An empty-string route on a prefixed blueprint yields the exact path `/api/p/<id>/departments` (no trailing slash), which is what the isolation test builds.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): departments/users routes and the property-isolation test suite"
```

---

