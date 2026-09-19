from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.models import Property
from app.schemas.enums import Shift

# Spec §3.3. Overridable per property via settings["shift_boundaries"].
DEFAULT_SHIFT_BOUNDARIES = {"am": "07:00", "pm": "15:00", "overnight": "23:00"}


def _boundary(raw: dict, key: str) -> time:
    value = raw.get(key) or DEFAULT_SHIFT_BOUNDARIES[key]
    hour, _, minute = value.partition(":")
    return time(int(hour), int(minute))


def shift_for(prop: Property, at: datetime) -> Shift:
    """Which shift `at` falls in, on the property's own clock.

    Computed once at creation and then stored, so editing the boundaries later does not
    retroactively relabel history (spec §3.3). Overnight is the window that wraps midnight,
    which is why this is a three-way comparison rather than a sorted bisect.
    """
    if at.tzinfo is None:
        raise ValueError("shift_for requires an aware datetime")
    raw = (prop.settings or {}).get("shift_boundaries") or {}
    am, pm, overnight = (_boundary(raw, k) for k in ("am", "pm", "overnight"))
    local = at.astimezone(ZoneInfo(prop.timezone)).time()
    if am <= local < pm:
        return Shift.am
    if pm <= local < overnight:
        return Shift.pm
    return Shift.overnight
