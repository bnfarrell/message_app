from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.schemas.enums import StayStatus

EventType = Literal["reservation.created", "stay.checked_in", "stay.checked_out", "stay.room_changed"]


@dataclass
class NormalizedGuest:
    first_name: str | None
    last_name: str | None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool = False
    pms_profile_id: str | None = None


@dataclass
class NormalizedStay:
    pms_reservation_id: str
    room_number: str | None
    room_type: str | None
    rate_code: str | None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int = 1
    children: int = 0
    is_return_guest: bool = False
    stay_count: int = 1


@dataclass
class PmsEvent:
    external_id: str
    type: EventType
    property_id: str
    guest: NormalizedGuest
    stay: NormalizedStay
    raw: dict = field(default_factory=dict)


class PmsAdapter(Protocol):
    integration_key: str

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]: ...

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]: ...
