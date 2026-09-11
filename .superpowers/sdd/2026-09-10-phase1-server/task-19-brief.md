### Task 19: WebSocket endpoint, presence, typing

**Files:**
- Create: `server/app/realtime/presence.py`, `server/app/realtime/ws.py`, `server/tests/test_presence.py`, `server/tests/test_ws.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `PresenceStore` with `update(conversation_id, user, state) -> set[str]` (changed conversation ids; `state ∈ {"viewing","composing"}`; `user = {"id","firstName","avatarUrl"}`), `clear_user(user_id) -> set[str]`, `sweep(now, ttl_seconds=10) -> set[str]`, `snapshot(conversation_id) -> list[dict]`; module singleton `presence.store`; `presence.broadcast_presence(property_id, conversation_ids)`; `ws.sock` (flask-sock `Sock`) with route `/ws`; `ws.start_sweeper(app)` (daemon thread, 5 s). Client → server frames: `{"type":"subscribe","propertyId"}`, `{"type":"presence","conversationId"|null,"state"}`, `{"type":"heartbeat"}`. Server → client: everything `broadcast.deliver` sends plus `{"type":"presence.update","payload":{"conversationId","users":[...]}}` and `{"type":"subscribed"}`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_presence.py`:
```python
from datetime import timedelta

from app import clock
from app.realtime.presence import PresenceStore

AVA = {"id": "u1", "firstName": "Ava", "avatarUrl": None}
MARCUS = {"id": "u2", "firstName": "Marcus", "avatarUrl": None}


def test_update_and_snapshot():
    s = PresenceStore()
    assert s.update("c1", AVA, "viewing") == {"c1"}
    assert s.update("c1", MARCUS, "composing") == {"c1"}
    snap = s.snapshot("c1")
    assert {(u["id"], u["state"]) for u in snap} == {("u1", "viewing"), ("u2", "composing")}


def test_moving_conversations_reports_both():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.update("c2", AVA, "viewing") == {"c1", "c2"}
    assert s.snapshot("c1") == [] and [u["id"] for u in s.snapshot("c2")] == ["u1"]


def test_null_conversation_clears():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.update(None, AVA, "viewing") == {"c1"}
    assert s.snapshot("c1") == []


def test_sweep_expires_stale_entries():
    s = PresenceStore()
    clock.freeze(clock.now())
    s.update("c1", AVA, "viewing")
    clock.advance(seconds=11)
    s.update("c1", MARCUS, "viewing")
    assert s.sweep(clock.now()) == {"c1"}
    assert [u["id"] for u in s.snapshot("c1")] == ["u2"]


def test_clear_user():
    s = PresenceStore()
    s.update("c1", AVA, "viewing")
    assert s.clear_user("u1") == {"c1"}
```

`server/tests/test_ws.py`:
```python
"""Drives the real WebSocket route with a dev server in a thread and simple_websocket's client."""
import json
import threading

import pytest
from werkzeug.serving import make_server


@pytest.fixture()
def live_server(app):
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _cookie(login):
    c = login("agent@hvh.test")
    return "sid=" + c.get_cookie("sid").value


def _connect(host, cookie):
    from simple_websocket import Client

    return Client.connect(f"ws://{host}/ws", headers={"Cookie": cookie})


def test_unauthenticated_socket_is_closed(live_server):
    from simple_websocket import Client, ConnectionClosed

    ws = Client.connect(f"ws://{live_server}/ws")
    with pytest.raises(ConnectionClosed):
        ws.receive(timeout=2)


def test_subscribe_and_receive_broadcast(app, fx, live_server, login, database):
    ws = _connect(live_server, _cookie(login))
    ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
    assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    from app.domain import notifications

    with database.session() as db:
        notifications.create(db, fx.property_a.id, fx.agent_a.id, "t", "Hello over the wire")
    msg = json.loads(ws.receive(timeout=2))
    assert msg["type"] == "notification.created" and msg["payload"]["title"] == "Hello over the wire"
    ws.close()


def test_subscribe_to_other_property_is_refused(app, fx, live_server, login):
    from simple_websocket import ConnectionClosed

    ws = _connect(live_server, _cookie(login))
    ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_b.id}))
    with pytest.raises(ConnectionClosed):
        ws.receive(timeout=2)


def test_presence_is_fanned_out_to_the_property(app, fx, live_server, login):
    a = _connect(live_server, _cookie(login))
    b = _connect(live_server, "sid=" + login("agent2@hvh.test").get_cookie("sid").value)
    for ws in (a, b):
        ws.send(json.dumps({"type": "subscribe", "propertyId": fx.property_a.id}))
        assert json.loads(ws.receive(timeout=2))["type"] == "subscribed"
    a.send(json.dumps({"type": "presence", "conversationId": "c-412", "state": "composing"}))
    got = json.loads(b.receive(timeout=2))
    assert got["type"] == "presence.update" and got["payload"]["conversationId"] == "c-412"
    assert got["payload"]["users"][0]["firstName"] == "Ava" and got["payload"]["users"][0]["state"] == "composing"
    a.close(); b.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_presence.py tests/test_ws.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/realtime/presence.py`**

