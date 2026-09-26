"""housekeeping.tick (spec §3.1) and the PMS checkout hook (spec §3.2)."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app import clock
from app.domain import hk_rooms, hk_tick
from app.models import HousekeepingAssignment, MaintainableUnit, Room, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent
from app.pms.handle_event import handle_event
from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all
from app.schemas.enums import (
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    PmUnitKind,
    StayStatus,
)
from tests.hk_helpers import add_stay, local_today, make_rooms, rooms_by_code


def _at(room: Room, when: datetime) -> None:
    room.status_changed_at = when


def test_tick_is_registered_every_five_minutes():
    load_all()
    assert "housekeeping.tick" in HANDLERS and jobs.RECURRING["housekeeping.tick"] == 300


def test_stayover_and_departure_rooms_go_dirty_after_local_midnight(database, fx, events):
    # FROZEN is 2026-09-10 12:00 UTC = 08:00 in New York; HVH midnight = 04:00 UTC.
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "104"))
        yesterday_evening = datetime(2026, 9, 9, 22, 0, tzinfo=UTC)
        for r in rooms.values():
            _at(r, yesterday_evening)
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        add_stay(db, pid, "102", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today)
        # 103 vacant; 104 cleaned at 07:00 local today and occupied — stays clean
        add_stay(db, pid, "104", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        _at(rooms["104"], datetime(2026, 9, 10, 11, 0, tzinfo=UTC))
        result = hk_tick.tick(db)
        assert result["dirtied"] == 2
        assert (rooms["101"].hk_status, rooms["101"].service_type) == (
            HkStatus.dirty, HkServiceType.stayover)
        assert (rooms["102"].hk_status, rooms["102"].service_type) == (
            HkStatus.dirty, HkServiceType.departure)
        assert rooms["103"].hk_status is HkStatus.inspected
        assert rooms["104"].hk_status is HkStatus.inspected
        ids = {rooms["101"].id, rooms["102"].id}
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and set(hk[0].payload["ids"]) == ids


def test_tick_is_idempotent_and_a_noop_tick_is_silent(database, fx, events):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 9, 22, 0, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 1
    events.clear()
    with database.session() as db:
        assert hk_tick.tick(db) == {"created": 0, "dirtied": 0}
    assert [e for e in events if e.type == hk_rooms.EVENT] == []


def test_dirty_in_progress_and_out_of_order_rooms_are_untouched(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "104"))
        for code, status in (("101", HkStatus.dirty), ("102", HkStatus.in_progress),
                             ("103", HkStatus.out_of_order), ("104", HkStatus.out_of_service)):
            rooms[code].hk_status = status
            _at(rooms[code], datetime(2026, 9, 9, 22, 0, tzinfo=UTC))
            add_stay(db, pid, code, status=StayStatus.checked_in, arrival=today,
                     departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 0
        assert [r.hk_status for r in rooms.values()] == [
            HkStatus.dirty, HkStatus.in_progress, HkStatus.out_of_order,
            HkStatus.out_of_service]


def test_midnight_is_property_local_not_utc(database, fx):
    """At 02:00 UTC on Sep 11 it is still 22:00 on Sep 10 in New York: a room last changed at
    01:00 local on Sep 10 was changed *today* and must not roll, although a UTC midnight has
    passed since."""
    clock.freeze(datetime(2026, 9, 11, 2, 0, tzinfo=UTC))
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        assert today == date(2026, 9, 10)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 10, 5, 0, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        assert hk_tick.tick(db)["dirtied"] == 0


def test_each_property_rolls_at_its_own_midnight(database, fx):
    """04:30 UTC: 00:30 in New York (HVH has rolled), 23:30 the day before in Chicago (LSI has
    not). Both rooms last changed at 03:00 UTC."""
    clock.freeze(datetime(2026, 9, 10, 4, 30, tzinfo=UTC))
    with database.session() as db:
        changed = datetime(2026, 9, 10, 3, 0, tzinfo=UTC)
        for prop in (fx.property_a, fx.property_b):
            today = local_today(db, prop.id)
            room = make_rooms(db, prop.id, codes=("501",))["501"]
            _at(room, changed)
            add_stay(db, prop.id, "501", status=StayStatus.checked_in,
                     arrival=today - timedelta(days=1), departure=today + timedelta(days=2))
        hk_tick.tick(db)
        assert rooms_by_code(db, fx.property_a.id)["501"].hk_status is HkStatus.dirty
        assert rooms_by_code(db, fx.property_b.id)["501"].hk_status is HkStatus.inspected


def test_midnight_after_the_dst_change_uses_the_new_offset(database, fx):
    """2026-11-01 New York leaves EDT. On Nov 2, local midnight is 05:00 UTC, not 04:00: a room
    changed at 04:30 UTC (23:30 EST on Nov 1) must roll. A fixed -4 offset would skip it."""
    clock.freeze(datetime(2026, 11, 2, 5, 30, tzinfo=UTC))
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        assert today == date(2026, 11, 2)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 11, 2, 4, 30, tzinfo=UTC))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=1))
        assert hk_tick.tick(db)["dirtied"] == 1


def test_a_checkout_the_hook_missed_is_caught_by_the_tick(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        _at(room, datetime(2026, 9, 10, 5, 0, tzinfo=UTC))  # after midnight, before checkout
        add_stay(db, pid, "101", status=StayStatus.checked_out,
                 arrival=today - timedelta(days=2), departure=today,
                 checked_out_at=datetime(2026, 9, 10, 11, 0, tzinfo=UTC))
        assert hk_tick.tick(db)["dirtied"] == 1
        assert room.service_type is HkServiceType.departure


def test_tick_creates_rooms_for_new_guest_room_units(database, fx):
    with database.session() as db:
        db.add(MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="777", name="Room 777", floor=7))
        db.flush()
        assert hk_tick.tick(db)["created"] == 1
        assert "777" in rooms_by_code(db, fx.property_a.id)


def _checkout_event(fx, room_number: str) -> PmsEvent:
    """RES-412 is the fixture's in-house stay (Sarah Chen, +15551234567)."""
    return PmsEvent(
        external_id=f"evt-{room_number}", type="stay.checked_out",
        property_id=fx.property_a.id,
        guest=NormalizedGuest(first_name="Sarah", last_name="Chen", phone_e164="+15551234567"),
        stay=NormalizedStay(pms_reservation_id="RES-412", room_number=room_number,
                            room_type="King", rate_code=None, status=StayStatus.checked_out,
                            arrival_date=date(2026, 9, 7), departure_date=date(2026, 9, 10)))


