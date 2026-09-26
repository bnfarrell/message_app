"""Shift windows (checklists spec §3.1), on the same configurable boundaries as the hotel log's
shift_for. Boundaries are read from settings on every call, so an edit applies immediately."""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Property
from app.schemas.enums import Shift

DEFAULT_SHIFT_BOUNDARIES = {"am": "07:00", "pm": "15:00", "overnight": "23:00"}


def boundary(raw: dict, key: str) -> time:
    value = raw.get(key) or DEFAULT_SHIFT_BOUNDARIES[key]
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute))


def _raw(prop: Property) -> dict:
    return (prop.settings or {}).get("shift_boundaries") or {}


def _at(prop: Property, day: date, t: time) -> datetime:
    return datetime.combine(day, t, tzinfo=ZoneInfo(prop.timezone)).astimezone(UTC)


def shift_window(prop: Property, day: date, shift: Shift) -> tuple[datetime, datetime]:
    """`day` is the date the shift starts; overnight ends at the next morning's am boundary."""
    raw = _raw(prop)
    am, pm, overnight = boundary(raw, "am"), boundary(raw, "pm"), boundary(raw, "overnight")
    if shift is Shift.am:
        return _at(prop, day, am), _at(prop, day, pm)
    if shift is Shift.pm:
        return _at(prop, day, pm), _at(prop, day, overnight)
    return _at(prop, day, overnight), _at(prop, day + timedelta(days=1), am)


def current_shift(prop: Property, at: datetime) -> tuple[date, Shift]:
    """The shift `at` falls in, and the date that shift started (02:00 → yesterday's overnight)."""
    from app.domain.log import shift_for  # local import: log imports `boundary` from here
    shift = shift_for(prop, at)
    local = at.astimezone(ZoneInfo(prop.timezone))
    day = local.date()
    if shift is Shift.overnight and local.time() < boundary(_raw(prop), "am"):
        day -= timedelta(days=1)
    return day, shift
