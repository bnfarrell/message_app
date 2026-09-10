# Phase 1 Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Flask/SQLAlchemy backend for the Phase 1 MVP — auth, property-scoped API, mock SMS in/out with consent, shared-inbox conversations, work orders with the closed-loop prompt, job worker, realtime WebSocket, mock PMS, seed data — passing the §11.1 acceptance tests.

**Architecture:** One Flask process built by an app factory. Blueprints validate with Pydantic and call a framework-free domain layer (`app/domain/*`) that takes `(db, property_id, ...)` everywhere. A SQLite-backed `job` table with an in-process worker thread replaces Redis/BullMQ; a flask-sock WebSocket with an in-memory connection registry and presence store replaces Redis pub/sub. Realtime events are queued on the SQLAlchemy session and flushed **after commit**.

**Tech Stack:** Python 3.14 · Flask 3 · SQLAlchemy 2.0 · Alembic · Pydantic v2 · bcrypt · flask-sock · pytest. SQLite now, PostgreSQL later by `DATABASE_URL`.

**Spec:** `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md` (read it; the plan argues from it). Full product spec: `docs/design.md`.

**Companion plan:** the React frontend is a separate plan written after this one ships (`docs/superpowers/plans/2026-09-XX-phase1-web.md`).

## Global Constraints

- Python `>=3.12` (3.14.7 on this machine). Run everything from `server/` with the repo-root venv activated: Git Bash `. ../.venv/Scripts/activate`, PowerShell `..\.venv\Scripts\Activate.ps1`. In commands below `python` means that venv.
- Every domain function signature starts `(db: Session, property_id: str, ...)` and every query filters on `property_id`. Exceptions: `auth`, `jobs`, `audit.record` (takes `property_id` as an optional field).
- Realtime events are never sent directly from domain code: call `realtime.broadcast.queue_event(db, property_id, type, payload)`; `Database.session()` delivers them after commit.
- `internal_note` is never joined into a guest-facing shape. `GuestThread` has `extra='forbid'`.
- Consent is enforced in `domain/messages.send`, nowhere else. Rejections raise `ConsentError` (HTTP 422, code `CONSENT_OPTED_OUT`), write an `audit_log` row, and create no `message` row.
- Time comes from `app/clock.py: now()` only — never `datetime.now()` in application code. All datetimes are timezone-aware UTC.
- JSON is camelCase on the wire (Pydantic `alias_generator=to_camel`), snake_case in Python and SQL.
- Error body shape: `{"error": {"code": str, "message": str, "details"?: any}}`.
- Session cookie is `sid`, `HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age=43200`.
- SQL stays portable: no SQLite-only functions; `Enum(native_enum=False)`, `JSON`, `UTCDateTime`.
- Table and column names are exactly those in spec §3.2 (the `session` table is named `user_session` to avoid keyword clashes; everything else verbatim).
- Commit after every task with the message given. Never commit `server/data/*.db` or `.venv`.

## File structure

```
.gitignore
.venv/                                   (not committed)
package.json                             root scripts: seed, server (web added by the web plan)
README.md
server/
  pyproject.toml                         deps, pytest, ruff
  alembic.ini
  alembic/env.py, script.py.mako, versions/0001_init.py
  run.py                                 dev entrypoint (threaded, reloader)
  app/__init__.py                        create_app()
  app/config.py                          Config dataclass, from_env()
  app/clock.py                           now(), freeze(), advance(), reset()
  app/db.py                              UTCDateTime, Base, Database, run_migrations(), get_db()
  app/errors.py                          AppError hierarchy + register_error_handlers()
  app/ratelimit.py                       RateLimiter + rate_limited()
  app/schemas/enums.py                   every StrEnum
  app/schemas/common.py                  CamelModel base
  app/schemas/{auth,conversations,work_orders,content,users,notifications,analytics,guests}.py
  app/schemas/export_json_schema.py      → web/src/api/schema.json
  app/models/__init__.py                 imports all models
  app/models/{core,guests,conversations,work_orders,content,infra}.py
  app/auth/{passwords,sessions,permissions,decorators}.py
  app/domain/{audit,notifications,sms,redaction,quick_replies,assets,categories,consent,guests,stays,
              conversations,messages,notes,work_orders,draft_prompts,users,analytics}.py
  app/queue/jobs.py                      enqueue, claim, complete/fail, ensure_recurring
  app/queue/worker.py                    Worker(app).start()/stop()/tick()
  app/queue/handlers/__init__.py         HANDLERS registry + @handler
  app/queue/handlers/{outbound,mock_delivery,sla,snooze,pms}.py
  app/channels/{base,mock_sms,registry,inbound}.py
  app/pms/{base,mock_pms,handle_event}.py
  app/realtime/{broadcast,registry,presence,ws}.py
  app/api/_util.py                       db_session(), parse_body(), ok()
  app/api/{health,auth,departments,users,conversations,work_orders,quick_replies,assets,categories,
           notifications,analytics,guests,hooks,dev,short_links}.py
  app/cli.py                             flask seed
  seed/seed.py, seed/data.py
  tests/conftest.py, tests/fixtures.py, tests/test_*.py
web/src/api/schema.json                  generated by Task 23 (consumed by the web plan)
```

