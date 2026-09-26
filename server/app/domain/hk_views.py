"""Housekeeping read models (spec §4.1). Everything the three screens render comes from here."""
from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain import hk_photos, hk_rooms, pm_cycles
from app.models import (
    Department,
    HousekeepingAssignment,
    MaintainableUnit,
    Property,
    PropertyMembership,
    Room,
    RoomEvent,
    UserAccount,
)
from app.schemas.enums import (
    DepartmentType,
    HkAssignmentStatus,
    HkStatus,
    RoomEventType,
    UserStatus,
)
from app.schemas.housekeeping import (
    HkAssignmentOut,
    HkBoardOut,
    HkEventOut,
    HkHousekeeperOut,
    HkInspectionRowOut,
    HkPhotoOut,
    HkRoomDetailOut,
    HkRoomOut,
    HkSummaryOut,
)

HISTORY = 30
_PERSON_EVENTS = (RoomEventType.assigned, RoomEventType.reassigned, RoomEventType.unassigned)
_DONE = (HkAssignmentStatus.done, HkAssignmentStatus.passed)


def _pick(db: Session, property_id: str, rooms: dict[str, Room],
          day: date) -> dict[str, HousekeepingAssignment]:
    """The assignment each room displays (plan clarification 5): today's open one; else, for a
    `clean` room, its latest `done` from any day; else today's latest passed one."""
    if not rooms:
        return {}
    rows = db.scalars(
        select(HousekeepingAssignment)
        .where(HousekeepingAssignment.property_id == property_id,
               HousekeepingAssignment.room_id.in_(list(rooms)),
               or_(HousekeepingAssignment.shift_date == day,
                   HousekeepingAssignment.status == HkAssignmentStatus.done))
        .order_by(HousekeepingAssignment.shift_date.desc(),
                  HousekeepingAssignment.created_at.desc(), HousekeepingAssignment.id.desc()))
    picked: dict[str, HousekeepingAssignment] = {}
    for a in rows:
        if a.shift_date != day and rooms[a.room_id].hk_status != HkStatus.clean:
            continue  # a stale done row never shows on a room that has moved on
        current = picked.get(a.room_id)
        if current is None or (current.status == HkAssignmentStatus.passed
                               and a.status != HkAssignmentStatus.passed):
            picked[a.room_id] = a
    return picked


def _names_for_assignments(db: Session, rows) -> dict[str, str]:
    return hk_rooms.names_for(db, [a.housekeeper_user_id for a in rows]
                              + [a.inspected_by_user_id for a in rows])


def _assignment_out(a: HousekeepingAssignment, names: dict[str, str]) -> HkAssignmentOut:
    return HkAssignmentOut(
        id=a.id, room_id=a.room_id, housekeeper_user_id=a.housekeeper_user_id,
        housekeeper_name=names.get(a.housekeeper_user_id), shift_date=a.shift_date,
        sequence=a.sequence, type=a.type, status=a.status, started_at=a.started_at,
        completed_at=a.completed_at, inspected_by_name=names.get(a.inspected_by_user_id or ""),
        inspected_at=a.inspected_at, inspection_note=a.inspection_note, fail_count=a.fail_count)


def assignment_out(db: Session, a: HousekeepingAssignment) -> HkAssignmentOut:
    return _assignment_out(a, _names_for_assignments(db, [a]))


def _room_out(room: Room, unit: MaintainableUnit, occ: hk_rooms.Occupancy,
              a: HousekeepingAssignment | None, names: dict[str, str]) -> HkRoomOut:
    return HkRoomOut(
        id=room.id, unit_id=unit.id, code=unit.code, floor=unit.floor, room_type=unit.room_type,
        hk_status=room.hk_status, service_type=room.service_type, rush=room.rush,
        occupancy=occ.kind, guest_name=occ.guest_name, departure_date=occ.departure_date,
        status_changed_at=room.status_changed_at, last_cleaned_at=room.last_cleaned_at,
        last_inspected_at=room.last_inspected_at, notes=room.notes,
        assignment=_assignment_out(a, names) if a else None)


def _rows(
    db: Session, property_id: str, pairs: list[tuple[Room, MaintainableUnit]] | None = None,
) -> tuple[date, list[HkRoomOut]]:
    prop = db.get(Property, property_id)
    day = pm_cycles.local_today(prop)
    pairs = hk_rooms.active_rooms(db, property_id) if pairs is None else pairs
    occupancy = hk_rooms.occupancy_by_code(db, prop)
    picked = _pick(db, property_id, {r.id: r for r, _ in pairs}, day)
    names = _names_for_assignments(db, list(picked.values()))
    return day, [_room_out(r, u, occupancy.get(u.code, hk_rooms.VACANT), picked.get(r.id), names)
                 for r, u in pairs]


