"""Shift derivation (spec §3.3). Pure function over (property, instant) — no DB writes."""
from datetime import UTC, datetime

import pytest

from app.domain.log import shift_for
from app.models import Property
from app.schemas.enums import Shift


def _prop(tz: str = "America/New_York", boundaries: dict | None = None) -> Property:
    settings = {"shift_boundaries": boundaries} if boundaries else {}
    return Property(name="T", code="T", timezone=tz, settings=settings)


@pytest.mark.parametrize(
    "local_hour,expected",
    [
        (0, Shift.overnight),   # after midnight, before am
        (6, Shift.overnight),
        (7, Shift.am),          # boundary is inclusive at the start
        (8, Shift.am),
        (14, Shift.am),
        (15, Shift.pm),         # boundary is inclusive at the start
        (22, Shift.pm),
        (23, Shift.overnight),  # boundary is inclusive at the start
    ],
)
def test_default_boundaries_partition_the_clock(local_hour, expected):
    # 2026-09-10 is EDT (UTC-4), so local hour H is UTC hour H+4, rolling to the next
    # day once H+4 reaches 24.
    utc_hour = local_hour + 4
    at = datetime(2026, 9, 10 + utc_hour // 24, utc_hour % 24, 30, tzinfo=UTC)
    assert shift_for(_prop(), at) == expected


def test_overnight_wraps_midnight_in_the_property_timezone():
    # 03:00 EDT on the 11th is 07:00 UTC — which under a naive UTC comparison would read as
    # `am`. It must read as `overnight`, because the label is about the property's clock.
    at = datetime(2026, 9, 11, 7, 0, tzinfo=UTC)
    assert shift_for(_prop(), at) == Shift.overnight


def test_a_different_timezone_gives_a_different_label_for_the_same_instant():
    at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)  # 08:00 EDT, 05:00 PDT
    assert shift_for(_prop("America/New_York"), at) == Shift.am
    assert shift_for(_prop("America/Los_Angeles"), at) == Shift.overnight


def test_custom_boundaries_from_property_settings():
    boundaries = {"am": "05:00", "pm": "13:00", "overnight": "21:00"}
    at = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)  # 06:00 EDT
    assert shift_for(_prop(boundaries=boundaries), at) == Shift.am
    at = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)  # 14:00 EDT
    assert shift_for(_prop(boundaries=boundaries), at) == Shift.pm
    at = datetime(2026, 9, 11, 2, 0, tzinfo=UTC)   # 22:00 EDT on the 10th
    assert shift_for(_prop(boundaries=boundaries), at) == Shift.overnight


def test_a_naive_datetime_is_rejected():
    with pytest.raises(ValueError):
        shift_for(_prop(), datetime(2026, 9, 10, 12, 0))
