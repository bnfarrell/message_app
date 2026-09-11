from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, guests
from app.models import PmsEvent as PmsEventRow
from app.models import Stay
from app.pms.base import PmsEvent
from app.realtime.broadcast import queue_event
from app.schemas.enums import StayStatus


def handle_event(db: Session, event: PmsEvent, integration_key: str = "mock") -> bool:
    """Idempotent on (integration_key, external_id, event_type). Returns False for a duplicate.

    Duplicate suppression is enforced at the DB level via
    UniqueConstraint(integration_key, external_id, event_type) on pms_event, not just the SELECT
    below — a concurrent replay races the SELECT, so the insert is retried inside a nested
    transaction and an IntegrityError is treated as "already handled" (same pattern as
    guests.find_or_create_by_phone).
    """
    dup = db.scalar(select(PmsEventRow.id).where(PmsEventRow.integration_key == integration_key,
                                                 PmsEventRow.external_id == event.external_id,
                                                 PmsEventRow.event_type == event.type))
    if dup:
        return False
    try:
        with db.begin_nested():
            row = PmsEventRow(integration_key=integration_key, external_id=event.external_id,
                              event_type=event.type, payload=event.raw)
            db.add(row)
            db.flush()
    except IntegrityError:
        return False

    guest, created = guests.find_or_create_by_phone(db, event.property_id, event.guest.phone_e164)
    for attr in ("first_name", "last_name", "email", "loyalty_tier", "vip", "pms_profile_id"):
        value = getattr(event.guest, attr)
        if value is not None:
            setattr(guest, attr, value)

    stay = db.scalar(select(Stay).where(Stay.property_id == event.property_id,
                                        Stay.pms_reservation_id == event.stay.pms_reservation_id))
    if stay is None:
        stay = Stay(guest_id=guest.id, property_id=event.property_id, pms_reservation_id=event.stay.pms_reservation_id,
                    arrival_date=event.stay.arrival_date, departure_date=event.stay.departure_date)
        db.add(stay)
    for attr in ("room_number", "room_type", "rate_code", "status", "arrival_date", "departure_date", "adults",
                 "children", "is_return_guest", "stay_count"):
        setattr(stay, attr, getattr(event.stay, attr))
    stay.raw_pms = event.raw
    now = clock.now()
    if event.type == "stay.checked_in" and stay.actual_checkin_at is None:
        stay.actual_checkin_at = now
    if event.type == "stay.checked_out":
        stay.status = StayStatus.checked_out
        stay.actual_checkout_at = stay.actual_checkout_at or now
    db.flush()
    row.processed_at = now
    audit.record(db, event.property_id, None, f"pms.{event.type}", "stay", stay.id,
                 after={"external_id": event.external_id, "room": stay.room_number})
    queue_event(db, event.property_id, "stay.updated", {"stayId": stay.id, "guestId": guest.id, "status": stay.status.value})
    return True
