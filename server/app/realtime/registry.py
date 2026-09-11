from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conn:
    ws: Any
    property_id: str
    user_id: str
    send_lock: threading.Lock = field(default_factory=threading.Lock)


class ConnectionRegistry:
    """In-memory set of live WebSocket connections, grouped by property. Single process by
    design."""

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
                       if c.property_id == property_id
                       and (user_id is None or c.user_id == user_id)]
        delivered = 0
        for c in targets:
            try:
                with c.send_lock:
                    c.ws.send(text)
                delivered += 1
            except Exception:
                self.remove(c.ws)
        return delivered


connections = ConnectionRegistry()
