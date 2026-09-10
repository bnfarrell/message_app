"""Single source of time for the application. Tests freeze/advance it."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen if _frozen is not None else datetime.now(timezone.utc)


def freeze(dt: datetime) -> None:
    global _frozen
    if dt.tzinfo is None:
        raise ValueError("clock.freeze requires an aware datetime")
    _frozen = dt.astimezone(timezone.utc)


def advance(*, seconds: float = 0, minutes: float = 0, hours: float = 0) -> datetime:
    freeze(now() + timedelta(seconds=seconds, minutes=minutes, hours=hours))
    return now()


def reset() -> None:
    global _frozen
    _frozen = None
