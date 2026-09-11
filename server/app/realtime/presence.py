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

    def touch(self, user_id: str) -> None:
        with self._lock:
            cid = self._where.get(user_id)
            entry = self._by_conv.get(cid, {}).get(user_id) if cid else None
            if entry:
                entry.seen_at = clock.now()


store = PresenceStore()


def broadcast_presence(property_id: str, conversation_ids: set[str]) -> None:
    for cid in conversation_ids:
        deliver(Event(property_id=property_id, type="presence.update",
                      payload={"conversationId": cid, "users": store.snapshot(cid)}))
