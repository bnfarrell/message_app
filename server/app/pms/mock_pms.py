"""Drives seeded stays through check-in and check-out so the inbox has a living hotel behind it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Guest, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent
from app.schemas.enums import StayStatus


class MockPmsAdapter:
    integration_key = "mock"

    def __init__(self):
        self._flip = False

    @staticmethod
    def _event(stay: Stay, guest: Guest, type: str, status: StayStatus) -> PmsEvent:
        return PmsEvent(
            external_id=stay.pms_reservation_id or stay.id, type=type, property_id=stay.property_id,
            guest=NormalizedGuest(first_name=guest.first_name, last_name=guest.last_name,
                                  phone_e164=guest.phone_e164,
                                  email=guest.email, loyalty_tier=guest.loyalty_tier, vip=guest.vip,
                                  pms_profile_id=guest.pms_profile_id),
            stay=NormalizedStay(pms_reservation_id=stay.pms_reservation_id or stay.id,
                                room_number=stay.room_number,
                                room_type=stay.room_type, rate_code=stay.rate_code, status=status,
                                arrival_date=stay.arrival_date, departure_date=stay.departure_date,
                                adults=stay.adults,
                                children=stay.children, is_return_guest=stay.is_return_guest,
                                stay_count=stay.stay_count),
            raw={"mock": True, "emitted_at": clock.now().isoformat()})

    def event_for(self, db: Session, property_id: str, stay_id: str, type: str) -> PmsEvent | None:
        stay = db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
        if stay is None:
            return None
        status = StayStatus.checked_in if type == "stay.checked_in" else StayStatus.checked_out
        return self._event(stay, db.get(Guest, stay.guest_id), type, status)

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]:
        rows = db.scalars(select(Stay).where(Stay.property_id == property_id,
                                              Stay.status == StayStatus.checked_in)).all()
        return [self._event(s, db.get(Guest, s.guest_id), "stay.checked_in",
                            StayStatus.checked_in).stay for s in rows]

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]:
        today = clock.now().date()
        arrival = db.scalar(select(Stay).where(Stay.property_id == property_id,
                                               Stay.status == StayStatus.reserved,
                                               Stay.arrival_date <= today)
                            .order_by(Stay.arrival_date, Stay.id).limit(1))
        departure = db.scalar(select(Stay).where(Stay.property_id == property_id,
                                                 Stay.status == StayStatus.checked_in,
                                                 Stay.departure_date <= today)
                              .order_by(Stay.departure_date, Stay.id).limit(1))
        self._flip = not self._flip
        order = [arrival, departure] if self._flip else [departure, arrival]
        for stay in order:
            if stay is None:
                continue
            guest = db.get(Guest, stay.guest_id)
            if stay.status == StayStatus.reserved:
                return [self._event(stay, guest, "stay.checked_in", StayStatus.checked_in)]
            return [self._event(stay, guest, "stay.checked_out", StayStatus.checked_out)]
        return []
