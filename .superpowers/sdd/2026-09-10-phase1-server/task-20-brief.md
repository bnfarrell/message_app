### Task 20: PMS adapter interface, MockPmsAdapter, idempotent event handling

**Files:**
- Create: `server/app/pms/__init__.py`, `server/app/pms/base.py`, `server/app/pms/mock_pms.py`, `server/app/pms/handle_event.py`, `server/app/queue/handlers/pms.py`, `server/tests/test_pms.py`

**Interfaces:**
- Produces: dataclasses `NormalizedGuest(first_name, last_name, phone_e164, email, loyalty_tier, vip, pms_profile_id)`, `NormalizedStay(pms_reservation_id, room_number, room_type, rate_code, status: StayStatus, arrival_date, departure_date, adults, children, is_return_guest, stay_count)`, `PmsEvent(external_id, type, property_id, guest, stay, raw)`; `PmsAdapter` Protocol (`fetch_in_house(db, property_id)`, `next_events(db, property_id) -> list[PmsEvent]`); `MockPmsAdapter.next_events` (checks in one `reserved` stay arriving today, or checks out one `checked_in` stay departing today, alternating); `handle_event(db, event, integration_key="mock") -> bool` (False when duplicate); recurring handler `pms.tick`; `MockPmsAdapter.event_for(db, property_id, stay_id, type)` for the dev endpoints (Task 21).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_pms.py`:
```python
from datetime import date

from sqlalchemy import select

from app import clock
from app.models import Guest, PmsEvent, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent as Ev
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.schemas.enums import StayStatus


def _event(fx, eid="R-1", type="stay.checked_in", phone="+15553334444", room="515"):
    today = clock.now().date()
    return Ev(external_id=eid, type=type, property_id=fx.property_a.id,
              guest=NormalizedGuest(first_name="Tom", last_name="Becker", phone_e164=phone, email=None,
                                    loyalty_tier="Silver", vip=False, pms_profile_id="P-9"),
              stay=NormalizedStay(pms_reservation_id=eid, room_number=room, room_type="Queen", rate_code="BAR",
                                  status=StayStatus.checked_in, arrival_date=today,
                                  departure_date=date.fromordinal(today.toordinal() + 2), adults=1, children=0,
                                  is_return_guest=False, stay_count=1),
              raw={"source": "test"})


def test_check_in_upserts_guest_and_stay(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        g = db.scalar(select(Guest).where(Guest.phone_e164 == "+15553334444"))
        assert g.first_name == "Tom" and g.loyalty_tier == "Silver" and g.pms_profile_id == "P-9"
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert s.status == StayStatus.checked_in and s.room_number == "515" and s.actual_checkin_at is not None
        assert s.raw_pms == {"source": "test"}


def test_duplicate_event_is_ignored(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        assert handle_event(db, _event(fx)) is False
        assert len(db.scalars(select(Stay)).all()) == 3  # 2 fixture stays + 1
        assert len(db.scalars(select(PmsEvent)).all()) == 1


def test_check_out_updates_existing_stay_and_does_not_reopen_consent(app, fx, database):
    with database.session() as db:
        handle_event(db, _event(fx))
        ev = _event(fx, eid="R-1", type="stay.checked_out")
        ev.stay.status = StayStatus.checked_out
        assert handle_event(db, ev) is True
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert s.status == StayStatus.checked_out and s.actual_checkout_at is not None


def test_mock_adapter_checks_in_arrivals_then_checks_out_departures(app, fx, database):
    today = clock.now().date()
    with database.session() as db:
        g = Guest(property_id=fx.property_a.id, first_name="Arriving", last_name="Guest", phone_e164="+15550009999")
        db.add(g); db.flush()
        db.add(Stay(guest_id=g.id, property_id=fx.property_a.id, pms_reservation_id="R-ARR", room_number="222",
                    status=StayStatus.reserved, arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 1)))
        fx_stay = db.get(Stay, fx.stay_inhouse_a.id)
        fx_stay.departure_date = today  # Sarah departs today
    adapter = MockPmsAdapter()
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert [e.type for e in events] == ["stay.checked_in"] and events[0].stay.pms_reservation_id == "R-ARR"
        for e in events:
            handle_event(db, e)
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert [e.type for e in events] == ["stay.checked_out"] and events[0].stay.pms_reservation_id == "RES-412"
        for e in events:
            handle_event(db, e)
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_pms.py -q`
Expected: FAIL with `ModuleNotFoundError: app.pms`.

- [ ] **Step 3: Write `app/pms/base.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.schemas.enums import StayStatus

EventType = Literal["reservation.created", "stay.checked_in", "stay.checked_out", "stay.room_changed"]


@dataclass
class NormalizedGuest:
    first_name: str | None
    last_name: str | None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool = False
    pms_profile_id: str | None = None


@dataclass
class NormalizedStay:
    pms_reservation_id: str
    room_number: str | None
    room_type: str | None
    rate_code: str | None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int = 1
    children: int = 0
    is_return_guest: bool = False
    stay_count: int = 1


@dataclass
class PmsEvent:
    external_id: str
    type: EventType
    property_id: str
    guest: NormalizedGuest
    stay: NormalizedStay
    raw: dict = field(default_factory=dict)


class PmsAdapter(Protocol):
    integration_key: str

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]: ...

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]: ...
```

- [ ] **Step 4: Write `app/pms/handle_event.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, guests
from app.models import PmsEvent as PmsEventRow
from app.models import Stay
from app.pms.base import PmsEvent
from app.realtime.broadcast import queue_event
from app.schemas.enums import StayStatus