---

### Task 1: Project scaffold, config, app factory, health route

**Files:**
- Create: `.gitignore`, `server/pyproject.toml`, `server/app/__init__.py`, `server/app/config.py`, `server/app/clock.py`, `server/app/errors.py`, `server/app/api/__init__.py`, `server/app/api/health.py`, `server/run.py`, `server/tests/__init__.py`, `server/tests/test_health.py`

**Interfaces:**
- Produces: `create_app(config: Config | None = None) -> Flask`; `Config` dataclass with fields `DATABASE_URL, SESSION_SECRET, MOCK_SMS_SECRET, SMS_ADAPTER, PMS_TICK_SECONDS, START_WORKER, CORS_ORIGIN, ENV, TESTING`; `clock.now() -> datetime`, `clock.freeze(dt)`, `clock.advance(seconds=…, minutes=…, hours=…)`, `clock.reset()`; `AppError(code, message, status, details=None)` and subclasses `NotFound, Unauthorized, Forbidden, ValidationFailed, ConsentError, TransitionError, Conflict`.

- [ ] **Step 1: Create the venv and verify the stack installs on Python 3.14**

Run from the repo root:
```bash
python -m venv .venv
. .venv/Scripts/activate
python -m pip install --upgrade pip
```
Expected: no errors. (If `python` resolves to something other than 3.14.x, use `py -3.14 -m venv .venv`.)