def _housekeepers(db: Session, property_id: str, day: date) -> list[HkHousekeeperOut]:
    people = db.execute(
        select(UserAccount.id, UserAccount.first_name, UserAccount.last_name)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .join(Department, Department.id == PropertyMembership.department_id)
        .where(PropertyMembership.property_id == property_id,
               Department.type == DepartmentType.housekeeping,
               UserAccount.status == UserStatus.active)
        .order_by(UserAccount.first_name, UserAccount.last_name, UserAccount.id)).all()
    today = db.scalars(select(HousekeepingAssignment).where(
        HousekeepingAssignment.property_id == property_id,
        HousekeepingAssignment.shift_date == day)).all()
    assigned = Counter(a.housekeeper_user_id for a in today)
    done = Counter(a.housekeeper_user_id for a in today if a.status in _DONE)
    return [HkHousekeeperOut(user_id=uid, name=f"{first} {last}", assigned=assigned[uid],
                             done=done[uid]) for uid, first, last in people]


def board(db: Session, property_id: str) -> HkBoardOut:
    day, rooms = _rows(db, property_id)
    count = Counter(r.hk_status for r in rooms)
    summary = HkSummaryOut(
        dirty=count[HkStatus.dirty], in_progress=count[HkStatus.in_progress],
        awaiting_inspection=count[HkStatus.clean], inspected=count[HkStatus.inspected],
        out_of_order=count[HkStatus.out_of_order] + count[HkStatus.out_of_service])
    return HkBoardOut(rooms=rooms, summary=summary,
                      housekeepers=_housekeepers(db, property_id, day))


def my_rooms(db: Session, property_id: str, user_id: str) -> list[HkRoomOut]:
    day, rooms = _rows(db, property_id)
    mine = [r for r in rooms if r.assignment and r.assignment.housekeeper_user_id == user_id
            and r.assignment.shift_date == day]
    return sorted(mine, key=lambda r: (not r.rush, r.assignment.sequence))


def room_row(db: Session, property_id: str, room_id: str) -> HkRoomOut:
    room = hk_rooms.get(db, property_id, room_id)
    _, (row,) = _rows(db, property_id, [(room, hk_rooms.unit_of(db, room))])
    return row


def _photos_out(property_id: str, assignment_id: str, photos) -> list[HkPhotoOut]:
    return [HkPhotoOut(id=p.id, content_type=p.content_type, byte_size=p.byte_size,
                       url=hk_photos.photo_url(property_id, assignment_id, p.id),
                       created_at=p.created_at) for p in photos]


def room_detail(db: Session, property_id: str, room_id: str) -> HkRoomDetailOut:
    row = room_row(db, property_id, room_id)
    events = db.scalars(select(RoomEvent).where(RoomEvent.room_id == row.id)
                        .order_by(RoomEvent.created_at.desc(), RoomEvent.id.desc())
                        .limit(HISTORY)).all()
    people = [e.user_id for e in events] + [v for e in events if e.type in _PERSON_EVENTS
                                             for v in (e.from_value, e.to_value)]
    names = hk_rooms.names_for(db, people)

    def person(e: RoomEvent, value: str | None) -> str | None:
        return names.get(value or "", value) if e.type in _PERSON_EVENTS else value

    photos = []
    if row.assignment:
        photos = _photos_out(property_id, row.assignment.id,
                             hk_photos.photos_for(db, [row.assignment.id])[row.assignment.id])
    return HkRoomDetailOut(
        room=row, photos=photos,
        events=[HkEventOut(id=e.id, type=e.type, from_value=person(e, e.from_value),
                           to_value=person(e, e.to_value), comment=e.comment,
                           user_name=names.get(e.user_id or ""), created_at=e.created_at)
                for e in events])


def inspections(db: Session, property_id: str) -> list[HkInspectionRowOut]:
    """Rooms awaiting inspection, oldest finished first, with who cleaned them and photos."""
    _, rooms = _rows(db, property_id)
    waiting = [r for r in rooms if r.hk_status == HkStatus.clean and r.assignment
               and r.assignment.status == HkAssignmentStatus.done]
    photos = hk_photos.photos_for(db, [r.assignment.id for r in waiting])
    waiting.sort(key=lambda r: (r.assignment.completed_at or r.status_changed_at, r.code))
    return [HkInspectionRowOut(room=r, photos=_photos_out(property_id, r.assignment.id,
                                                          photos[r.assignment.id]))
            for r in waiting]
