from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime

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
_events_lock = threading.Lock()


def _record(ev: broadcast.Event) -> None:
    # Called from whichever thread committed the delivering transaction — must never block or
    # raise, or it disrupts real event delivery for every request (see broadcast.deliver()).
    try:
        with _events_lock:
            _events.append(ev)
    except Exception:
        pass


def install_event_recorder() -> None:
    broadcast.remove_listener(_record)
    broadcast.add_listener(_record)


@bp.get("/sim/guests")
def sim_guests():
    with db_session() as db:
        rows = db.execute(select(Guest, Property).join(Property, Property.id == Guest.property_id)
                          .order_by(Property.name, Guest.last_name)).all()
        in_house = {s.guest_id: s for s in db.scalars(
            select(Stay).where(Stay.status == StayStatus.checked_in)).all()}
        out = []
        for g, p in rows:
            stay = in_house.get(g.id)
            out.append(SimGuest(
                property_id=p.id, property_name=p.name, property_sms_number=p.sms_number,
                guest_id=g.id,
                name=f"{g.first_name or ''} {g.last_name or ''}".strip() or "Unknown",
                phone=g.phone_e164,
                room_number=stay.room_number if stay else None, in_house=stay is not None,
                stay_id=stay.id if stay else None,
                sms_consent_status=g.sms_consent_status,
                will_fail=g.phone_e164.endswith(FAIL_SUFFIX)))
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


def _parse_since(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as e:
        raise ValidationFailed("since must be an ISO datetime") from e
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@bp.get("/sim/events")
def sim_events():
    since = _parse_since(request.args.get("since"))
    with _events_lock:
        snapshot = list(_events)
    if since is not None:
        snapshot = [e for e in snapshot if e.at > since]
    return ok([SimEvent(type=e.type, property_id=e.property_id, at=e.at, payload=e.payload)
              for e in snapshot])


def _pms(stay_id: str, type: str):
    with db_session() as db:
        stay = db.get(Stay, stay_id)
        if stay is None:
            raise NotFound("Stay not found")
        event = pms_adapter.event_for(db, stay.property_id, stay_id, type)
        if event is None:
            raise NotFound("Stay not found")
        handle_event(db, event, integration_key=pms_adapter.integration_key)
    return no_content()


@bp.post("/pms/check-in/<stay_id>")
def pms_check_in(stay_id: str):
    return _pms(stay_id, "stay.checked_in")


@bp.post("/pms/check-out/<stay_id>")
def pms_check_out(stay_id: str):
    return _pms(stay_id, "stay.checked_out")
