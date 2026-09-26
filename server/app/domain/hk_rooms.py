"""Housekeeping rooms: the row, derived occupancy, the audit trail and the single realtime
emission point (spec §2.1, §2.3, §5). Every other hk_* module builds on these."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import Session

from app import clock
from app.domain import pm_cycles
from app.errors import NotFound
from app.models import (
    Department,
    Guest,
    HousekeepingAssignment,
    HousekeepingPhoto,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    RoomEvent,
    Stay,
    UserAccount,
)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkOccupancy,
    HkServiceType,
    HkStatus,
    PmUnitKind,
    Role,
    RoomEventType,
    StayStatus,
    UserStatus,
)

EVENT = "housekeeping.rooms.changed"


def emit(db: Session, property_id: str, room_ids: list[str]) -> None:
    """The one place housekeeping calls queue_event (spec §5). Ids only, always a list, so a
    bulk action sends one event and no guest data goes property-wide."""
    ids = list(dict.fromkeys(room_ids))
    if ids:
        queue_event(db, property_id, EVENT, {"ids": ids})


def ensure_rooms(db: Session, property_id: str) -> list[Room]:
    """A room row for every active guest-room unit that lacks one — the same rule the 0008
    backfill applied, so a later CSV import just works. Returns the rows it created."""
    existing = set(db.scalars(select(Room.unit_id).where(Room.property_id == property_id)))
    units = db.scalars(select(MaintainableUnit).where(
        MaintainableUnit.property_id == property_id,
        MaintainableUnit.kind == PmUnitKind.guest_room,
        MaintainableUnit.active.is_(True))).all()
    now = clock.now()
    created = [Room(property_id=property_id, unit_id=u.id, hk_status=HkStatus.inspected,
                    rush=False, status_changed_at=now)
               for u in units if u.id not in existing]
    db.add_all(created)
    db.flush()
    return created


def get(db: Session, property_id: str, room_id: str) -> Room:
    room = db.scalar(select(Room).where(Room.id == room_id, Room.property_id == property_id))
    if room is None:
        raise NotFound("Room not found")
    return room


def unit_of(db: Session, room: Room) -> MaintainableUnit:
    return db.get(MaintainableUnit, room.unit_id)


def active_rooms(db: Session, property_id: str) -> list[tuple[Room, MaintainableUnit]]:
    """The board's rooms. A deactivated unit keeps its row and history but leaves the board;
    reactivating it brings the same row back (spec §7)."""
    return [(r, u) for r, u in db.execute(
        select(Room, MaintainableUnit)
        .join(MaintainableUnit, MaintainableUnit.id == Room.unit_id)
        .where(Room.property_id == property_id, MaintainableUnit.active.is_(True),
               MaintainableUnit.kind == PmUnitKind.guest_room)
        # NULLS LAST pinned: SQLite sorts NULL first on ASC, PostgreSQL last.
        .order_by(MaintainableUnit.floor.asc().nulls_last(), MaintainableUnit.code)).all()]


@dataclass(frozen=True)
class Occupancy:
    kind: HkOccupancy
    guest_name: str | None = None
    departure_date: date | None = None
    # The latest checkout today, tracked apart from `kind` so the tick can dirty a room whose
    # checkout the PMS hook missed even when an arrival now occupies the `kind` slot.
    checked_out_at: datetime | None = None


VACANT = Occupancy(HkOccupancy.vacant)


def occupancy_by_code(db: Session, prop: Property) -> dict[str, Occupancy]:
    """Derived from `stay` on `stay.room_number == unit.code`, never stored (spec §2.1).
    A checked-in stay beats a reservation arriving today; checked-in with a departure date of
    today or earlier is a departure. Rooms with no relevant stay are absent (= VACANT)."""
    today = pm_cycles.local_today(prop)
    midnight = pm_cycles.local_day_start_utc(prop, today)
    rows = db.execute(
        select(Stay, Guest).join(Guest, Guest.id == Stay.guest_id)
        .where(Stay.property_id == prop.id, Stay.room_number.is_not(None),
               or_(Stay.status == StayStatus.checked_in,
                   and_(Stay.status == StayStatus.reserved, Stay.arrival_date == today),
                   and_(Stay.status == StayStatus.checked_out,
                        Stay.actual_checkout_at >= midnight)))).all()
    best: dict[str, tuple[int, Occupancy]] = {}
    checkouts: dict[str, datetime] = {}
    for stay, guest in rows:
        code = stay.room_number
        if stay.status == StayStatus.checked_out:
            if code not in checkouts or stay.actual_checkout_at > checkouts[code]:
                checkouts[code] = stay.actual_checkout_at
            continue
        name = " ".join(p for p in (guest.first_name, guest.last_name) if p) or None
        if stay.status == StayStatus.checked_in:
            kind = (HkOccupancy.departure if stay.departure_date <= today
                    else HkOccupancy.stayover)
            rank = 2
        else:
            kind, rank = HkOccupancy.arrival, 1
        if code not in best or rank > best[code][0]:
            best[code] = (rank, Occupancy(kind, name, stay.departure_date))
    return {code: replace(best.get(code, (0, VACANT))[1], checked_out_at=checkouts.get(code))
            for code in set(best) | set(checkouts)}


def occupancy_of(db: Session, room: Room) -> Occupancy:
    prop = db.get(Property, room.property_id)
    return occupancy_by_code(db, prop).get(unit_of(db, room).code, VACANT)


def service_type_for(occ: Occupancy) -> HkServiceType:
    """Spec §3.3: touch_up if someone is in the room, else a departure clean."""
    if occ.kind in (HkOccupancy.stayover, HkOccupancy.departure):
        return HkServiceType.touch_up
    return HkServiceType.departure


def record(db: Session, room: Room, type: RoomEventType, user_id: str | None, *,
           assignment_id: str | None = None, from_value: str | None = None,
           to_value: str | None = None, comment: str | None = None) -> RoomEvent:
    ev = RoomEvent(room_id=room.id, assignment_id=assignment_id, property_id=room.property_id,
                   user_id=user_id, type=type, from_value=from_value, to_value=to_value,
                   comment=comment)
    db.add(ev)
    db.flush()
    return ev


def set_status(db: Session, room: Room, status: HkStatus, user_id: str | None, *,
               event_type: RoomEventType = RoomEventType.status_changed,
               assignment_id: str | None = None, comment: str | None = None) -> None:
    old = room.hk_status
    room.hk_status = status
    room.status_changed_at = clock.now()
    record(db, room, event_type, user_id, assignment_id=assignment_id, from_value=old.value,
           to_value=status.value, comment=comment)


def today(db: Session, property_id: str) -> date:
    return pm_cycles.local_today(db.get(Property, property_id))


def open_assignment(db: Session, room: Room, day: date) -> HousekeepingAssignment | None:
    """At most one non-passed assignment per room per shift date (spec §2.2)."""
    return db.scalar(select(HousekeepingAssignment).where(
        HousekeepingAssignment.room_id == room.id, HousekeepingAssignment.shift_date == day,
        HousekeepingAssignment.status != HkAssignmentStatus.passed))


def next_sequence(db: Session, property_id: str, user_id: str, day: date) -> int:
    top = db.scalar(select(func.max(HousekeepingAssignment.sequence)).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.housekeeper_user_id == user_id,
        HousekeepingAssignment.shift_date == day))
    return (top or 0) + 1


def delete_assignment(db: Session, assignment: HousekeepingAssignment) -> None:
    """FKs are enforced, so detach the history and drop the photos first. The events keep
    their room_id, so the room's story survives."""
    db.execute(update(RoomEvent).where(RoomEvent.assignment_id == assignment.id)
               .values(assignment_id=None))
    db.execute(delete(HousekeepingPhoto).where(HousekeepingPhoto.assignment_id == assignment.id))
    db.delete(assignment)
    db.flush()