- [ ] **Step 2: Write `.gitignore` at the repo root**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
server/data/
*.db
*.db-wal
*.db-shm
node_modules/
web/dist/
.env
```

- [ ] **Step 3: Write `server/pyproject.toml`**

```toml
[project]
name = "concierge-server"
version = "0.1.0"
description = "Hotel guest engagement & operations platform — Phase 1 server"
requires-python = ">=3.12"
dependencies = [
  "flask>=3.1",
  "sqlalchemy>=2.0.36",
  "alembic>=1.14",
  "pydantic>=2.9",
  "bcrypt>=4.2",
  "flask-sock>=0.7",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.6", "simple-websocket>=1.1"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*", "seed*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
filterwarnings = ["error::DeprecationWarning:app.*"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP"]
```

- [ ] **Step 4: Install the server package in editable mode**

Run from `server/`:
```bash
cd server
pip install -e ".[dev]"
python -c "import flask, sqlalchemy, alembic, pydantic, bcrypt, flask_sock; print(flask.__version__, sqlalchemy.__version__, alembic.__version__, pydantic.VERSION, bcrypt.__version__)"
```
Expected: five version strings, no ImportError. If any package lacks a Python 3.14 wheel, stop and report which one before continuing.

- [ ] **Step 5: Write the failing health test**

`server/tests/__init__.py` — empty file.

`server/tests/test_health.py`:
```python
from app import create_app
from app.config import Config


def test_health_returns_ok():
    app = create_app(Config(TESTING=True, DATABASE_URL="sqlite:///:memory:"))
    client = app.test_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok"}


def test_unknown_route_uses_error_shape():
    app = create_app(Config(TESTING=True, DATABASE_URL="sqlite:///:memory:"))
    res = app.test_client().get("/api/nope")
    assert res.status_code == 404
    body = res.get_json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python -m pytest tests/test_health.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 7: Write `app/clock.py`**

```python
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
```

- [ ] **Step 8: Write `app/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass
class Config:
    DATABASE_URL: str = "sqlite:///data/app.db"
    SESSION_SECRET: str = "dev-secret-change-me"
    MOCK_SMS_SECRET: str = "dev"
    SMS_ADAPTER: str = "mock"
    PMS_TICK_SECONDS: int = 90
    START_WORKER: bool = False
    CORS_ORIGIN: str = "http://localhost:5173"
    ENV: str = "development"
    TESTING: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @classmethod
    def from_env(cls) -> Config:
        load_dotenv()
        return cls(
            DATABASE_URL=os.getenv("DATABASE_URL", cls.DATABASE_URL),
            SESSION_SECRET=os.getenv("SESSION_SECRET", cls.SESSION_SECRET),
            MOCK_SMS_SECRET=os.getenv("MOCK_SMS_SECRET", cls.MOCK_SMS_SECRET),
            SMS_ADAPTER=os.getenv("SMS_ADAPTER", cls.SMS_ADAPTER),
            PMS_TICK_SECONDS=int(os.getenv("PMS_TICK_SECONDS", cls.PMS_TICK_SECONDS)),
            START_WORKER=os.getenv("START_WORKER", "0") == "1",
            CORS_ORIGIN=os.getenv("CORS_ORIGIN", cls.CORS_ORIGIN),
            ENV=os.getenv("FLASK_ENV", cls.ENV),
        )
```

- [ ] **Step 9: Write `app/errors.py`**

```python
from __future__ import annotations

from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    status = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str | None = None, *, details: Any = None, code: str | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code.replace("_", " ").capitalize()
        self.details = details
        if code:
            self.code = code

    def to_body(self) -> dict:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details is not None:
            err["details"] = self.details
        return {"error": err}


class ValidationFailed(AppError):
    status = 400
    code = "VALIDATION_FAILED"


class Unauthorized(AppError):
    status = 401
    code = "UNAUTHORIZED"


class Forbidden(AppError):
    status = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status = 409
    code = "CONFLICT"


class TransitionError(AppError):
    status = 409
    code = "INVALID_TRANSITION"


class ConsentError(AppError):
    status = 422
    code = "CONSENT_OPTED_OUT"


class RateLimited(AppError):
    status = 429
    code = "RATE_LIMITED"


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(e: AppError):
        return jsonify(e.to_body()), e.status

    @app.errorhandler(ValidationError)
    def _pydantic_error(e: ValidationError):
        return jsonify(ValidationFailed("Invalid request", details=e.errors()).to_body()), 400

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        code = (e.name or "error").upper().replace(" ", "_")
        return jsonify({"error": {"code": code, "message": e.description}}), e.code or 500
```

- [ ] **Step 10: Write the health blueprint and the app factory**

`server/app/api/__init__.py` — empty file.

`server/app/api/health.py`:
```python
from flask import Blueprint, jsonify

bp = Blueprint("health", __name__)


@bp.get("/api/health")
def health():
    return jsonify({"status": "ok"})
```

`server/app/__init__.py`:
```python
from __future__ import annotations

from flask import Flask

from app.config import Config
from app.errors import register_error_handlers


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    app = Flask(__name__)
    app.config["APP"] = config
    app.config["TESTING"] = config.TESTING
    app.config["SECRET_KEY"] = config.SESSION_SECRET

    register_error_handlers(app)

    from app.api import health

    app.register_blueprint(health.bp)
    return app
```

`server/run.py`:
```python
from app import create_app
from app.config import Config

if __name__ == "__main__":
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=5000, debug=not cfg.is_production, threaded=True)
```

- [ ] **Step 11: Run the tests**

Run: `python -m pytest -q`
Expected: `2 passed`.

- [ ] **Step 12: Commit**

```bash
cd ..
git add .gitignore server
git commit -m "feat(server): scaffold Flask app factory, config, clock, error shape"
```

---

### Task 2: SQLAlchemy models, enums, and the initial Alembic migration

**Files:**
- Create: `server/app/db.py`, `server/app/schemas/__init__.py`, `server/app/schemas/enums.py`, `server/app/models/__init__.py`, `server/app/models/core.py`, `server/app/models/guests.py`, `server/app/models/conversations.py`, `server/app/models/work_orders.py`, `server/app/models/content.py`, `server/app/models/infra.py`, `server/alembic.ini`, `server/alembic/env.py`, `server/alembic/script.py.mako`, `server/alembic/versions/0001_init.py` (generated), `server/tests/test_models.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `Database(url).session()` context manager (commit on success, rollback on error); `get_db() -> Database` (from `current_app.extensions["db"]`); `run_migrations(url)`; `Base`; `UTCDateTime`; `new_id() -> str`; all model classes and all enums named below. Every model has `id`, `created_at`, `updated_at`.

- [ ] **Step 1: Write the failing model test**

`server/tests/test_models.py`:
```python
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import StatementError

from app.db import Database, run_migrations
from app.models import Conversation, Guest, Property
from app.schemas.enums import ConversationStatus, SmsConsentStatus

EXPECTED_TABLES = {
    "property", "user_account", "property_membership", "department", "guest", "stay",
    "conversation", "message", "internal_note", "resolution_category", "work_order",
    "work_order_event", "draft_prompt", "quick_reply", "digital_asset", "user_session",
    "job", "notification", "audit_log", "pms_event", "alembic_version",
}


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 't.db').as_posix()}"


