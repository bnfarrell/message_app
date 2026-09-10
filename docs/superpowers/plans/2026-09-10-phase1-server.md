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

### Task 4: Authentication — passwords, sessions, decorators, permissions, rate limiting

**Files:**
- Create: `server/app/auth/__init__.py`, `server/app/auth/passwords.py`, `server/app/auth/sessions.py`, `server/app/auth/permissions.py`, `server/app/auth/decorators.py`, `server/app/ratelimit.py`, `server/app/schemas/common.py`, `server/app/schemas/auth.py`, `server/app/api/_util.py`, `server/app/api/auth.py`, `server/app/domain/__init__.py`, `server/app/domain/audit.py`, `server/tests/test_auth.py`
- Modify: `server/app/__init__.py`, `server/tests/fixtures.py` (use `hash_password`), `server/tests/conftest.py` (reset limiters), `server/pyproject.toml` (`pydantic[email]`)

**Interfaces:**
- Produces: `hash_password(pw, rounds=12) -> str`, `verify_password(pw, hash) -> bool`; `create_session(db, user_id, ip, user_agent) -> str` (raw token), `load_session(db, token) -> UserSession | None`, `touch_session(db, s)`, `revoke_session(db, token)`, constants `COOKIE_NAME="sid"`, `SESSION_HOURS=12`; decorators `require_auth`, `require_property`, `require_role(*roles)`, `require_capability(cap)` setting `g.user`, `g.session_token`, `g.property_id`, `g.membership`; `has_capability(role, cap) -> bool`; `RateLimiter(limit, window_seconds).allow(key) -> bool`, `.reset()`, `rate_limited(limiter)`, module-level `login_limiter`, `webhook_limiter`; `CamelModel`; `db_session()` context manager; `parse_body(Model)`, `parse_query(Model)`, `serialize(obj)`, `ok(payload, status=200)`, `no_content()`, `client_meta() -> (ip, user_agent)`; `audit.record(db, property_id, actor_user_id, action, entity_type, entity_id, *, before=None, after=None, ip=None, user_agent=None)`.

- [ ] **Step 1: Write the failing auth tests**

`server/tests/test_auth.py`:
```python
from sqlalchemy import select

from app import clock
from app.models import AuditLog


def test_login_sets_cookie_and_me_returns_memberships(app, fx, client):
    res = client.post("/api/auth/login", json={"email": "agent@hvh.test", "password": "Password123!"})
    assert res.status_code == 200
    cookie = res.headers.get("Set-Cookie", "")
    assert "sid=" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    body = res.get_json()
    assert body["user"]["email"] == "agent@hvh.test"
    assert body["memberships"][0]["role"] == "agent"
    assert body["memberships"][0]["propertyId"] == fx.property_a.id

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.get_json()["user"]["firstName"] == "Ava"


def test_login_rejects_bad_password_and_unknown_email(app, fx, client):
    bad = client.post("/api/auth/login", json={"email": "agent@hvh.test", "password": "nope"})
    assert bad.status_code == 401
    assert bad.get_json()["error"]["code"] == "UNAUTHORIZED"
    unknown = client.post("/api/auth/login", json={"email": "ghost@hvh.test", "password": "Password123!"})
    assert unknown.status_code == 401


def test_login_validates_body(app, fx, client):
    res = client.post("/api/auth/login", json={"email": "not-an-email"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_me_requires_session(app, client):
    assert client.get("/api/auth/me").status_code == 401


def test_logout_revokes_session(app, fx, login):
    c = login("agent@hvh.test")
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_expired_session_is_rejected(app, fx, login):
    c = login("agent@hvh.test")
    clock.advance(hours=13)
    assert c.get("/api/auth/me").status_code == 401


def test_login_is_rate_limited(app, fx, client):
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "agent@hvh.test", "password": "nope"})
    res = client.post("/api/auth/login", json={"email": "agent@hvh.test", "password": "nope"})
    assert res.status_code == 429


def test_login_and_logout_are_audited(app, fx, login, database):
    c = login("agent@hvh.test")
    c.post("/api/auth/logout")
    with database.session() as db:
        actions = [a.action for a in db.scalars(select(AuditLog)).all()]
    assert "auth.login" in actions and "auth.logout" in actions


def test_disabled_user_cannot_login(app, fx, client, database):
    from app.models import UserAccount
    from app.schemas.enums import UserStatus

    with database.session() as db:
        u = db.get(UserAccount, fx.agent_a.id)
        u.status = UserStatus.disabled
    res = client.post("/api/auth/login", json={"email": "agent@hvh.test", "password": "Password123!"})
    assert res.status_code == 401
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_auth.py -q`
Expected: FAIL — `404` on `/api/auth/login` and assertion errors from the `login` fixture.

- [ ] **Step 3: Add the email extra and write `app/auth/passwords.py`; switch the fixture to it**

In `server/pyproject.toml` replace `"pydantic>=2.9",` with `"pydantic[email]>=2.9",` then run `pip install -e ".[dev]"`.

`server/app/auth/__init__.py` — empty.

`server/app/auth/passwords.py`:
```python
import bcrypt

ROUNDS = 12


def hash_password(password: str, rounds: int = ROUNDS) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False
```

In `server/tests/fixtures.py` replace `import bcrypt` and the `_hash` function with:
```python
from app.auth.passwords import hash_password


def _hash(pw: str) -> str:
    return hash_password(pw, rounds=4)  # low cost: tests only
```

- [ ] **Step 4: Write `app/auth/sessions.py`**

```python
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
```

- [ ] **Step 5: Write `app/auth/permissions.py`**

```python
from app.schemas.enums import Role

STAFF = {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin, Role.corporate}

# Mirrors docs/design.md §3.2 for the Phase 1 capabilities.
CAPABILITIES: dict[str, set[Role]] = {
    "view_all_conversations": {Role.agent, Role.supervisor, Role.manager, Role.admin, Role.corporate},
    "reply": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "assign": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "add_note": STAFF,
    "archive": {Role.agent, Role.supervisor, Role.manager, Role.admin},
    "create_work_order": {Role.agent, Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "close_work_order": {Role.dept_staff, Role.supervisor, Role.manager, Role.admin},
    "view_property_analytics": {Role.supervisor, Role.manager, Role.admin, Role.corporate},
    "view_own_stats": {Role.agent, Role.dept_staff},
    "manage_admin": {Role.admin, Role.corporate},
    "export": {Role.manager, Role.admin, Role.corporate},
}


def has_capability(role: Role, capability: str) -> bool:
    return role in CAPABILITIES.get(capability, set())
```

