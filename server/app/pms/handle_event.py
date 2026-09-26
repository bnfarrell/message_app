from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, guests, hk_rooms
from app.models import PmsEvent as PmsEventRow
from app.models import Stay
from app.pms.base import PmsEvent
from app.realtime.broadcast import queue_event
from app.schemas.enums import StayStatus


def _find_stay(db: Session, property_id: str, pms_reservation_id: str) -> Stay | None:
    return db.scalar(select(Stay).where(Stay.property_id == property_id,
                                        Stay.pms_reservation_id == pms_reservation_id))


def handle_event(db: Session, event: PmsEvent, integration_key: str = "mock") -> bool:
    """Idempotent on (property_id, integration_key, external_id, event_type). False for a dup.

    The key is per-property because `Stay` is unique on (property_id, pms_reservation_id): most
    PMSs number reservations per property, so two properties may legitimately send the same
    external_id and a global key would swallow the second one as a duplicate of the first.

    Duplicate suppression is enforced at the DB level via
    UniqueConstraint(property_id, integration_key, external_id, event_type) on pms_event, not just
    the SELECT below — a concurrent replay races the SELECT, so the insert is retried inside a
    nested transaction and an IntegrityError is treated as "already handled" (same pattern as
    guests.find_or_create_by_phone).
    """
    dup = db.scalar(select(PmsEventRow.id).where(PmsEventRow.property_id == event.property_id,
                                                 PmsEventRow.integration_key == integration_key,
                                                 PmsEventRow.external_id == event.external_id,
                                                 PmsEventRow.event_type == event.type))
    if dup:
        return False
    try:
        with db.begin_nested():
            row = PmsEventRow(property_id=event.property_id, integration_key=integration_key,
                              external_id=event.external_id,
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

    stay = _find_stay(db, event.property_id, event.stay.pms_reservation_id)
    if stay is None:
        # Race-safe for the same reason as the pms_event insert above: Stay carries
        # UniqueConstraint(property_id, pms_reservation_id) (uq_stay_property_reservation), so a
        # second event for the same reservation racing past our SELECT (e.g. reservation.created
        # and stay.checked_in, which differ by event_type and so both pass the dedup check above)
        # hits the constraint instead of creating a duplicate Stay row.
        try:
            with db.begin_nested():
                stay = Stay(guest_id=guest.id, property_id=event.property_id,
                           pms_reservation_id=event.stay.pms_reservation_id,
                           arrival_date=event.stay.arrival_date,
                           departure_date=event.stay.departure_date)
                db.add(stay)
                db.flush()
        except IntegrityError:
            stay = _find_stay(db, event.property_id, event.stay.pms_reservation_id)
    for attr in ("room_number", "room_type", "rate_code", "status", "arrival_date",
                 "departure_date", "adults", "children", "is_return_guest", "stay_count"):
        setattr(stay, attr, getattr(event.stay, attr))
    stay.raw_pms = event.raw
    now = clock.now()
    if event.type == "stay.checked_out":
        stay.status = StayStatus.checked_out
    # The attribute loop above copies `status` straight off the event, so keying the timestamp
    # off event.type alone left a stay with status=checked_in and actual_checkin_at NULL whenever
    # the status arrived on some other event type (e.g. a room_changed carrying the current
    # status). stays.find_in_house_for_guest orders on actual_checkin_at, where NULL sorts first
    # on PostgreSQL — so that row became "the" in-house stay and attached the wrong room number
    # to an inbound SMS. Write status and its timestamp together instead.
    if (stay.status in (StayStatus.checked_in, StayStatus.checked_out)
            and stay.actual_checkin_at is None):
        stay.actual_checkin_at = now
    if stay.status == StayStatus.checked_out and stay.actual_checkout_at is None:
        stay.actual_checkout_at = now
    db.flush()
    if event.type == "stay.checked_out":
        # Spec §3.2: a 9am checkout appears on the housekeeping board at 9am, not at the next
        # tick. check-in and room change do not touch status — occupancy is derived.
        hk_rooms.dirty_on_checkout(db, event.property_id, stay.room_number)
    row.processed_at = now
    audit.record(db, event.property_id, None, f"pms.{event.type}", "stay", stay.id,
                 after={"external_id": event.external_id, "room": stay.room_number})
    queue_event(db, event.property_id, "stay.updated",
                {"stayId": stay.id, "guestId": guest.id, "status": stay.status.value})
    return True