```python
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime

from app import clock
from app.realtime.broadcast import Event, deliver

TTL_SECONDS = 10


@dataclass
class Entry:
    user: dict
    state: str
    seen_at: datetime


class PresenceStore:
    def __init__(self):
        self._by_conv: dict[str, dict[str, Entry]] = {}
        self._where: dict[str, str] = {}  # user_id -> conversation_id
        self._lock = threading.Lock()

    def update(self, conversation_id: str | None, user: dict, state: str) -> set[str]:
        changed: set[str] = set()
        uid = user["id"]
        with self._lock:
            prev = self._where.get(uid)
            if prev and prev != conversation_id:
                self._by_conv.get(prev, {}).pop(uid, None)
                changed.add(prev)
            if conversation_id:
                self._by_conv.setdefault(conversation_id, {})[uid] = Entry(user, state, clock.now())
                self._where[uid] = conversation_id
                changed.add(conversation_id)
            else:
                self._where.pop(uid, None)
        return changed

    def clear_user(self, user_id: str) -> set[str]:
        with self._lock:
            prev = self._where.pop(user_id, None)
            if prev:
                self._by_conv.get(prev, {}).pop(user_id, None)
                return {prev}
        return set()

    def sweep(self, now: datetime, ttl_seconds: int = TTL_SECONDS) -> set[str]:
        changed: set[str] = set()
        with self._lock:
            for cid, users in list(self._by_conv.items()):
                for uid, e in list(users.items()):
                    if (now - e.seen_at).total_seconds() > ttl_seconds:
                        users.pop(uid)
                        self._where.pop(uid, None)
                        changed.add(cid)
                if not users:
                    self._by_conv.pop(cid)
        return changed

    def snapshot(self, conversation_id: str) -> list[dict]:
        with self._lock:
            return [{**e.user, "state": e.state} for e in self._by_conv.get(conversation_id, {}).values()]


store = PresenceStore()


def broadcast_presence(property_id: str, conversation_ids: set[str]) -> None:
    for cid in conversation_ids:
        deliver(Event(property_id=property_id, type="presence.update",
                      payload={"conversationId": cid, "users": store.snapshot(cid)}))
```

- [ ] **Step 4: Write `app/realtime/ws.py`**

```python
from __future__ import annotations

import json
import logging
import threading

from flask import Flask, request
from flask_sock import Sock
from sqlalchemy import select

from app import clock
from app.auth.sessions import COOKIE_NAME, load_session
from app.db import get_db
from app.models import PropertyMembership, UserAccount
from app.realtime import presence
from app.realtime.registry import connections

log = logging.getLogger("ws")
sock = Sock()


@sock.route("/ws")
def ws_route(ws):
    token = request.cookies.get(COOKIE_NAME)
    user = None
    if token:
        with get_db().session() as db:
            s = load_session(db, token)
            if s:
                u = db.get(UserAccount, s.user_id)
                user = {"id": u.id, "firstName": u.first_name, "avatarUrl": u.avatar_url}
    if user is None:
        ws.close(4401, "unauthorized")
        return
    property_id: str | None = None
    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            kind = frame.get("type")
            if kind == "subscribe":
                pid = frame.get("propertyId")
                with get_db().session() as db:
                    ok = db.scalar(select(PropertyMembership.id).where(PropertyMembership.user_id == user["id"],
                                                                       PropertyMembership.property_id == pid))
                if not ok:
                    ws.close(4403, "no membership")
                    return
                if property_id:
                    connections.remove(ws)
                property_id = pid
                connections.add(ws, property_id, user["id"])
                ws.send(json.dumps({"type": "subscribed", "propertyId": property_id, "at": clock.now().isoformat()}))
            elif kind == "presence" and property_id:
                state = frame.get("state") if frame.get("state") in ("viewing", "composing") else "viewing"
                changed = presence.store.update(frame.get("conversationId"), user, state)
                presence.broadcast_presence(property_id, changed)
            elif kind == "heartbeat" and property_id:
                presence.store.touch(user["id"])  # refresh seen_at without changing state
    except Exception:  # noqa: BLE001 — connection errors are routine
        log.debug("ws closed", exc_info=True)
    finally:
        connections.remove(ws)
        if property_id:
            presence.broadcast_presence(property_id, presence.store.clear_user(user["id"]))


def start_sweeper(app: Flask, interval: float = 5.0) -> threading.Thread:
    stop = threading.Event()

    def loop():
        while not stop.wait(interval):
            changed = presence.store.sweep(clock.now())
            # We don't know each conversation's property here; look them up cheaply.
            if changed:
                from app.models import Conversation

                with app.app_context(), get_db().session() as db:
                    rows = db.execute(select(Conversation.id, Conversation.property_id)
                                      .where(Conversation.id.in_(list(changed)))).all()
                by_prop: dict[str, set[str]] = {}
                for cid, pid in rows:
                    by_prop.setdefault(pid, set()).add(cid)
                for pid, cids in by_prop.items():
                    presence.broadcast_presence(pid, cids)

    t = threading.Thread(target=loop, name="presence-sweeper", daemon=True)
    t.start()
    app.extensions["presence_sweeper_stop"] = stop
    return t
```

Add the `touch` method to `PresenceStore` (Step 3), after `clear_user`:
```python
    def touch(self, user_id: str) -> None:
        with self._lock:
            cid = self._where.get(user_id)
            entry = self._by_conv.get(cid, {}).get(user_id) if cid else None
            if entry:
                entry.seen_at = clock.now()
```

In `create_app`, after blueprints:
```python
    from app.realtime.ws import sock, start_sweeper

    sock.init_app(app)
    if config.START_WORKER and (under_reloader or not app.debug):
        start_sweeper(app)
```
(Reuse the same `under_reloader` guard computed for the worker; order the blocks so `under_reloader` is defined first.)

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q`
Expected: all pass. `test_ws.py` needs `simple-websocket` (already in dev extras).

- [ ] **Step 6: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): WebSocket endpoint with membership check, presence store, typing fan-out"
```

---