- [ ] **Step 6: Write `app/ratelimit.py`**

```python
from __future__ import annotations

import threading
from collections import deque
from functools import wraps

from flask import request

from app import clock
from app.errors import RateLimited


class RateLimiter:
    """Sliding-window limiter, in-memory, per key. Single process by design."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = clock.now().timestamp()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def rate_limited(limiter: RateLimiter):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            key = request.headers.get("X-Forwarded-For", request.remote_addr or "?").split(",")[0]
            if not limiter.allow(key):
                raise RateLimited("Too many requests, slow down")
            return fn(*a, **kw)

        return wrapper

    return deco


login_limiter = RateLimiter(limit=10, window_seconds=60)
webhook_limiter = RateLimiter(limit=60, window_seconds=60)
```

- [ ] **Step 7: Write the Pydantic base and auth schemas**

`server/app/schemas/common.py`:
```python
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """camelCase on the wire, snake_case in Python. Strict: unknown fields are rejected."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        from_attributes=True,
    )
```

`server/app/schemas/auth.py`:
```python
from pydantic import EmailStr, Field

from app.schemas.common import CamelModel
from app.schemas.enums import Role


class LoginRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    locale: str


class MembershipOut(CamelModel):
    property_id: str
    property_name: str
    property_code: str
    role: Role
    department_id: str | None = None


class SessionOut(CamelModel):
    user: UserOut
    memberships: list[MembershipOut]
```

- [ ] **Step 8: Write `app/api/_util.py`**

```python
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, TypeVar

from flask import jsonify, request
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ValidationFailed

M = TypeVar("M", bound=BaseModel)


@contextmanager
def db_session() -> Iterator[Session]:
    with get_db().session() as db:
        yield db


def parse_body(model: type[M]) -> M:
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict() if request.form else {}
    try:
        return model.model_validate(data)
    except ValidationError as e:
        raise ValidationFailed("Invalid request body", details=e.errors(include_url=False)) from e


def parse_query(model: type[M]) -> M:
    try:
        return model.model_validate(request.args.to_dict())
    except ValidationError as e:
        raise ValidationFailed("Invalid query", details=e.errors(include_url=False)) from e


def serialize(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    if isinstance(obj, list):
        return [serialize(o) for o in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj


def ok(payload: Any, status: int = 200):
    return jsonify(serialize(payload)), status


def no_content():
    return "", 204


def client_meta() -> tuple[str | None, str | None]:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0] or None
    return ip, request.headers.get("User-Agent")
```

- [ ] **Step 9: Write `app/domain/audit.py` (the only writer of `audit_log`)**

`server/app/domain/__init__.py` — empty.

`server/app/domain/audit.py`:
```python
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(
    db: Session,
    property_id: str | None,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    *,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    """Append-only. Nothing else in the codebase writes to audit_log."""
    row = AuditLog(
        property_id=property_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip=ip,
        user_agent=user_agent[:300] if user_agent else None,
    )
    db.add(row)
    return row
```

- [ ] **Step 10: Write `app/auth/decorators.py`**

```python
from __future__ import annotations

from functools import wraps

from flask import g, request
from sqlalchemy import select

from app.auth.permissions import has_capability
from app.auth.sessions import COOKIE_NAME, load_session, touch_session
from app.db import get_db
from app.errors import Forbidden, Unauthorized
from app.models import PropertyMembership, UserAccount
from app.schemas.enums import Role, UserStatus


def require_auth(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            raise Unauthorized("Sign in required")
        with get_db().session() as db:
            s = load_session(db, token)
            if s is None:
                raise Unauthorized("Session expired")
            user = db.get(UserAccount, s.user_id)
            if user is None or user.status != UserStatus.active:
                raise Unauthorized("Account disabled")
            touch_session(db, s)
            g.user = user
            g.session_token = token
        return fn(*a, **kw)

    return wrapper


def require_property(fn):
    """Loads g.membership for (g.user, <property_id>) or raises 403. Must follow require_auth."""

    @wraps(fn)
    def wrapper(*a, **kw):
        property_id = kw.get("property_id")
        if not property_id:
            raise Forbidden("Property required")
        with get_db().session() as db:
            m = db.scalar(
                select(PropertyMembership).where(
                    PropertyMembership.user_id == g.user.id,
                    PropertyMembership.property_id == property_id,
                )
            )
        if m is None:
            raise Forbidden("No access to this property")
        g.property_id = property_id
        g.membership = m
        return fn(*a, **kw)

    return wrapper


def require_role(*roles: Role):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.membership.role not in roles:
                raise Forbidden("Your role cannot do that")
            return fn(*a, **kw)

        return wrapper

    return deco


def require_capability(capability: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not has_capability(g.membership.role, capability):
                raise Forbidden(f"Your role lacks '{capability}'")
            return fn(*a, **kw)

        return wrapper

    return deco
```

- [ ] **Step 11: Write the auth blueprint**

`server/app/api/auth.py`:
```python
from __future__ import annotations

from flask import Blueprint, g, make_response
from sqlalchemy import select

from app.api._util import client_meta, db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth
from app.auth.passwords import verify_password
from app.auth.sessions import COOKIE_NAME, SESSION_HOURS, create_session, revoke_session
from app.domain import audit
from app.errors import Unauthorized
from app.models import Property, PropertyMembership, UserAccount
from app.ratelimit import login_limiter, rate_limited
from app.schemas.auth import LoginRequest, MembershipOut, SessionOut, UserOut
from app.schemas.enums import UserStatus

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _session_out(db, user: UserAccount) -> SessionOut:
    rows = db.execute(
        select(PropertyMembership, Property)
        .join(Property, Property.id == PropertyMembership.property_id)
        .where(PropertyMembership.user_id == user.id)
        .order_by(Property.name)
    ).all()
    return SessionOut(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipOut(property_id=p.id, property_name=p.name, property_code=p.code,
                          role=m.role, department_id=m.department_id)
            for m, p in rows
        ],
    )


@bp.post("/login")
@rate_limited(login_limiter)
def login():
    body = parse_body(LoginRequest)
    ip, ua = client_meta()
    with db_session() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == body.email.lower()))
        if user is None or user.status != UserStatus.active or not verify_password(
            body.password, user.password_hash
        ):
            audit.record(db, None, None, "auth.login_failed", "user_account",
                         user.id if user else None, after={"email": body.email}, ip=ip, user_agent=ua)
            raise Unauthorized("Email or password is incorrect")
        token = create_session(db, user.id, ip, ua)
        audit.record(db, None, user.id, "auth.login", "user_account", user.id, ip=ip, user_agent=ua)
        payload = _session_out(db, user)
    resp = make_response(ok(payload)[0], 200)
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_HOURS * 3600, httponly=True,
                    samesite="Lax", path="/", secure=False)
    return resp


@bp.post("/logout")
@require_auth
def logout():
    ip, ua = client_meta()
    with db_session() as db:
        revoke_session(db, g.session_token)
        audit.record(db, None, g.user.id, "auth.logout", "user_account", g.user.id, ip=ip, user_agent=ua)
    resp = make_response(no_content())
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@bp.get("/me")
@require_auth
def me():
    with db_session() as db:
        user = db.get(UserAccount, g.user.id)
        return ok(_session_out(db, user))
```

