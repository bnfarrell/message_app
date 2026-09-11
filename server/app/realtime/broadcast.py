"""Realtime events are queued on the SQLAlchemy session and delivered after commit.

Domain code calls queue_event(); Database.session() calls deliver() for each queued event once the
transaction has committed, so a client that refetches on an event always sees the committed data.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app import clock
from app.realtime.registry import connections


@dataclass
class Event:
    property_id: str
    type: str
    payload: dict[str, Any]
    at: datetime = field(default_factory=clock.now)
    user_id: str | None = None  # None = everyone on the property

    def to_json(self) -> str:
        return json.dumps(
            {"type": self.type, "propertyId": self.property_id, "payload": self.payload,
             "at": self.at.isoformat()},
            default=str,
        )


log = logging.getLogger("realtime")

_listeners: list[Callable[[Event], None]] = []
_lock = threading.Lock()


def queue_event(db: Session, property_id: str, type: str, payload: dict[str, Any],
                user_id: str | None = None) -> Event:
    ev = Event(property_id=property_id, type=type, payload=payload, user_id=user_id)
    db.info.setdefault("events", []).append(ev)
    return ev


def deliver(ev: Event) -> None:
    # The delivered count used to be discarded, so an event that reached nobody looked exactly
    # like one that reached everybody. Two API processes on the same port is the case that
    # matters: the registry is per-process, so the worker in process B broadcasts into an empty
    # dict while the browser's socket sits in process A, and nothing anywhere says so.
    delivered = connections.send(ev.property_id, ev.to_json(), user_id=ev.user_id)
    if delivered == 0:
        log.warning("%s for property %s reached 0 sockets (%d connected to this process)",
                    ev.type, ev.property_id, connections.count(ev.property_id))
    with _lock:
        listeners = list(_listeners)
    for fn in listeners:
        fn(ev)


def add_listener(fn: Callable[[Event], None]) -> None:
    with _lock:
        _listeners.append(fn)


def remove_listener(fn: Callable[[Event], None]) -> None:
    with _lock:
        if fn in _listeners:
            _listeners.remove(fn)
