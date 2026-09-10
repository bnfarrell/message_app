from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.guests import find_by_phone
from app.models import Guest, Stay
from app.schemas.enums import StayStatus


def find_in_house_for_guest(db: Session, property_id: str, guest_id: str) -> Stay | None:
    return db.scalar(
        select(Stay).where(Stay.property_id == property_id, Stay.guest_id == guest_id,
                           Stay.status == StayStatus.checked_in)
        .order_by(Stay.actual_checkin_at.desc())
    )


def find_in_house_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, Stay] | None:
    guest = find_by_phone(db, property_id, phone)
    if guest is None:
        return None
    stay = find_in_house_for_guest(db, property_id, guest.id)
    return (guest, stay) if stay else None


def get(db: Session, property_id: str, stay_id: str) -> Stay | None:
    return db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
