from __future__ import annotations

import importlib
from collections.abc import Callable

from sqlalchemy.orm import Session

Handler = Callable[[Session, dict], None]
HANDLERS: dict[str, Handler] = {}

MODULES = ("outbound", "mock_delivery", "sla", "snooze", "pms", "pm")


def handler(job_type: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn

    return deco


def load_all() -> None:
    """Import every handler module so its @handler decorators run. Safe to call repeatedly."""
    for name in MODULES:
        try:
            importlib.import_module(f"app.queue.handlers.{name}")
        except ModuleNotFoundError as e:
            if e.name != f"app.queue.handlers.{name}":
                raise
