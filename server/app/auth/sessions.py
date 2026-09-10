from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import UserSession

SESSION_HOURS = 12
COOKIE_NAME = "sid"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create_session(db: Session, user_id: str, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    now = clock.now()
    db.add(
        UserSession(
            user_id=user_id,
            token_hash=_hash(token),
            expires_at=now + timedelta(hours=SESSION_HOURS),
            ip=ip,
            user_agent=(user_agent or "")[:300],
            last_seen_at=now,
        )
    )
    db.flush()
    return token


def load_session(db: Session, token: str) -> UserSession | None:
    s = db.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
    if s is None or s.expires_at <= clock.now():
        return None
    return s


def touch_session(db: Session, s: UserSession) -> None:
    now = clock.now()
    if s.last_seen_at is None or (now - s.last_seen_at) >= timedelta(minutes=1):
        s.last_seen_at = now


def revoke_session(db: Session, token: str) -> None:
    s = db.scalar(select(UserSession).where(UserSession.token_hash == _hash(token)))
    if s is not None:
        db.delete(s)
