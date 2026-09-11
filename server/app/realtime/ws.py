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