def hk_supervisors(db: Session, property_id: str) -> list[str]:
    """Who hears about rush and ready-for-inspection: active supervisors and managers in a
    housekeeping-type department."""
    return list(db.scalars(
        select(PropertyMembership.user_id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .join(UserAccount, UserAccount.id == PropertyMembership.user_id)
        .where(PropertyMembership.property_id == property_id,
               PropertyMembership.role.in_([Role.supervisor, Role.manager]),
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)
        .order_by(PropertyMembership.user_id)).all())


def names_for(db: Session, user_ids: list[str | None]) -> dict[str, str]:
    """Display names for ids read off this property's own rows."""
    ids = [u for u in user_ids if u]
    if not ids:
        return {}
    rows = db.execute(select(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
                      .where(UserAccount.id.in_(ids))).all()
    return {uid: f"{first} {last}" for uid, first, last in rows}


def dirty_on_checkout(db: Session, property_id: str, room_number: str | None) -> None:
    """PMS `stay.checked_out` (spec §3.2): the room appears dirty at checkout, not at the next
    tick. A room number with no unit is ignored — the stay itself is still processed."""
    if not room_number:
        return
    room = db.scalar(
        select(Room).join(MaintainableUnit, MaintainableUnit.id == Room.unit_id)
        .where(Room.property_id == property_id, MaintainableUnit.code == room_number,
               MaintainableUnit.kind == PmUnitKind.guest_room,
               MaintainableUnit.active.is_(True)))
    if room is None or room.hk_status not in (HkStatus.clean, HkStatus.inspected):
        return
    room.service_type = HkServiceType.departure
    set_status(db, room, HkStatus.dirty, None, comment="Guest checked out")
    emit(db, property_id, [room.id])
