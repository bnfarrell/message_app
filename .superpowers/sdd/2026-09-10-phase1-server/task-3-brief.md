### Task 3: Test infrastructure — app fixture, template DB, fixture data, login helper

**Files:**
- Create: `server/tests/conftest.py`, `server/tests/fixtures.py`, `server/tests/test_fixtures.py`

**Interfaces:**
- Produces (pytest fixtures): `app` (Flask app on a fresh DB copy, clock frozen at `2026-09-10T12:00:00Z`), `client`, `database`, `fx: Fixture`, `login(email) -> FlaskClient`. `Fixture` dataclass fields: `property_a, property_b, dept_front_desk, dept_housekeeping, dept_engineering, agent_a, agent_a2, engineer_a, housekeeper_a, supervisor_a, manager_a, admin_a, corporate_a, admin_b, agent_b, guest_inhouse_a, stay_inhouse_a, guest_nostay_a, guest_b, stay_b` (all model instances; ids via `.id`). Password for every fixture user: `Password123!`.
- Consumes: Task 4's `hash_password`. Until Task 4 lands, `fixtures.py` uses `bcrypt` directly with the same algorithm (cost 12) so this task is testable now; Task 4 switches it to `app.auth.passwords.hash_password`.

- [ ] **Step 1: Write the failing fixture test**

`server/tests/test_fixtures.py`:
```python
from sqlalchemy import func, select

from app.models import Guest, PropertyMembership, UserAccount


def test_fixture_loads_two_properties_and_users(app, fx, database):
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 11
        assert db.scalar(select(func.count()).select_from(PropertyMembership)) == 11
        assert db.scalar(select(func.count()).select_from(Guest)) == 3
    assert fx.property_a.id != fx.property_b.id
    assert fx.stay_inhouse_a.room_number == "412"


def test_clock_is_frozen(app):
    from app import clock

    assert clock.now().isoformat() == "2026-09-10T12:00:00+00:00"


def test_each_test_gets_a_fresh_database(app, database):
    from app.models import Property

    with database.session() as db:
        db.add(Property(name="Scratch", code="SCR", timezone="UTC"))
    # The next test's assertion on counts would fail if this leaked.
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_fixtures.py -q`
Expected: FAIL with `fixture 'fx' not found`.

