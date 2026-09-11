from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app import clock
from app.auth.passwords import hash_password
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
    return hash_password(pw, rounds=4)  # low cost: tests only


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
    b = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago",
                 sms_number="+15550200",
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

    stay_inhouse_a = Stay(guest_id=guest_inhouse_a.id, property_id=a.id,
                          pms_reservation_id="RES-412",
                          room_number="412", room_type="King", status=StayStatus.checked_in,
                          arrival_date=today,
                          departure_date=date.fromordinal(today.toordinal() + 3),
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
        stay_inhouse_a=stay_inhouse_a, guest_nostay_a=guest_nostay_a, guest_b=guest_b,
        stay_b=stay_b,
    )