Note on the failed-login audit: `raise Unauthorized` inside `with db_session()` rolls the session back, so the `auth.login_failed` row is lost. Fix it the simple way: move the failed branch out of the `with` — load the user in one session, and if the check fails open a second short `with db_session() as db:` that writes only the audit row, then raise. Structure the final code as:

```python
    with db_session() as db:
        user = db.scalar(select(UserAccount).where(UserAccount.email == body.email.lower()))
        valid = (user is not None and user.status == UserStatus.active
                 and verify_password(body.password, user.password_hash))
        if valid:
            token = create_session(db, user.id, ip, ua)
            audit.record(db, None, user.id, "auth.login", "user_account", user.id, ip=ip, user_agent=ua)
            payload = _session_out(db, user)
    if not valid:
        with db_session() as db:
            audit.record(db, None, None, "auth.login_failed", "user_account",
                         user.id if user else None, after={"email": body.email}, ip=ip, user_agent=ua)
        raise Unauthorized("Email or password is incorrect")
```

- [ ] **Step 12: Register the blueprint and reset limiters in tests**

In `server/app/__init__.py` replace the blueprint block with:
```python
    from app.api import auth, health

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
```

In `server/tests/conftest.py`, inside the `app` fixture before `yield application`, add:
```python
    from app.ratelimit import login_limiter, webhook_limiter

    login_limiter.reset()
    webhook_limiter.reset()
```

- [ ] **Step 13: Run the tests**

Run: `python -m pytest -q`
Expected: all pass (`18 passed`).

- [ ] **Step 14: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): password auth, server-side sessions, role/capability decorators, rate limiting"
```

---

### Task 5: First property-scoped routes + the automated property-isolation suite (§11.1 #9)

**Files:**
- Create: `server/app/schemas/users.py`, `server/app/domain/users.py`, `server/app/api/departments.py`, `server/app/api/users.py`, `server/tests/test_isolation.py`, `server/tests/test_departments_users.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `GET /api/p/<property_id>/departments`, `GET /api/p/<property_id>/users`; `DepartmentOut`, `StaffUserOut`; `domain.users.list_departments(db, property_id)`, `list_staff(db, property_id)`, `members_of_department(db, property_id, department_id) -> list[str]`; the isolation test that auto-discovers every `/api/p/<property_id>/...` rule.
- Consumes: Task 4 decorators and `_util`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_departments_users.py`:
```python
def test_departments_lists_only_this_property(app, fx, login):
    c = login("agent@hvh.test")
    res = c.get(f"/api/p/{fx.property_a.id}/departments")
    assert res.status_code == 200
    names = sorted(d["name"] for d in res.get_json())
    assert names == ["Engineering", "Front Desk", "Housekeeping"]


def test_users_lists_staff_with_roles(app, fx, login):
    c = login("agent@hvh.test")
    res = c.get(f"/api/p/{fx.property_a.id}/users")
    assert res.status_code == 200
    rows = {u["email"]: u for u in res.get_json()}
    assert rows["engineer@hvh.test"]["role"] == "dept_staff"
    assert rows["engineer@hvh.test"]["departmentId"] == fx.dept_engineering.id
    assert "admin@lsi.test" not in rows
    assert "passwordHash" not in rows["engineer@hvh.test"]
```

`server/tests/test_isolation.py`:
```python
"""design.md §11.1 #9: a member of Property A gets 403 on every Property B resource.

Enumerates every rule under /api/p/<property_id> so new routes are covered automatically.
"""
import re

SKIP_METHODS = {"HEAD", "OPTIONS"}
DUMMY_ID = "00000000-0000-0000-0000-000000000000"


def property_rules(app):
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/p/<property_id>"):
            for method in sorted(rule.methods - SKIP_METHODS):
                yield rule, method


def build_path(rule, property_id: str) -> str:
    path = rule.rule.replace("<property_id>", property_id)
    return re.sub(r"<[^>]+>", DUMMY_ID, path)  # 403 must fire before any lookup


def test_route_enumeration_finds_routes(app):
    assert len(list(property_rules(app))) >= 2


def test_member_of_a_gets_403_on_every_b_route(app, fx, login):
    c = login("admin@hvh.test")  # admin at A, no membership at B
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_b.id), method=method, json={})
        if res.status_code != 403:
            failures.append((method, rule.rule, res.status_code))
    assert not failures, f"routes reachable across properties: {failures}"


def test_admin_of_a_is_not_403_on_own_property(app, fx, login):
    """Guards the previous test against vacuity: the same routes must not 403 for a member."""
    c = login("admin@hvh.test")
    failures = []
    for rule, method in property_rules(app):
        res = c.open(build_path(rule, fx.property_a.id), method=method, json={})
        if res.status_code == 403:
            failures.append((method, rule.rule))
    assert not failures, f"admin blocked on own property: {failures}"


def test_anonymous_gets_401_on_every_property_route(app, fx, client):
    for rule, method in property_rules(app):
        res = client.open(build_path(rule, fx.property_a.id), method=method, json={})
        assert res.status_code == 401, (method, rule.rule, res.status_code)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_isolation.py tests/test_departments_users.py -q`
Expected: FAIL — enumeration finds 0 routes; the others get 404.

- [ ] **Step 3: Write schemas and domain**

`server/app/schemas/users.py`:
```python
from app.schemas.common import CamelModel
from app.schemas.enums import DepartmentType, Role


class DepartmentOut(CamelModel):
    id: str
    name: str
    type: DepartmentType
    escalation_minutes: int
    active: bool


class StaffUserOut(CamelModel):
    id: str
    email: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None
    status: str
```

`server/app/domain/users.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, PropertyMembership, UserAccount
from app.schemas.users import DepartmentOut, StaffUserOut


def list_departments(db: Session, property_id: str) -> list[DepartmentOut]:
    rows = db.scalars(
        select(Department).where(Department.property_id == property_id).order_by(Department.name)
    ).all()
    return [DepartmentOut.model_validate(d) for d in rows]