def test_migration_creates_all_tables(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    names = set(inspect(database.engine).get_table_names())
    assert EXPECTED_TABLES <= names, EXPECTED_TABLES - names
    database.engine.dispose()


def test_sqlite_pragmas_applied(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    database.engine.dispose()


def test_enum_values_are_stored_as_values_and_validated(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.session() as db:
        p = Property(name="Test", code="TST", timezone="UTC")
        db.add(p)
        db.flush()
        g = Guest(property_id=p.id, phone_e164="+15550001111", first_name="A", last_name="B",
                  sms_consent_status=SmsConsentStatus.opted_in)
        db.add(g)
        db.flush()
        c = Conversation(property_id=p.id, guest_id=g.id, status=ConversationStatus.open)
        db.add(c)
    with database.engine.connect() as conn:
        raw = conn.execute(text("SELECT status FROM conversation")).scalar()
        assert raw == "open"
    with pytest.raises(StatementError):
        with database.session() as db:
            db.add(Conversation(property_id=p.id, guest_id=g.id, status="bogus"))
            db.flush()
    database.engine.dispose()


def test_utc_datetime_round_trips_aware(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.session() as db:
        p = Property(name="Test", code="TST", timezone="UTC")
        db.add(p)
    with database.session() as db:
        loaded = db.get(Property, p.id)
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset().total_seconds() == 0
        assert isinstance(loaded.created_at, datetime)
        assert loaded.created_at.tzinfo == timezone.utc
    database.engine.dispose()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_models.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Write `app/db.py`**

```python
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
        except Exception:
            db.rollback()
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
```

Note: `app.realtime.broadcast.deliver` is created in Task 7. Until then the import only runs if a session queued events, which nothing does yet.

- [ ] **Step 4: Write `app/schemas/__init__.py` (empty) and `app/schemas/enums.py`**

```python
from enum import StrEnum


class Role(StrEnum):
    agent = "agent"
    dept_staff = "dept_staff"
    supervisor = "supervisor"
    manager = "manager"
    admin = "admin"
    corporate = "corporate"


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"


class DepartmentType(StrEnum):
    front_desk = "front_desk"
    housekeeping = "housekeeping"
    engineering = "engineering"
    food_beverage = "food_beverage"
    spa = "spa"
    security = "security"
    valet = "valet"
    other = "other"


class SmsConsentStatus(StrEnum):
    unknown = "unknown"
    opted_in = "opted_in"
    opted_out = "opted_out"


class StayStatus(StrEnum):
    reserved = "reserved"
    checked_in = "checked_in"
    checked_out = "checked_out"
    cancelled = "cancelled"
    no_show = "no_show"


class ConversationStatus(StrEnum):
    open = "open"
    snoozed = "snoozed"
    archived = "archived"


class Channel(StrEnum):
    sms = "sms"
    web = "web"
    whatsapp = "whatsapp"
    email = "email"


class Direction(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class AuthorType(StrEnum):
    guest = "guest"
    staff = "staff"
    system = "system"
    automation = "automation"


class DeliveryStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    undelivered = "undelivered"


class WorkOrderType(StrEnum):
    maintenance = "maintenance"
    housekeeping = "housekeeping"
    guest_request = "guest_request"
    pm = "pm"
    other = "other"


class Priority(StrEnum):
    low = "low"
    normal = "normal"
    high = "high"
    urgent = "urgent"


class WorkOrderStatus(StrEnum):
    open = "open"
    assigned = "assigned"
    in_progress = "in_progress"
    blocked = "blocked"
    complete = "complete"
    verified = "verified"
    cancelled = "cancelled"


class LocationType(StrEnum):
    room = "room"
    public_area = "public_area"
    equipment = "equipment"
    other = "other"


class WorkOrderEventType(StrEnum):
    created = "created"
    status_changed = "status_changed"
    assigned = "assigned"
    commented = "commented"
    priority_changed = "priority_changed"


class DraftPromptStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    dismissed = "dismissed"


class AssetType(StrEnum):
    file = "file"
    link = "link"
    menu = "menu"
    map = "map"
    form = "form"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    dead = "dead"
```

- [ ] **Step 5: Write the model modules**

`server/app/models/core.py`:
```python
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, new_id, utcnow
from app.schemas.enums import DepartmentType, Role, UserStatus


def enum_type(enum_cls: type[StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        length=32,
        create_constraint=True,
        name=f"ck_enum_{enum_cls.__name__.lower()}",
        values_callable=lambda e: [m.value for m in e],
    )


class TimestampMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Property(TimestampMixin, Base):
    __tablename__ = "property"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    address: Mapped[str | None] = mapped_column(String(400))
    phone: Mapped[str | None] = mapped_column(String(32))
    sms_number: Mapped[str | None] = mapped_column(String(32))
    brand: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(16))
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_account"
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus), default=UserStatus.active, nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(String(200))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Department(TimestampMixin, Base):
    __tablename__ = "department"
    property_id: Mapped[str] = mapped_column(
        ForeignKey("property.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[DepartmentType] = mapped_column(enum_type(DepartmentType), nullable=False)
    escalation_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PropertyMembership(TimestampMixin, Base):
    __tablename__ = "property_membership"
    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_membership_user_property"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("property.id"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(enum_type(Role), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
```

`server/app/models/guests.py`:
```python
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import SmsConsentStatus, StayStatus


class Guest(TimestampMixin, Base):
    __tablename__ = "guest"
    __table_args__ = (UniqueConstraint("property_id", "phone_e164", name="uq_guest_property_phone"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    loyalty_program: Mapped[str | None] = mapped_column(String(50))
    loyalty_tier: Mapped[str | None] = mapped_column(String(50))
    loyalty_number: Mapped[str | None] = mapped_column(String(50))
    vip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pms_profile_id: Mapped[str | None] = mapped_column(String(100))
    sms_consent_status: Mapped[SmsConsentStatus] = mapped_column(
        enum_type(SmsConsentStatus), default=SmsConsentStatus.unknown, nullable=False
    )
    sms_consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sms_consent_source: Mapped[str | None] = mapped_column(String(50))
    notes_summary: Mapped[str | None] = mapped_column(String(2000))


class Stay(TimestampMixin, Base):
    __tablename__ = "stay"
    __table_args__ = (Index("ix_stay_property_status", "property_id", "status"),)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guest.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    pms_reservation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    room_number: Mapped[str | None] = mapped_column(String(10))
    room_type: Mapped[str | None] = mapped_column(String(50))
    rate_code: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[StayStatus] = mapped_column(
        enum_type(StayStatus), default=StayStatus.reserved, nullable=False
    )
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_checkin_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    actual_checkout_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    children: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(50))
    market_segment: Mapped[str | None] = mapped_column(String(50))
    is_return_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stay_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_pms: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
```

`server/app/models/conversations.py`:
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.models.guests import Guest, Stay
from app.schemas.enums import AuthorType, Channel, ConversationStatus, DeliveryStatus, Direction


class ResolutionCategory(TimestampMixin, Base):
    __tablename__ = "resolution_category"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("resolution_category.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (
        Index("ix_conversation_property_status", "property_id", "status"),
        Index("ix_conversation_property_sla", "property_id", "sla_due_at"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guest.id"), nullable=False, index=True)
    stay_id: Mapped[str | None] = mapped_column(ForeignKey("stay.id"))
    status: Mapped[ConversationStatus] = mapped_column(
        enum_type(ConversationStatus), default=ConversationStatus.open, nullable=False
    )
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    assigned_department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    channel_primary: Mapped[Channel] = mapped_column(
        enum_type(Channel), default=Channel.sms, nullable=False
    )
    last_guest_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_staff_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_response_seconds: Mapped[int | None] = mapped_column(Integer)
    sla_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sla_breach_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_category_id: Mapped[str | None] = mapped_column(ForeignKey("resolution_category.id"))
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    guest: Mapped[Guest] = relationship(Guest, lazy="joined")
    stay: Mapped[Stay | None] = relationship(Stay, lazy="joined")


class Message(TimestampMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_conversation_sent", "conversation_id", "sent_at"),
        UniqueConstraint("property_id", "provider_message_id", name="uq_message_property_provider"),
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    direction: Mapped[Direction] = mapped_column(enum_type(Direction), nullable=False)
    author_type: Mapped[AuthorType] = mapped_column(enum_type(AuthorType), nullable=False)
    author_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    channel: Mapped[Channel] = mapped_column(enum_type(Channel), default=Channel.sms, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    digital_asset_id: Mapped[str | None] = mapped_column(ForeignKey("digital_asset.id"))
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        enum_type(DeliveryStatus), default=DeliveryStatus.queued, nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    provider_error_code: Mapped[str | None] = mapped_column(String(50))
    provider_error_message: Mapped[str | None] = mapped_column(String(500))
    redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class InternalNote(TimestampMixin, Base):
    """NEVER joined into any guest-facing query. Separate table by design (spec §3.2)."""

    __tablename__ = "internal_note"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
```

`server/app/models/work_orders.py`:
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import (
    DraftPromptStatus,
    LocationType,
    Priority,
    WorkOrderEventType,
    WorkOrderStatus,
    WorkOrderType,
)


class WorkOrder(TimestampMixin, Base):
    __tablename__ = "work_order"
    __table_args__ = (Index("ix_work_order_property_status", "property_id", "status"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[WorkOrderType] = mapped_column(enum_type(WorkOrderType), nullable=False)
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority), default=Priority.normal, nullable=False
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        enum_type(WorkOrderStatus), default=WorkOrderStatus.open, nullable=False
    )
    location_type: Mapped[LocationType] = mapped_column(
        enum_type(LocationType), default=LocationType.room, nullable=False
    )
    location_ref: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    reported_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    source_conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation.id"), index=True
    )
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("message.id"))
    attachments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    guest_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WorkOrderEvent(TimestampMixin, Base):
    __tablename__ = "work_order_event"
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_order.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    type: Mapped[WorkOrderEventType] = mapped_column(enum_type(WorkOrderEventType), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(100))
    to_value: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)


class DraftPrompt(TimestampMixin, Base):
    """The unsent, editable closed-loop message (design.md §6.4)."""

    __tablename__ = "draft_prompt"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftPromptStatus] = mapped_column(
        enum_type(DraftPromptStatus), default=DraftPromptStatus.pending, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
```

`server/app/models/content.py`:
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import AssetType


class QuickReply(TimestampMixin, Base):
    __tablename__ = "quick_reply"
    __table_args__ = (UniqueConstraint("property_id", "shortcut", name="uq_quick_reply_shortcut"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    shortcut: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DigitalAsset(TimestampMixin, Base):
    __tablename__ = "digital_asset"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[AssetType] = mapped_column(enum_type(AssetType), default=AssetType.link, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    short_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

`server/app/models/infra.py`:
```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import JobStatus


class UserSession(TimestampMixin, Base):
    __tablename__ = "user_session"
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Job(TimestampMixin, Base):
    __tablename__ = "job"
    __table_args__ = (Index("ix_job_status_run_at", "status", "run_at"),)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus), default=JobStatus.queued, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Notification(TimestampMixin, Base):
    __tablename__ = "notification"
    __table_args__ = (Index("ix_notification_user_read", "user_id", "read_at"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(String(1000))
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuditLog(TimestampMixin, Base):
    """Append-only. The domain layer exposes only audit.record()."""

    __tablename__ = "audit_log"
    property_id: Mapped[str | None] = mapped_column(ForeignKey("property.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(36))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(300))


class PmsEvent(TimestampMixin, Base):
    __tablename__ = "pms_event"
    __table_args__ = (
        UniqueConstraint("integration_key", "external_id", "event_type", name="uq_pms_event_idem"),
    )
    integration_key: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    error: Mapped[str | None] = mapped_column(Text)
```

`server/app/models/__init__.py`:
```python
from app.models.content import DigitalAsset, QuickReply
from app.models.conversations import Conversation, InternalNote, Message, ResolutionCategory
from app.models.core import Department, Property, PropertyMembership, UserAccount
from app.models.guests import Guest, Stay
from app.models.infra import AuditLog, Job, Notification, PmsEvent, UserSession
from app.models.work_orders import DraftPrompt, WorkOrder, WorkOrderEvent

__all__ = [
    "AuditLog", "Conversation", "Department", "DigitalAsset", "DraftPrompt", "Guest",
    "InternalNote", "Job", "Message", "Notification", "PmsEvent", "Property",
    "PropertyMembership", "QuickReply", "ResolutionCategory", "Stay", "UserAccount",
    "UserSession", "WorkOrder", "WorkOrderEvent",
]
```

- [ ] **Step 6: Configure Alembic**

`server/alembic.ini`:
```ini
[alembic]
script_location = alembic
prepend_sys_path = .
file_template = %%(rev)s_%%(slug)s

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

`server/alembic/env.py`:
```python
import os

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.db import Base

config = context.config
url = config.get_main_option("sqlalchemy.url") or os.environ.get(
    "DATABASE_URL", "sqlite:///data/app.db"
)
config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`server/alembic/script.py.mako`:
```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Create the empty directory `server/alembic/versions/` (add a `.gitkeep`).

- [ ] **Step 7: Generate the initial migration**

Run from `server/`:
```bash
mkdir -p data
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic revision --autogenerate -m init --rev-id 0001
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic upgrade head
DATABASE_URL=sqlite:///data/migrate-check.db python -m alembic check
rm data/migrate-check.db
```
Expected: `alembic/versions/0001_init.py` created containing `op.create_table("property", ...)` etc.; `upgrade head` succeeds; `alembic check` prints `No new upgrade operations detected.` Open the generated file and confirm every table from `EXPECTED_TABLES` (except `alembic_version`) has a `create_table`. Do not hand-edit it except to fix an autogenerate error.

(PowerShell equivalent of the env prefix: `$env:DATABASE_URL="sqlite:///data/migrate-check.db"; python -m alembic upgrade head`.)

- [ ] **Step 8: Register the database on the app**

Modify `server/app/__init__.py` — add after `app.config["SECRET_KEY"] = ...`:
```python
    from app.db import Database

    app.extensions["db"] = Database(config.DATABASE_URL)
```

- [ ] **Step 9: Run the tests**

Run: `python -m pytest -q`
Expected: `6 passed`.

- [ ] **Step 10: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SQLAlchemy models, enums, and initial Alembic migration"
```

---

### Task 3: Test infrastructure — app fixture, template DB, fixture data, login helper

**Files:**
- Create: `server/tests/conftest.py`, `server/tests/fixtures.py`, `server/tests/test_fixtures.py`

**Interfaces:**
- Produces (pytest fixtures): `app` (Flask app on a fresh DB copy, clock frozen at `2026-09-10T12:00:00Z`), `client`, `database`, `fx: Fixture`, `login(email) -> FlaskClient`. `Fixture` dataclass fields: `property_a, property_b, dept_front_desk, dept_housekeeping, dept_engineering, agent_a, agent_a2, engineer_a, housekeeper_a, supervisor_a, manager_a, admin_a, corporate_a, admin_b, agent_b, guest_inhouse_a, stay_inhouse_a, guest_nostay_a, guest_b, stay_b` (all model instances; ids via `.id`). Password for every fixture user: `Password123!`.
- Consumes: Task 4's `hash_password`. Until Task 4 lands, `fixtures.py` uses `bcrypt` directly with the same algorithm (cost 12) so this task is testable now; Task 4 switches it to `app.auth.passwords.hash_password`.

- [ ] **Step 1: Write the failing fixture test**

`server/tests/test_fixtures.py`:
```python
from sqlalchemy import func, select

from app.models import Guest, PropertyMembership, UserAccount


def test_fixture_loads_two_properties_and_users(app, fx, database):
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(UserAccount)) == 11
        assert db.scalar(select(func.count()).select_from(PropertyMembership)) == 11
        assert db.scalar(select(func.count()).select_from(Guest)) == 3
    assert fx.property_a.id != fx.property_b.id
    assert fx.stay_inhouse_a.room_number == "412"


def test_clock_is_frozen(app):
    from app import clock

    assert clock.now().isoformat() == "2026-09-10T12:00:00+00:00"


def test_each_test_gets_a_fresh_database(app, database):
    from app.models import Property

    with database.session() as db:
        db.add(Property(name="Scratch", code="SCR", timezone="UTC"))
    # The next test's assertion on counts would fail if this leaked.
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_fixtures.py -q`
Expected: FAIL with `fixture 'fx' not found`.

- [ ] **Step 3: Write `tests/fixtures.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import bcrypt
from sqlalchemy.orm import Session

from app import clock
from app.models import (
    Department,
    Guest,
    Property,
    PropertyMembership,
    Stay,
    UserAccount,
)
from app.schemas.enums import DepartmentType, Role, SmsConsentStatus, StayStatus

PASSWORD = "Password123!"


def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=4)).decode()  # low cost: tests only


@dataclass
class Fixture:
    property_a: Property
    property_b: Property
    dept_front_desk: Department
    dept_housekeeping: Department
    dept_engineering: Department
    agent_a: UserAccount
    agent_a2: UserAccount
    engineer_a: UserAccount
    housekeeper_a: UserAccount
    supervisor_a: UserAccount
    manager_a: UserAccount
    admin_a: UserAccount
    corporate_a: UserAccount
    admin_b: UserAccount
    agent_b: UserAccount
    guest_inhouse_a: Guest
    stay_inhouse_a: Stay
    guest_nostay_a: Guest
    guest_b: Guest
    stay_b: Stay


def _user(db: Session, email: str, first: str, last: str) -> UserAccount:
    u = UserAccount(email=email, first_name=first, last_name=last, password_hash=_hash(PASSWORD))
    db.add(u)
    db.flush()
    return u


def _member(db: Session, user: UserAccount, prop: Property, role: Role,
            dept: Department | None = None) -> None:
    db.add(PropertyMembership(user_id=user.id, property_id=prop.id, role=role,
                              department_id=dept.id if dept else None))


def load_fixture(db: Session) -> Fixture:
    today = clock.now().date()
    a = Property(name="Harbourview Hotel", code="HVH", timezone="America/New_York",
                 sms_number="+15550100",
                 settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                           "help_text": "Harbourview Hotel: text us anytime or call +1 555 0100."})
    b = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago", sms_number="+15550200",
                 settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                           "help_text": "Lakeside Inn: call +1 555 0200."})
    db.add_all([a, b])
    db.flush()

    fd = Department(property_id=a.id, name="Front Desk", type=DepartmentType.front_desk)
    hk = Department(property_id=a.id, name="Housekeeping", type=DepartmentType.housekeeping)
    eng = Department(property_id=a.id, name="Engineering", type=DepartmentType.engineering)
    fd_b = Department(property_id=b.id, name="Front Desk", type=DepartmentType.front_desk)
    db.add_all([fd, hk, eng, fd_b])
    db.flush()

    agent_a = _user(db, "agent@hvh.test", "Ava", "Agent")
    agent_a2 = _user(db, "agent2@hvh.test", "Marcus", "Reyes")
    engineer_a = _user(db, "engineer@hvh.test", "Eli", "Engineer")
    housekeeper_a = _user(db, "housekeeper@hvh.test", "Hana", "Keeper")
    supervisor_a = _user(db, "supervisor@hvh.test", "Sam", "Super")
    manager_a = _user(db, "manager@hvh.test", "Morgan", "Manager")
    admin_a = _user(db, "admin@hvh.test", "Alex", "Admin")
    corporate_a = _user(db, "corporate@hvh.test", "Casey", "Corp")
    admin_b = _user(db, "admin@lsi.test", "Blake", "Admin")
    agent_b = _user(db, "agent@lsi.test", "Bea", "Agent")
    shared = _user(db, "regional@group.test", "Riley", "Regional")  # manager at both properties

    _member(db, agent_a, a, Role.agent, fd)
    _member(db, agent_a2, a, Role.agent, fd)
    _member(db, engineer_a, a, Role.dept_staff, eng)
    _member(db, housekeeper_a, a, Role.dept_staff, hk)
    _member(db, supervisor_a, a, Role.supervisor, eng)
    _member(db, manager_a, a, Role.manager)
    _member(db, admin_a, a, Role.admin)
    _member(db, corporate_a, a, Role.corporate)
    _member(db, admin_b, b, Role.admin)
    _member(db, agent_b, b, Role.agent, fd_b)
    _member(db, shared, b, Role.manager)

    guest_inhouse_a = Guest(property_id=a.id, first_name="Sarah", last_name="Chen",
                            phone_e164="+15551234567", loyalty_tier="Gold",
                            sms_consent_status=SmsConsentStatus.opted_in,
                            sms_consent_at=clock.now(), sms_consent_source="pms")
    guest_nostay_a = Guest(property_id=a.id, first_name="Diego", last_name="Ruiz",
                           phone_e164="+15559876543", sms_consent_status=SmsConsentStatus.opted_in,
                           sms_consent_at=clock.now(), sms_consent_source="inbound_sms")
    guest_b = Guest(property_id=b.id, first_name="Nia", last_name="Okafor",
                    phone_e164="+15557778888", sms_consent_status=SmsConsentStatus.opted_in,
                    sms_consent_at=clock.now(), sms_consent_source="pms")
    db.add_all([guest_inhouse_a, guest_nostay_a, guest_b])
    db.flush()

    stay_inhouse_a = Stay(guest_id=guest_inhouse_a.id, property_id=a.id, pms_reservation_id="RES-412",
                          room_number="412", room_type="King", status=StayStatus.checked_in,
                          arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 3),
                          actual_checkin_at=clock.now())
    stay_b = Stay(guest_id=guest_b.id, property_id=b.id, pms_reservation_id="RES-B-101",
                  room_number="101", room_type="Queen", status=StayStatus.checked_in,
                  arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 1),
                  actual_checkin_at=clock.now())
    db.add_all([stay_inhouse_a, stay_b])
    db.flush()

    return Fixture(
        property_a=a, property_b=b, dept_front_desk=fd, dept_housekeeping=hk, dept_engineering=eng,
        agent_a=agent_a, agent_a2=agent_a2, engineer_a=engineer_a, housekeeper_a=housekeeper_a,
        supervisor_a=supervisor_a, manager_a=manager_a, admin_a=admin_a, corporate_a=corporate_a,
        admin_b=admin_b, agent_b=agent_b, guest_inhouse_a=guest_inhouse_a,
        stay_inhouse_a=stay_inhouse_a, guest_nostay_a=guest_nostay_a, guest_b=guest_b, stay_b=stay_b,
    )
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
from __future__ import annotations

import shutil
from datetime import datetime, timezone

import pytest

from app import clock, create_app
from app.config import Config
from app.db import run_migrations
from tests.fixtures import PASSWORD, load_fixture

FROZEN = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="session")
def template_db_path(tmp_path_factory):
    path = tmp_path_factory.mktemp("template") / "template.db"
    run_migrations(f"sqlite:///{path.as_posix()}")
    return path


@pytest.fixture()
def app(template_db_path, tmp_path):
    db_path = tmp_path / "test.db"
    shutil.copy(template_db_path, db_path)
    clock.freeze(FROZEN)
    cfg = Config(
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        TESTING=True,
        START_WORKER=False,
        ENV="testing",
        PMS_TICK_SECONDS=0,
    )
    application = create_app(cfg)
    yield application
    application.extensions["db"].engine.dispose()
    clock.reset()


@pytest.fixture()
def database(app):
    return app.extensions["db"]


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def fx(database):
    with database.session() as db:
        return load_fixture(db)


@pytest.fixture()
def login(app):
    def _login(email: str, password: str = PASSWORD):
        c = app.test_client()
        res = c.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.get_json()
        return c

    return _login
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q`
Expected: `9 passed`.

- [ ] **Step 6: Commit**

```bash
cd ..
git add server/tests
git commit -m "test(server): app/database fixtures, deterministic fixture data, frozen clock"
```

---
