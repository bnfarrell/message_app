"""Shift windows (checklists spec §3.1). HVH is New York (EDT = UTC-4 until 2026-11-01), LSI
Chicago. Default boundaries: am 07:00, pm 15:00, overnight 23:00."""
from datetime import UTC, date, datetime

from app.domain import shifts
from app.models import Property
from app.schemas.enums import Shift


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def test_default_windows(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        d = date(2026, 9, 10)
        assert shifts.shift_window(p, d, Shift.am) == (utc(2026, 9, 10, 11), utc(2026, 9, 10, 19))
        assert shifts.shift_window(p, d, Shift.pm) == (utc(2026, 9, 10, 19), utc(2026, 9, 11, 3))
        assert shifts.shift_window(p, d, Shift.overnight) == (utc(2026, 9, 11, 3),
                                                              utc(2026, 9, 11, 11))


def test_current_shift_after_midnight_is_the_previous_days_overnight(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        assert shifts.current_shift(p, utc(2026, 9, 11, 6)) == (date(2026, 9, 10),
                                                                Shift.overnight)
        assert shifts.current_shift(p, utc(2026, 9, 11, 12)) == (date(2026, 9, 11), Shift.am)


def test_window_follows_edited_boundaries(database, fx):
    """Review focus 1: boundaries are read at call time, never cached."""
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        p.settings = {**(p.settings or {}),
                      "shift_boundaries": {"am": "06:00", "pm": "14:00", "overnight": "22:00"}}
        db.flush()
        assert shifts.shift_window(p, date(2026, 9, 10), Shift.am) == (utc(2026, 9, 10, 10),
                                                                       utc(2026, 9, 10, 18))


def test_overnight_across_the_dst_change_has_its_true_length(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_a.id)
        start, end = shifts.shift_window(p, date(2026, 10, 31), Shift.overnight)
        assert (start, end) == (utc(2026, 11, 1, 3), utc(2026, 11, 1, 12))  # 9 hours, not 8


def test_each_property_uses_its_own_zone(database, fx):
    with database.session() as db:
        p = db.get(Property, fx.property_b.id)
        assert shifts.shift_window(p, date(2026, 9, 10), Shift.am) == (utc(2026, 9, 10, 12),
                                                                       utc(2026, 9, 10, 20))