def handle_event(db: Session, event: PmsEvent, integration_key: str = "mock") -> bool:
    """Idempotent on (integration_key, external_id, event_type). Returns False for a duplicate."""
    dup = db.scalar(select(PmsEventRow.id).where(PmsEventRow.integration_key == integration_key,
                                                 PmsEventRow.external_id == event.external_id,
                                                 PmsEventRow.event_type == event.type))
    if dup:
        return False
    row = PmsEventRow(integration_key=integration_key, external_id=event.external_id, event_type=event.type,
                      payload=event.raw)
    db.add(row)

    guest, created = guests.find_or_create_by_phone(db, event.property_id, event.guest.phone_e164)
    for attr in ("first_name", "last_name", "email", "loyalty_tier", "vip", "pms_profile_id"):
        value = getattr(event.guest, attr)
        if value is not None:
            setattr(guest, attr, value)

    stay = db.scalar(select(Stay).where(Stay.property_id == event.property_id,
                                        Stay.pms_reservation_id == event.stay.pms_reservation_id))
    if stay is None:
        stay = Stay(guest_id=guest.id, property_id=event.property_id, pms_reservation_id=event.stay.pms_reservation_id,
                    arrival_date=event.stay.arrival_date, departure_date=event.stay.departure_date)
        db.add(stay)
    for attr in ("room_number", "room_type", "rate_code", "status", "arrival_date", "departure_date", "adults",
                 "children", "is_return_guest", "stay_count"):
        setattr(stay, attr, getattr(event.stay, attr))
    stay.raw_pms = event.raw
    now = clock.now()
    if event.type == "stay.checked_in" and stay.actual_checkin_at is None:
        stay.actual_checkin_at = now
    if event.type == "stay.checked_out":
        stay.status = StayStatus.checked_out
        stay.actual_checkout_at = stay.actual_checkout_at or now
    db.flush()
    row.processed_at = now
    audit.record(db, event.property_id, None, f"pms.{event.type}", "stay", stay.id,
                 after={"external_id": event.external_id, "room": stay.room_number})
    queue_event(db, event.property_id, "stay.updated", {"stayId": stay.id, "guestId": guest.id, "status": stay.status.value})
    return True
```

- [ ] **Step 5: Write `app/pms/mock_pms.py` and the handler**

`mock_pms.py`:
```python
"""Drives seeded stays through check-in and check-out so the inbox has a living hotel behind it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Guest, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent
from app.schemas.enums import StayStatus


class MockPmsAdapter:
    integration_key = "mock"

    def __init__(self):
        self._flip = False

    @staticmethod
    def _event(stay: Stay, guest: Guest, type: str, status: StayStatus) -> PmsEvent:
        return PmsEvent(
            external_id=stay.pms_reservation_id or stay.id, type=type, property_id=stay.property_id,
            guest=NormalizedGuest(first_name=guest.first_name, last_name=guest.last_name, phone_e164=guest.phone_e164,
                                  email=guest.email, loyalty_tier=guest.loyalty_tier, vip=guest.vip,
                                  pms_profile_id=guest.pms_profile_id),
            stay=NormalizedStay(pms_reservation_id=stay.pms_reservation_id or stay.id, room_number=stay.room_number,
                                room_type=stay.room_type, rate_code=stay.rate_code, status=status,
                                arrival_date=stay.arrival_date, departure_date=stay.departure_date, adults=stay.adults,
                                children=stay.children, is_return_guest=stay.is_return_guest, stay_count=stay.stay_count),
            raw={"mock": True, "emitted_at": clock.now().isoformat()})

    def event_for(self, db: Session, property_id: str, stay_id: str, type: str) -> PmsEvent | None:
        stay = db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
        if stay is None:
            return None
        status = StayStatus.checked_in if type == "stay.checked_in" else StayStatus.checked_out
        return self._event(stay, db.get(Guest, stay.guest_id), type, status)

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]:
        rows = db.scalars(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.checked_in)).all()
        return [self._event(s, db.get(Guest, s.guest_id), "stay.checked_in", StayStatus.checked_in).stay for s in rows]

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]:
        today = clock.now().date()
        arrival = db.scalar(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.reserved,
                                               Stay.arrival_date <= today).order_by(Stay.arrival_date).limit(1))
        departure = db.scalar(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.checked_in,
                                                 Stay.departure_date <= today).order_by(Stay.departure_date).limit(1))
        self._flip = not self._flip
        order = [arrival, departure] if self._flip else [departure, arrival]
        for stay in order:
            if stay is None:
                continue
            guest = db.get(Guest, stay.guest_id)
            if stay.status == StayStatus.reserved:
                return [self._event(stay, guest, "stay.checked_in", StayStatus.checked_in)]
            return [self._event(stay, guest, "stay.checked_out", StayStatus.checked_out)]
        return []
```

`app/queue/handlers/pms.py`:
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Property
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.queue.handlers import handler

adapter = MockPmsAdapter()


@handler("pms.tick")
def pms_tick(db: Session, payload: dict) -> None:
    for pid in db.scalars(select(Property.id)).all():
        for event in adapter.next_events(db, pid):
            handle_event(db, event, integration_key=adapter.integration_key)
```

Register the adapter on the app in `create_app`: `from app.queue.handlers import pms as pms_handler; app.extensions["pms_adapter"] = pms_handler.adapter` (import after `load_all()` has run inside `Worker.__init__`, or simply import the module directly — it is safe to import before the worker exists).

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): PMS adapter interface, mock PMS driving check-ins/outs, idempotent event handling"
```

---