- [ ] **Step 3: Write `tests/fixtures.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import bcrypt
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    Department,
    Guest,
    Property,
    PropertyMembership,
    Stay,
    UserAccount,
)
from app.schemas.enums import DepartmentType, Role, SmsConsentStatus, StayStatus

PASSWORD = "Password123!"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=4)).decode()  # low cost: tests only


@dataclass
class Fixture:
    property_a: Property
    property_b: Property
    dept_front_desk: Department
    dept_housekeeping: Department
    dept_engineering: Department
    agent_a: UserAccount
    agent_a2: UserAccount
    engineer_a: UserAccount
    housekeeper_a: UserAccount
    supervisor_a: UserAccount
    manager_a: UserAccount
    admin_a: UserAccount
    corporate_a: UserAccount
    admin_b: UserAccount
    agent_b: UserAccount
    guest_inhouse_a: Guest
    stay_inhouse_a: Stay
    guest_nostay_a: Guest
    guest_b: Guest
    stay_b: Stay


def _user(db: Session, email: str, first: str, last: str) -> UserAccount:
    u = UserAccount(email=email, first_name=first, last_name=last, password_hash=_hash(PASSWORD))
    db.add(u)
    db.flush()
    return u


def _member(db: Session, user: UserAccount, prop: Property, role: Role,
            dept: Department | None = None) -> None:
    db.add(PropertyMembership(user_id=user.id, property_id=prop.id, role=role,
                              department_id=dept.id if dept else None))


def load_fixture(db: Session) -> Fixture:
    today = clock.now().date()
    a = Property(name="Harbourview Hotel", code="HVH", timezone="America/New_York",
                 sms_number="+15550100",
                 settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                           "help_text": "Harbourview Hotel: text us anytime or call +1 555 0100."})
    b = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago", sms_number="+15550200",
                 settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                           "help_text": "Lakeside Inn: call +1 555 0200."})
    db.add_all([a, b])
    db.flush()

    fd = Department(property_id=a.id, name="Front Desk", type=DepartmentType.front_desk)
    hk = Department(property_id=a.id, name="Housekeeping", type=DepartmentType.housekeeping)
    eng = Department(property_id=a.id, name="Engineering", type=DepartmentType.engineering)
    fd_b = Department(property_id=b.id, name="Front Desk", type=DepartmentType.front_desk)
    db.add_all([fd, hk, eng, fd_b])
    db.flush()

    agent_a = _user(db, "agent@hvh.test", "Ava", "Agent")
    agent_a2 = _user(db, "agent2@hvh.test", "Marcus", "Reyes")
    engineer_a = _user(db, "engineer@hvh.test", "Eli", "Engineer")
    housekeeper_a = _user(db, "housekeeper@hvh.test", "Hana", "Keeper")
    supervisor_a = _user(db, "supervisor@hvh.test", "Sam", "Super")
    manager_a = _user(db, "manager@hvh.test", "Morgan", "Manager")
    admin_a = _user(db, "admin@hvh.test", "Alex", "Admin")
    corporate_a = _user(db, "corporate@hvh.test", "Casey", "Corp")
    admin_b = _user(db, "admin@lsi.test", "Blake", "Admin")
    agent_b = _user(db, "agent@lsi.test", "Bea", "Agent")
    shared = _user(db, "regional@group.test", "Riley", "Regional")  # manager at both properties

    _member(db, agent_a, a, Role.agent, fd)
    _member(db, agent_a2, a, Role.agent, fd)
    _member(db, engineer_a, a, Role.dept_staff, eng)
    _member(db, housekeeper_a, a, Role.dept_staff, hk)
    _member(db, supervisor_a, a, Role.supervisor, eng)
    _member(db, manager_a, a, Role.manager)
    _member(db, admin_a, a, Role.admin)
    _member(db, corporate_a, a, Role.corporate)
    _member(db, admin_b, b, Role.admin)
    _member(db, agent_b, b, Role.agent, fd_b)
    _member(db, shared, b, Role.manager)

    guest_inhouse_a = Guest(property_id=a.id, first_name="Sarah", last_name="Chen",
                            phone_e164="+15551234567", loyalty_tier="Gold",
                            sms_consent_status=SmsConsentStatus.opted_in,
                            sms_consent_at=clock.now(), sms_consent_source="pms")
    guest_nostay_a = Guest(property_id=a.id, first_name="Diego", last_name="Ruiz",
                           phone_e164="+15559876543", sms_consent_status=SmsConsentStatus.opted_in,
                           sms_consent_at=clock.now(), sms_consent_source="inbound_sms")
    guest_b = Guest(property_id=b.id, first_name="Nia", last_name="Okafor",
                    phone_e164="+15557778888", sms_consent_status=SmsConsentStatus.opted_in,
                    sms_consent_at=clock.now(), sms_consent_source="pms")
    db.add_all([guest_inhouse_a, guest_nostay_a, guest_b])
    db.flush()

    stay_inhouse_a = Stay(guest_id=guest_inhouse_a.id, property_id=a.id, pms_reservation_id="RES-412",
                          room_number="412", room_type="King", status=StayStatus.checked_in,
                          arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 3),
                          actual_checkin_at=clock.now())
    stay_b = Stay(guest_id=guest_b.id, property_id=b.id, pms_reservation_id="RES-B-101",
                  room_number="101", room_type="Queen", status=StayStatus.checked_in,
                  arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 1),
                  actual_checkin_at=clock.now())
    db.add_all([stay_inhouse_a, stay_b])
    db.flush()

    return Fixture(
        property_a=a, property_b=b, dept_front_desk=fd, dept_housekeeping=hk, dept_engineering=eng,
        agent_a=agent_a, agent_a2=agent_a2, engineer_a=engineer_a, housekeeper_a=housekeeper_a,
        supervisor_a=supervisor_a, manager_a=manager_a, admin_a=admin_a, corporate_a=corporate_a,
        admin_b=admin_b, agent_b=agent_b, guest_inhouse_a=guest_inhouse_a,
        stay_inhouse_a=stay_inhouse_a, guest_nostay_a=guest_nostay_a, guest_b=guest_b, stay_b=stay_b,
    )
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
from __future__ import annotations

import shutil
from datetime import datetime, timezone

import pytest

from app import clock, create_app
from app.config import Config
from app.db import run_migrations
from tests.fixtures import PASSWORD, load_fixture

FROZEN = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def template_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("template") / "template.db"
    run_migrations(f"sqlite:///{path.as_posix()}")
    return path


@pytest.fixture()
def app(template_db_path, tmp_path):
    db_path = tmp_path / "test.db"
    shutil.copy(template_db_path, db_path)
    clock.freeze(FROZEN)
    cfg = Config(
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        TESTING=True,
        START_WORKER=False,
        ENV="testing",
        PMS_TICK_SECONDS=0,
    )
    application = create_app(cfg)
    yield application
    application.extensions["db"].engine.dispose()
    clock.reset()


@pytest.fixture()
def database(app):
    return app.extensions["db"]


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def fx(database):
    with database.session() as db:
        return load_fixture(db)


@pytest.fixture()
def login(app):
    def _login(email: str, password: str = PASSWORD):
        c = app.test_client()
        res = c.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.get_json()
        return c

    return _login
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q`
Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
cd ..
git add server/tests
git commit -m "test(server): app/database fixtures, deterministic fixture data, frozen clock"
```

---

