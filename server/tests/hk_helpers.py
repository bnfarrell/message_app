"""Shared set-up for the housekeeping tests."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.domain import hk_rooms, pm_cycles
from app.models import (
    Guest,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    Stay,
    UserAccount,
)
from app.schemas.enums import PmUnitKind, Role, StayStatus
from tests.fixtures import PASSWORD


def make_rooms(db: Session, property_id: str, codes=("101", "102", "204")) -> dict[str, Room]:
    for code in codes:
        db.add(MaintainableUnit(property_id=property_id, kind=PmUnitKind.guest_room, code=code,
                                name=f"Room {code}",
                                floor=int(code[0]) if code[:1].isdigit() else None))
    db.flush()
    hk_rooms.ensure_rooms(db, property_id)
    return rooms_by_code(db, property_id)


def rooms_by_code(db: Session, property_id: str) -> dict[str, Room]:
    return {unit.code: room for room, unit in hk_rooms.active_rooms(db, property_id)}


def local_today(db: Session, property_id: str) -> date:
    return pm_cycles.local_today(db.get(Property, property_id))


def add_stay(db: Session, property_id: str, room_number: str, *, status: StayStatus,
             arrival: date, departure: date, checked_out_at: datetime | None = None,
             first: str = "Test", last: str = "Guest") -> Stay:
    guest = Guest(property_id=property_id, first_name=first, last_name=last,
                  phone_e164=f"+1555{uuid.uuid4().int % 10**7:07d}")
    db.add(guest)
    db.flush()
    stay = Stay(guest_id=guest.id, property_id=property_id, room_number=room_number,
                status=status, arrival_date=arrival, departure_date=departure,
                actual_checkout_at=checked_out_at)
    db.add(stay)
    db.flush()
    return stay


def add_user(db: Session, property_id: str, email: str, role: Role,
             department_id: str | None, first: str = "Pat", last: str = "Person") -> str:
    user = UserAccount(email=email, first_name=first, last_name=last,
                       password_hash=hash_password(PASSWORD, rounds=4))
    db.add(user)
    db.flush()
    db.add(PropertyMembership(user_id=user.id, property_id=property_id, role=role,
                              department_id=department_id))
    db.flush()
    return user.id


def add_hk_supervisor(db: Session, fx) -> str:
    """The fixture's supervisor is Engineering; housekeeping needs its own."""
    return add_user(db, fx.property_a.id, "grace@hvh.test", Role.supervisor,
                    fx.dept_housekeeping.id, "Grace", "Osei")
