"""Assignment (spec §3.4): a supervisor gives today's dirty rooms to housekeepers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import hk_rooms, notifications
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import Department, HousekeepingAssignment, PropertyMembership, Room, UserAccount
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkServiceType,
    HkStatus,
    RoomEventType,
    UserStatus,
)

ASSIGNABLE = (HkStatus.dirty, HkStatus.in_progress)
MOVABLE = (HkAssignmentStatus.assigned, HkAssignmentStatus.in_progress)


def get(db: Session, property_id: str, assignment_id: str) -> HousekeepingAssignment:
    a = db.scalar(select(HousekeepingAssignment).where(
        HousekeepingAssignment.id == assignment_id,
        HousekeepingAssignment.property_id == property_id))
    if a is None:
        raise NotFound("Assignment not found")
    return a


def _is_housekeeper(db: Session, property_id: str, user_id: str) -> bool:
    """Role alone is not enough: an engineering dept_staff must not get rooms (spec §4.2)."""
    return db.scalar(
        select(PropertyMembership.id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.user_id == user_id,
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)) is not None


def assign(db: Session, property_id: str, actor_id: str, room_ids: list[str],
           housekeeper_id: str) -> list[HousekeepingAssignment]:
    if not _is_housekeeper(db, property_id, housekeeper_id):
        raise ValidationFailed("Rooms can only be assigned to active housekeeping staff",
                               details={"housekeeperUserId": "not_housekeeping"})
    day = hk_rooms.today(db, property_id)
    rooms = [hk_rooms.get(db, property_id, rid) for rid in dict.fromkeys(room_ids)]
    # Validate everything before touching anything, so a bad room in a batch of twelve
    # leaves the other eleven as they were.
    plan: list[tuple[Room, HousekeepingAssignment | None]] = []
    for room in rooms:
        if room.hk_status not in ASSIGNABLE:
            code = hk_rooms.unit_of(db, room).code
            raise TransitionError(f"Room {code} is {room.hk_status.value} and cannot be assigned")
        current = hk_rooms.open_assignment(db, room, day)
        if current and current.housekeeper_user_id != housekeeper_id \
                and current.status not in MOVABLE:
            code = hk_rooms.unit_of(db, room).code
            raise TransitionError(f"Room {code} is awaiting inspection and cannot be reassigned")
        plan.append((room, current))

    seq = hk_rooms.next_sequence(db, property_id, housekeeper_id, day)
    out: list[HousekeepingAssignment] = []
    changed: list[str] = []
    for room, current in plan:
        if current and current.housekeeper_user_id == housekeeper_id:
            out.append(current)
            continue
        if current:
            previous = current.housekeeper_user_id
            current.housekeeper_user_id = housekeeper_id
            current.sequence = seq
            hk_rooms.record(db, room, RoomEventType.reassigned, actor_id,
                            assignment_id=current.id, from_value=previous,
                            to_value=housekeeper_id)
            a = current
        else:
            a = HousekeepingAssignment(
                property_id=property_id, room_id=room.id, housekeeper_user_id=housekeeper_id,
                shift_date=day, sequence=seq, type=room.service_type or HkServiceType.departure,
                status=HkAssignmentStatus.assigned, fail_count=0)
            db.add(a)
            db.flush()
            hk_rooms.record(db, room, RoomEventType.assigned, actor_id, assignment_id=a.id,
                            to_value=housekeeper_id)
        seq += 1
        out.append(a)
        changed.append(room.id)
    if changed:
        n = len(changed)
        notifications.notify_users(db, property_id, [housekeeper_id], "hk.assigned",
                                   f"{n} room{'' if n == 1 else 's'} assigned to you",
                                   entity_type="room", entity_id=changed[0] if n == 1 else None)
    hk_rooms.emit(db, property_id, changed)
    return out


def unassign(db: Session, property_id: str, actor_id: str, assignment_id: str) -> Room:
    a = get(db, property_id, assignment_id)
    if a.status != HkAssignmentStatus.assigned:
        raise TransitionError("A started room cannot be unassigned")
    room = db.get(Room, a.room_id)
    previous = a.housekeeper_user_id
    hk_rooms.delete_assignment(db, a)
    hk_rooms.record(db, room, RoomEventType.unassigned, actor_id, from_value=previous)
    hk_rooms.emit(db, property_id, [room.id])
    return room


def reorder(db: Session, property_id: str, actor_id: str, housekeeper_id: str,
            assignment_ids: list[str]) -> list[HousekeepingAssignment]:
    """The ids must be exactly that housekeeper's open assignments for today."""
    day = hk_rooms.today(db, property_id)
    current = {a.id: a for a in db.scalars(select(HousekeepingAssignment).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.housekeeper_user_id == housekeeper_id,
        HousekeepingAssignment.shift_date == day,
        HousekeepingAssignment.status != HkAssignmentStatus.passed))}
    if len(assignment_ids) != len(current) or set(assignment_ids) != set(current):
        raise ValidationFailed("List every one of that housekeeper's rooms for today, once",
                               details={"assignmentIds": "mismatch"})
    ordered = [current[i] for i in assignment_ids]
    for position, a in enumerate(ordered, start=1):
        a.sequence = position
    db.flush()
    hk_rooms.emit(db, property_id, [a.room_id for a in ordered])
    return ordered