def list_staff(db: Session, property_id: str) -> list[StaffUserOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id)
        .order_by(UserAccount.first_name, UserAccount.last_name)
    ).all()
    return [
        StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name,
                     avatar_url=u.avatar_url, role=m.role, department_id=m.department_id,
                     status=u.status.value)
        for u, m in rows
    ]


def members_of_department(db: Session, property_id: str, department_id: str) -> list[str]:
    return list(
        db.scalars(
            select(PropertyMembership.user_id).where(
                PropertyMembership.property_id == property_id,
                PropertyMembership.department_id == department_id,
            )
        ).all()
    )
```

- [ ] **Step 4: Write the blueprints and register them**

`server/app/api/departments.py`:
```python
from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("departments", __name__, url_prefix="/api/p/<property_id>/departments")


@bp.get("")
@require_auth
@require_property
def list_departments(property_id: str):
    with db_session() as db:
        return ok(users.list_departments(db, g.property_id))
```

`server/app/api/users.py`:
```python
from flask import Blueprint, g

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import users

bp = Blueprint("users", __name__, url_prefix="/api/p/<property_id>/users")


@bp.get("")
@require_auth
@require_property
def list_users(property_id: str):
    with db_session() as db:
        return ok(users.list_staff(db, g.property_id))
```

In `create_app`, extend the import to `from app.api import auth, departments, health, users` and register `departments.bp` and `users.bp`. An empty-string route on a prefixed blueprint yields the exact path `/api/p/<id>/departments` (no trailing slash), which is what the isolation test builds.

- [ ] **Step 5: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): departments/users routes and the property-isolation test suite"
```

---

### Task 6: Pure domain utilities — SMS segments, card redaction, quick-reply interpolation

**Files:**
- Create: `server/app/domain/sms.py`, `server/app/domain/redaction.py`, `server/app/domain/quick_replies.py` (interpolation only; CRUD arrives in Task 16), `server/tests/test_sms.py`, `server/tests/test_redaction.py`, `server/tests/test_interpolate.py`

**Interfaces:**
- Produces: `sms.segment_count(body) -> int`, `sms.is_gsm7(body) -> bool`; `redaction.redact(body) -> tuple[str, bool]`; `quick_replies.interpolate(body, ctx: dict[str, str | None]) -> str` with keys `guest_first_name, room_number, property_name, agent_first_name, departure_date`; `quick_replies.VARIABLES`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_sms.py`:
```python
import pytest

from app.domain.sms import is_gsm7, segment_count


@pytest.mark.parametrize("body,expected", [
    ("", 0),
    ("Hi", 1),
    ("a" * 160, 1),
    ("a" * 161, 2),
    ("a" * 306, 2),
    ("a" * 307, 3),
    ("Café " + "a" * 155, 1),          # é is in the GSM-7 basic set
    ("€" * 80, 1),                      # € is a GSM-7 extension char: counts double -> 160 septets
    ("€" * 81, 2),
    ("Hello 😊", 1),                    # emoji forces UCS-2: 70 per single segment
    ("😊" * 35, 1),                     # 35 emoji = 70 UTF-16 code units
    ("😊" * 36, 2),
    ("你好" * 34, 2),                    # 68 units UCS-2: 67 per segment when multipart
])
def test_segment_count(body, expected):
    assert segment_count(body) == expected


def test_is_gsm7():
    assert is_gsm7("Hello, room 412 is ready @ 3pm!")
    assert not is_gsm7("Hello — dash")  # em dash is not GSM-7
```

`server/tests/test_redaction.py`:
```python
from app.domain.redaction import redact


def test_redacts_valid_card_with_spaces():
    body, flagged = redact("my card is 4242 4242 4242 4242 thanks")
    assert flagged is True
    assert body == "my card is **** **** **** 4242 thanks"


def test_redacts_valid_card_with_dashes_and_plain():
    assert redact("5555-5555-5555-4444")[0] == "**** **** **** 4444"
    assert redact("378282246310005")[0] == "**** **** **** 0005"  # 15-digit Amex


def test_leaves_luhn_invalid_numbers_alone():
    body, flagged = redact("call 1234 5678 9012 3456")
    assert flagged is False and body == "call 1234 5678 9012 3456"


def test_leaves_phone_numbers_and_reservation_ids_alone():
    assert redact("my number is +1 555 123 4567")[1] is False
    assert redact("reservation 48213377")[1] is False


def test_redacts_multiple_occurrences():
    body, flagged = redact("4242424242424242 and 4000056655665556")
    assert flagged and body == "**** **** **** 4242 and **** **** **** 5556"
```

`server/tests/test_interpolate.py`:
```python
from app.domain.quick_replies import interpolate


def test_interpolates_known_variables():
    out = interpolate("Hi {{guest_first_name}}, room {{room_number}} at {{property_name}}.",
                      {"guest_first_name": "Sarah", "room_number": "412", "property_name": "Harbourview"})
    assert out == "Hi Sarah, room 412 at Harbourview."


def test_missing_values_fall_back_gracefully():
    out = interpolate("Hi {{guest_first_name}}, checkout {{departure_date}}.",
                      {"guest_first_name": None, "departure_date": None})
    assert out == "Hi there, checkout soon."


def test_unknown_variables_are_left_visible():
    assert interpolate("x {{nope}} y", {}) == "x {{nope}} y"


def test_whitespace_inside_braces_is_tolerated():
    assert interpolate("Hi {{ guest_first_name }}", {"guest_first_name": "Diego"}) == "Hi Diego"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sms.py tests/test_redaction.py tests/test_interpolate.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/domain/sms.py`**

```python
"""SMS segment counting per GSM 03.38: 160/153 septets for GSM-7, 70/67 code units for UCS-2."""

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = set("^{}\\[~]|€\f")


def is_gsm7(body: str) -> bool:
    return all(ch in GSM7_BASIC or ch in GSM7_EXTENDED for ch in body)


def _gsm7_septets(body: str) -> int:
    return sum(2 if ch in GSM7_EXTENDED else 1 for ch in body)


def _utf16_units(body: str) -> int:
    return len(body.encode("utf-16-le")) // 2