def test_pms_checkout_dirties_the_room_immediately(database, fx):
    with database.session() as db:
        make_rooms(db, fx.property_a.id, codes=("412",))
        assert handle_event(db, _checkout_event(fx, "412"))
        room = rooms_by_code(db, fx.property_a.id)["412"]
        assert (room.hk_status, room.service_type) == (HkStatus.dirty, HkServiceType.departure)


def test_checkout_for_an_unknown_room_number_is_ignored(database, fx):
    """Review focus 5."""
    with database.session() as db:
        assert handle_event(db, _checkout_event(fx, "9999"))
        stay = db.scalar(select(Stay).where(Stay.pms_reservation_id == "RES-412"))
        assert stay.status is StayStatus.checked_out


def test_checkout_after_a_same_day_clean_reopens_the_assignment(database, fx):
    """A stayover cleaned today, then the guest checks out before inspection: the room goes
    dirty for departure and the `done` assignment reopens to `assigned` so it can be
    reassigned or started (controller ruling)."""
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("412",))["412"]
        room.hk_status = HkStatus.dirty
        today = local_today(db, fx.property_a.id)
        assignment = HousekeepingAssignment(
            property_id=fx.property_a.id, room_id=room.id,
            housekeeper_user_id=fx.housekeeper_a.id, shift_date=today, sequence=1,
            type=HkServiceType.stayover, status=HkAssignmentStatus.done,
            started_at=clock.now(), completed_at=clock.now())
        db.add(assignment)
        room.hk_status = HkStatus.clean
        db.flush()
        assert handle_event(db, _checkout_event(fx, "412"))
        assert room.hk_status is HkStatus.dirty
        assert room.service_type is HkServiceType.departure
        assert assignment.status is HkAssignmentStatus.assigned
        assert assignment.started_at is None
        assert assignment.completed_at is None
        assert assignment.fail_count == 0
