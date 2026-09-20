## Task 2: Shift derivation

**Files:**
- Create: `server/app/domain/log.py` (first function only)
- Test: `server/tests/test_log_shift.py`

**Interfaces:**
- Consumes: `Shift` from `app.schemas.enums`; `Property` from `app.models`
- Produces: `app.domain.log.shift_for(prop: Property, at: datetime) -> Shift` and `app.domain.log.DEFAULT_SHIFT_BOUNDARIES: dict[str, str]`

- [ ] **Step 1: Write the failing test**

Create `server/tests/test_log_shift.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_shift.py -q`
Expected: FAIL with `ImportError: cannot import name 'shift_for' from 'app.domain.log'`

- [ ] **Step 3: Write the implementation**

Create `server/app/domain/log.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_shift.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Lint and commit**

```bash
cd server && ../.venv/Scripts/python.exe -m ruff check .
git add server/app/domain/log.py server/tests/test_log_shift.py
git commit -m "feat(server): derive hotel log shift from property timezone and boundaries"
```

---

