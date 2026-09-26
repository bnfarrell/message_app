"""The housekeeping transition table (spec §3.3). Anything not implemented here is a 409."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app import clock
from app.auth.permissions import has_capability
from app.domain import hk_assignments, hk_rooms, notifications
from app.errors import Conflict, Forbidden, TransitionError, ValidationFailed
from app.models import HousekeepingAssignment, Room
from app.schemas.enums import (
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    Role,
    RoomEventType,
)

OUT = (HkStatus.out_of_order, HkStatus.out_of_service)


def _clean_note(note: str | None) -> str | None:
    return (note or "").strip() or None


def _code(db: Session, room: Room) -> str:
    return hk_rooms.unit_of(db, room).code


def mark_dirty(db: Session, property_id: str, actor_id: str, room_id: str,
               note: str | None) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if room.hk_status == HkStatus.clean:
        raise TransitionError("This room is awaiting inspection — a supervisor must fail the "
                              "inspection to send it back")
    if room.hk_status != HkStatus.inspected:
        raise TransitionError(f"A room that is {room.hk_status.value} cannot be marked dirty")
    room.service_type = hk_rooms.service_type_for(hk_rooms.occupancy_of(db, room))
    hk_rooms.set_status(db, room, HkStatus.dirty, actor_id,
                        event_type=RoomEventType.marked_dirty, comment=_clean_note(note))
    hk_rooms.emit(db, property_id, [room.id])
    return room


def set_rush(db: Session, property_id: str, actor_id: str, room_id: str, on: bool) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if on:
        if room.hk_status not in (HkStatus.dirty, HkStatus.in_progress):
            raise TransitionError("Only a room waiting to be cleaned can be rushed")
        if room.rush:
            return room
        room.rush = True
        hk_rooms.record(db, room, RoomEventType.rush_set, actor_id)
        notifications.notify_users(db, property_id, hk_rooms.hk_supervisors(db, property_id),
                                   "hk.rush", f"Rush: Room {_code(db, room)}",
                                   entity_type="room", entity_id=room.id)
    else:
        if not room.rush:
            return room
        room.rush = False
        hk_rooms.record(db, room, RoomEventType.rush_cleared, actor_id)
    hk_rooms.emit(db, property_id, [room.id])
    return room


def set_room_status(db: Session, property_id: str, actor_id: str, room_id: str,
                    status: HkStatus, note: str | None) -> Room:
    room = hk_rooms.get(db, property_id, room_id)
    if status in OUT:
        if room.hk_status == status:
            raise TransitionError(f"The room is already {status.value}")
        current = hk_rooms.open_assignment(db, room, hk_rooms.today(db, property_id))
        if current:
            hk_rooms.delete_assignment(db, current)
        room.rush = False
    elif status == HkStatus.dirty:
        if room.hk_status not in OUT:
            raise TransitionError("Only an out-of-order or out-of-service room can be put back "
                                  "in service; use Mark dirty otherwise")
        room.service_type = hk_rooms.service_type_for(hk_rooms.occupancy_of(db, room))
    else:
        raise ValidationFailed("Unsupported status", details={"status": "unsupported"})
    hk_rooms.set_status(db, room, status, actor_id, comment=_clean_note(note))
    hk_rooms.emit(db, property_id, [room.id])
    return room


def require_owner_or_manager(a: HousekeepingAssignment, actor_id: str, role: Role) -> None:
    if a.housekeeper_user_id != actor_id and not has_capability(role, "manage_housekeeping"):
        raise Forbidden("That room is assigned to someone else")


def _begin(db: Session, room: Room, a: HousekeepingAssignment, actor_id: str) -> None:
    a.status = HkAssignmentStatus.in_progress
    a.started_at = clock.now()
    hk_rooms.set_status(db, room, HkStatus.in_progress, actor_id,
                        event_type=RoomEventType.started, assignment_id=a.id)
    hk_rooms.emit(db, room.property_id, [room.id])


def start(db: Session, property_id: str, actor_id: str, role: Role,
          assignment_id: str) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    require_owner_or_manager(a, actor_id, role)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.assigned or room.hk_status != HkStatus.dirty:
        raise TransitionError("Only an assigned, dirty room can be started")
    _begin(db, room, a, actor_id)
    return a


def complete(db: Session, property_id: str, actor_id: str, role: Role,
             assignment_id: str) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    require_owner_or_manager(a, actor_id, role)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.in_progress or room.hk_status != HkStatus.in_progress:
        raise TransitionError("Only a room in progress can be marked ready")
    now = clock.now()
    a.status = HkAssignmentStatus.done
    a.completed_at = now
    room.last_cleaned_at = now
    hk_rooms.set_status(db, room, HkStatus.clean, actor_id,
                        event_type=RoomEventType.completed, assignment_id=a.id)
    notifications.notify_users(db, property_id, hk_rooms.hk_supervisors(db, property_id),
                               "hk.ready_for_inspection",
                               f"Ready for inspection: Room {_code(db, room)}",
                               entity_type="room", entity_id=room.id)
    hk_rooms.emit(db, property_id, [room.id])
    return a


def inspect(db: Session, property_id: str, actor_id: str, assignment_id: str,
            result: Literal["pass", "fail"], note: str | None) -> HousekeepingAssignment:
    a = hk_assignments.get(db, property_id, assignment_id)
    room = db.get(Room, a.room_id)
    if a.status != HkAssignmentStatus.done or room.hk_status != HkStatus.clean:
        raise TransitionError("Only a room awaiting inspection can be inspected")
    note = _clean_note(note)
    if result == "fail" and not note:
        raise ValidationFailed("A note is required when failing an inspection",
                               details={"note": "required"})
    now = clock.now()
    a.inspected_by_user_id = actor_id
    a.inspected_at = now
    a.inspection_note = note
    if result == "pass":
        a.status = HkAssignmentStatus.passed
        room.rush = False
        room.last_inspected_at = now
        hk_rooms.set_status(db, room, HkStatus.inspected, actor_id,
                            event_type=RoomEventType.inspection_passed, assignment_id=a.id,
                            comment=note)
    else:
        # The same row goes back (spec §2.2): one row tells the room's whole day.
        a.status = HkAssignmentStatus.assigned
        a.fail_count += 1
        a.started_at = None
        a.completed_at = None
        hk_rooms.set_status(db, room, HkStatus.dirty, actor_id,
                            event_type=RoomEventType.inspection_failed, assignment_id=a.id,
                            comment=note)
        notifications.notify_users(db, property_id, [a.housekeeper_user_id],
                                   "hk.inspection_failed",
                                   f"Room {_code(db, room)} failed inspection", body=note[:140],
                                   entity_type="room", entity_id=room.id)
    hk_rooms.emit(db, property_id, [room.id])
    return a


def self_assign_start(db: Session, property_id: str, actor_id: str,
                      room_id: str) -> HousekeepingAssignment:
    """Supervisors clean rooms too (spec §3.3): assign to self and start in one step."""
    room = hk_rooms.get(db, property_id, room_id)
    if room.hk_status != HkStatus.dirty:
        raise TransitionError("Only a dirty room can be started")
    day = hk_rooms.today(db, property_id)
    if hk_rooms.open_assignment(db, room, day):
        raise Conflict("This room is already assigned — start it from the assignment")
    a = HousekeepingAssignment(
        property_id=property_id, room_id=room.id, housekeeper_user_id=actor_id, shift_date=day,
        sequence=hk_rooms.next_sequence(db, property_id, actor_id, day),
        type=room.service_type or HkServiceType.departure, status=HkAssignmentStatus.assigned,
        fail_count=0)
    db.add(a)
    db.flush()
    hk_rooms.record(db, room, RoomEventType.assigned, actor_id, assignment_id=a.id,
                    to_value=actor_id)
    _begin(db, room, a, actor_id)
    return a
