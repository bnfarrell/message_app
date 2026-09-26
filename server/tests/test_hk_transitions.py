"""The transition table (spec §3.3), as a matrix: every (from status, action) not in ALLOWED
must be a 409, so a new status can never silently gain a transition."""
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.domain import hk_assignments, hk_rooms, hk_transitions
from app.errors import Conflict, Forbidden, TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Notification, RoomEvent
from app.schemas.enums import (
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    Role,
    RoomEventType,
    StayStatus,
)
from tests.hk_helpers import add_hk_supervisor, add_stay, local_today, make_rooms

STATES = ["inspected", "dirty", "in_progress", "clean", "out_of_order", "out_of_service"]
ACTIONS = ["mark_dirty", "start", "complete", "pass", "fail", "ooo", "oos", "back"]
ALLOWED = {
    ("inspected", "mark_dirty"), ("inspected", "ooo"), ("inspected", "oos"),
    ("dirty", "start"), ("dirty", "ooo"), ("dirty", "oos"),
    ("in_progress", "complete"), ("in_progress", "ooo"), ("in_progress", "oos"),
    ("clean", "pass"), ("clean", "fail"), ("clean", "ooo"), ("clean", "oos"),
    ("out_of_order", "back"), ("out_of_order", "oos"),
    ("out_of_service", "back"), ("out_of_service", "ooo"),
}
RESULT = {"mark_dirty": HkStatus.dirty, "start": HkStatus.in_progress,
          "complete": HkStatus.clean, "pass": HkStatus.inspected, "fail": HkStatus.dirty,
          "ooo": HkStatus.out_of_order, "oos": HkStatus.out_of_service, "back": HkStatus.dirty}


def _build(db, fx, state):
    """A room in `state`, reached through the real domain calls."""
    pid, sup, hk = fx.property_a.id, fx.supervisor_a.id, fx.housekeeper_a.id
    room = make_rooms(db, pid, codes=("101",))["101"]
    if state in ("out_of_order", "out_of_service"):
        hk_transitions.set_room_status(db, pid, sup, room.id, HkStatus(state), None)
        return room
    if state == "inspected":
        return room
    hk_transitions.mark_dirty(db, pid, sup, room.id, None)
    (a,) = hk_assignments.assign(db, pid, sup, [room.id], hk)
    if state in ("in_progress", "clean"):
        hk_transitions.start(db, pid, hk, Role.dept_staff, a.id)
    if state == "clean":
        hk_transitions.complete(db, pid, hk, Role.dept_staff, a.id)
    return room


def _assignment_for(db, fx, room):
    """The room's latest assignment, or a bare `assigned` row so the room-status guard (not a
    missing id) is what gets exercised."""
    a = db.scalar(select(HousekeepingAssignment).where(HousekeepingAssignment.room_id == room.id)
                  .order_by(HousekeepingAssignment.created_at.desc()))
    if a is None:
        a = HousekeepingAssignment(property_id=room.property_id, room_id=room.id,
                                   housekeeper_user_id=fx.housekeeper_a.id,
                                   shift_date=local_today(db, room.property_id), sequence=1,
                                   type=HkServiceType.departure,
                                   status=HkAssignmentStatus.assigned)
        db.add(a)
        db.flush()
    return a


def _act(db, fx, room, action):
    pid, sup = fx.property_a.id, fx.supervisor_a.id
    if action == "mark_dirty":
        return hk_transitions.mark_dirty(db, pid, sup, room.id, None)
    if action in ("ooo", "oos", "back"):
        status = {"ooo": HkStatus.out_of_order, "oos": HkStatus.out_of_service,
                  "back": HkStatus.dirty}[action]
        return hk_transitions.set_room_status(db, pid, sup, room.id, status, None)
    a = _assignment_for(db, fx, room)
    if action == "start":
        return hk_transitions.start(db, pid, sup, Role.supervisor, a.id)
    if action == "complete":
        return hk_transitions.complete(db, pid, sup, Role.supervisor, a.id)
    return hk_transitions.inspect(db, pid, sup, a.id, action, "Streaky mirror.")


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("action", ACTIONS)
def test_transition_matrix(database, fx, state, action):
    with database.session() as db:
        room = _build(db, fx, state)
        assert room.hk_status is HkStatus(state)
        if (state, action) in ALLOWED:
            _act(db, fx, room, action)
            assert room.hk_status is RESULT[action]
        else:
            with pytest.raises(TransitionError):
                _act(db, fx, room, action)


def test_mark_dirty_on_a_room_awaiting_inspection_points_at_the_fail_path(database, fx):
    with database.session() as db:
        room = _build(db, fx, "clean")
        with pytest.raises(TransitionError, match="supervisor must fail"):
            hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)


