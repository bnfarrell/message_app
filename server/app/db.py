from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from flask import current_app
from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app import clock


def new_id() -> str:
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in the database, returns aware UTC to Python. Portable across engines."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime passed to UTCDateTime; use app.clock.now()")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str):
        self.url = url
        is_sqlite = url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        self.engine = create_engine(url, connect_args=connect_args)
        if is_sqlite:

            @event.listens_for(self.engine, "connect")
            def _set_pragmas(dbapi_conn, _record):
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA busy_timeout=5000")
                cur.close()

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        events: list = []
        try:
            yield db
            db.commit()
            events = db.info.pop("events", [])
        except Exception as exc:
            db.rollback()
            # The rollback above has already released any write lock this session held, so a
            # pending audit write (e.g. ConsentError.audit_write) can safely land on a brand-new
            # connection here — never on the still-open `db` above, which is what deadlocked it.
            audit_write = getattr(exc, "audit_write", None)
            if audit_write is not None:
                with self.SessionLocal() as audit_db:
                    audit_write(audit_db)
                    audit_db.commit()
            raise
        finally:
            db.close()
        if events:
            from app.realtime.broadcast import deliver

            for ev in events:
                deliver(ev)


def get_db() -> Database:
    return current_app.extensions["db"]


def run_migrations(url: str) -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    server_dir = Path(__file__).resolve().parent.parent
    cfg = AlembicConfig(str(server_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(server_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def utcnow() -> datetime:
    return clock.now()
