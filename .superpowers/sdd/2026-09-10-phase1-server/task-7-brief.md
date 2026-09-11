### Task 7: Realtime event outbox, connection registry, and notifications

**Files:**
- Create: `server/app/realtime/__init__.py`, `server/app/realtime/registry.py`, `server/app/realtime/broadcast.py`, `server/app/domain/notifications.py`, `server/app/schemas/notifications.py`, `server/app/api/notifications.py`, `server/tests/test_notifications.py`
- Modify: `server/app/__init__.py`, `server/tests/conftest.py` (add `events` fixture)

**Interfaces:**
- Produces: `broadcast.Event(property_id, type, payload, at, user_id=None)`; `broadcast.queue_event(db, property_id, type, payload, user_id=None)` (appends to `db.info["events"]`; delivered after commit by `Database.session()`); `broadcast.deliver(event)`; `broadcast.add_listener(fn)` / `remove_listener(fn)` (tests and the WS layer subscribe); `registry.ConnectionRegistry` with `add(ws, property_id, user_id)`, `remove(ws)`, `send(property_id, text, user_id=None) -> int`, `count(property_id)`; module singleton `registry.connections`. `notifications.create(db, property_id, user_id, type, title, body=None, entity_type=None, entity_id=None) -> Notification`; `notify_users(db, property_id, user_ids, ...)`; `notify_user_or_department(db, property_id, *, user_id, department_id, type, title, body=None, entity_type=None, entity_id=None) -> list[Notification]` (falls back to the property's `front_desk` department, then to all admins); `list_for_user(db, property_id, user_id, unread_only, limit=50)`; `mark_read`, `mark_all_read`, `unread_count`. `NotificationOut`. Routes under `/api/p/<property_id>/notifications`. Test fixture `events: list[Event]`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_notifications.py`:
```python
from app.domain import notifications
from app.schemas.enums import DepartmentType


def test_create_persists_and_broadcasts_to_user(app, fx, database, events):
    with database.session() as db:
        n = notifications.create(db, fx.property_a.id, fx.agent_a.id, "test", "Hello", body="b",
                                 entity_type="conversation", entity_id="c1")
    assert n.id
    ev = [e for e in events if e.type == "notification.created"]
    assert len(ev) == 1
    assert ev[0].user_id == fx.agent_a.id
    assert ev[0].property_id == fx.property_a.id
    assert ev[0].payload["title"] == "Hello"


def test_events_are_delivered_only_after_commit(app, fx, database, events):
    import pytest

    with pytest.raises(RuntimeError):
        with database.session() as db:
            notifications.create(db, fx.property_a.id, fx.agent_a.id, "test", "Never")
            raise RuntimeError("boom")
    assert events == []


def test_notify_user_or_department_prefers_user(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=fx.agent_a2.id, department_id=fx.dept_engineering.id,
            type="t", title="x")
    assert [r.user_id for r in rows] == [fx.agent_a2.id]


def test_notify_department_fans_out_to_members(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=None, department_id=fx.dept_engineering.id, type="t", title="x")
    assert sorted(r.user_id for r in rows) == sorted([fx.engineer_a.id, fx.supervisor_a.id])


def test_notify_falls_back_to_front_desk(app, fx, database):
    with database.session() as db:
        rows = notifications.notify_user_or_department(
            db, fx.property_a.id, user_id=None, department_id=None, type="t", title="x")
    assert sorted(r.user_id for r in rows) == sorted([fx.agent_a.id, fx.agent_a2.id])


def test_list_mark_read_and_unread_count_via_api(app, fx, database, login):
    with database.session() as db:
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "One")
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "Two")
        notifications.create(db, fx.property_a.id, fx.agent_a2.id, "t", "Not mine")
    c = login("agent@hvh.test")
    base = f"/api/p/{fx.property_a.id}/notifications"
    rows = c.get(base).get_json()
    assert [r["title"] for r in rows] == ["Two", "One"]
    assert c.get(base + "/unread-count").get_json() == {"count": 2}
    assert c.post(f"{base}/{rows[0]['id']}/read").status_code == 204
    assert c.get(base + "?unread=1").get_json()[0]["title"] == "One"
    assert c.post(base + "/read-all").status_code == 204
    assert c.get(base + "/unread-count").get_json() == {"count": 0}


def test_cannot_mark_someone_elses_notification(app, fx, database, login):
    with database.session() as db:
        n = notifications.create(db, fx.property_a.id, fx.agent_a2.id, "t", "Not mine")
    c = login("agent@hvh.test")
    assert c.post(f"/api/p/{fx.property_a.id}/notifications/{n.id}/read").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_notifications.py -q`
Expected: FAIL with `fixture 'events' not found`.

- [ ] **Step 3: Write the registry and broadcast modules**

`server/app/realtime/__init__.py` — empty.

`server/app/realtime/registry.py`:
```python
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class Conn:
    ws: Any
    property_id: str
    user_id: str


class ConnectionRegistry:
    """In-memory set of live WebSocket connections, grouped by property. Single process by design."""

    def __init__(self):
        self._conns: dict[int, Conn] = {}
        self._lock = threading.Lock()

    def add(self, ws: Any, property_id: str, user_id: str) -> None:
        with self._lock:
            self._conns[id(ws)] = Conn(ws, property_id, user_id)

    def remove(self, ws: Any) -> None:
        with self._lock:
            self._conns.pop(id(ws), None)

    def count(self, property_id: str) -> int:
        with self._lock:
            return sum(1 for c in self._conns.values() if c.property_id == property_id)

    def users_online(self, property_id: str) -> set[str]:
        with self._lock:
            return {c.user_id for c in self._conns.values() if c.property_id == property_id}

    def send(self, property_id: str, text: str, user_id: str | None = None) -> int:
        with self._lock:
            targets = [c for c in self._conns.values()
                       if c.property_id == property_id and (user_id is None or c.user_id == user_id)]
        delivered = 0
        for c in targets:
            try:
                c.ws.send(text)
                delivered += 1
            except Exception:
                self.remove(c.ws)
        return delivered


connections = ConnectionRegistry()
```

`server/app/realtime/broadcast.py`:
```python
"""Realtime events are queued on the SQLAlchemy session and delivered after commit.

Domain code calls queue_event(); Database.session() calls deliver() for each queued event once the
transaction has committed, so a client that refetches on an event always sees the committed data.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

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


_listeners: list[Callable[[Event], None]] = []
_lock = threading.Lock()


def queue_event(db: Session, property_id: str, type: str, payload: dict[str, Any],
                user_id: str | None = None) -> Event:
    ev = Event(property_id=property_id, type=type, payload=payload, user_id=user_id)
    db.info.setdefault("events", []).append(ev)
    return ev


def deliver(ev: Event) -> None:
    connections.send(ev.property_id, ev.to_json(), user_id=ev.user_id)
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
```

`Database.session()` (Task 2) already imports `deliver` lazily and calls it after commit. Add the `events` fixture to `server/tests/conftest.py`:
```python
@pytest.fixture()
def events(app):
    from app.realtime import broadcast

    captured = []
    fn = captured.append  # keep one reference: a fresh bound method would not compare equal on removal
    broadcast.add_listener(fn)
    yield captured
    broadcast.remove_listener(fn)
```

- [ ] **Step 4: Write the notifications domain and schema**

`server/app/schemas/notifications.py`:
```python
from datetime import datetime

from app.schemas.common import CamelModel


class NotificationOut(CamelModel):
    id: str
    type: str
    title: str
    body: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    read_at: datetime | None = None
    created_at: datetime


class UnreadCount(CamelModel):
    count: int
```

`server/app/domain/notifications.py`:
```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.domain.users import members_of_department
from app.models import Department, Notification, PropertyMembership
from app.realtime.broadcast import queue_event
from app.schemas.enums import DepartmentType, Role
from app.schemas.notifications import NotificationOut


def create(db: Session, property_id: str, user_id: str, type: str, title: str, body: str | None = None,
           entity_type: str | None = None, entity_id: str | None = None) -> Notification:
    n = Notification(property_id=property_id, user_id=user_id, type=type, title=title, body=body,
                     entity_type=entity_type, entity_id=entity_id)
    db.add(n)
    db.flush()
    queue_event(db, property_id, "notification.created",
                NotificationOut.model_validate(n).model_dump(mode="json", by_alias=True),
                user_id=user_id)
    return n


def notify_users(db: Session, property_id: str, user_ids: list[str], type: str, title: str,
                 body: str | None = None, entity_type: str | None = None,
                 entity_id: str | None = None) -> list[Notification]:
    return [create(db, property_id, uid, type, title, body, entity_type, entity_id)
            for uid in dict.fromkeys(user_ids)]


def _front_desk_members(db: Session, property_id: str) -> list[str]:
    dept_id = db.scalar(select(Department.id).where(Department.property_id == property_id,
                                                    Department.type == DepartmentType.front_desk))
    return members_of_department(db, property_id, dept_id) if dept_id else []


def _admins(db: Session, property_id: str) -> list[str]:
    return list(db.scalars(select(PropertyMembership.user_id).where(
        PropertyMembership.property_id == property_id, PropertyMembership.role == Role.admin)).all())


def notify_user_or_department(db: Session, property_id: str, *, user_id: str | None,
                              department_id: str | None, type: str, title: str,
                              body: str | None = None, entity_type: str | None = None,
                              entity_id: str | None = None) -> list[Notification]:
    if user_id:
        targets = [user_id]
    elif department_id:
        targets = members_of_department(db, property_id, department_id)
    else:
        targets = []
    if not targets:
        targets = _front_desk_members(db, property_id) or _admins(db, property_id)
    return notify_users(db, property_id, targets, type, title, body, entity_type, entity_id)


def list_for_user(db: Session, property_id: str, user_id: str, unread_only: bool = False,
                  limit: int = 50) -> list[NotificationOut]:
    q = select(Notification).where(Notification.property_id == property_id,
                                   Notification.user_id == user_id)
    if unread_only:
        q = q.where(Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(Notification.created_at.desc()).limit(limit)).all()
    return [NotificationOut.model_validate(n) for n in rows]


def unread_count(db: Session, property_id: str, user_id: str) -> int:
    return db.scalar(select(func.count()).select_from(Notification).where(
        Notification.property_id == property_id, Notification.user_id == user_id,
        Notification.read_at.is_(None))) or 0


def mark_read(db: Session, property_id: str, user_id: str, notification_id: str) -> bool:
    n = db.scalar(select(Notification).where(Notification.id == notification_id,
                                             Notification.property_id == property_id,
                                             Notification.user_id == user_id))
    if n is None:
        return False
    if n.read_at is None:
        n.read_at = clock.now()
    return True


def mark_all_read(db: Session, property_id: str, user_id: str) -> int:
    rows = db.scalars(select(Notification).where(Notification.property_id == property_id,
                                                 Notification.user_id == user_id,
                                                 Notification.read_at.is_(None))).all()
    now = clock.now()
    for n in rows:
        n.read_at = now
    return len(rows)
```

- [ ] **Step 5: Write the blueprint and register it**

`server/app/api/notifications.py`:
```python
from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok
from app.auth.decorators import require_auth, require_property
from app.domain import notifications
from app.errors import NotFound
from app.schemas.notifications import UnreadCount

bp = Blueprint("notifications", __name__, url_prefix="/api/p/<property_id>/notifications")


@bp.get("")
@require_auth
@require_property
def list_notifications(property_id: str):
    unread = request.args.get("unread") in ("1", "true")
    with db_session() as db:
        return ok(notifications.list_for_user(db, g.property_id, g.user.id, unread_only=unread))


@bp.get("/unread-count")
@require_auth
@require_property
def unread(property_id: str):
    with db_session() as db:
        return ok(UnreadCount(count=notifications.unread_count(db, g.property_id, g.user.id)))


@bp.post("/<notification_id>/read")
@require_auth
@require_property
def mark_read(property_id: str, notification_id: str):
    with db_session() as db:
        if not notifications.mark_read(db, g.property_id, g.user.id, notification_id):
            raise NotFound("Notification not found")
    return no_content()


@bp.post("/read-all")
@require_auth
@require_property
def mark_all(property_id: str):
    with db_session() as db:
        notifications.mark_all_read(db, g.property_id, g.user.id)
    return no_content()
```

Register `notifications.bp` in `create_app`.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass, including the isolation suite now covering four new routes.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): after-commit realtime event outbox, connection registry, notifications"
```

---