def test_mark_dirty_sets_touch_up_when_occupied(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        today = local_today(db, pid)
        room = make_rooms(db, pid, codes=("101",))["101"]
        add_stay(db, pid, "101", status=StayStatus.checked_in, arrival=today,
                 departure=today + timedelta(days=2))
        hk_transitions.mark_dirty(db, pid, fx.agent_a.id, room.id, "Spill")
        assert room.service_type is HkServiceType.touch_up
        ev = db.scalar(select(RoomEvent).where(RoomEvent.type == RoomEventType.marked_dirty))
        assert ev.comment == "Spill"


def test_fail_requires_a_non_blank_note(database, fx):
    """Review focus 4: whitespace is not a note."""
    with database.session() as db:
        room = _build(db, fx, "clean")
        a = _assignment_for(db, fx, room)
        for note in (None, "", "   "):
            with pytest.raises(ValidationFailed):
                hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "fail",
                                       note)


def test_fail_returns_the_same_row_and_tells_the_housekeeper(database, fx):
    with database.session() as db:
        room = _build(db, fx, "clean")
        a = _assignment_for(db, fx, room)
        hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "fail",
                               "Hair in the sink.")
        assert db.scalar(select(func.count()).select_from(HousekeepingAssignment)) == 1
        assert (a.status, a.fail_count, a.inspection_note) == (
            HkAssignmentStatus.assigned, 1, "Hair in the sink.")
        assert a.started_at is None and a.completed_at is None
        note = db.scalar(select(Notification).where(
            Notification.user_id == fx.housekeeper_a.id,
            Notification.type == "hk.inspection_failed"))
        assert note.body == "Hair in the sink."


def test_pass_clears_rush_and_stamps_the_inspection(database, fx):
    with database.session() as db:
        room = _build(db, fx, "in_progress")
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        a = _assignment_for(db, fx, room)
        hk_transitions.complete(db, fx.property_a.id, fx.housekeeper_a.id, Role.dept_staff, a.id)
        hk_transitions.inspect(db, fx.property_a.id, fx.supervisor_a.id, a.id, "pass", None)
        assert room.rush is False and room.last_inspected_at is not None
        assert a.status is HkAssignmentStatus.passed


def test_rush_only_on_rooms_waiting_to_be_cleaned_and_notifies_hk_supervisors(database, fx):
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
        with pytest.raises(TransitionError):
            hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)
        hk_transitions.set_rush(db, fx.property_a.id, fx.agent_a.id, room.id, True)  # no-op
        titles = db.scalars(select(Notification.title).where(Notification.user_id == grace)).all()
        assert titles == ["Rush: Room 101"]


def test_complete_notifies_hk_supervisors(database, fx):
    with database.session() as db:
        grace = add_hk_supervisor(db, fx)
        _build(db, fx, "clean")
        assert db.scalar(select(Notification.type).where(Notification.user_id == grace)) \
            == "hk.ready_for_inspection"


def test_out_of_order_removes_the_open_assignment(database, fx):
    with database.session() as db:
        room = _build(db, fx, "in_progress")
        hk_transitions.set_room_status(db, fx.property_a.id, fx.supervisor_a.id, room.id,
                                       HkStatus.out_of_order, "AC leak")
        assert db.scalar(select(func.count()).select_from(HousekeepingAssignment)) == 0
        assert room.rush is False


def test_a_housekeeper_cannot_start_someone_elses_room(database, fx):
    with database.session() as db:
        room = _build(db, fx, "dirty")
        a = _assignment_for(db, fx, room)
        with pytest.raises(Forbidden):
            hk_transitions.start(db, fx.property_a.id, fx.engineer_a.id, Role.dept_staff, a.id)
        hk_transitions.start(db, fx.property_a.id, fx.supervisor_a.id, Role.supervisor, a.id)


def test_supervisor_self_assign_start(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
        a = hk_transitions.self_assign_start(db, fx.property_a.id, fx.supervisor_a.id, room.id)
        assert (a.housekeeper_user_id, a.status) == (fx.supervisor_a.id,
                                                     HkAssignmentStatus.in_progress)
        assert room.hk_status is HkStatus.in_progress


def test_self_assign_start_refuses_an_assigned_room(database, fx):
    with database.session() as db:
        room = _build(db, fx, "dirty")
        with pytest.raises(Conflict):
            hk_transitions.self_assign_start(db, fx.property_a.id, fx.supervisor_a.id, room.id)


def test_each_mutation_emits_exactly_one_event(database, fx, events):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]
    events.clear()
    with database.session() as db:
        hk_transitions.mark_dirty(db, fx.property_a.id, fx.agent_a.id, room.id, None)
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and hk[0].payload == {"ids": [room.id]}
