"""`housekeeping.tick` (spec §3.1): every 5 minutes, deliberately stateless.

It never records "I rolled today"; it asks each room whether it ought to be dirty and is not.
The before-midnight test makes it idempotent: a room it dirtied now has status_changed_at =
now, and a room cleaned today has status_changed_at after midnight, so neither rolls again.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import hk_rooms, pm_cycles
from app.models import Property
from app.schemas.enums import HkOccupancy, HkServiceType, HkStatus

_ROLLS = {HkOccupancy.stayover: HkServiceType.stayover,
          HkOccupancy.departure: HkServiceType.departure}


def tick(db: Session) -> dict[str, int]:
    created = dirtied = 0
    for prop in db.scalars(select(Property).order_by(Property.id)).all():
        new = hk_rooms.ensure_rooms(db, prop.id)
        changed = [r.id for r in new]
        created += len(new)
        midnight = pm_cycles.local_day_start_utc(prop, pm_cycles.local_today(prop))
        occupancy = hk_rooms.occupancy_by_code(db, prop)
        for room, unit in hk_rooms.active_rooms(db, prop.id):
            if room.hk_status not in (HkStatus.clean, HkStatus.inspected):
                continue
            occ = occupancy.get(unit.code, hk_rooms.VACANT)
            if occ.checked_out_at and occ.checked_out_at > room.status_changed_at:
                hk_rooms.dirty_for_departure(db, room, "Guest checked out")
            elif room.status_changed_at < midnight and occ.kind in _ROLLS:
                room.service_type = _ROLLS[occ.kind]
                hk_rooms.set_status(db, room, HkStatus.dirty, None, comment="Daily roll")
            else:
                continue
            changed.append(room.id)
            dirtied += 1
        hk_rooms.emit(db, prop.id, changed)
    return {"created": created, "dirtied": dirtied}
