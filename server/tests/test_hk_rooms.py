"""hk_rooms (spec §2.1, §2.3, §5)."""
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.domain import hk_rooms
from app.models import HousekeepingAssignment, MaintainableUnit, Property, RoomEvent
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    PmUnitKind,
    RoomEventType,
    StayStatus,
)
from tests.hk_helpers import add_stay, local_today, make_rooms


def test_ensure_rooms_covers_active_guest_rooms_only_and_is_idempotent(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        db.add_all([
            MaintainableUnit(property_id=pid, kind=PmUnitKind.guest_room, code="101", name="R"),
            MaintainableUnit(property_id=pid, kind=PmUnitKind.guest_room, code="102", name="R",
                             active=False),
            MaintainableUnit(property_id=pid, kind=PmUnitKind.equipment, code="BOILER-1",
                             name="Boiler"),
        ])
        db.flush()
        created = hk_rooms.ensure_rooms(db, pid)
        assert len(created) == 1
        assert created[0].hk_status is HkStatus.inspected
        assert hk_rooms.ensure_rooms(db, pid) == []


def test_active_rooms_puts_floorless_units_last(database, fx):
    """Review focus 1: SQLite sorts NULL first on ASC, PostgreSQL last — pinned either way."""
    with database.session() as db:
        make_rooms(db, fx.property_a.id, codes=("PH", "301", "101"))
        codes = [u.code for _, u in hk_rooms.active_rooms(db, fx.property_a.id)]
        assert codes == ["101", "301", "PH"]


def test_occupancy_is_derived_from_stays(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        make_rooms(db, pid, codes=("101", "102", "103", "104", "105", "106"))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today + timedelta(days=2), first="Stella", last="Over")
        add_stay(db, pid, "102", status=StayStatus.checked_in, arrival=today - timedelta(days=2),
                 departure=today)
        add_stay(db, pid, "103", status=StayStatus.checked_in, arrival=today - timedelta(days=4),
                 departure=today - timedelta(days=1))  # overdue: still a departure
        add_stay(db, pid, "104", status=StayStatus.reserved, arrival=today,
                 departure=today + timedelta(days=1))
        add_stay(db, pid, "105", status=StayStatus.checked_out, arrival=today - timedelta(days=2),
                 departure=today, checked_out_at=clock.now() - timedelta(hours=1))
        # 106: a checked-in guest beats a reservation arriving today
        add_stay(db, pid, "106", status=StayStatus.reserved, arrival=today,
                 departure=today + timedelta(days=2))
        add_stay(db, pid, "106", status=StayStatus.checked_in, arrival=today - timedelta(days=1),
                 departure=today)
        occ = hk_rooms.occupancy_by_code(db, db.get(Property, pid))
        assert occ["101"].kind is HkOccupancy.stayover
        assert occ["101"].guest_name == "Stella Over"
        assert occ["102"].kind is HkOccupancy.departure
        assert occ["103"].kind is HkOccupancy.departure
        assert occ["104"].kind is HkOccupancy.arrival
        assert occ["105"].kind is HkOccupancy.vacant
        assert occ["105"].checked_out_at is not None
        assert occ["106"].kind is HkOccupancy.departure
        assert "999" not in occ  # no stay = vacant, by absence


def test_service_type_for_occupied_is_touch_up_else_departure():
    assert hk_rooms.service_type_for(hk_rooms.Occupancy(HkOccupancy.stayover)) \
        is HkServiceType.touch_up
    assert hk_rooms.service_type_for(hk_rooms.VACANT) is HkServiceType.departure


def test_set_status_stamps_time_and_records_the_event(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        hk_rooms.set_status(db, room, HkStatus.out_of_order, fx.supervisor_a.id,
                            comment="Leak")
        assert room.hk_status is HkStatus.out_of_order
        assert room.status_changed_at == clock.now()
        ev = db.scalar(select(RoomEvent).where(RoomEvent.room_id == room.id))
        assert (ev.type, ev.from_value, ev.to_value, ev.comment) == (
            RoomEventType.status_changed, "inspected", "out_of_order", "Leak")


def test_emit_dedups_and_skips_empty(database, fx, events):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        hk_rooms.emit(db, fx.property_a.id, [room.id, room.id])
        hk_rooms.emit(db, fx.property_a.id, [])
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and hk[0].payload == {"ids": [room.id]}


def test_delete_assignment_keeps_the_history(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id)["101"]
        a = HousekeepingAssignment(property_id=fx.property_a.id, room_id=room.id,
                                   housekeeper_user_id=fx.housekeeper_a.id,
                                   shift_date=local_today(db, fx.property_a.id), sequence=1,
                                   type=HkServiceType.departure,
                                   status=HkAssignmentStatus.assigned)
        db.add(a)
        db.flush()
        hk_rooms.record(db, room, RoomEventType.assigned, None, assignment_id=a.id)
        hk_rooms.delete_assignment(db, a)
        ev = db.scalar(select(RoomEvent).where(RoomEvent.room_id == room.id))
        assert ev.assignment_id is None
        assert db.scalar(select(HousekeepingAssignment)) is None


def test_hk_supervisors_are_housekeeping_supervisors_and_managers(database, fx):
    from tests.hk_helpers import add_hk_supervisor
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        # fx.supervisor_a is Engineering and must not be paged about a dirty room
        assert hk_rooms.hk_supervisors(db, fx.property_a.id) == [grace]
