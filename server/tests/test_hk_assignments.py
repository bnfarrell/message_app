"""Assignment (spec §3.4, §4.2)."""
import pytest
from sqlalchemy import func, select

from app.domain import hk_assignments, hk_rooms
from app.errors import TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Notification, RoomEvent, UserAccount
from app.schemas.enums import (
    HkAssignmentStatus,
    HkStatus,
    Role,
    RoomEventType,
    UserStatus,
)
from tests.hk_helpers import add_user, make_rooms


def _dirty(rooms):
    for r in rooms.values():
        r.hk_status = HkStatus.dirty
    return rooms


def _count(db, model, *where):
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_bulk_assign_appends_in_order_and_notifies_once(database, fx, events):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102", "103")))
        out = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                    [r.id for r in rooms.values()], fx.housekeeper_a.id)
        assert [a.sequence for a in out] == [1, 2, 3]
        assert all(a.status is HkAssignmentStatus.assigned for a in out)
        notes = db.scalars(select(Notification).where(
            Notification.user_id == fx.housekeeper_a.id)).all()
        assert [n.title for n in notes] == ["3 rooms assigned to you"]
        ids = {r.id for r in rooms.values()}
    hk = [e for e in events if e.type == hk_rooms.EVENT]
    assert len(hk) == 1 and set(hk[0].payload["ids"]) == ids


def test_assigning_again_to_the_same_housekeeper_is_a_no_op(database, fx):
    """Review focus 2: a double-submit must not duplicate the row or the notification."""
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                              fx.housekeeper_a.id)
        hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                              fx.housekeeper_a.id)
        assert _count(db, HousekeepingAssignment) == 1
        assert _count(db, Notification, Notification.user_id == fx.housekeeper_a.id) == 1


def test_reassign_moves_the_row_and_records_it(database, fx):
    with database.session() as db:
        rosa = add_user(db, fx.property_a.id, "rosa@hvh.test", Role.dept_staff,
                        fx.dept_housekeeping.id, "Rosa", "Lima")
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (first,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                         fx.housekeeper_a.id)
        (moved,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                         rosa)
        assert moved.id == first.id and moved.housekeeper_user_id == rosa
        ev = db.scalar(select(RoomEvent).where(RoomEvent.type == RoomEventType.reassigned))
        assert (ev.from_value, ev.to_value) == (fx.housekeeper_a.id, rosa)


def test_a_room_awaiting_inspection_cannot_be_reassigned(database, fx):
    with database.session() as db:
        rosa = add_user(db, fx.property_a.id, "rosa@hvh.test", Role.dept_staff,
                        fx.dept_housekeeping.id, "Rosa", "Lima")
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (a,) = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                     fx.housekeeper_a.id)
        a.status = HkAssignmentStatus.done
        room.hk_status = HkStatus.in_progress  # still assignable, so the done row is what blocks
        with pytest.raises(TransitionError, match="awaiting inspection"):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id], rosa)


def test_only_dirty_or_in_progress_rooms_can_be_assigned(database, fx):
    with database.session() as db:
        room = make_rooms(db, fx.property_a.id, codes=("101",))["101"]  # inspected
        with pytest.raises(TransitionError):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.housekeeper_a.id)


def test_engineering_staff_cannot_receive_housekeeping_rooms(database, fx):
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        with pytest.raises(ValidationFailed):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.engineer_a.id)


def test_cannot_assign_to_a_disabled_housekeeper(database, fx):
    """Review focus 3."""
    with database.session() as db:
        db.get(UserAccount, fx.housekeeper_a.id).status = UserStatus.disabled
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        with pytest.raises(ValidationFailed):
            hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id, [room.id],
                                  fx.housekeeper_a.id)


def test_unassign_refuses_a_started_room_and_keeps_history_otherwise(database, fx):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102")))
        a1, a2 = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                       [rooms["101"].id, rooms["102"].id], fx.housekeeper_a.id)
        a2.status = HkAssignmentStatus.in_progress
        with pytest.raises(TransitionError):
            hk_assignments.unassign(db, fx.property_a.id, fx.supervisor_a.id, a2.id)
        hk_assignments.unassign(db, fx.property_a.id, fx.supervisor_a.id, a1.id)
        assert db.get(HousekeepingAssignment, a1.id) is None
        types = set(db.scalars(select(RoomEvent.type).where(
            RoomEvent.room_id == rooms["101"].id)))
        assert types == {RoomEventType.assigned, RoomEventType.unassigned}


def test_reorder_sets_the_sequence_and_rejects_foreign_ids(database, fx):
    with database.session() as db:
        rooms = _dirty(make_rooms(db, fx.property_a.id, codes=("101", "102", "103")))
        a = hk_assignments.assign(db, fx.property_a.id, fx.supervisor_a.id,
                                  [r.id for r in rooms.values()], fx.housekeeper_a.id)
        out = hk_assignments.reorder(db, fx.property_a.id, fx.supervisor_a.id,
                                     fx.housekeeper_a.id, [a[2].id, a[0].id, a[1].id])
        assert [(x.id, x.sequence) for x in out] == [(a[2].id, 1), (a[0].id, 2), (a[1].id, 3)]
        with pytest.raises(ValidationFailed):
            hk_assignments.reorder(db, fx.property_a.id, fx.supervisor_a.id,
                                   fx.housekeeper_a.id, [a[0].id, a[1].id])


def test_a_manager_from_another_department_can_assign(database, fx):
    with database.session() as db:
        room = _dirty(make_rooms(db, fx.property_a.id, codes=("101",)))["101"]
        (a,) = hk_assignments.assign(db, fx.property_a.id, fx.manager_a.id, [room.id],
                                     fx.housekeeper_a.id)
        assert a.housekeeper_user_id == fx.housekeeper_a.id