def segment_count(body: str) -> int:
    if not body:
        return 0
    if is_gsm7(body):
        n = _gsm7_septets(body)
        return 1 if n <= 160 else -(-n // 153)
    n = _utf16_units(body)
    return 1 if n <= 70 else -(-n // 67)
```

- [ ] **Step 4: Write `app/domain/redaction.py`**

```python
"""PCI: card numbers texted by guests are masked before storage (design.md §9.1)."""
import re

_CANDIDATE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(body: str) -> tuple[str, bool]:
    flagged = False

    def _sub(m: re.Match) -> str:
        nonlocal flagged
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            flagged = True
            return f"**** **** **** {digits[-4:]}"
        return m.group(0)

    return _CANDIDATE.sub(_sub, body), flagged
```

Only 13–19-digit Luhn-valid runs are masked; 10/11-digit phone numbers and 8-digit reservation ids never match.

- [ ] **Step 5: Write `app/domain/quick_replies.py` (interpolation half)**

```python
from __future__ import annotations

import re

VARIABLES = ("guest_first_name", "room_number", "property_name", "agent_first_name", "departure_date")
FALLBACKS = {
    "guest_first_name": "there",
    "room_number": "your room",
    "property_name": "the hotel",
    "agent_first_name": "the front desk",
    "departure_date": "soon",
}
_HOLE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def interpolate(body: str, ctx: dict[str, str | None]) -> str:
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in VARIABLES:
            return m.group(0)
        value = ctx.get(key)
        return str(value) if value not in (None, "") else FALLBACKS[key]

    return _HOLE.sub(_sub, body)
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SMS segment counting, card-number redaction, quick-reply interpolation"
```

---

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
    broadcast.add_listener(captured.append)
    yield captured
    broadcast.remove_listener(captured.append)
```
(`captured.append` is the same bound-method object only if you keep a reference — store it: `fn = captured.append; broadcast.add_listener(fn); yield captured; broadcast.remove_listener(fn)`.)

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

### Task 8: Job queue and worker

**Files:**
- Create: `server/app/queue/__init__.py`, `server/app/queue/jobs.py`, `server/app/queue/worker.py`, `server/app/queue/handlers/__init__.py`, `server/tests/test_queue.py`
- Modify: `server/app/__init__.py` (start worker when `START_WORKER`), `server/tests/conftest.py` (add `worker` fixture)

**Interfaces:**
- Produces: `jobs.enqueue(db, type, payload, run_at=None, max_attempts=5) -> Job`; `jobs.claim_due(db, limit=20) -> list[Job]`; `jobs.complete(db, job)`; `jobs.fail(db, job, exc)`; `jobs.reclaim_stale(db, older_than_seconds=60) -> int`; `jobs.ensure_recurring(db, type, payload=None) -> Job | None`; `jobs.RECURRING: dict[str, int]` (type → interval seconds: `sla.sweep: 30`, `snooze.wake: 60`, `pms.tick: <config>`); `handlers.HANDLERS`, `@handlers.handler("type")`, `handlers.load_all()`; `Worker(app, interval=0.5)` with `tick() -> int`, `start()`, `stop()`; test fixture `worker` (a `Worker` bound to the test app; call `worker.tick()`).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_queue.py`:
```python
import pytest
from sqlalchemy import select

from app import clock
from app.models import Job
from app.queue import jobs
from app.queue.handlers import HANDLERS, handler
from app.schemas.enums import JobStatus


@pytest.fixture()
def fake_handlers():
    calls = []

    @handler("test.ok")
    def _ok(db, payload):
        calls.append(("ok", payload))

    @handler("test.boom")
    def _boom(db, payload):
        calls.append(("boom", payload))
        raise RuntimeError("kaboom")

    yield calls
    HANDLERS.pop("test.ok", None)
    HANDLERS.pop("test.boom", None)


def test_enqueue_and_tick_runs_handler(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.ok", {"n": 1})
    assert worker.tick() == 1
    assert fake_handlers == [("ok", {"n": 1})]
    with database.session() as db:
        assert db.get(Job, job.id).status == JobStatus.done


def test_future_jobs_wait_for_their_time(app, database, worker, fake_handlers):
    from datetime import timedelta

    with database.session() as db:
        jobs.enqueue(db, "test.ok", {}, run_at=clock.now() + timedelta(seconds=30))
    assert worker.tick() == 0
    clock.advance(seconds=31)
    assert worker.tick() == 1


def test_failure_retries_with_backoff_then_dies(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.boom", {}, max_attempts=3)
    for attempt in range(1, 4):
        assert worker.tick() == 1
        with database.session() as db:
            j = db.get(Job, job.id)
            assert j.attempts == attempt
            assert "kaboom" in (j.last_error or "")
            if attempt < 3:
                assert j.status == JobStatus.queued
                assert (j.run_at - clock.now()).total_seconds() == pytest.approx(2**attempt, abs=1)
                clock.advance(seconds=2**attempt + 1)
            else:
                assert j.status == JobStatus.dead
    assert worker.tick() == 0
    assert len(fake_handlers) == 3


def test_unknown_job_type_is_marked_dead(app, database, worker):
    with database.session() as db:
        job = jobs.enqueue(db, "nope.nothing", {})
    worker.tick()
    with database.session() as db:
        j = db.get(Job, job.id)
        assert j.status == JobStatus.dead and "No handler" in j.last_error


def test_recurring_job_reenqueues_itself(app, database, worker, fake_handlers):
    jobs.RECURRING["test.ok"] = 30
    try:
        with database.session() as db:
            first = jobs.ensure_recurring(db, "test.ok")
            assert jobs.ensure_recurring(db, "test.ok") is None  # already queued
        worker.tick()
        with database.session() as db:
            queued = db.scalars(select(Job).where(Job.type == "test.ok",
                                                  Job.status == JobStatus.queued)).all()
            assert len(queued) == 1 and queued[0].id != first.id
            assert (queued[0].run_at - clock.now()).total_seconds() == pytest.approx(30, abs=1)
    finally:
        jobs.RECURRING.pop("test.ok", None)


def test_stale_running_jobs_are_reclaimed(app, database, worker, fake_handlers):
    with database.session() as db:
        job = jobs.enqueue(db, "test.ok", {})
        job.status = JobStatus.running
        job.locked_at = clock.now()
    clock.advance(seconds=61)
    with database.session() as db:
        assert jobs.reclaim_stale(db) == 1
    assert worker.tick() == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_queue.py -q`
Expected: FAIL with `ModuleNotFoundError: app.queue`.

- [ ] **Step 3: Write the handler registry**

`server/app/queue/__init__.py` — empty.

`server/app/queue/handlers/__init__.py`:
```python
from __future__ import annotations

import importlib
from typing import Callable

from sqlalchemy.orm import Session

Handler = Callable[[Session, dict], None]
HANDLERS: dict[str, Handler] = {}

MODULES = ("outbound", "mock_delivery", "sla", "snooze", "pms")


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
```

(Modules that don't exist yet are skipped; Tasks 9, 13 and 20 add them.)

- [ ] **Step 4: Write `app/queue/jobs.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Job
from app.schemas.enums import JobStatus

RECURRING: dict[str, int] = {"sla.sweep": 30, "snooze.wake": 60}
STALE_SECONDS = 60


def enqueue(db: Session, type: str, payload: dict | None = None, run_at: datetime | None = None,
            max_attempts: int = 5) -> Job:
    job = Job(type=type, payload=payload or {}, run_at=run_at or clock.now(),
              max_attempts=max_attempts, status=JobStatus.queued)
    db.add(job)
    db.flush()
    return job


def claim_due(db: Session, limit: int = 20) -> list[Job]:
    now = clock.now()
    due = db.scalars(
        select(Job).where(Job.status == JobStatus.queued, Job.run_at <= now)
        .order_by(Job.run_at).limit(limit).with_for_update(skip_locked=True)
    ).all()
    for job in due:
        job.status = JobStatus.running
        job.locked_at = now
    db.flush()
    return due


def complete(db: Session, job: Job) -> None:
    job.status = JobStatus.done
    job.finished_at = clock.now()
    job.locked_at = None


def fail(db: Session, job: Job, exc: BaseException, *, retry: bool = True) -> None:
    job.attempts += 1
    job.last_error = repr(exc)[:2000]
    job.locked_at = None
    if retry and job.attempts < job.max_attempts:
        job.status = JobStatus.queued
        job.run_at = clock.now() + timedelta(seconds=2**job.attempts)
    else:
        job.status = JobStatus.dead
        job.finished_at = clock.now()


def reclaim_stale(db: Session, older_than_seconds: int = STALE_SECONDS) -> int:
    cutoff = clock.now() - timedelta(seconds=older_than_seconds)
    rows = db.scalars(select(Job).where(Job.status == JobStatus.running, Job.locked_at < cutoff)).all()
    for job in rows:
        job.status = JobStatus.queued
        job.locked_at = None
    return len(rows)


def ensure_recurring(db: Session, type: str, payload: dict | None = None) -> Job | None:
    exists = db.scalar(select(Job.id).where(Job.type == type,
                                            Job.status.in_([JobStatus.queued, JobStatus.running])))
    if exists:
        return None
    return enqueue(db, type, payload or {}, max_attempts=1)


def schedule_next_recurrence(db: Session, job: Job) -> None:
    interval = RECURRING.get(job.type)
    if interval:
        enqueue(db, job.type, job.payload, run_at=clock.now() + timedelta(seconds=interval),
                max_attempts=1)
```

`with_for_update(skip_locked=True)` is a no-op on SQLite and correct on Postgres.

- [ ] **Step 5: Write `app/queue/worker.py`**

```python
from __future__ import annotations

import logging
import threading

from flask import Flask

from app.queue import jobs
from app.queue.handlers import HANDLERS, load_all

log = logging.getLogger("worker")


class Worker:
    def __init__(self, app: Flask, interval: float = 0.5):
        self.app = app
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        load_all()

    def tick(self) -> int:
        """Run one pass. Returns how many jobs were executed (successfully or not)."""
        database = self.app.extensions["db"]
        with self.app.app_context():
            with database.session() as db:
                jobs.reclaim_stale(db)
                claimed = jobs.claim_due(db)
                claimed_ids = [(j.id, j.type, dict(j.payload)) for j in claimed]
            ran = 0
            for job_id, job_type, payload in claimed_ids:
                ran += 1
                fn = HANDLERS.get(job_type)
                try:
                    if fn is None:
                        raise LookupError(f"No handler for job type {job_type!r}")
                    with database.session() as db:
                        fn(db, payload)
                        job = db.get(jobs.Job, job_id)
                        jobs.complete(db, job)
                        jobs.schedule_next_recurrence(db, job)
                except Exception as exc:  # noqa: BLE001 — the worker must survive any handler error
                    log.exception("job %s (%s) failed", job_id, job_type)
                    with database.session() as db:
                        job = db.get(jobs.Job, job_id)
                        jobs.fail(db, job, exc, retry=not isinstance(exc, LookupError))
                        if job.type in jobs.RECURRING and job.status != jobs.JobStatus.queued:
                            jobs.schedule_next_recurrence(db, job)
            return ran

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("worker tick crashed")
            self._stop.wait(self.interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
```

`jobs.py` must also export `Job` and `JobStatus` for the worker's `db.get(jobs.Job, ...)` — they are already imported there, so `jobs.Job` and `jobs.JobStatus` resolve.

- [ ] **Step 6: Wire the worker into the app factory and tests**

In `create_app`, after blueprints:
```python
    import os

    from app.queue import jobs as _jobs
    from app.queue.worker import Worker

    _jobs.RECURRING["pms.tick"] = config.PMS_TICK_SECONDS or 0
    if not config.PMS_TICK_SECONDS:
        _jobs.RECURRING.pop("pms.tick", None)
    app.extensions["worker"] = Worker(app)
    under_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    if config.START_WORKER and (under_reloader or not app.debug):
        with app.extensions["db"].session() as db:
            for job_type in _jobs.RECURRING:
                _jobs.ensure_recurring(db, job_type)
        app.extensions["worker"].start()
```

`run.py` runs with `debug=True` in development, so the Werkzeug reloader is on and only the child process (`WERKZEUG_RUN_MAIN=true`) starts the worker.

In `server/tests/conftest.py` add:
```python
@pytest.fixture()
def worker(app):
    return app.extensions["worker"]
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SQLite-backed job queue with retry/backoff/dead-letter and in-process worker"
```

---

### Task 9: Channel adapter interface, MockSmsAdapter, outbound send and delivery-status handlers

**Files:**
- Create: `server/app/channels/__init__.py`, `server/app/channels/base.py`, `server/app/channels/mock_sms.py`, `server/app/channels/registry.py`, `server/app/queue/handlers/outbound.py`, `server/app/queue/handlers/mock_delivery.py`, `server/app/domain/messages.py` (delivery-status half; `send`/`record_inbound` arrive in Task 11), `server/app/schemas/conversations.py` (message shapes only for now), `server/tests/factories.py`, `server/tests/test_mock_sms.py`

**Interfaces:**
- Produces: `ChannelAdapter` Protocol (`channel`, `supports_rich_media`, `max_length`, `send(db, to, body, *, message_id) -> SendResult`, `verify_inbound(request) -> bool`, `parse_inbound(payload) -> InboundMessage`); dataclasses `SendResult(provider_message_id)`, `InboundMessage(from_, to, body, provider_message_id)`; `MockSmsAdapter`; `registry.get_sms_adapter() -> ChannelAdapter` (from `current_app.extensions["sms_adapter"]`); handlers `outbound.send` and `mock.delivery_status`; `messages.update_delivery_status(db, property_id, message_id, status, *, provider_message_id=None, error_code=None, error_message=None) -> Message`; `messages.retry(db, property_id, message_id) -> Message`; `MessageOut` schema; test factories `make_conversation(db, fx, guest=None, **overrides) -> Conversation`, `make_message(db, conversation, *, direction, body, **overrides) -> Message`.

- [ ] **Step 1: Write the failing tests**

`server/tests/factories.py`:
```python
from __future__ import annotations

from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation, Guest, Message
from app.schemas.enums import AuthorType, Channel, ConversationStatus, DeliveryStatus, Direction


def make_conversation(db: Session, fx, guest: Guest | None = None, **overrides) -> Conversation:
    guest = guest or fx.guest_inhouse_a
    stay_id = fx.stay_inhouse_a.id if guest.id == fx.guest_inhouse_a.id else None
    c = Conversation(property_id=guest.property_id, guest_id=guest.id, stay_id=stay_id,
                     status=ConversationStatus.open, channel_primary=Channel.sms)
    for k, v in overrides.items():
        setattr(c, k, v)
    db.add(c)
    db.flush()
    return c


def make_message(db: Session, conversation: Conversation, *, direction: Direction, body: str,
                 **overrides) -> Message:
    m = Message(
        conversation_id=conversation.id, property_id=conversation.property_id, direction=direction,
        author_type=AuthorType.guest if direction == Direction.inbound else AuthorType.staff,
        channel=Channel.sms, body=body,
        delivery_status=DeliveryStatus.delivered if direction == Direction.inbound else DeliveryStatus.queued,
        sent_at=clock.now(),
    )
    for k, v in overrides.items():
        setattr(m, k, v)
    db.add(m)
    db.flush()
    return m
```

`server/tests/test_mock_sms.py`:
```python
from app.channels.mock_sms import MockSmsAdapter
from app.models import Message
from app.queue import jobs
from app.schemas.enums import DeliveryStatus, Direction
from tests.factories import make_conversation, make_message


def _outbound(database, fx, to_phone: str):
    with database.session() as db:
        guest = fx.guest_inhouse_a
        guest.phone_e164 = to_phone
        conv = make_conversation(db, fx, guest)
        msg = make_message(db, conv, direction=Direction.outbound, body="Hello")
        jobs.enqueue(db, "outbound.send", {"message_id": msg.id})
    return msg.id


def test_send_delivers_in_two_steps_and_broadcasts(app, fx, database, worker, events):
    msg_id = _outbound(database, fx, "+15551234567")
    worker.tick()  # outbound.send → provider id, schedules mock.delivery_status jobs
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.provider_message_id.startswith("mock-")
        assert m.delivery_status == DeliveryStatus.queued
    from app import clock

    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.sent
    clock.advance(seconds=1)
    worker.tick()
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == DeliveryStatus.delivered
        assert m.delivered_at is not None
    statuses = [e.payload["deliveryStatus"] for e in events if e.type == "message.status_changed"]
    assert statuses == ["sent", "delivered"]


def test_numbers_ending_0000_fail_with_carrier_code(app, fx, database, worker, events):
    msg_id = _outbound(database, fx, "+15552000000")
    worker.tick()
    from app import clock

    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        m = db.get(Message, msg_id)
        assert m.delivery_status == DeliveryStatus.failed
        assert m.provider_error_code == "30007"
        assert "mock" in m.provider_error_message.lower()


def test_retry_requeues_a_failed_message(app, fx, database, worker):
    from app import clock
    from app.domain import messages

    msg_id = _outbound(database, fx, "+15552000000")
    worker.tick()
    clock.advance(seconds=0.5)
    worker.tick()
    with database.session() as db:
        # Give the guest a working number so the retry can succeed.
        fx.guest_inhouse_a.phone_e164 = "+15551234567"
        db.merge(fx.guest_inhouse_a)
        m = messages.retry(db, fx.property_a.id, msg_id)
        assert m.delivery_status == DeliveryStatus.queued
        assert m.provider_error_code is None
    worker.tick()
    clock.advance(seconds=2)
    worker.tick()
    worker.tick()
    with database.session() as db:
        assert db.get(Message, msg_id).delivery_status == DeliveryStatus.delivered


def test_parse_inbound_reads_twilio_field_names(app):
    a = MockSmsAdapter(secret="dev")
    m = a.parse_inbound({"From": "+15551234567", "To": "+15550100", "Body": " hi ", "MessageSid": "SM1"})
    assert (m.from_, m.to, m.body, m.provider_message_id) == ("+15551234567", "+15550100", "hi", "SM1")


def test_verify_inbound_checks_shared_secret(app):
    a = MockSmsAdapter(secret="dev")
    with app.test_request_context(headers={"X-Mock-Secret": "dev"}):
        from flask import request

        assert a.verify_inbound(request) is True
    with app.test_request_context(headers={"X-Mock-Secret": "wrong"}):
        from flask import request

        assert a.verify_inbound(request) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_mock_sms.py -q`
Expected: FAIL with `ModuleNotFoundError: app.channels`.

- [ ] **Step 3: Write the adapter interface and the mock**

`server/app/channels/__init__.py` — empty.

`server/app/channels/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from flask import Request
from sqlalchemy.orm import Session

from app.schemas.enums import Channel


@dataclass(frozen=True)
class SendResult:
    provider_message_id: str


@dataclass(frozen=True)
class InboundMessage:
    from_: str
    to: str
    body: str
    provider_message_id: str


class ChannelAdapter(Protocol):
    channel: Channel
    supports_rich_media: bool
    max_length: int

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult: ...

    def verify_inbound(self, request: Request) -> bool: ...

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage: ...
```

`server/app/channels/mock_sms.py`:
```python
"""Fake SMS wire. Everything above it — consent, queueing, delivery status, retry — is real."""
from __future__ import annotations

import hmac
import uuid
from datetime import timedelta
from typing import Mapping

from flask import Request
from sqlalchemy.orm import Session

from app import clock
from app.channels.base import InboundMessage, SendResult
from app.queue import jobs
from app.schemas.enums import Channel

FAIL_SUFFIX = "0000"
FAIL_CODE = "30007"
FAIL_MESSAGE = "Carrier violation (mock)"


class MockSmsAdapter:
    channel = Channel.sms
    supports_rich_media = False
    max_length = 1600

    def __init__(self, secret: str = "dev"):
        self.secret = secret

    def send(self, db: Session, to: str, body: str, *, message_id: str) -> SendResult:
        provider_id = f"mock-{uuid.uuid4().hex[:12]}"
        now = clock.now()
        if to.endswith(FAIL_SUFFIX):
            jobs.enqueue(db, "mock.delivery_status",
                         {"message_id": message_id, "status": "failed",
                          "error_code": FAIL_CODE, "error_message": FAIL_MESSAGE},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
        else:
            jobs.enqueue(db, "mock.delivery_status", {"message_id": message_id, "status": "sent"},
                         run_at=now + timedelta(milliseconds=400), max_attempts=1)
            jobs.enqueue(db, "mock.delivery_status", {"message_id": message_id, "status": "delivered"},
                         run_at=now + timedelta(milliseconds=1200), max_attempts=1)
        return SendResult(provider_message_id=provider_id)

    def verify_inbound(self, request: Request) -> bool:
        given = request.headers.get("X-Mock-Secret", "")
        return hmac.compare_digest(given, self.secret)

    def parse_inbound(self, payload: Mapping[str, str]) -> InboundMessage:
        return InboundMessage(
            from_=payload.get("From", "").strip(),
            to=payload.get("To", "").strip(),
            body=(payload.get("Body") or "").strip(),
            provider_message_id=payload.get("MessageSid") or f"mock-in-{uuid.uuid4().hex[:12]}",
        )
```

`server/app/channels/registry.py`:
```python
from flask import Flask, current_app

from app.channels.base import ChannelAdapter
from app.channels.mock_sms import MockSmsAdapter
from app.config import Config


def build_sms_adapter(config: Config) -> ChannelAdapter:
    if config.SMS_ADAPTER == "mock":
        return MockSmsAdapter(secret=config.MOCK_SMS_SECRET)
    raise ValueError(f"Unknown SMS_ADAPTER {config.SMS_ADAPTER!r}; Phase 1 supports 'mock'")


def install(app: Flask, config: Config) -> None:
    app.extensions["sms_adapter"] = build_sms_adapter(config)


def get_sms_adapter() -> ChannelAdapter:
    return current_app.extensions["sms_adapter"]
```

In `create_app`, right after the database is registered: `from app.channels import registry as channel_registry; channel_registry.install(app, config)`.

- [ ] **Step 4: Write the message schema and the delivery-status half of the messages domain**

`server/app/schemas/conversations.py` (Task 11 adds the conversation shapes to this same file):
```python
from datetime import datetime

from app.schemas.common import CamelModel
from app.schemas.enums import AuthorType, Channel, DeliveryStatus, Direction


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    direction: Direction
    author_type: AuthorType
    author_user_id: str | None = None
    channel: Channel
    body: str
    digital_asset_id: str | None = None
    delivery_status: DeliveryStatus
    provider_error_code: str | None = None
    provider_error_message: str | None = None
    redacted: bool
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
```

`server/app/domain/messages.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import Conflict, NotFound
from app.models import Message
from app.queue import jobs
from app.realtime.broadcast import queue_event
from app.schemas.conversations import MessageOut
from app.schemas.enums import DeliveryStatus, Direction


def _get(db: Session, property_id: str, message_id: str) -> Message:
    m = db.scalar(select(Message).where(Message.id == message_id, Message.property_id == property_id))
    if m is None:
        raise NotFound("Message not found")
    return m


def update_delivery_status(db: Session, property_id: str, message_id: str, status: DeliveryStatus, *,
                           provider_message_id: str | None = None, error_code: str | None = None,
                           error_message: str | None = None) -> Message:
    m = _get(db, property_id, message_id)
    m.delivery_status = status
    if provider_message_id:
        m.provider_message_id = provider_message_id
    if status == DeliveryStatus.delivered:
        m.delivered_at = clock.now()
    if status in (DeliveryStatus.failed, DeliveryStatus.undelivered):
        m.provider_error_code = error_code
        m.provider_error_message = error_message
    db.flush()
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m


def retry(db: Session, property_id: str, message_id: str) -> Message:
    m = _get(db, property_id, message_id)
    if m.direction != Direction.outbound or m.delivery_status not in (
        DeliveryStatus.failed, DeliveryStatus.undelivered
    ):
        raise Conflict("Only failed outbound messages can be retried")
    m.delivery_status = DeliveryStatus.queued
    m.provider_error_code = None
    m.provider_error_message = None
    m.provider_message_id = None
    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    queue_event(db, property_id, "message.status_changed",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m
```

- [ ] **Step 5: Write the two handlers**

`server/app/queue/handlers/outbound.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.registry import get_sms_adapter
from app.domain import messages
from app.models import Conversation, Guest, Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("outbound.send")
def outbound_send(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None or msg.delivery_status != DeliveryStatus.queued:
        return  # already handled or retried; idempotent
    conv = db.get(Conversation, msg.conversation_id)
    guest = db.get(Guest, conv.guest_id)
    adapter = get_sms_adapter()
    try:
        result = adapter.send(db, guest.phone_e164, msg.body, message_id=msg.id)
    except Exception as exc:  # provider threw: mark failed, then re-raise so the job retries
        messages.update_delivery_status(db, msg.property_id, msg.id, DeliveryStatus.failed,
                                        error_code="ADAPTER_ERROR", error_message=repr(exc)[:500])
        raise
    msg.provider_message_id = result.provider_message_id
    db.flush()
```

`server/app/queue/handlers/mock_delivery.py`:
```python
from sqlalchemy.orm import Session

from app.domain import messages
from app.models import Message
from app.queue.handlers import handler
from app.schemas.enums import DeliveryStatus


@handler("mock.delivery_status")
def mock_delivery_status(db: Session, payload: dict) -> None:
    msg = db.get(Message, payload["message_id"])
    if msg is None:
        return
    target = DeliveryStatus(payload["status"])
    # A retry resets the message to queued and schedules a new sequence; stale events must not
    # overwrite it. Only advance forward: queued→sent→delivered, or queued/sent→failed.
    order = [DeliveryStatus.queued, DeliveryStatus.sent, DeliveryStatus.delivered]
    if target in order and msg.delivery_status in order and order.index(target) <= order.index(msg.delivery_status):
        return
    if msg.provider_message_id is None:
        return  # message was reset by a retry after this job was scheduled
    messages.update_delivery_status(db, msg.property_id, msg.id, target,
                                    error_code=payload.get("error_code"),
                                    error_message=payload.get("error_message"))
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): ChannelAdapter interface, MockSmsAdapter, outbound send and delivery-status jobs"
```

---
