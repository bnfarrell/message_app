### Task 21: Dev-only endpoints for the phone simulator and mock PMS

**Files:**
- Create: `server/app/api/dev.py`, `server/app/schemas/dev.py`, `server/tests/test_dev.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces (registered only when `not config.is_production`): `GET /api/dev/sim/guests` → `list[SimGuest]` (seeded guests across properties with phone, name, room, consent, property sms number, `willFail` flag for `…0000` numbers); `GET /api/dev/sim/thread?phone=&propertyId=` → `GuestThread`; `GET /api/dev/sim/events?since=` → last 100 realtime events the server delivered (ring buffer fed by a `broadcast` listener) as `list[SimEvent]`; `POST /api/dev/pms/check-in/<stay_id>` and `POST /api/dev/pms/check-out/<stay_id>` → 204. Dev routes require no login (they are for the simulator page in development) but are absent in production.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_dev.py`:
```python
from app import create_app
from app.config import Config
from tests.factories import inbound


def test_dev_routes_absent_in_production(template_db_path, tmp_path):
    import shutil

    p = tmp_path / "prod.db"
    shutil.copy(template_db_path, p)
    app = create_app(Config(DATABASE_URL=f"sqlite:///{p.as_posix()}", ENV="production", TESTING=True))
    assert app.test_client().get("/api/dev/sim/guests").status_code == 404
    app.extensions["db"].engine.dispose()


def test_sim_guests_and_thread(app, fx, client):
    guests = client.get("/api/dev/sim/guests").get_json()
    sarah = [g for g in guests if g["phone"] == fx.guest_inhouse_a.phone_e164][0]
    assert sarah["roomNumber"] == "412" and sarah["propertyId"] == fx.property_a.id and sarah["willFail"] is False
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    t = client.get(f"/api/dev/sim/thread?phone={fx.guest_inhouse_a.phone_e164}&propertyId={fx.property_a.id}").get_json()
    assert [m["body"] for m in t["messages"]] == ["hello"] and "notes" not in t


def test_sim_events_ring_buffer(app, fx, client):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    events = client.get("/api/dev/sim/events").get_json()
    assert any(e["type"] == "message.created" for e in events)
    assert all({"type", "propertyId", "at", "payload"} <= set(e) for e in events)


def test_dev_pms_endpoints(app, fx, client, database):
    from sqlalchemy import select

    from app.models import Stay
    from app.schemas.enums import StayStatus

    assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
    with database.session() as db:
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
    assert client.post("/api/dev/pms/check-in/nope").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_dev.py -q`
Expected: FAIL with 404s on `/api/dev/...` in the non-production app.

- [ ] **Step 3: Write the schema and blueprint**

`app/schemas/dev.py`:
```python
from datetime import datetime
from typing import Any

from app.schemas.common import CamelModel
from app.schemas.enums import SmsConsentStatus


class SimGuest(CamelModel):
    property_id: str
    property_name: str
    property_sms_number: str | None = None
    guest_id: str
    name: str
    phone: str
    room_number: str | None = None
    in_house: bool
    sms_consent_status: SmsConsentStatus
    will_fail: bool


class SimEvent(CamelModel):
    type: str
    property_id: str
    at: datetime
    payload: dict[str, Any]
```

`app/api/dev.py`:
```python
from __future__ import annotations

from collections import deque

from flask import Blueprint, request
from sqlalchemy import select

from app.api._util import db_session, no_content, ok
from app.channels.mock_sms import FAIL_SUFFIX
from app.domain import conversations
from app.errors import NotFound, ValidationFailed
from app.models import Guest, Property, Stay
from app.pms.handle_event import handle_event
from app.queue.handlers.pms import adapter as pms_adapter
from app.realtime import broadcast
from app.schemas.dev import SimEvent, SimGuest
from app.schemas.enums import StayStatus

bp = Blueprint("dev", __name__, url_prefix="/api/dev")
_events: deque[broadcast.Event] = deque(maxlen=100)


def _record(ev: broadcast.Event) -> None:
    _events.append(ev)


def install_event_recorder() -> None:
    broadcast.remove_listener(_record)
    broadcast.add_listener(_record)


@bp.get("/sim/guests")
def sim_guests():
    with db_session() as db:
        rows = db.execute(select(Guest, Property).join(Property, Property.id == Guest.property_id)
                          .order_by(Property.name, Guest.last_name)).all()
        in_house = {s.guest_id: s for s in db.scalars(select(Stay).where(Stay.status == StayStatus.checked_in)).all()}
        out = []
        for g, p in rows:
            stay = in_house.get(g.id)
            out.append(SimGuest(property_id=p.id, property_name=p.name, property_sms_number=p.sms_number, guest_id=g.id,
                                name=f"{g.first_name or ''} {g.last_name or ''}".strip() or "Unknown", phone=g.phone_e164,
                                room_number=stay.room_number if stay else None, in_house=stay is not None,
                                sms_consent_status=g.sms_consent_status, will_fail=g.phone_e164.endswith(FAIL_SUFFIX)))
        return ok(out)


@bp.get("/sim/thread")
def sim_thread():
    phone, property_id = request.args.get("phone"), request.args.get("propertyId")
    if not phone or not property_id:
        raise ValidationFailed("phone and propertyId are required")
    with db_session() as db:
        if db.get(Property, property_id) is None:
            raise NotFound("Property not found")
        return ok(conversations.guest_thread(db, property_id, phone))


@bp.get("/sim/events")
def sim_events():
    return ok([SimEvent(type=e.type, property_id=e.property_id, at=e.at, payload=e.payload) for e in list(_events)])


def _pms(stay_id: str, type: str):
    with db_session() as db:
        stay = db.get(Stay, stay_id)
        if stay is None:
            raise NotFound("Stay not found")
        event = pms_adapter.event_for(db, stay.property_id, stay_id, type)
        handle_event(db, event, integration_key=pms_adapter.integration_key)
    return no_content()


@bp.post("/pms/check-in/<stay_id>")
def pms_check_in(stay_id: str):
    return _pms(stay_id, "stay.checked_in")


@bp.post("/pms/check-out/<stay_id>")
def pms_check_out(stay_id: str):
    return _pms(stay_id, "stay.checked_out")
```

In `create_app`:
```python
    if not config.is_production:
        from app.api import dev

        dev.install_event_recorder()
        app.register_blueprint(dev.bp)
```

Note: `handle_event` for a `stay.checked_out` of an already-processed `external_id` is deduplicated by `(integration_key, external_id, event_type)`, so pressing "check out" twice is a no-op — intended.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): dev-only simulator and mock PMS endpoints"
```

---

