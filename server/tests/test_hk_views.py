"""Read models (spec §4.1, §4.3; plan clarifications 2 and 5)."""
from datetime import timedelta

from app import clock
from app.domain import hk_assignments, hk_photos, hk_transitions, hk_views
from app.models import HousekeepingAssignment, MaintainableUnit
from app.schemas.enums import (
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    Role,
    StayStatus,
)
from tests.hk_helpers import add_stay, local_today, make_rooms

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"


def _dirty_and_assign(db, fx, codes):
    rooms = make_rooms(db, fx.property_a.id, codes=codes)
    for r in rooms.values():
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.supervisor_a.id, r.id, None)
    out = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                [r.id for r in rooms.values()], fx.housekeeper_a.id)
    return rooms, out


def test_board_rows_occupancy_summary_and_housekeepers(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        rooms = make_rooms(db, pid, codes=("101", "102", "103", "PH"))
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2), first="Sarah", last="Chen")
        hk_transitions.mark_dirty(db, pid, fx.agent_a.id, rooms["101"].id, None)
        hk_transitions.set_room_status(db, pid, fx.supervisor_a.id, rooms["103"].id,
                                       HkStatus.out_of_order, "Leak")
        hk_assignments.assign(db, pid, fx.supervisor_a.id, [rooms["101"].id],
                              fx.housekeeper_a.id)
        out = hk_views.board(db, pid)
        assert [r.code for r in out.rooms] == ["101", "102", "103", "PH"]
        r101 = out.rooms[0]
        assert (r101.occupancy, r101.guest_name) == (HkOccupancy.stayover, "Sarah Chen")
        assert r101.assignment.housekeeper_name == "Hana Keeper"
        assert out.rooms[3].floor is None
        s = out.summary
        assert (s.dirty, s.in_progress, s.awaiting_inspection, s.inspected, s.out_of_order) \
            == (1, 0, 0, 2, 1)
        assert sum((s.dirty, s.in_progress, s.awaiting_inspection, s.inspected,
                    s.out_of_order)) == len(out.rooms)
        assert [(h.name, h.assigned, h.done) for h in out.housekeepers] == [
            ("Hana Keeper", 1, 0)]


def test_my_rooms_is_rush_first_then_sequence_and_only_mine(database, fx):
    with database.session() as db:
        rooms, assigned = _dirty_and_assign(db, fx, ("101", "102", "103"))
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["103"].id, True)
        mine = hk_views.my_rooms(db, fx.property_a.id, fx.housekeeper_a.id)
        assert [r.code for r in mine] == ["103", "101", "102"]
        assert hk_views.my_rooms(db, fx.property_a.id, fx.engineer_a.id) == []


def test_room_detail_history_names_people_and_caps_at_thirty(database, fx):
    with database.session() as db:
        rooms, (a,) = _dirty_and_assign(db, fx, ("101",))
        for _ in range(20):
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["101"].id, True)
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, rooms["101"].id, False)
        detail = hk_views.room_detail(db, fx.property_a.id, rooms["101"].id)
        assert len(detail.events) == 30
        assert all(e.user_name for e in detail.events)


def test_assignment_events_show_names_not_ids(database, fx):
    with database.session() as db:
        rooms, _ = _dirty_and_assign(db, fx, ("101",))
        detail = hk_views.room_detail(db, fx.property_a.id, rooms["101"].id)
        ev = next(e for e in detail.events if e.type.value == "assigned")
        assert ev.to_value == "Hana Keeper"


def test_inspection_queue_is_oldest_first_with_photos(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        rooms, (a1, a2) = _dirty_and_assign(db, fx, ("101", "102"))
        for a in (a2, a1):  # 102 finishes first
            hk_transitions.start(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id)
            if a is a2:
                hk_photos.attach(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id, data=PNG)
            hk_transitions.complete(db, pid, fx.housekeeper_a.id, Role.dept_staff, a.id)
            clock.freeze(clock.now() + timedelta(minutes=20))
        queue = hk_views.inspections(db, pid)
        assert [row.room.code for row in queue] == ["102", "101"]
        assert len(queue[0].photos) == 1 and queue[0].photos[0].url.endswith(
            f"/photos/{queue[0].photos[0].id}")


def test_deactivated_unit_leaves_the_board_and_comes_back_as_the_same_row(database, fx):
    with database.session() as db:
        rooms = make_rooms(db, fx.property_a.id, codes=("101",))
        unit = db.get(MaintainableUnit, rooms["101"].unit_id)
        unit.active = False
        db.flush()
        assert hk_views.board(db, fx.property_a.id).rooms == []
        unit.active = True
        db.flush()
        assert hk_views.board(db, fx.property_a.id).rooms[0].id == rooms["101"].id


def test_yesterdays_uninspected_clean_shows_but_a_stale_done_never_does(database, fx):
    """Plan clarification 5."""
    with database.session() as db:
        pid = fx.property_a.id
        yesterday = local_today(db, pid) - timedelta(days=1)
        rooms = make_rooms(db, pid, codes=("101", "102"))
        for code, status in (("101", HkStatus.clean), ("102", HkStatus.dirty)):
            rooms[code].hk_status = status
            db.add(HousekeepingAssignment(
                property_id=pid, room_id=rooms[code].id, housekeeper_user_id=fx.housekeeper_a.id,
                shift_date=yesterday, sequence=1, type=HkServiceType.departure,
                status=HkAssignmentStatus.done, completed_at=clock.now() - timedelta(hours=14)))
        db.flush()
        board = {r.code: r for r in hk_views.board(db, pid).rooms}
        assert board["101"].assignment is not None
        assert board["102"].assignment is None
        assert [row.room.code for row in hk_views.inspections(db, pid)] == ["101"]
