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
        valid = (user is not None and user.status == UserStatus.active
                 and verify_password(body.password, user.password_hash))
        if valid:
            token = create_session(db, user.id, ip, ua)
            audit.record(db, None, user.id, "auth.login", "user_account", user.id, ip=ip, user_agent=ua)
            payload = _session_out(db, user)
    if not valid:
        # Written in its own session: raising inside the block above would roll the audit row back.
        with db_session() as db:
            audit.record(db, None, None, "auth.login_failed", "user_account",
                         user.id if user else None, after={"email": body.email}, ip=ip, user_agent=ua)
        raise Unauthorized("Email or password is incorrect")
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
    fn = captured.append  # keep one reference: a fresh bound method would not compare equal on removal
    broadcast.add_listener(fn)
    yield captured
    broadcast.remove_listener(fn)
```

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
    from app.models import Guest

    with database.session() as db:
        guest = db.get(Guest, fx.guest_inhouse_a.id)  # re-attach: fixture objects are detached
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
        from app.models import Guest

        db.get(Guest, fx.guest_inhouse_a.id).phone_e164 = "+15551234567"  # a working number for the retry
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

### Task 10: Guests, stays, and consent

**Files:**
- Create: `server/app/domain/guests.py`, `server/app/domain/stays.py`, `server/app/domain/consent.py`, `server/tests/test_consent.py`, `server/tests/test_guests_stays.py`

**Interfaces:**
- Produces: `guests.find_by_phone(db, property_id, phone) -> Guest | None`; `guests.find_or_create_by_phone(db, property_id, phone) -> tuple[Guest, bool]` (created flag); `guests.normalize_phone(raw) -> str` (E.164 for US numbers: digits only → `+1XXXXXXXXXX`; already `+` → kept); `stays.find_in_house_for_guest(db, property_id, guest_id) -> Stay | None`; `stays.find_in_house_by_phone(db, property_id, phone) -> tuple[Guest, Stay] | None`; `consent.STOP_WORDS`, `consent.START_WORDS`, `consent.HELP_WORDS`; `consent.classify_keyword(body) -> Literal["stop","start","help"] | None`; `consent.opt_out(db, guest, source)`, `consent.opt_in(db, guest, source)`; `consent.assert_can_send(guest, *, allow_opt_out_confirmation=False)` raising `ConsentError`; `consent.STOP_CONFIRMATION(property_name) -> str`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_consent.py`:
```python
import pytest

from app.domain import consent
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus


@pytest.mark.parametrize("body,expected", [
    ("STOP", "stop"), ("stop", "stop"), (" Stop please ", "stop"), ("STOPALL", "stop"),
    ("UNSUBSCRIBE", "stop"), ("CANCEL", "stop"), ("END", "stop"), ("QUIT", "stop"),
    ("START", "start"), ("UNSTOP", "start"), ("YES", "start"),
    ("HELP", "help"), ("help me", "help"),
    ("Please stop the AC noise", None),     # 'stop' not the first word → real message
    ("Can you help with towels?", None),
    ("", None),
])
def test_classify_keyword(body, expected):
    assert consent.classify_keyword(body) == expected


def test_opt_out_and_opt_in_record_source_and_time(app, fx, database):
    from app import clock

    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.opt_out(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_out
        assert g.sms_consent_source == "sms_keyword"
        assert g.sms_consent_at == clock.now()
        consent.opt_in(db, g, "sms_keyword")
        assert g.sms_consent_status == SmsConsentStatus.opted_in


def test_assert_can_send_blocks_opted_out_unless_confirmation(app, fx, database):
    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        consent.assert_can_send(g)
        consent.opt_out(db, g, "sms_keyword")
        with pytest.raises(ConsentError) as ei:
            consent.assert_can_send(g)
        assert ei.value.code == "CONSENT_OPTED_OUT"
        consent.assert_can_send(g, allow_opt_out_confirmation=True)  # the one exception
```

`server/tests/test_guests_stays.py`:
```python
from app.domain import guests, stays
from app.schemas.enums import SmsConsentStatus


def test_normalize_phone():
    assert guests.normalize_phone("(555) 123-4567") == "+15551234567"
    assert guests.normalize_phone("15551234567") == "+15551234567"
    assert guests.normalize_phone("+44 20 7946 0958") == "+442079460958"


def test_find_or_create_by_phone_is_idempotent_and_property_scoped(app, fx, database):
    with database.session() as db:
        g1, created1 = guests.find_or_create_by_phone(db, fx.property_a.id, "+15550001111")
        g2, created2 = guests.find_or_create_by_phone(db, fx.property_a.id, "+1 (555) 000-1111")
        gb, createdb = guests.find_or_create_by_phone(db, fx.property_b.id, "+15550001111")
    assert created1 and not created2 and createdb
    assert g1.id == g2.id and gb.id != g1.id
    assert g1.sms_consent_status == SmsConsentStatus.unknown


def test_find_in_house_by_phone_matches_checked_in_stay_only(app, fx, database):
    with database.session() as db:
        hit = stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
        assert hit is not None and hit[1].room_number == "412"
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_nostay_a.phone_e164) is None
        # Same phone at another property is not in-house here.
        assert stays.find_in_house_by_phone(db, fx.property_a.id, fx.guest_b.phone_e164) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_consent.py tests/test_guests_stays.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write `app/domain/guests.py`**

```python
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Guest


def normalize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def find_by_phone(db: Session, property_id: str, phone: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.property_id == property_id,
                                         Guest.phone_e164 == normalize_phone(phone)))


def find_or_create_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, bool]:
    existing = find_by_phone(db, property_id, phone)
    if existing:
        return existing, False
    g = Guest(property_id=property_id, phone_e164=normalize_phone(phone))
    db.add(g)
    db.flush()
    return g, True


def get(db: Session, property_id: str, guest_id: str) -> Guest | None:
    return db.scalar(select(Guest).where(Guest.id == guest_id, Guest.property_id == property_id))
```

- [ ] **Step 4: Write `app/domain/stays.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.guests import find_by_phone
from app.models import Guest, Stay
from app.schemas.enums import StayStatus


def find_in_house_for_guest(db: Session, property_id: str, guest_id: str) -> Stay | None:
    return db.scalar(
        select(Stay).where(Stay.property_id == property_id, Stay.guest_id == guest_id,
                           Stay.status == StayStatus.checked_in)
        .order_by(Stay.actual_checkin_at.desc())
    )


def find_in_house_by_phone(db: Session, property_id: str, phone: str) -> tuple[Guest, Stay] | None:
    guest = find_by_phone(db, property_id, phone)
    if guest is None:
        return None
    stay = find_in_house_for_guest(db, property_id, guest.id)
    return (guest, stay) if stay else None


def get(db: Session, property_id: str, stay_id: str) -> Stay | None:
    return db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
```

- [ ] **Step 5: Write `app/domain/consent.py`**

```python
"""TCPA consent (design.md §9.1). assert_can_send() is called from exactly one place: messages.send()."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app import clock
from app.domain import audit
from app.errors import ConsentError
from app.models import Guest
from app.schemas.enums import SmsConsentStatus

STOP_WORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit"}
START_WORDS = {"start", "unstop", "yes"}
HELP_WORDS = {"help"}

Keyword = Literal["stop", "start", "help"]


def classify_keyword(body: str) -> Keyword | None:
    words = body.strip().lower().split()
    if not words:
        return None
    first = words[0].strip(".,!?")
    if first in STOP_WORDS:
        return "stop"
    if first in START_WORDS:
        return "start"
    if first in HELP_WORDS:
        return "help"
    return None


def STOP_CONFIRMATION(property_name: str) -> str:
    return f"You're unsubscribed from {property_name} messages. Reply START to resume."


def _set(db: Session, guest: Guest, status: SmsConsentStatus, source: str) -> None:
    before = {"sms_consent_status": guest.sms_consent_status.value}
    guest.sms_consent_status = status
    guest.sms_consent_at = clock.now()
    guest.sms_consent_source = source
    db.flush()
    audit.record(db, guest.property_id, None, f"consent.{status.value}", "guest", guest.id,
                 before=before, after={"sms_consent_status": status.value, "source": source})


def opt_out(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_out, source)


def opt_in(db: Session, guest: Guest, source: str) -> None:
    _set(db, guest, SmsConsentStatus.opted_in, source)


def assert_can_send(guest: Guest, *, allow_opt_out_confirmation: bool = False) -> None:
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        raise ConsentError("Guest has opted out of SMS")
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): guests, in-house stay lookup, TCPA consent keywords and send-path check"
```

---

### Task 11: Conversations domain, the send path, the inbound path, and the SMS webhook (§11.1 #1, #2, #5)

**Files:**
- Create: `server/app/domain/conversations.py`, `server/app/channels/inbound.py`, `server/app/api/hooks.py`, `server/tests/test_inbound.py`, `server/tests/test_send.py`
- Modify: `server/app/domain/messages.py` (add `send`, `record_inbound`), `server/app/schemas/conversations.py` (add conversation shapes), `server/app/__init__.py`, `server/tests/factories.py` (add `inbound(client, fx, from_phone, body, to=None)` helper)

**Interfaces:**
- Produces: `conversations.find_or_create_for_guest(db, property_id, guest, stay=None) -> tuple[Conversation, bool]` (reopens archived); `conversations.get(db, property_id, conversation_id) -> Conversation` (404); `conversations.sla_minutes(db, property_id) -> int`; `conversations.auto_resolve_hours(db, property_id) -> int`; `messages.send(db, property_id, conversation_id, body, *, author_user_id, author_type=AuthorType.staff, digital_asset_id=None, draft_prompt_id=None, allow_opt_out_confirmation=False, ip=None, user_agent=None) -> Message`; `messages.record_inbound(db, property_id, conversation, body, provider_message_id, *, start_sla=True) -> Message` (redaction is computed internally; corrected during Task 11 — the old `*, redacted` wording contradicted this task's own Step 5); `inbound.handle(db, property_id, msg: InboundMessage) -> InboundResult(conversation, message, created_conversation, keyword)`; `POST /api/hooks/sms/inbound` (form-encoded Twilio fields, `X-Mock-Secret`); `ConversationSummary`, `GuestOut`, `StayOut` schemas. Test helper `inbound(client, fx, from_phone, body, to=None) -> Response`.

- [ ] **Step 1: Write the failing tests**

Add to `server/tests/factories.py`:
```python
def inbound(client, fx, from_phone: str, body: str, to: str | None = None, sid: str | None = None):
    import uuid

    return client.post(
        "/api/hooks/sms/inbound",
        data={"From": from_phone, "To": to or fx.property_a.sms_number, "Body": body,
              "MessageSid": sid or f"SM{uuid.uuid4().hex[:10]}"},
        headers={"X-Mock-Secret": "dev"},
    )
```

`server/tests/test_inbound.py`:
```python
from sqlalchemy import select

from app.models import AuditLog, Conversation, Guest, Message
from app.schemas.enums import ConversationStatus, DeliveryStatus, Direction, SmsConsentStatus
from tests.factories import inbound


def test_unknown_number_creates_guest_and_conversation(app, fx, client, database, events):
    """§11.1 #1"""
    res = inbound(client, fx, "+15550142290", "Hi, arriving around 9pm tonight, is that ok?")
    assert res.status_code == 204
    with database.session() as db:
        g = db.scalar(select(Guest).where(Guest.phone_e164 == "+15550142290"))
        assert g.property_id == fx.property_a.id
        assert g.sms_consent_status == SmsConsentStatus.opted_in
        assert g.sms_consent_source == "inbound_sms"
        c = db.scalar(select(Conversation).where(Conversation.guest_id == g.id))
        assert c.status == ConversationStatus.open and c.stay_id is None
        assert c.sla_due_at is not None and c.last_guest_message_at is not None
        m = db.scalar(select(Message).where(Message.conversation_id == c.id))
        assert m.direction == Direction.inbound and m.body.startswith("Hi, arriving")
    assert [e.type for e in events if e.type.startswith("conversation.")] == ["conversation.created"]
    assert any(e.type == "message.created" for e in events)


def test_known_in_house_guest_attaches_stay(app, fx, client, database):
    """§11.1 #2"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        assert c.stay_id == fx.stay_inhouse_a.id


def test_second_message_reuses_open_conversation(app, fx, client, database):
    inbound(client, fx, "+15550142290", "one")
    inbound(client, fx, "+15550142290", "two")
    with database.session() as db:
        assert db.scalar(select(Conversation).where(
            Conversation.property_id == fx.property_a.id)) is not None
        convs = db.scalars(select(Conversation).where(Conversation.property_id == fx.property_a.id)).all()
        assert len(convs) == 1
        assert len(db.scalars(select(Message).where(Message.conversation_id == convs[0].id)).all()) == 2


def test_archived_conversation_reopens_on_inbound(app, fx, client, database):
    from app import clock

    inbound(client, fx, "+15550142290", "one")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.property_id == fx.property_a.id))
        c.status = ConversationStatus.archived
        c.archived_at = clock.now()
    inbound(client, fx, "+15550142290", "two")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.property_id == fx.property_a.id))
        assert c.status == ConversationStatus.open and c.archived_at is None


def test_duplicate_provider_sid_is_idempotent(app, fx, client, database):
    inbound(client, fx, "+15550142290", "one", sid="SM-dup")
    inbound(client, fx, "+15550142290", "one", sid="SM-dup")
    with database.session() as db:
        assert len(db.scalars(select(Message)).all()) == 1


def test_stop_opts_out_sends_one_confirmation_and_blocks_sends(app, fx, client, database, worker, login):
    """§11.1 #5"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "STOP")
    with database.session() as db:
        g = db.get(Guest, fx.guest_inhouse_a.id)
        assert g.sms_consent_status == SmsConsentStatus.opted_out
        c = db.scalar(select(Conversation).where(Conversation.guest_id == g.id))
        msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.sent_at)).all()
        assert [m.direction for m in msgs] == [Direction.inbound, Direction.outbound]
        assert "unsubscribed" in msgs[1].body.lower() and "START" in msgs[1].body
        assert c.sla_due_at is None  # keyword messages do not start an SLA
    staff = login("agent@hvh.test")
    res = staff.post(f"/api/p/{fx.property_a.id}/conversations/{c.id}/messages", json={"body": "Hello?"})
    assert res.status_code == 422
    assert res.get_json()["error"]["code"] == "CONSENT_OPTED_OUT"
    with database.session() as db:
        assert len(db.scalars(select(Message).where(Message.direction == Direction.outbound)).all()) == 1
        actions = [a.action for a in db.scalars(select(AuditLog)).all()]
        assert "message.rejected_opted_out" in actions and "consent.opted_out" in actions
    # START re-enables
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "START")
    with database.session() as db:
        assert db.get(Guest, fx.guest_inhouse_a.id).sms_consent_status == SmsConsentStatus.opted_in


def test_help_replies_with_property_help_text(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "HELP")
    with database.session() as db:
        out = db.scalar(select(Message).where(Message.direction == Direction.outbound))
        assert "555 0100" in out.body


def test_card_numbers_are_redacted_before_storage(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "charge it to 4242 4242 4242 4242 pls")
    with database.session() as db:
        m = db.scalar(select(Message).where(Message.direction == Direction.inbound))
        assert m.redacted is True and "4242 4242 4242 4242" not in m.body and m.body.endswith("4242 pls")


def test_webhook_rejects_bad_secret_and_unknown_property_number(app, fx, client):
    res = client.post("/api/hooks/sms/inbound", data={"From": "+15550142290", "To": fx.property_a.sms_number,
                                                     "Body": "x", "MessageSid": "SM1"},
                      headers={"X-Mock-Secret": "wrong"})
    assert res.status_code == 401
    res = inbound(client, fx, "+15550142290", "x", to="+19999999999")
    assert res.status_code == 404


def test_inbound_notifies_front_desk_when_unassigned(app, fx, client, database):
    from app.models import Notification

    inbound(client, fx, "+15550142290", "hello")
    with database.session() as db:
        targets = sorted(n.user_id for n in db.scalars(select(Notification)).all())
    assert targets == sorted([fx.agent_a.id, fx.agent_a2.id])
```

`server/tests/test_send.py`:
```python
from sqlalchemy import select

from app import clock
from app.domain import messages
from app.models import Conversation, Message
from app.schemas.enums import DeliveryStatus, Direction
from tests.factories import inbound


def _conversation_id(database, fx):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))


def test_send_queues_message_clears_sla_and_records_first_response(app, fx, client, database, events):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _conversation_id(database, fx)
    clock.advance(minutes=3)
    with database.session() as db:
        m = messages.send(db, fx.property_a.id, cid, "On it, Sarah.", author_user_id=fx.agent_a.id)
        assert m.delivery_status == DeliveryStatus.queued and m.direction == Direction.outbound
        c = db.get(Conversation, cid)
        assert c.sla_due_at is None
        assert c.first_response_seconds == 180
        assert c.last_staff_message_at == clock.now()
    assert any(e.type == "message.created" and e.payload["body"] == "On it, Sarah." for e in events)
    from app.models import Job

    with database.session() as db:
        assert db.scalar(select(Job).where(Job.type == "outbound.send")) is not None


def test_send_via_api_requires_reply_capability(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _conversation_id(database, fx)
    corporate = login("corporate@hvh.test")
    assert corporate.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                          json={"body": "x"}).status_code == 403
    agent = login("agent@hvh.test")
    res = agent.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages", json={"body": "x"})
    assert res.status_code == 201
    assert res.get_json()["deliveryStatus"] == "queued"


def test_first_response_is_recorded_only_once(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    cid = _conversation_id(database, fx)
    clock.advance(minutes=2)
    with database.session() as db:
        messages.send(db, fx.property_a.id, cid, "a", author_user_id=fx.agent_a.id)
    clock.advance(minutes=10)
    with database.session() as db:
        messages.send(db, fx.property_a.id, cid, "b", author_user_id=fx.agent_a.id)
        assert db.get(Conversation, cid).first_response_seconds == 120


def test_send_rejects_over_length(app, fx, client, database):
    import pytest

    from app.errors import ValidationFailed

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    cid = _conversation_id(database, fx)
    with database.session() as db, pytest.raises(ValidationFailed):
        messages.send(db, fx.property_a.id, cid, "x" * 1601, author_user_id=fx.agent_a.id)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_inbound.py tests/test_send.py -q`
Expected: FAIL — 404 on the webhook, `ImportError` for `messages.send`.

- [ ] **Step 3: Add conversation shapes to `app/schemas/conversations.py`**

Append:
```python
from datetime import date

from app.schemas.enums import ConversationStatus, SmsConsentStatus, StayStatus


class GuestOut(CamelModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool
    sms_consent_status: SmsConsentStatus
    notes_summary: str | None = None


class StayOut(CamelModel):
    id: str
    room_number: str | None = None
    room_type: str | None = None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int
    children: int
    is_return_guest: bool
    stay_count: int


class ConversationSummary(CamelModel):
    id: str
    status: ConversationStatus
    guest: GuestOut
    room_number: str | None = None
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    channel_primary: Channel
    last_guest_message_at: datetime | None = None
    last_staff_message_at: datetime | None = None
    last_message_preview: str | None = None
    sla_due_at: datetime | None = None
    unanswered: bool
    open_work_order_count: int
    snoozed_until: datetime | None = None
```

(Keep the existing `MessageOut`; `ConversationDetail`, `NoteOut`, etc. arrive in Task 12.)

- [ ] **Step 4: Write `app/domain/conversations.py` (creation half; list/detail/assign arrive in Task 12)**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.errors import NotFound
from app.models import Conversation, Guest, Property, Stay
from app.realtime.broadcast import queue_event
from app.schemas.enums import Channel, ConversationStatus


def get(db: Session, property_id: str, conversation_id: str) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                             Conversation.property_id == property_id))
    if c is None:
        raise NotFound("Conversation not found")
    return c


def _setting(db: Session, property_id: str, key: str, default: int) -> int:
    settings = db.scalar(select(Property.settings).where(Property.id == property_id)) or {}
    return int(settings.get(key, default))


def sla_minutes(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "sla_minutes", 15)


def auto_resolve_hours(db: Session, property_id: str) -> int:
    return _setting(db, property_id, "auto_resolve_hours", 4)


def find_or_create_for_guest(db: Session, property_id: str, guest: Guest,
                             stay: Stay | None = None) -> tuple[Conversation, bool]:
    """Returns the guest's single live conversation, reopening an archived one if that is all there is."""
    c = db.scalar(
        select(Conversation).where(Conversation.property_id == property_id,
                                   Conversation.guest_id == guest.id)
        .order_by(Conversation.updated_at.desc())
    )
    if c is None:
        c = Conversation(property_id=property_id, guest_id=guest.id, stay_id=stay.id if stay else None,
                         status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(c)
        db.flush()
        return c, True
    if c.status == ConversationStatus.archived:
        c.status = ConversationStatus.open
        c.archived_at = None
        c.resolution_category_id = None
    elif c.status == ConversationStatus.snoozed:
        c.status = ConversationStatus.open
        c.snoozed_until = None
    if stay and c.stay_id != stay.id:
        c.stay_id = stay.id
    db.flush()
    return c, False


def touch_updated(db: Session, c: Conversation) -> None:
    c.updated_at = clock.now()
    queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
```

- [ ] **Step 5: Add `send` and `record_inbound` to `app/domain/messages.py`**

Add these imports at the top of `messages.py`:
```python
from datetime import timedelta

from app.domain import audit, consent
from app.domain import conversations as conv_domain
from app.domain.redaction import redact
from app.errors import ValidationFailed
from app.models import Conversation, DigitalAsset, Guest, WorkOrder
from app.schemas.enums import AuthorType, Channel, DraftPromptStatus
```
(`DraftPrompt`/`WorkOrder` are used by the `draft_prompt_id` branch; the model already exists.)

Then append:
```python
MAX_BODY = 1600


def send(db: Session, property_id: str, conversation_id: str, body: str, *,
         author_user_id: str | None, author_type: AuthorType = AuthorType.staff,
         digital_asset_id: str | None = None, draft_prompt_id: str | None = None,
         allow_opt_out_confirmation: bool = False, ip: str | None = None,
         user_agent: str | None = None) -> Message:
    """THE outbound path. Every message to a guest goes through here (design.md §9.1)."""
    body = (body or "").strip()
    if not body:
        raise ValidationFailed("Message body is empty")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"Message body exceeds {MAX_BODY} characters")

    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    if guest.sms_consent_status == SmsConsentStatus.opted_out and not allow_opt_out_confirmation:
        # The caller's session will roll back when ConsentError propagates, so the audit row gets its own
        # session. Nothing has been written in `db` yet at this point, so SQLite WAL allows the second writer.
        with get_db().session() as audit_db:
            audit.record(audit_db, property_id, author_user_id, "message.rejected_opted_out", "conversation",
                         conv.id, after={"body_length": len(body)}, ip=ip, user_agent=user_agent)
    consent.assert_can_send(guest, allow_opt_out_confirmation=allow_opt_out_confirmation)

    if digital_asset_id:
        asset = db.scalar(select(DigitalAsset).where(DigitalAsset.id == digital_asset_id,
                                                     DigitalAsset.property_id == property_id))
        if asset is None:
            raise ValidationFailed("Unknown digital asset")
        body = f"{body} /a/{asset.short_code}"
        asset.send_count += 1

    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.outbound,
                author_type=author_type, author_user_id=author_user_id, channel=Channel.sms,
                body=body, digital_asset_id=digital_asset_id, delivery_status=DeliveryStatus.queued,
                sent_at=now)
    db.add(m)

    conv.last_staff_message_at = now
    conv.sla_due_at = None
    conv.sla_breach_notified_at = None
    if conv.first_response_seconds is None and conv.last_guest_message_at is not None \
            and author_type == AuthorType.staff:
        conv.first_response_seconds = int((now - conv.last_guest_message_at).total_seconds())

    if draft_prompt_id:
        from app.models import DraftPrompt

        dp = db.scalar(select(DraftPrompt).where(DraftPrompt.id == draft_prompt_id,
                                                 DraftPrompt.property_id == property_id,
                                                 DraftPrompt.conversation_id == conv.id))
        if dp is not None and dp.status == DraftPromptStatus.pending:
            dp.status = DraftPromptStatus.sent
            dp.resolved_at = now
            dp.resolved_by_user_id = author_user_id
            wo = db.get(WorkOrder, dp.work_order_id)
            if wo is not None:
                wo.guest_notified_at = now

    db.flush()
    jobs.enqueue(db, "outbound.send", {"message_id": m.id})
    audit.record(db, property_id, author_user_id, "message.sent", "message", m.id,
                 after={"conversation_id": conv.id, "length": len(body)}, ip=ip, user_agent=user_agent)
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    conv_domain.touch_updated(db, conv)
    return m


def record_inbound(db: Session, property_id: str, conv: Conversation, body: str,
                   provider_message_id: str, *, start_sla: bool = True) -> Message:
    clean, redacted = redact(body)
    now = clock.now()
    m = Message(conversation_id=conv.id, property_id=property_id, direction=Direction.inbound,
                author_type=AuthorType.guest, channel=Channel.sms, body=clean, redacted=redacted,
                delivery_status=DeliveryStatus.delivered, provider_message_id=provider_message_id,
                sent_at=now, delivered_at=now)
    db.add(m)
    conv.last_guest_message_at = now
    if start_sla:
        conv.sla_due_at = now + timedelta(minutes=conv_domain.sla_minutes(db, property_id))
        conv.sla_breach_notified_at = None
    db.flush()
    queue_event(db, property_id, "message.created",
                MessageOut.model_validate(m).model_dump(mode="json", by_alias=True))
    return m
```

Add `from app.db import get_db` and `SmsConsentStatus` to the imports for the consent block above.

- [ ] **Step 6: Write `app/channels/inbound.py`**

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.base import InboundMessage
from app.domain import consent, guests, messages, notifications, stays
from app.domain import conversations as conv_domain
from app.models import Conversation, Message, Property
from app.realtime.broadcast import queue_event
from app.schemas.enums import AuthorType, SmsConsentStatus


@dataclass
class InboundResult:
    conversation: Conversation
    message: Message
    created_conversation: bool
    keyword: str | None


def property_for_number(db: Session, to_number: str) -> Property | None:
    return db.scalar(select(Property).where(Property.sms_number == guests.normalize_phone(to_number)))


def handle(db: Session, property_id: str, msg: InboundMessage) -> InboundResult:
    existing = db.scalar(select(Message).where(Message.property_id == property_id,
                                               Message.provider_message_id == msg.provider_message_id))
    if existing is not None:
        conv = db.get(Conversation, existing.conversation_id)
        return InboundResult(conv, existing, False, None)

    guest, _ = guests.find_or_create_by_phone(db, property_id, msg.from_)
    if guest.sms_consent_status == SmsConsentStatus.unknown:
        consent.opt_in(db, guest, "inbound_sms")

    stay = stays.find_in_house_for_guest(db, property_id, guest.id)
    conv, created = conv_domain.find_or_create_for_guest(db, property_id, guest, stay)

    keyword = consent.classify_keyword(msg.body)
    message = messages.record_inbound(db, property_id, conv, msg.body, msg.provider_message_id,
                                      start_sla=keyword is None)

    prop = db.get(Property, property_id)
    if keyword == "stop":
        consent.opt_out(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, consent.STOP_CONFIRMATION(prop.name),
                      author_user_id=None, author_type=AuthorType.system,
                      allow_opt_out_confirmation=True)
    elif keyword == "start":
        consent.opt_in(db, guest, "sms_keyword")
        messages.send(db, property_id, conv.id, f"You're resubscribed to {prop.name} messages.",
                      author_user_id=None, author_type=AuthorType.system)
    elif keyword == "help":
        help_text = (prop.settings or {}).get("help_text") or f"{prop.name}: reply to this number."
        messages.send(db, property_id, conv.id, help_text, author_user_id=None,
                      author_type=AuthorType.system, allow_opt_out_confirmation=True)
    else:
        name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or guest.phone_e164
        room = f" · {stay.room_number}" if stay and stay.room_number else ""
        notifications.notify_user_or_department(
            db, property_id, user_id=conv.assigned_user_id, department_id=conv.assigned_department_id,
            type="message.inbound", title=f"{name}{room}", body=message.body[:140],
            entity_type="conversation", entity_id=conv.id)

    queue_event(db, property_id, "conversation.created" if created else "conversation.updated",
                {"id": conv.id})
    return InboundResult(conv, message, created, keyword)
```

Because `messages.send` calls `conv_domain.touch_updated`, a keyword reply will also emit `conversation.updated`; the test only checks `conversation.*` events for the first-message case (which emits exactly one `conversation.created`), so `handle` must **not** call `touch_updated` itself — it queues its own single event as written above. Ensure `messages.send` is not invoked in the non-keyword branch.

- [ ] **Step 7: Write the webhook blueprint and register it**

`server/app/api/hooks.py`:
```python
from flask import Blueprint, request

from app.api._util import db_session, no_content
from app.channels import inbound
from app.channels.registry import get_sms_adapter
from app.errors import NotFound, Unauthorized
from app.ratelimit import rate_limited, webhook_limiter

bp = Blueprint("hooks", __name__, url_prefix="/api/hooks")


@bp.post("/sms/inbound")
@rate_limited(webhook_limiter)
def sms_inbound():
    adapter = get_sms_adapter()
    if not adapter.verify_inbound(request):
        raise Unauthorized("Bad webhook signature")
    payload = request.form.to_dict() if request.form else (request.get_json(silent=True) or {})
    msg = adapter.parse_inbound(payload)
    with db_session() as db:
        prop = inbound.property_for_number(db, msg.to)
        if prop is None:
            raise NotFound("No property uses that number")
        inbound.handle(db, prop.id, msg)
    return no_content()
```

Register `hooks.bp` in `create_app`. Also register a minimal conversations blueprint now so `test_stop_opts_out…` and `test_send_via_api…` can POST a message; the full blueprint is Task 12. Create `server/app/api/conversations.py` with just:

```python
from flask import Blueprint, g

from app.api._util import client_meta, db_session, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import messages
from app.schemas.conversations import MessageOut, SendMessageRequest

bp = Blueprint("conversations", __name__, url_prefix="/api/p/<property_id>/conversations")


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
@require_capability("reply")
def send_message(property_id: str, conversation_id: str):
    body = parse_body(SendMessageRequest)
    ip, ua = client_meta()
    with db_session() as db:
        m = messages.send(db, g.property_id, conversation_id, body.body, author_user_id=g.user.id,
                          digital_asset_id=body.digital_asset_id, draft_prompt_id=body.draft_prompt_id,
                          ip=ip, user_agent=ua)
        return ok(MessageOut.model_validate(m), 201)
```

and add to `app/schemas/conversations.py`:
```python
from pydantic import Field


class SendMessageRequest(CamelModel):
    body: str = Field(min_length=1, max_length=1600)
    digital_asset_id: str | None = None
    draft_prompt_id: str | None = None
```

- [ ] **Step 8: Run the tests**

Run: `python -m pytest -q`
Expected: all pass. The isolation suite now covers `POST …/conversations/<id>/messages` — it must return 403 for the cross-property user *before* the 404 for the dummy conversation id, which the decorator order guarantees.

- [ ] **Step 9: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): conversations, the consent-enforced send path, inbound SMS handling and webhook"
```

---

### Task 12: Conversations API — list with filters, detail, notes, assign/archive/snooze, retry (§11.1 #4, #10)

**Files:**
- Create: `server/app/domain/notes.py`, `server/tests/test_conversations_api.py`, `server/tests/test_note_leakage.py`
- Modify: `server/app/domain/conversations.py` (list, detail, patch), `server/app/schemas/conversations.py` (detail shapes), `server/app/api/conversations.py` (all routes)

**Interfaces:**
- Produces: `conversations.list(db, property_id, *, filter: str, viewer_user_id, viewer_role, viewer_department_id, dept: str | None, limit=50, offset=0) -> list[ConversationSummary]` where `filter ∈ {all, mine, unassigned, overdue, resolved, archived}`; `conversations.detail(db, property_id, conversation_id) -> ConversationDetail`; `conversations.patch(db, property_id, conversation_id, actor_user_id, changes: ConversationPatch) -> Conversation`; `conversations.guest_thread(db, property_id, phone) -> GuestThread`; `notes.create(db, property_id, conversation_id, author_user_id, body) -> InternalNote` (extracts `@first_name` mentions → notifications); `notes.list(db, property_id, conversation_id) -> list[NoteOut]`. Schemas: `NoteOut`, `WorkOrderBrief`, `DraftPromptOut`, `ConversationDetail` (strict), `GuestThread` + `GuestThreadMessage` (strict, no note field), `ConversationPatch`, `CreateNoteRequest`, `ListQuery`. Routes: `GET conversations`, `GET conversations/<id>`, `POST conversations/<id>/messages`, `POST conversations/<id>/messages/<mid>/retry`, `POST conversations/<id>/notes`, `PATCH conversations/<id>`, `POST conversations/<id>/draft-prompts/<pid>/dismiss` (the dismiss route lands in Task 15 when `draft_prompts` exists — list it here so the blueprint is complete, but implement in 15).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_conversations_api.py`:
```python
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.models import Conversation, Message
from app.schemas.enums import ConversationStatus, DeliveryStatus
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def _base(fx):
    return f"/api/p/{fx.property_a.id}/conversations"


def test_list_sorts_oldest_unanswered_first_and_shows_context(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "late checkout?")
    clock.advance(minutes=1)
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    c = login("agent@hvh.test")
    rows = c.get(_base(fx)).get_json()
    assert [r["guest"]["firstName"] for r in rows] == ["Diego", "Sarah"]
    sarah = rows[1]
    assert sarah["roomNumber"] == "412" and sarah["unanswered"] is True
    assert sarah["lastMessagePreview"] == "AC broken"
    assert sarah["slaDueAt"] is not None


def test_filters_mine_unassigned_overdue_resolved_archived(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "one")
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    diego, sarah = _cid(database, fx.guest_nostay_a.id), _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    assert c.patch(f"{_base(fx)}/{sarah}", json={"assignedUserId": fx.agent_a.id}).status_code == 200
    assert {r["id"] for r in c.get(_base(fx) + "?filter=mine").get_json()} == {sarah}
    assert {r["id"] for r in c.get(_base(fx) + "?filter=unassigned").get_json()} == {diego}
    assert c.get(_base(fx) + "?filter=overdue").get_json() == []
    clock.advance(minutes=16)
    assert {r["id"] for r in c.get(_base(fx) + "?filter=overdue").get_json()} == {diego, sarah}
    # Resolved: no guest message for 4h and no open WO → leaves "all", appears in "resolved".
    c.post(f"{_base(fx)}/{diego}/messages", json={"body": "Sure"})
    clock.advance(hours=4, minutes=1)
    assert diego not in {r["id"] for r in c.get(_base(fx)).get_json()}
    assert {r["id"] for r in c.get(_base(fx) + "?filter=resolved").get_json()} == {diego}
    # Archive with a category (none seeded → null), then it lives only in "archived".
    assert c.patch(f"{_base(fx)}/{diego}", json={"status": "archived"}).status_code == 200
    assert {r["id"] for r in c.get(_base(fx) + "?filter=archived").get_json()} == {diego}
    assert diego not in {r["id"] for r in c.get(_base(fx) + "?filter=resolved").get_json()}


def test_dept_staff_sees_only_their_department_or_own_conversations(app, fx, client, database, login):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "one")
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    diego, sarah = _cid(database, fx.guest_nostay_a.id), _cid(database, fx.guest_inhouse_a.id)
    agent = login("agent@hvh.test")
    agent.patch(f"{_base(fx)}/{sarah}", json={"assignedDepartmentId": fx.dept_engineering.id})
    eng = login("engineer@hvh.test")
    assert {r["id"] for r in eng.get(_base(fx)).get_json()} == {sarah}
    assert eng.get(f"{_base(fx)}/{diego}").status_code == 403


def test_detail_includes_messages_notes_and_stay(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    assert c.post(f"{_base(fx)}/{cid}/notes", json={"body": "Gold guest, @Marcus please watch"}).status_code == 201
    d = c.get(f"{_base(fx)}/{cid}").get_json()
    assert d["guest"]["firstName"] == "Sarah" and d["stay"]["roomNumber"] == "412"
    assert [m["body"] for m in d["messages"]] == ["AC broken"]
    assert d["notes"][0]["body"].startswith("Gold guest") and d["notes"][0]["authorName"] == "Ava Agent"
    assert d["workOrders"] == [] and d["draftPrompts"] == []


def test_note_mention_notifies_mentioned_user(app, fx, client, database, login):
    from app.models import Notification

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    login("agent@hvh.test").post(f"{_base(fx)}/{cid}/notes", json={"body": "@Marcus can you take this"})
    with database.session() as db:
        n = db.scalar(select(Notification).where(Notification.type == "note.mention"))
        assert n.user_id == fx.agent_a2.id


def test_snooze_hides_and_wakes(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    until = (clock.now() + timedelta(hours=1)).isoformat()
    assert c.patch(f"{_base(fx)}/{cid}", json={"status": "snoozed", "snoozedUntil": until}).status_code == 200
    assert c.get(_base(fx)).get_json() == []
    with database.session() as db:
        assert db.get(Conversation, cid).status == ConversationStatus.snoozed


def test_retry_failed_message_via_api(app, fx, client, database, login, worker):
    """§11.1 #4 (server half): failure carries the provider error; retry re-queues."""
    with database.session() as db:
        g = db.get(type(fx.guest_inhouse_a), fx.guest_inhouse_a.id)
        g.phone_e164 = "+15552000000"
    inbound(client, fx, "+15552000000", "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    c = login("agent@hvh.test")
    mid = c.post(f"{_base(fx)}/{cid}/messages", json={"body": "hello"}).get_json()["id"]
    worker.tick(); clock.advance(seconds=0.5); worker.tick()
    d = c.get(f"{_base(fx)}/{cid}").get_json()
    failed = [m for m in d["messages"] if m["id"] == mid][0]
    assert failed["deliveryStatus"] == "failed" and failed["providerErrorCode"] == "30007"
    res = c.post(f"{_base(fx)}/{cid}/messages/{mid}/retry")
    assert res.status_code == 200 and res.get_json()["deliveryStatus"] == "queued"


def test_archive_requires_capability(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    login("agent@hvh.test").patch(f"{_base(fx)}/{cid}", json={"assignedDepartmentId": fx.dept_engineering.id})
    eng = login("engineer@hvh.test")
    assert eng.patch(f"{_base(fx)}/{cid}", json={"status": "archived"}).status_code == 403
```

`server/tests/test_note_leakage.py`:
```python
"""§11.1 #10: an internal note never appears in any guest-facing payload."""
import json

from pydantic import ValidationError

from app.domain import conversations
from app.schemas.conversations import GuestThread
from tests.factories import inbound

SECRET = "SECRET-NOTE-do-not-leak-7f3a"


def test_guest_thread_excludes_notes_entirely(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
    c = login("agent@hvh.test")
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/notes", json={"body": SECRET})
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages", json={"body": "visible reply"})
    with database.session() as db:
        thread = conversations.guest_thread(db, fx.property_a.id, fx.guest_inhouse_a.phone_e164)
    payload = json.dumps(thread.model_dump(mode="json", by_alias=True))
    assert SECRET not in payload
    assert "visible reply" in payload
    assert "note" not in payload.lower()


def test_guest_thread_schema_rejects_a_notes_field():
    try:
        GuestThread.model_validate({"phone": "+1", "propertyName": "x", "messages": [], "notes": []})
    except ValidationError:
        return
    raise AssertionError("GuestThread accepted a 'notes' field — it must be extra='forbid'")


def test_staff_detail_keeps_notes_in_a_separate_array(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
    c = login("agent@hvh.test")
    c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/notes", json={"body": SECRET})
    d = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()
    assert all(SECRET not in m["body"] for m in d["messages"])
    assert d["notes"][0]["body"] == SECRET
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_conversations_api.py tests/test_note_leakage.py -q`
Expected: FAIL — 404/405 on the new routes, `ImportError` for `GuestThread`.

- [ ] **Step 3: Add the remaining schemas to `app/schemas/conversations.py`**

```python
from app.schemas.enums import DraftPromptStatus, Priority, WorkOrderStatus, WorkOrderType


class NoteOut(CamelModel):
    id: str
    author_user_id: str
    author_name: str
    body: str
    mentions: list[str]
    created_at: datetime


class WorkOrderBrief(CamelModel):
    id: str
    title: str
    status: WorkOrderStatus
    priority: Priority
    type: WorkOrderType
    department_id: str | None = None
    assigned_user_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    guest_notified_at: datetime | None = None


class DraftPromptOut(CamelModel):
    id: str
    work_order_id: str
    work_order_title: str
    body: str
    status: DraftPromptStatus
    created_at: datetime


class ConversationDetail(CamelModel):
    id: str
    status: ConversationStatus
    guest: GuestOut
    stay: StayOut | None = None
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    channel_primary: Channel
    last_guest_message_at: datetime | None = None
    last_staff_message_at: datetime | None = None
    first_response_seconds: int | None = None
    sla_due_at: datetime | None = None
    snoozed_until: datetime | None = None
    resolution_category_id: str | None = None
    archived_at: datetime | None = None
    messages: list[MessageOut]
    notes: list[NoteOut]
    work_orders: list[WorkOrderBrief]
    draft_prompts: list[DraftPromptOut]


class GuestThreadMessage(CamelModel):
    """What a guest could ever see. Deliberately has no field that could carry an internal note."""

    id: str
    direction: Direction
    body: str
    sent_at: datetime | None = None
    delivery_status: DeliveryStatus


class GuestThread(CamelModel):
    phone: str
    property_name: str
    messages: list[GuestThreadMessage]


class ConversationPatch(CamelModel):
    assigned_user_id: str | None = None
    assigned_department_id: str | None = None
    status: ConversationStatus | None = None
    resolution_category_id: str | None = None
    snoozed_until: datetime | None = None
    clear_assignment: bool = False


class CreateNoteRequest(CamelModel):
    body: str = Field(min_length=1, max_length=4000)


class ListQuery(CamelModel):
    filter: str = "all"
    dept: str | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
```

- [ ] **Step 4: Write `app/domain/notes.py`**

```python
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, notifications
from app.domain import conversations as conv_domain
from app.models import InternalNote, PropertyMembership, UserAccount
from app.schemas.conversations import NoteOut

_MENTION = re.compile(r"@([A-Za-z][\w'-]*)")


def _resolve_mentions(db: Session, property_id: str, body: str) -> list[str]:
    names = {m.lower() for m in _MENTION.findall(body)}
    if not names:
        return []
    rows = db.execute(
        select(UserAccount.id, UserAccount.first_name)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .where(PropertyMembership.property_id == property_id)
    ).all()
    return [uid for uid, first in rows if first.lower() in names]


def create(db: Session, property_id: str, conversation_id: str, author_user_id: str, body: str) -> InternalNote:
    conv = conv_domain.get(db, property_id, conversation_id)
    mentions = _resolve_mentions(db, property_id, body)
    note = InternalNote(conversation_id=conv.id, property_id=property_id, author_user_id=author_user_id,
                        body=body.strip(), mentions=mentions)
    db.add(note)
    db.flush()
    author = db.get(UserAccount, author_user_id)
    for uid in mentions:
        if uid != author_user_id:
            notifications.create(db, property_id, uid, "note.mention",
                                 f"{author.first_name} mentioned you", body=body[:140],
                                 entity_type="conversation", entity_id=conv.id)
    audit.record(db, property_id, author_user_id, "note.created", "internal_note", note.id,
                 after={"conversation_id": conv.id})
    conv_domain.touch_updated(db, conv)
    return note


def list_for(db: Session, property_id: str, conversation_id: str) -> list[NoteOut]:
    rows = db.execute(
        select(InternalNote, UserAccount)
        .join(UserAccount, UserAccount.id == InternalNote.author_user_id)
        .where(InternalNote.conversation_id == conversation_id, InternalNote.property_id == property_id)
        .order_by(InternalNote.created_at)
    ).all()
    return [NoteOut(id=n.id, author_user_id=n.author_user_id, author_name=f"{u.first_name} {u.last_name}",
                    body=n.body, mentions=list(n.mentions or []), created_at=n.created_at)
            for n, u in rows]
```

- [ ] **Step 5: Add list/detail/patch/guest_thread to `app/domain/conversations.py`**

Append (with the extra imports `and_, case, exists, func, or_` from sqlalchemy, `timedelta`, the models `Department, InternalNote, Message, WorkOrder, DraftPrompt, UserAccount`, the schemas, `Role`, `WorkOrderStatus`, `DraftPromptStatus`, `Direction`, and `from app.domain import audit, notifications`):

```python
OPEN_WO = [WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress, WorkOrderStatus.blocked]


def _open_wo_exists():
    return exists().where(WorkOrder.source_conversation_id == Conversation.id, WorkOrder.status.in_(OPEN_WO))


def _resolved_condition(db: Session, property_id: str):
    """Spec §4 'Resolved': open, quiet for N hours, no open work order — and answered, so an ignored
    guest can never fall out of the queue (a refinement of the spec wording)."""
    cutoff = clock.now() - timedelta(hours=auto_resolve_hours(db, property_id))
    return and_(Conversation.status == ConversationStatus.open,
                Conversation.last_guest_message_at.isnot(None),
                Conversation.last_guest_message_at < cutoff,
                ~_unanswered_expr(),
                ~_open_wo_exists())


def _unanswered_expr():
    return and_(Conversation.last_guest_message_at.isnot(None),
                or_(Conversation.last_staff_message_at.is_(None),
                    Conversation.last_staff_message_at < Conversation.last_guest_message_at))


def viewer_scope(q, viewer_role: Role, viewer_user_id: str, viewer_department_id: str | None):
    if viewer_role == Role.dept_staff:
        return q.where(or_(Conversation.assigned_user_id == viewer_user_id,
                           Conversation.assigned_department_id == viewer_department_id))
    return q


def list(db: Session, property_id: str, *, filter: str, viewer_user_id: str, viewer_role: Role,
         viewer_department_id: str | None, dept: str | None = None, limit: int = 50,
         offset: int = 0) -> list[ConversationSummary]:  # noqa: A001 — mirrors the API name
    now = clock.now()
    live = Conversation.status.in_([ConversationStatus.open, ConversationStatus.snoozed])
    resolved = _resolved_condition(db, property_id)
    q = select(Conversation).where(Conversation.property_id == property_id)
    if filter == "all":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved)
    elif filter == "mine":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved,
                    Conversation.assigned_user_id == viewer_user_id)
    elif filter == "unassigned":
        q = q.where(Conversation.status == ConversationStatus.open, ~resolved,
                    Conversation.assigned_user_id.is_(None), Conversation.assigned_department_id.is_(None))
    elif filter == "overdue":
        q = q.where(Conversation.status == ConversationStatus.open, Conversation.sla_due_at.isnot(None),
                    Conversation.sla_due_at < now)
    elif filter == "resolved":
        q = q.where(resolved)
    elif filter == "archived":
        q = q.where(Conversation.status == ConversationStatus.archived)
    elif filter == "snoozed":
        q = q.where(Conversation.status == ConversationStatus.snoozed)
    else:
        raise ValidationFailed(f"Unknown filter {filter!r}")
    if dept:
        q = q.where(Conversation.assigned_department_id == dept)
    q = viewer_scope(q, viewer_role, viewer_user_id, viewer_department_id)
    q = q.order_by(case((_unanswered_expr(), 0), else_=1),
                   Conversation.last_guest_message_at.asc().nulls_last(),
                   Conversation.updated_at.desc()).limit(limit).offset(offset)
    rows = db.scalars(q).all()
    return [_summary(db, c) for c in rows]


def _last_preview(db: Session, conversation_id: str) -> str | None:
    body = db.scalar(select(Message.body).where(Message.conversation_id == conversation_id)
                     .order_by(Message.sent_at.desc()).limit(1))
    return body[:140] if body else None


def _open_wo_count(db: Session, conversation_id: str) -> int:
    return db.scalar(select(func.count()).select_from(WorkOrder).where(
        WorkOrder.source_conversation_id == conversation_id, WorkOrder.status.in_(OPEN_WO))) or 0


def _summary(db: Session, c: Conversation) -> ConversationSummary:
    unanswered = bool(c.last_guest_message_at and (c.last_staff_message_at is None
                                                    or c.last_staff_message_at < c.last_guest_message_at))
    return ConversationSummary(
        id=c.id, status=c.status, guest=GuestOut.model_validate(c.guest),
        room_number=c.stay.room_number if c.stay else None,
        assigned_user_id=c.assigned_user_id, assigned_department_id=c.assigned_department_id,
        channel_primary=c.channel_primary, last_guest_message_at=c.last_guest_message_at,
        last_staff_message_at=c.last_staff_message_at, last_message_preview=_last_preview(db, c.id),
        sla_due_at=c.sla_due_at, unanswered=unanswered, open_work_order_count=_open_wo_count(db, c.id),
        snoozed_until=c.snoozed_until,
    )


def assert_viewer_can_see(c: Conversation, viewer_role: Role, viewer_user_id: str,
                          viewer_department_id: str | None) -> None:
    if viewer_role == Role.dept_staff and not (
        c.assigned_user_id == viewer_user_id or c.assigned_department_id == viewer_department_id
    ):
        raise Forbidden("This conversation belongs to another department")


def detail(db: Session, property_id: str, conversation_id: str) -> ConversationDetail:
    from app.domain import notes as notes_domain

    c = get(db, property_id, conversation_id)
    msgs = db.scalars(select(Message).where(Message.conversation_id == c.id).order_by(Message.sent_at)).all()
    wos = db.scalars(select(WorkOrder).where(WorkOrder.source_conversation_id == c.id)
                     .order_by(WorkOrder.created_at.desc())).all()
    prompts = db.execute(select(DraftPrompt, WorkOrder.title).join(WorkOrder, WorkOrder.id == DraftPrompt.work_order_id)
                         .where(DraftPrompt.conversation_id == c.id, DraftPrompt.status == DraftPromptStatus.pending)
                         .order_by(DraftPrompt.created_at)).all()
    return ConversationDetail(
        id=c.id, status=c.status, guest=GuestOut.model_validate(c.guest),
        stay=StayOut.model_validate(c.stay) if c.stay else None,
        assigned_user_id=c.assigned_user_id, assigned_department_id=c.assigned_department_id,
        channel_primary=c.channel_primary, last_guest_message_at=c.last_guest_message_at,
        last_staff_message_at=c.last_staff_message_at, first_response_seconds=c.first_response_seconds,
        sla_due_at=c.sla_due_at, snoozed_until=c.snoozed_until,
        resolution_category_id=c.resolution_category_id, archived_at=c.archived_at,
        messages=[MessageOut.model_validate(m) for m in msgs],
        notes=notes_domain.list_for(db, property_id, c.id),
        work_orders=[WorkOrderBrief.model_validate(w) for w in wos],
        draft_prompts=[DraftPromptOut(id=p.id, work_order_id=p.work_order_id, work_order_title=title,
                                      body=p.body, status=p.status, created_at=p.created_at)
                       for p, title in prompts],
    )


def guest_thread(db: Session, property_id: str, phone: str) -> GuestThread:
    """Guest-facing shape. Queries only `message` — internal_note is never touched here."""
    from app.domain.guests import find_by_phone

    prop = db.get(Property, property_id)
    guest = find_by_phone(db, property_id, phone)
    msgs: list[Message] = []
    if guest:
        msgs = db.scalars(
            select(Message).join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.guest_id == guest.id, Message.property_id == property_id)
            .order_by(Message.sent_at)
        ).all()
    return GuestThread(phone=guest.phone_e164 if guest else phone, property_name=prop.name,
                       messages=[GuestThreadMessage(id=m.id, direction=m.direction, body=m.body,
                                                    sent_at=m.sent_at, delivery_status=m.delivery_status)
                                 for m in msgs])


def patch(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
          changes: ConversationPatch, *, can_archive: bool) -> Conversation:
    c = get(db, property_id, conversation_id)
    before = {"status": c.status.value, "assigned_user_id": c.assigned_user_id,
              "assigned_department_id": c.assigned_department_id}
    if changes.clear_assignment:
        c.assigned_user_id = None
        c.assigned_department_id = None
    if changes.assigned_user_id is not None:
        if not db.scalar(select(PropertyMembership.id).where(PropertyMembership.property_id == property_id,
                                                              PropertyMembership.user_id == changes.assigned_user_id)):
            raise ValidationFailed("Assignee is not a member of this property")
        c.assigned_user_id = changes.assigned_user_id
        if changes.assigned_user_id != actor_user_id:
            notifications.create(db, property_id, changes.assigned_user_id, "conversation.assigned",
                                 "Conversation assigned to you", entity_type="conversation", entity_id=c.id)
    if changes.assigned_department_id is not None:
        if not db.scalar(select(Department.id).where(Department.id == changes.assigned_department_id,
                                                     Department.property_id == property_id)):
            raise ValidationFailed("Unknown department")
        c.assigned_department_id = changes.assigned_department_id
        c.assigned_user_id = None if changes.assigned_user_id is None else c.assigned_user_id
    if changes.status is not None:
        if changes.status == ConversationStatus.archived:
            if not can_archive:
                raise Forbidden("Your role cannot archive conversations")
            c.status = ConversationStatus.archived
            c.archived_at = clock.now()
            c.resolution_category_id = changes.resolution_category_id
        elif changes.status == ConversationStatus.snoozed:
            if changes.snoozed_until is None:
                raise ValidationFailed("snoozedUntil is required to snooze")
            c.status = ConversationStatus.snoozed
            c.snoozed_until = changes.snoozed_until
        elif changes.status == ConversationStatus.open:
            c.status = ConversationStatus.open
            c.archived_at = None
            c.snoozed_until = None
    elif changes.resolution_category_id is not None:
        c.resolution_category_id = changes.resolution_category_id
    db.flush()
    after = {"status": c.status.value, "assigned_user_id": c.assigned_user_id,
             "assigned_department_id": c.assigned_department_id}
    audit.record(db, property_id, actor_user_id, "conversation.patched", "conversation", c.id,
                 before=before, after=after)
    queue_event(db, property_id, "conversation.assigned" if before["assigned_user_id"] != after["assigned_user_id"]
                or before["assigned_department_id"] != after["assigned_department_id"] else "conversation.updated",
                {"id": c.id})
    return c
```

`Forbidden`, `ValidationFailed` come from `app.errors`; `PropertyMembership`, `Department` from `app.models`.

- [ ] **Step 6: Complete `app/api/conversations.py`**

Replace the file with:
```python
from flask import Blueprint, g

from app.api._util import client_meta, db_session, no_content, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import conversations, messages, notes
from app.schemas.conversations import (
    ConversationPatch, CreateNoteRequest, ListQuery, MessageOut, NoteOut, SendMessageRequest,
)

bp = Blueprint("conversations", __name__, url_prefix="/api/p/<property_id>/conversations")


def _viewer():
    m = g.membership
    return dict(viewer_user_id=g.user.id, viewer_role=m.role, viewer_department_id=m.department_id)


@bp.get("")
@require_auth
@require_property
def list_conversations(property_id: str):
    q = parse_query(ListQuery)
    with db_session() as db:
        return ok(conversations.list(db, g.property_id, filter=q.filter, dept=q.dept, limit=q.limit,
                                     offset=q.offset, **_viewer()))


@bp.get("/<conversation_id>")
@require_auth
@require_property
def get_conversation(property_id: str, conversation_id: str):
    with db_session() as db:
        c = conversations.get(db, g.property_id, conversation_id)
        conversations.assert_viewer_can_see(c, g.membership.role, g.user.id, g.membership.department_id)
        return ok(conversations.detail(db, g.property_id, conversation_id))


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
@require_capability("reply")
def send_message(property_id: str, conversation_id: str):
    body = parse_body(SendMessageRequest)
    ip, ua = client_meta()
    with db_session() as db:
        m = messages.send(db, g.property_id, conversation_id, body.body, author_user_id=g.user.id,
                          digital_asset_id=body.digital_asset_id, draft_prompt_id=body.draft_prompt_id,
                          ip=ip, user_agent=ua)
        return ok(MessageOut.model_validate(m), 201)


@bp.post("/<conversation_id>/messages/<message_id>/retry")
@require_auth
@require_property
@require_capability("reply")
def retry_message(property_id: str, conversation_id: str, message_id: str):
    with db_session() as db:
        conversations.get(db, g.property_id, conversation_id)
        m = messages.retry(db, g.property_id, message_id)
        return ok(MessageOut.model_validate(m))


@bp.post("/<conversation_id>/notes")
@require_auth
@require_property
@require_capability("add_note")
def add_note(property_id: str, conversation_id: str):
    body = parse_body(CreateNoteRequest)
    with db_session() as db:
        n = notes.create(db, g.property_id, conversation_id, g.user.id, body.body)
        out = [x for x in notes.list_for(db, g.property_id, conversation_id) if x.id == n.id][0]
        return ok(out, 201)


@bp.patch("/<conversation_id>")
@require_auth
@require_property
@require_capability("assign")
def patch_conversation(property_id: str, conversation_id: str):
    changes = parse_body(ConversationPatch)
    with db_session() as db:
        conversations.patch(db, g.property_id, conversation_id, g.user.id, changes,
                            can_archive=has_capability(g.membership.role, "archive"))
        return ok(conversations.detail(db, g.property_id, conversation_id))
```

- [ ] **Step 7: Run the tests**

Run: `python -m pytest -q`
Expected: all pass. If `test_member_of_a_gets_403_on_every_b_route` fails on `PATCH` with a 400, the decorator order is wrong — `require_property` must run before `parse_body`, which it does when `parse_body` is called inside the view function, not in a decorator.

- [ ] **Step 8: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): conversation list/detail/patch, internal notes with mentions, guest-thread shape"
```

---

### Task 13: SLA sweep and snooze wake (§11.1 #8)

**Files:**
- Create: `server/app/queue/handlers/sla.py`, `server/app/queue/handlers/snooze.py`, `server/tests/test_sla.py`

**Interfaces:**
- Produces: handlers `sla.sweep` (recurring 30 s) and `snooze.wake` (recurring 60 s); `sla.sweep_once(db) -> int` and `snooze.wake_once(db) -> int` for direct use in tests.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_sla.py`:
```python
from datetime import timedelta

from sqlalchemy import select

from app import clock
from app.models import Conversation, Notification
from app.queue.handlers.sla import sweep_once
from app.queue.handlers.snooze import wake_once
from app.schemas.enums import ConversationStatus
from tests.factories import inbound


def test_overdue_conversation_notifies_assignee_once(app, fx, client, database, login, events):
    """§11.1 #8"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        c.assigned_user_id = fx.agent_a.id
        cid = c.id
    with database.session() as db:
        assert sweep_once(db) == 0  # not yet due
    clock.advance(minutes=15, seconds=1)
    with database.session() as db:
        assert sweep_once(db) == 1
    with database.session() as db:
        assert sweep_once(db) == 0  # notified only once
        n = db.scalars(select(Notification).where(Notification.type == "sla.breach")).all()
        assert len(n) == 1 and n[0].user_id == fx.agent_a.id and n[0].entity_id == cid
    staff = login("agent@hvh.test")
    assert {r["id"] for r in staff.get(f"/api/p/{fx.property_a.id}/conversations?filter=overdue").get_json()} == {cid}
    assert any(e.type == "conversation.updated" and e.payload["id"] == cid for e in events)


def test_overdue_unassigned_conversation_notifies_front_desk(app, fx, client, database):
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "hello")
    clock.advance(minutes=16)
    with database.session() as db:
        sweep_once(db)
        targets = sorted(n.user_id for n in db.scalars(select(Notification).where(Notification.type == "sla.breach")).all())
    assert targets == sorted([fx.agent_a.id, fx.agent_a2.id])


def test_reply_clears_the_breach_and_a_new_inbound_restarts_it(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    with database.session() as db:
        cid = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
    clock.advance(minutes=16)
    with database.session() as db:
        assert sweep_once(db) == 1
    login("agent@hvh.test").post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages", json={"body": "hi"})
    with database.session() as db:
        c = db.get(Conversation, cid)
        assert c.sla_due_at is None and c.sla_breach_notified_at is None
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "two")
    clock.advance(minutes=16)
    with database.session() as db:
        assert sweep_once(db) == 1


def test_snooze_wake_reopens_due_conversations(app, fx, client, database):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "one")
    with database.session() as db:
        c = db.scalar(select(Conversation).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        c.status = ConversationStatus.snoozed
        c.snoozed_until = clock.now() + timedelta(minutes=30)
        cid = c.id
    with database.session() as db:
        assert wake_once(db) == 0
    clock.advance(minutes=31)
    with database.session() as db:
        assert wake_once(db) == 1
        c = db.get(Conversation, cid)
        assert c.status == ConversationStatus.open and c.snoozed_until is None


def test_recurring_jobs_are_registered(app):
    from app.queue import jobs

    assert jobs.RECURRING["sla.sweep"] == 30 and jobs.RECURRING["snooze.wake"] == 60
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_sla.py -q`
Expected: FAIL with `ModuleNotFoundError: app.queue.handlers.sla`.

- [ ] **Step 3: Write the handlers**

`server/app/queue/handlers/sla.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import notifications
from app.models import Conversation, Guest, Stay
from app.queue.handlers import handler
from app.realtime.broadcast import queue_event
from app.schemas.enums import ConversationStatus


def sweep_once(db: Session) -> int:
    now = clock.now()
    due = db.scalars(select(Conversation).where(
        Conversation.status == ConversationStatus.open,
        Conversation.sla_due_at.isnot(None), Conversation.sla_due_at < now,
        Conversation.sla_breach_notified_at.is_(None))).all()
    for c in due:
        guest = db.get(Guest, c.guest_id)
        stay = db.get(Stay, c.stay_id) if c.stay_id else None
        name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or guest.phone_e164
        room = f" · {stay.room_number}" if stay and stay.room_number else ""
        minutes = int((now - c.sla_due_at).total_seconds() // 60)
        notifications.notify_user_or_department(
            db, c.property_id, user_id=c.assigned_user_id, department_id=c.assigned_department_id,
            type="sla.breach", title=f"Response overdue: {name}{room}",
            body=f"No reply for {minutes} min past the SLA", entity_type="conversation", entity_id=c.id)
        c.sla_breach_notified_at = now
        queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
    db.flush()
    return len(due)


@handler("sla.sweep")
def sla_sweep(db: Session, payload: dict) -> None:
    sweep_once(db)
```

`server/app/queue/handlers/snooze.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation
from app.queue.handlers import handler
from app.realtime.broadcast import queue_event
from app.schemas.enums import ConversationStatus


def wake_once(db: Session) -> int:
    now = clock.now()
    due = db.scalars(select(Conversation).where(
        Conversation.status == ConversationStatus.snoozed,
        Conversation.snoozed_until.isnot(None), Conversation.snoozed_until <= now)).all()
    for c in due:
        c.status = ConversationStatus.open
        c.snoozed_until = None
        queue_event(db, c.property_id, "conversation.updated", {"id": c.id})
    db.flush()
    return len(due)


@handler("snooze.wake")
def snooze_wake(db: Session, payload: dict) -> None:
    wake_once(db)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): SLA breach sweep and snooze wake jobs"
```

---

### Task 14: Work orders domain — state machine, prefill, events, closed-loop prompt (§11.1 #6, #7)

**Files:**
- Create: `server/app/domain/work_orders.py`, `server/app/domain/draft_prompts.py`, `server/app/schemas/work_orders.py`, `server/tests/test_work_orders.py`

**Interfaces:**
- Produces: `work_orders.TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]]`; `assert_transition(from_, to)` raising `TransitionError`; `create(db, property_id, actor_user_id, data: CreateWorkOrder) -> WorkOrder` (writes `created` event, assigns → `assigned` status, notifies assignee/department, broadcasts `work_order.created`); `prefill_from_conversation(db, property_id, conversation_id) -> WorkOrderPrefill` (title from last inbound body, description = last 3 inbound messages, room, department guessed by keyword); `transition(db, property_id, work_order_id, actor_user_id, to, comment=None) -> WorkOrder` (events, timestamps, `acknowledged_at`, on `complete` with `source_conversation_id` → `draft_prompts.create_for_completion`); `assign(db, property_id, work_order_id, actor_user_id, *, user_id=None, department_id=None)`; `comment(db, ...)`; `set_priority(db, ...)`; `get(db, property_id, id) -> WorkOrder`; `list(db, property_id, *, status, type, dept, assignee, mine_user_id) -> list[WorkOrderOut]`; `detail(db, property_id, id) -> WorkOrderDetail`. `draft_prompts.create_for_completion(db, wo) -> DraftPrompt | None`; `draft_prompts.dismiss(db, property_id, conversation_id, prompt_id, actor_user_id)`; `draft_prompts.draft_body(guest_first_name, room, title) -> str`. Schemas: `CreateWorkOrder`, `WorkOrderPatch`, `WorkOrderOut`, `WorkOrderEventOut`, `WorkOrderDetail`, `WorkOrderPrefill`, `WorkOrderListQuery`. `DEPARTMENT_KEYWORDS` mapping.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_work_orders.py`:
```python
import pytest
from sqlalchemy import select

from app import clock
from app.domain import work_orders
from app.errors import TransitionError
from app.models import Conversation, DraftPrompt, Message, Notification, WorkOrderEvent
from app.schemas.enums import Direction, DraftPromptStatus, Priority, WorkOrderStatus, WorkOrderType
from app.schemas.work_orders import CreateWorkOrder
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


@pytest.mark.parametrize("frm,to,ok", [
    ("open", "assigned", True), ("open", "in_progress", True), ("open", "cancelled", True),
    ("open", "complete", False), ("assigned", "in_progress", True), ("assigned", "open", True),
    ("in_progress", "blocked", True), ("in_progress", "complete", True), ("blocked", "in_progress", True),
    ("blocked", "complete", False), ("complete", "verified", True), ("complete", "in_progress", True),
    ("verified", "open", False), ("cancelled", "open", False),
])
def test_transition_matrix(frm, to, ok):
    if ok:
        work_orders.assert_transition(WorkOrderStatus(frm), WorkOrderStatus(to))
    else:
        with pytest.raises(TransitionError):
            work_orders.assert_transition(WorkOrderStatus(frm), WorkOrderStatus(to))


def test_prefill_from_conversation(app, fx, client, database):
    """§11.1 #6 (prefill half)"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "Hi there")
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working at all")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        p = work_orders.prefill_from_conversation(db, fx.property_a.id, cid)
    assert p.title == "The AC in our room isn't working at all"
    assert "Hi there" in p.description and "AC" in p.description
    assert p.location_ref == "412" and p.guest_name == "Sarah Chen"
    assert p.department_id == fx.dept_engineering.id and p.type == WorkOrderType.maintenance
    assert p.source_conversation_id == cid and p.source_message_id is not None


def test_create_from_conversation_stores_source_and_notifies_department(app, fx, client, database, events):
    """§11.1 #6 (create half)"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", description="Guest reports warm room", type=WorkOrderType.maintenance,
            priority=Priority.urgent, location_ref="412", department_id=fx.dept_engineering.id,
            source_conversation_id=cid))
        assert wo.status == WorkOrderStatus.open and wo.source_conversation_id == cid
        ev = db.scalars(select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == wo.id)).all()
        assert [e.type.value for e in ev] == ["created"]
        targets = sorted(n.user_id for n in db.scalars(select(Notification).where(Notification.type == "work_order.created")).all())
        assert targets == sorted([fx.engineer_a.id, fx.supervisor_a.id])
    assert any(e.type == "work_order.created" for e in events)


def test_create_with_assignee_starts_assigned(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="Toilet running", type=WorkOrderType.maintenance, location_ref="221",
            department_id=fx.dept_engineering.id, assigned_user_id=fx.engineer_a.id))
        assert wo.status == WorkOrderStatus.assigned and wo.assigned_user_id == fx.engineer_a.id
        n = db.scalar(select(Notification).where(Notification.type == "work_order.assigned"))
        assert n.user_id == fx.engineer_a.id


def test_complete_creates_unsent_editable_draft_prompt(app, fx, client, database, events):
    """§11.1 #7"""
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
        msgs_before = len(db.scalars(select(Message)).all())
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id, WorkOrderStatus.in_progress)
    clock.advance(minutes=14)
    with database.session() as db:
        wo = work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id, WorkOrderStatus.complete,
                                    comment="Cleared condensate line")
        assert wo.completed_at == clock.now() and wo.started_at is not None
        prompts = db.scalars(select(DraftPrompt).where(DraftPrompt.conversation_id == cid)).all()
        assert len(prompts) == 1 and prompts[0].status == DraftPromptStatus.pending
        assert "Sarah" in prompts[0].body and "412" in prompts[0].body
        assert len(db.scalars(select(Message)).all()) == msgs_before  # nothing was sent
        types = [e.type.value for e in db.scalars(select(WorkOrderEvent).where(WorkOrderEvent.work_order_id == wo_id)
                                                   .order_by(WorkOrderEvent.created_at)).all()]
        assert types == ["created", "status_changed", "status_changed"]
    assert any(e.type == "draft_prompt.created" for e in events)
    assert any(e.type == "work_order.updated" for e in events)


def test_complete_without_source_conversation_creates_no_prompt(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="Hallway light", type=WorkOrderType.maintenance, location_ref="5F"))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id, WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id, WorkOrderStatus.complete)
        assert db.scalars(select(DraftPrompt)).all() == []


def test_sending_the_draft_marks_prompt_sent_and_guest_notified(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC not cooling", type=WorkOrderType.maintenance, location_ref="412",
            department_id=fx.dept_engineering.id, source_conversation_id=cid))
        wo_id = wo.id
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id, WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo_id, fx.engineer_a.id, WorkOrderStatus.complete)
        pid = db.scalar(select(DraftPrompt.id).where(DraftPrompt.conversation_id == cid))
    c = login("agent@hvh.test")
    d = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()
    assert d["draftPrompts"][0]["id"] == pid and d["draftPrompts"][0]["workOrderTitle"] == "AC not cooling"
    res = c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                 json={"body": "Hi Sarah — fixed!", "draftPromptId": pid})
    assert res.status_code == 201
    with database.session() as db:
        assert db.get(DraftPrompt, pid).status == DraftPromptStatus.sent
        from app.models import WorkOrder

        assert db.get(WorkOrder, wo_id).guest_notified_at is not None
    assert c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"] == []


def test_invalid_transition_is_409_and_audited(app, fx, database):
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.supervisor_a.id, CreateWorkOrder(
            title="x", type=WorkOrderType.other, location_ref="lobby"))
        with pytest.raises(TransitionError):
            work_orders.transition(db, fx.property_a.id, wo.id, fx.supervisor_a.id, WorkOrderStatus.complete)


def test_department_keyword_guess():
    from app.domain.work_orders import guess_department_type

    assert guess_department_type("the ac is broken and it's hot") == "engineering"
    assert guess_department_type("could we get extra towels and pillows") == "housekeeping"
    assert guess_department_type("late checkout please") == "front_desk"
    assert guess_department_type("hello") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_work_orders.py -q`
Expected: FAIL with `ModuleNotFoundError: app.domain.work_orders`.

- [ ] **Step 3: Write `app/schemas/work_orders.py`**

```python
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import LocationType, Priority, WorkOrderEventType, WorkOrderStatus, WorkOrderType


class CreateWorkOrder(CamelModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    type: WorkOrderType = WorkOrderType.maintenance
    priority: Priority = Priority.normal
    location_type: LocationType = LocationType.room
    location_ref: str | None = None
    department_id: str | None = None
    assigned_user_id: str | None = None
    due_at: datetime | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None


class WorkOrderPatch(CamelModel):
    status: WorkOrderStatus | None = None
    assigned_user_id: str | None = None
    department_id: str | None = None
    priority: Priority | None = None
    comment: str | None = Field(default=None, max_length=2000)
    clear_assignee: bool = False


class WorkOrderOut(CamelModel):
    id: str
    title: str
    description: str | None = None
    type: WorkOrderType
    priority: Priority
    status: WorkOrderStatus
    location_type: LocationType
    location_ref: str | None = None
    department_id: str | None = None
    assigned_user_id: str | None = None
    reported_by_user_id: str | None = None
    source_conversation_id: str | None = None
    source_message_id: str | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    verified_at: datetime | None = None
    guest_notified_at: datetime | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WorkOrderEventOut(CamelModel):
    id: str
    user_id: str | None = None
    user_name: str | None = None
    type: WorkOrderEventType
    from_value: str | None = None
    to_value: str | None = None
    comment: str | None = None
    created_at: datetime


class WorkOrderDetail(WorkOrderOut):
    events: list[WorkOrderEventOut]
    guest_name: str | None = None
    room_number: str | None = None


class WorkOrderPrefill(CamelModel):
    title: str
    description: str
    type: WorkOrderType
    priority: Priority
    location_type: LocationType
    location_ref: str | None = None
    department_id: str | None = None
    guest_name: str | None = None
    source_conversation_id: str
    source_message_id: str | None = None


class WorkOrderListQuery(CamelModel):
    status: str | None = None          # comma-separated
    type: WorkOrderType | None = None
    dept: str | None = None
    assignee: str | None = None
    mine: bool = False
    include_closed: bool = False
```

- [ ] **Step 4: Write `app/domain/draft_prompts.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit
from app.errors import NotFound
from app.models import Conversation, DraftPrompt, Guest, Stay, WorkOrder
from app.realtime.broadcast import queue_event
from app.schemas.enums import DraftPromptStatus


def draft_body(guest_first_name: str | None, room: str | None, title: str) -> str:
    name = guest_first_name or "there"
    where = f" in {room}" if room else ""
    return (f"Hi {name} — our team has taken care of \"{title.lower()}\"{where}. "
            f"Please text us if anything still isn't right.")


def create_for_completion(db: Session, wo: WorkOrder) -> DraftPrompt | None:
    """design.md §6.4: the highest-value twenty lines. Never sends; only proposes."""
    if not wo.source_conversation_id:
        return None
    conv = db.get(Conversation, wo.source_conversation_id)
    if conv is None:
        return None
    existing = db.scalar(select(DraftPrompt).where(DraftPrompt.work_order_id == wo.id,
                                                   DraftPrompt.status == DraftPromptStatus.pending))
    if existing:
        return existing
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    room = stay.room_number if stay else wo.location_ref
    dp = DraftPrompt(property_id=wo.property_id, conversation_id=conv.id, work_order_id=wo.id,
                     body=draft_body(guest.first_name, room, wo.title), status=DraftPromptStatus.pending)
    db.add(dp)
    db.flush()
    queue_event(db, wo.property_id, "draft_prompt.created",
                {"id": dp.id, "conversationId": conv.id, "workOrderId": wo.id, "body": dp.body})
    return dp


def dismiss(db: Session, property_id: str, conversation_id: str, prompt_id: str, actor_user_id: str) -> DraftPrompt:
    dp = db.scalar(select(DraftPrompt).where(DraftPrompt.id == prompt_id, DraftPrompt.property_id == property_id,
                                             DraftPrompt.conversation_id == conversation_id))
    if dp is None:
        raise NotFound("Prompt not found")
    if dp.status == DraftPromptStatus.pending:
        dp.status = DraftPromptStatus.dismissed
        dp.resolved_at = clock.now()
        dp.resolved_by_user_id = actor_user_id
        audit.record(db, property_id, actor_user_id, "draft_prompt.dismissed", "draft_prompt", dp.id)
        queue_event(db, property_id, "conversation.updated", {"id": conversation_id})
    return dp
```

- [ ] **Step 5: Write `app/domain/work_orders.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, draft_prompts, notifications
from app.domain import conversations as conv_domain
from app.errors import NotFound, TransitionError, ValidationFailed
from app.models import (Conversation, Department, Guest, Message, PropertyMembership, Stay, UserAccount,
                        WorkOrder, WorkOrderEvent)
from app.realtime.broadcast import queue_event
from app.schemas.enums import (DepartmentType, Direction, LocationType, Priority, WorkOrderEventType,
                               WorkOrderStatus, WorkOrderType)
from app.schemas.work_orders import (CreateWorkOrder, WorkOrderDetail, WorkOrderEventOut, WorkOrderOut,
                                     WorkOrderPrefill)

S = WorkOrderStatus
TRANSITIONS: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    S.open: {S.assigned, S.in_progress, S.cancelled},
    S.assigned: {S.in_progress, S.open, S.cancelled},
    S.in_progress: {S.blocked, S.complete, S.cancelled},
    S.blocked: {S.in_progress, S.cancelled},
    S.complete: {S.verified, S.in_progress},
    S.verified: set(),
    S.cancelled: set(),
}
OPEN_STATUSES = [S.open, S.assigned, S.in_progress, S.blocked, S.complete]

DEPARTMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "engineering": ("ac", "a/c", "air", "heat", "hvac", "hot", "cold", "leak", "toilet", "shower", "drain",
                    "light", "bulb", "tv", "remote", "wifi", "door", "lock", "broken", "not working",
                    "elevator", "noise", "outlet", "plug"),
    "housekeeping": ("towel", "towels", "pillow", "sheets", "linen", "clean", "dirty", "trash", "vacuum",
                     "amenities", "shampoo", "soap", "toilet paper", "housekeeping", "turndown"),
    "front_desk": ("checkout", "check out", "check-in", "late", "early", "bill", "folio", "charge",
                   "reservation", "key", "parking", "valet", "wake", "luggage"),
}
TYPE_FOR_DEPARTMENT = {"engineering": WorkOrderType.maintenance, "housekeeping": WorkOrderType.housekeeping,
                       "front_desk": WorkOrderType.guest_request}


def assert_transition(from_: WorkOrderStatus, to: WorkOrderStatus) -> None:
    if to not in TRANSITIONS.get(from_, set()):
        raise TransitionError(f"Cannot move a work order from {from_.value} to {to.value}")


def guess_department_type(text: str) -> str | None:
    import re

    t = text.lower()
    scores = {dept: sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", t))
              for dept, kws in DEPARTMENT_KEYWORDS.items()}  # word boundaries: "ac" must not match "back"
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def get(db: Session, property_id: str, work_order_id: str) -> WorkOrder:
    wo = db.scalar(select(WorkOrder).where(WorkOrder.id == work_order_id, WorkOrder.property_id == property_id))
    if wo is None:
        raise NotFound("Work order not found")
    return wo


def _event(db: Session, wo: WorkOrder, user_id: str | None, type: WorkOrderEventType,
           from_value: str | None = None, to_value: str | None = None, comment: str | None = None) -> None:
    db.add(WorkOrderEvent(work_order_id=wo.id, property_id=wo.property_id, user_id=user_id, type=type,
                          from_value=from_value, to_value=to_value, comment=comment))


def _emit(db: Session, wo: WorkOrder, type: str) -> None:
    queue_event(db, wo.property_id, type, WorkOrderOut.model_validate(wo).model_dump(mode="json", by_alias=True))


def _validate_refs(db: Session, property_id: str, department_id: str | None, assigned_user_id: str | None) -> None:
    if department_id and not db.scalar(select(Department.id).where(Department.id == department_id,
                                                                    Department.property_id == property_id)):
        raise ValidationFailed("Unknown department")
    if assigned_user_id and not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id, PropertyMembership.user_id == assigned_user_id)):
        raise ValidationFailed("Assignee is not a member of this property")


def create(db: Session, property_id: str, actor_user_id: str, data: CreateWorkOrder) -> WorkOrder:
    _validate_refs(db, property_id, data.department_id, data.assigned_user_id)
    if data.source_conversation_id:
        conv_domain.get(db, property_id, data.source_conversation_id)
    wo = WorkOrder(property_id=property_id, title=data.title.strip(), description=data.description, type=data.type,
                   priority=data.priority, location_type=data.location_type, location_ref=data.location_ref,
                   department_id=data.department_id, assigned_user_id=data.assigned_user_id,
                   reported_by_user_id=actor_user_id, source_conversation_id=data.source_conversation_id,
                   source_message_id=data.source_message_id, due_at=data.due_at,
                   status=S.assigned if data.assigned_user_id else S.open)
    db.add(wo)
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.created, to_value=wo.status.value)
    if wo.assigned_user_id:
        notifications.create(db, property_id, wo.assigned_user_id, "work_order.assigned",
                             f"Assigned: {wo.title}", body=wo.location_ref, entity_type="work_order", entity_id=wo.id)
    elif wo.department_id:
        notifications.notify_user_or_department(db, property_id, user_id=None, department_id=wo.department_id,
                                                type="work_order.created", title=f"New work order: {wo.title}",
                                                body=wo.location_ref, entity_type="work_order", entity_id=wo.id)
    audit.record(db, property_id, actor_user_id, "work_order.created", "work_order", wo.id,
                 after={"title": wo.title, "source_conversation_id": wo.source_conversation_id})
    _emit(db, wo, "work_order.created")
    if wo.source_conversation_id:
        queue_event(db, property_id, "conversation.updated", {"id": wo.source_conversation_id})
    return wo


def prefill_from_conversation(db: Session, property_id: str, conversation_id: str) -> WorkOrderPrefill:
    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    inbound = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.direction == Direction.inbound)
                         .order_by(Message.sent_at.desc()).limit(3)).all()
    last = inbound[0] if inbound else None
    title = (last.body.strip().splitlines()[0][:120] if last else "Guest request")
    description = "\n".join(m.body for m in reversed(inbound))
    dept_type = guess_department_type(description)
    dept_id = None
    if dept_type:
        dept_id = db.scalar(select(Department.id).where(Department.property_id == property_id,
                                                        Department.type == DepartmentType(dept_type)))
    name = f"{guest.first_name or ''} {guest.last_name or ''}".strip() or None
    return WorkOrderPrefill(
        title=title, description=description, type=TYPE_FOR_DEPARTMENT.get(dept_type, WorkOrderType.guest_request),
        priority=Priority.normal, location_type=LocationType.room if stay else LocationType.other,
        location_ref=stay.room_number if stay else None, department_id=dept_id, guest_name=name,
        source_conversation_id=conv.id, source_message_id=last.id if last else None)


def transition(db: Session, property_id: str, work_order_id: str, actor_user_id: str, to: WorkOrderStatus,
               comment: str | None = None) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    assert_transition(wo.status, to)
    now = clock.now()
    frm = wo.status
    wo.status = to
    if to == S.in_progress and wo.started_at is None:
        wo.started_at = now
    if to == S.complete:
        wo.completed_at = now
    if to == S.verified:
        wo.verified_at = now
    if wo.assigned_user_id == actor_user_id and wo.acknowledged_at is None:
        wo.acknowledged_at = now
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.status_changed, from_value=frm.value, to_value=to.value,
           comment=comment)
    audit.record(db, property_id, actor_user_id, "work_order.transition", "work_order", wo.id,
                 before={"status": frm.value}, after={"status": to.value})
    _emit(db, wo, "work_order.updated")
    if to == S.complete:
        draft_prompts.create_for_completion(db, wo)
    if wo.source_conversation_id:
        queue_event(db, property_id, "conversation.updated", {"id": wo.source_conversation_id})
    return wo


def assign(db: Session, property_id: str, work_order_id: str, actor_user_id: str, *,
           user_id: str | None = None, department_id: str | None = None, clear: bool = False) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    _validate_refs(db, property_id, department_id, user_id)
    before = wo.assigned_user_id
    if clear:
        wo.assigned_user_id = None
        if wo.status == S.assigned:
            wo.status = S.open
    if department_id:
        wo.department_id = department_id
    if user_id:
        wo.assigned_user_id = user_id
        wo.acknowledged_at = None
        if wo.status == S.open:
            wo.status = S.assigned
        if user_id != actor_user_id:
            notifications.create(db, property_id, user_id, "work_order.assigned", f"Assigned: {wo.title}",
                                 body=wo.location_ref, entity_type="work_order", entity_id=wo.id)
    db.flush()
    _event(db, wo, actor_user_id, WorkOrderEventType.assigned, from_value=before, to_value=wo.assigned_user_id)
    _emit(db, wo, "work_order.updated")
    return wo


def comment(db: Session, property_id: str, work_order_id: str, actor_user_id: str, text: str) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    _event(db, wo, actor_user_id, WorkOrderEventType.commented, comment=text.strip())
    wo.updated_at = clock.now()
    _emit(db, wo, "work_order.updated")
    return wo


def set_priority(db: Session, property_id: str, work_order_id: str, actor_user_id: str, priority: Priority) -> WorkOrder:
    wo = get(db, property_id, work_order_id)
    before = wo.priority
    wo.priority = priority
    _event(db, wo, actor_user_id, WorkOrderEventType.priority_changed, from_value=before.value, to_value=priority.value)
    _emit(db, wo, "work_order.updated")
    return wo


def list(db: Session, property_id: str, *, status: str | None = None, type: WorkOrderType | None = None,
         dept: str | None = None, assignee: str | None = None, mine_user_id: str | None = None,
         include_closed: bool = False) -> list[WorkOrderOut]:
    # `from __future__ import annotations` keeps this annotation lazy, and the def statement binds the
    # module-level name `list` only after the signature is built, so the annotation means builtins.list.
    q = select(WorkOrder).where(WorkOrder.property_id == property_id)
    if status:
        q = q.where(WorkOrder.status.in_([S(s) for s in status.split(",") if s]))
    elif not include_closed:
        q = q.where(WorkOrder.status.in_(OPEN_STATUSES))
    if type:
        q = q.where(WorkOrder.type == type)
    if dept:
        q = q.where(WorkOrder.department_id == dept)
    if assignee:
        q = q.where(WorkOrder.assigned_user_id == assignee)
    if mine_user_id:
        q = q.where(WorkOrder.assigned_user_id == mine_user_id)
    rows = db.scalars(q.order_by(WorkOrder.created_at.desc())).all()
    return [WorkOrderOut.model_validate(w) for w in rows]


def detail(db: Session, property_id: str, work_order_id: str) -> WorkOrderDetail:
    wo = get(db, property_id, work_order_id)
    rows = db.execute(select(WorkOrderEvent, UserAccount).outerjoin(UserAccount, UserAccount.id == WorkOrderEvent.user_id)
                      .where(WorkOrderEvent.work_order_id == wo.id).order_by(WorkOrderEvent.created_at)).all()
    guest_name = room = None
    if wo.source_conversation_id:
        conv = db.get(Conversation, wo.source_conversation_id)
        if conv:
            g = db.get(Guest, conv.guest_id)
            guest_name = f"{g.first_name or ''} {g.last_name or ''}".strip() or g.phone_e164
            st = db.get(Stay, conv.stay_id) if conv.stay_id else None
            room = st.room_number if st else None
    base = WorkOrderOut.model_validate(wo).model_dump()
    return WorkOrderDetail(**base, guest_name=guest_name, room_number=room or wo.location_ref,
                           events=[WorkOrderEventOut(id=e.id, user_id=e.user_id,
                                                     user_name=f"{u.first_name} {u.last_name}" if u else None,
                                                     type=e.type, from_value=e.from_value, to_value=e.to_value,
                                                     comment=e.comment, created_at=e.created_at) for e, u in rows])
```

Inside `work_orders.py` never call the builtin `list(...)` after this definition — use a list comprehension or `[*xs]` — because the module-level name now refers to this function. (`conversations.py` has the same convention.)

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): work order state machine, prefill from conversation, events, closed-loop draft prompt"
```

---

### Task 15: Work orders API and draft-prompt dismiss

**Files:**
- Create: `server/app/api/work_orders.py`, `server/tests/test_work_orders_api.py`
- Modify: `server/app/api/conversations.py` (dismiss route), `server/app/__init__.py`

**Interfaces:**
- Produces routes: `GET work-orders`, `GET work-orders/prefill?conversationId=`, `POST work-orders`, `GET work-orders/<id>`, `PATCH work-orders/<id>` (status | assignedUserId | departmentId | priority | comment | clearAssignee), `POST conversations/<id>/draft-prompts/<pid>/dismiss`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_work_orders_api.py`:
```python
from sqlalchemy import select

from app.models import Conversation
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_prefill_create_transition_and_detail_via_api(app, fx, client, database, login):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "The AC in our room isn't working")
    cid = _cid(database, fx.guest_inhouse_a.id)
    base = f"/api/p/{fx.property_a.id}/work-orders"
    agent = login("agent@hvh.test")
    p = agent.get(f"{base}/prefill?conversationId={cid}").get_json()
    assert p["locationRef"] == "412" and p["departmentId"] == fx.dept_engineering.id
    res = agent.post(base, json={**{k: p[k] for k in ("title", "description", "type", "priority", "locationType",
                                                           "locationRef", "departmentId", "sourceConversationId",
                                                           "sourceMessageId")}, "priority": "urgent"})
    assert res.status_code == 201
    wo = res.get_json()
    assert wo["status"] == "open" and wo["sourceConversationId"] == cid
    eng = login("engineer@hvh.test")
    assert eng.patch(f"{base}/{wo['id']}", json={"assignedUserId": fx.engineer_a.id}).get_json()["status"] == "assigned"
    assert eng.patch(f"{base}/{wo['id']}", json={"status": "in_progress"}).get_json()["status"] == "in_progress"
    bad = eng.patch(f"{base}/{wo['id']}", json={"status": "verified"})
    assert bad.status_code == 409 and bad.get_json()["error"]["code"] == "INVALID_TRANSITION"
    done = eng.patch(f"{base}/{wo['id']}", json={"status": "complete", "comment": "Cleared drain line"})
    assert done.status_code == 200
    d = eng.get(f"{base}/{wo['id']}").get_json()
    assert [e["type"] for e in d["events"]] == ["created", "assigned", "status_changed", "status_changed"]
    assert d["events"][-1]["comment"] == "Cleared drain line" and d["guestName"] == "Sarah Chen"
    assert d["events"][1]["userName"] == "Eli Engineer"


def test_close_requires_capability_but_create_does_not(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/work-orders"
    agent = login("agent@hvh.test")
    wo = agent.post(base, json={"title": "Lamp", "type": "maintenance", "locationRef": "330"}).get_json()
    agent.patch(f"{base}/{wo['id']}", json={"status": "in_progress"})
    assert agent.patch(f"{base}/{wo['id']}", json={"status": "complete"}).status_code == 403
    sup = login("supervisor@hvh.test")
    assert sup.patch(f"{base}/{wo['id']}", json={"status": "complete"}).status_code == 200


def test_list_filters(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/work-orders"
    sup = login("supervisor@hvh.test")
    a = sup.post(base, json={"title": "A", "type": "maintenance", "locationRef": "1", "assignedUserId": fx.engineer_a.id}).get_json()
    b = sup.post(base, json={"title": "B", "type": "housekeeping", "locationRef": "2", "departmentId": fx.dept_housekeeping.id}).get_json()
    sup.patch(f"{base}/{b['id']}", json={"status": "cancelled"})
    ids = lambda r: {w["id"] for w in r.get_json()}  # noqa: E731
    assert ids(sup.get(base)) == {a["id"]}
    assert ids(sup.get(base + "?includeClosed=true")) == {a["id"], b["id"]}
    assert ids(sup.get(base + "?status=cancelled")) == {b["id"]}
    eng = login("engineer@hvh.test")
    assert ids(eng.get(base + "?mine=true")) == {a["id"]}
    assert ids(sup.get(base + f"?dept={fx.dept_housekeeping.id}&includeClosed=true")) == {b["id"]}


def test_dismiss_draft_prompt(app, fx, client, database, login):
    from app.domain import work_orders
    from app.schemas.enums import WorkOrderStatus, WorkOrderType
    from app.schemas.work_orders import CreateWorkOrder

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    cid = _cid(database, fx.guest_inhouse_a.id)
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC", type=WorkOrderType.maintenance, locationRef="412", sourceConversationId=cid))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.in_progress)
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.complete)
    c = login("agent@hvh.test")
    pid = c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"][0]["id"]
    assert c.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/draft-prompts/{pid}/dismiss").status_code == 204
    assert c.get(f"/api/p/{fx.property_a.id}/conversations/{cid}").get_json()["draftPrompts"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_work_orders_api.py -q`
Expected: FAIL with 404s.

- [ ] **Step 3: Write `app/api/work_orders.py`**

```python
from flask import Blueprint, g, request

from app.api._util import db_session, ok, parse_body, parse_query
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import work_orders
from app.errors import Forbidden, ValidationFailed
from app.schemas.enums import WorkOrderStatus
from app.schemas.work_orders import CreateWorkOrder, WorkOrderListQuery, WorkOrderOut, WorkOrderPatch

bp = Blueprint("work_orders", __name__, url_prefix="/api/p/<property_id>/work-orders")
CLOSING = {WorkOrderStatus.complete, WorkOrderStatus.verified, WorkOrderStatus.cancelled}


@bp.get("")
@require_auth
@require_property
def list_work_orders(property_id: str):
    q = parse_query(WorkOrderListQuery)
    with db_session() as db:
        return ok(work_orders.list(db, g.property_id, status=q.status, type=q.type, dept=q.dept,
                                   assignee=q.assignee, mine_user_id=g.user.id if q.mine else None,
                                   include_closed=q.include_closed))


@bp.get("/prefill")
@require_auth
@require_property
@require_capability("create_work_order")
def prefill(property_id: str):
    conversation_id = request.args.get("conversationId")
    if not conversation_id:
        raise ValidationFailed("conversationId is required")
    with db_session() as db:
        return ok(work_orders.prefill_from_conversation(db, g.property_id, conversation_id))


@bp.post("")
@require_auth
@require_property
@require_capability("create_work_order")
def create_work_order(property_id: str):
    data = parse_body(CreateWorkOrder)
    with db_session() as db:
        wo = work_orders.create(db, g.property_id, g.user.id, data)
        return ok(WorkOrderOut.model_validate(wo), 201)


@bp.get("/<work_order_id>")
@require_auth
@require_property
def get_work_order(property_id: str, work_order_id: str):
    with db_session() as db:
        return ok(work_orders.detail(db, g.property_id, work_order_id))


@bp.patch("/<work_order_id>")
@require_auth
@require_property
def patch_work_order(property_id: str, work_order_id: str):
    p = parse_body(WorkOrderPatch)
    with db_session() as db:
        if p.assigned_user_id or p.department_id or p.clear_assignee:
            work_orders.assign(db, g.property_id, work_order_id, g.user.id, user_id=p.assigned_user_id,
                               department_id=p.department_id, clear=p.clear_assignee)
        if p.priority is not None:
            work_orders.set_priority(db, g.property_id, work_order_id, g.user.id, p.priority)
        if p.status is not None:
            if p.status in CLOSING and not has_capability(g.membership.role, "close_work_order"):
                raise Forbidden("Your role cannot close work orders")
            work_orders.transition(db, g.property_id, work_order_id, g.user.id, p.status, comment=p.comment)
        elif p.comment:
            work_orders.comment(db, g.property_id, work_order_id, g.user.id, p.comment)
        return ok(work_orders.detail(db, g.property_id, work_order_id))
```

Add the dismiss route to `app/api/conversations.py`:
```python
from app.domain import draft_prompts


@bp.post("/<conversation_id>/draft-prompts/<prompt_id>/dismiss")
@require_auth
@require_property
@require_capability("reply")
def dismiss_prompt(property_id: str, conversation_id: str, prompt_id: str):
    with db_session() as db:
        draft_prompts.dismiss(db, g.property_id, conversation_id, prompt_id, g.user.id)
    return no_content()
```

Register `work_orders.bp` in `create_app`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass (isolation suite now covers five more routes).

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): work order API with prefill, transitions, filters; draft-prompt dismiss"
```

---

### Task 16: Quick replies, digital assets, resolution categories — CRUD, search, short links

**Files:**
- Create: `server/app/schemas/content.py`, `server/app/domain/assets.py`, `server/app/domain/categories.py`, `server/app/api/quick_replies.py`, `server/app/api/assets.py`, `server/app/api/categories.py`, `server/app/api/short_links.py`, `server/tests/test_content.py`
- Modify: `server/app/domain/quick_replies.py` (add CRUD + search + `context_for_conversation`), `server/app/__init__.py`

**Interfaces:**
- Produces: `quick_replies.list(db, property_id, q=None, department_id=None, include_inactive=False) -> list[QuickReplyOut]`; `create/update/delete`; `quick_replies.render(db, property_id, quick_reply_id, conversation_id, agent_user_id) -> RenderedQuickReply` (interpolated body + segment count; bumps `usage_count`); `quick_replies.context_for_conversation(db, property_id, conversation_id, agent_user_id) -> dict`; `assets.list/create/update/delete/get_by_short_code`, `assets.new_short_code(db) -> str` (6 chars, base32, unique); `categories.list_tree/create/update/delete`. Schemas: `QuickReplyIn/Out`, `RenderedQuickReply`, `AssetIn/Out`, `CategoryIn/Out`. Routes: `quick-replies` (`GET ?q=&dept=&includeInactive=`, `POST`, `PATCH /<id>`, `DELETE /<id>`, `POST /<id>/render {conversationId}`), `assets` (`GET/POST/PATCH/DELETE`), `resolution-categories` (`GET/POST/PATCH/DELETE`), public `GET /a/<short_code>` → 302.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_content.py`:
```python
from sqlalchemy import select

from app.models import Conversation, DigitalAsset
from tests.factories import inbound


def _cid(database, guest_id):
    with database.session() as db:
        return db.scalar(select(Conversation.id).where(Conversation.guest_id == guest_id))


def test_quick_reply_crud_search_and_render(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/quick-replies"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"shortcut": "/wifi", "title": "WiFi", "body": "Hi {{guest_first_name}}, WiFi is Harbourview-Guest, room {{room_number}}."})
    assert r.status_code == 201
    qr = r.get_json()
    admin.post(base, json={"shortcut": "/towels", "title": "Towels", "body": "Towels on the way to {{room_number}}.",
                           "departmentId": fx.dept_housekeeping.id})
    dup = admin.post(base, json={"shortcut": "/wifi", "title": "x", "body": "y"})
    assert dup.status_code == 409
    agent = login("agent@hvh.test")
    assert [x["shortcut"] for x in agent.get(base + "?q=wif").get_json()] == ["/wifi"]
    assert [x["shortcut"] for x in agent.get(base + "?q=on the way").get_json()] == ["/towels"]
    assert agent.post(base, json={"shortcut": "/x", "title": "x", "body": "y"}).status_code == 403
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    cid = _cid(database, fx.guest_inhouse_a.id)
    rendered = agent.post(f"{base}/{qr['id']}/render", json={"conversationId": cid}).get_json()
    assert rendered["body"] == "Hi Sarah, WiFi is Harbourview-Guest, room 412."
    assert rendered["segments"] == 1
    assert agent.get(base).get_json()[0]["usageCount"] == 1  # sorted by usage desc
    assert admin.patch(f"{base}/{qr['id']}", json={"active": False}).status_code == 200
    assert [x["shortcut"] for x in agent.get(base).get_json()] == ["/towels"]
    assert len(admin.get(base + "?includeInactive=true").get_json()) == 2
    assert admin.delete(f"{base}/{qr['id']}").status_code == 204


def test_assets_crud_short_link_and_send_appends_link(app, fx, client, database, login, worker):
    base = f"/api/p/{fx.property_a.id}/assets"
    admin = login("admin@hvh.test")
    a = admin.post(base, json={"name": "WiFi card", "type": "link", "url": "https://example.test/wifi.pdf",
                               "category": "Connectivity"}).get_json()
    assert len(a["shortCode"]) == 6
    r = client.get(f"/a/{a['shortCode']}")
    assert r.status_code == 302 and r.headers["Location"] == "https://example.test/wifi.pdf"
    assert client.get("/a/nope00").status_code == 404
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "wifi?")
    cid = _cid(database, fx.guest_inhouse_a.id)
    agent = login("agent@hvh.test")
    m = agent.post(f"/api/p/{fx.property_a.id}/conversations/{cid}/messages",
                   json={"body": "Here you go:", "digitalAssetId": a["id"]}).get_json()
    assert m["body"] == f"Here you go: /a/{a['shortCode']}" and m["digitalAssetId"] == a["id"]
    with database.session() as db:
        assert db.get(DigitalAsset, a["id"]).send_count == 1
    assert admin.patch(f"{base}/{a['id']}", json={"name": "WiFi card v2"}).get_json()["name"] == "WiFi card v2"
    assert admin.delete(f"{base}/{a['id']}").status_code == 204
    assert client.get(f"/a/{a['shortCode']}").status_code == 404


def test_resolution_categories_tree(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/resolution-categories"
    admin = login("admin@hvh.test")
    parent = admin.post(base, json={"name": "Maintenance"}).get_json()
    child = admin.post(base, json={"name": "HVAC", "parentId": parent["id"]}).get_json()
    tree = admin.get(base).get_json()
    assert tree[0]["name"] == "Maintenance" and tree[0]["children"][0]["id"] == child["id"]
    assert admin.patch(f"{base}/{child['id']}", json={"name": "HVAC / AC"}).get_json()["name"] == "HVAC / AC"
    assert admin.delete(f"{base}/{parent['id']}").status_code == 409  # has children
    assert admin.delete(f"{base}/{child['id']}").status_code == 204
    assert admin.delete(f"{base}/{parent['id']}").status_code == 204
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_content.py -q`
Expected: FAIL with 404s.

- [ ] **Step 3: Write `app/schemas/content.py`**

```python
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import AssetType


class QuickReplyIn(CamelModel):
    shortcut: str = Field(min_length=2, max_length=40, pattern=r"^/[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1600)
    category: str | None = None
    department_id: str | None = None
    locale: str = "en"
    active: bool = True


class QuickReplyPatch(CamelModel):
    shortcut: str | None = Field(default=None, pattern=r"^/[a-z0-9_-]+$")
    title: str | None = None
    body: str | None = None
    category: str | None = None
    department_id: str | None = None
    active: bool | None = None


class QuickReplyOut(CamelModel):
    id: str
    shortcut: str
    title: str
    body: str
    category: str | None = None
    department_id: str | None = None
    locale: str
    usage_count: int
    active: bool


class RenderRequest(CamelModel):
    conversation_id: str


class RenderedQuickReply(CamelModel):
    body: str
    segments: int
    characters: int


class AssetIn(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    category: str | None = None
    type: AssetType = AssetType.link
    url: str = Field(min_length=1, max_length=1000)
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool = True
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetPatch(CamelModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    type: AssetType | None = None
    url: str | None = None
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class AssetOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    category: str | None = None
    type: AssetType
    url: str
    short_code: str
    thumbnail_url: str | None = None
    department_id: str | None = None
    active: bool
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    send_count: int


class CategoryIn(CamelModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: str | None = None
    active: bool = True


class CategoryPatch(CamelModel):
    name: str | None = None
    parent_id: str | None = None
    active: bool | None = None


class CategoryOut(CamelModel):
    id: str
    name: str
    parent_id: str | None = None
    active: bool
    children: list["CategoryOut"] = []
```

- [ ] **Step 4: Extend `app/domain/quick_replies.py`**

Append (imports: `select, or_, func` from sqlalchemy; `Session`; `Conversation, Guest, Property, QuickReply, Stay, UserAccount`; `Conflict, NotFound`; schemas; `segment_count` from `app.domain.sms`; `conv_domain`):
```python
def list(db: Session, property_id: str, q: str | None = None, department_id: str | None = None,
         include_inactive: bool = False) -> list[QuickReplyOut]:
    stmt = select(QuickReply).where(QuickReply.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(QuickReply.active.is_(True))
    if department_id:
        stmt = stmt.where(or_(QuickReply.department_id == department_id, QuickReply.department_id.is_(None)))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(QuickReply.shortcut).like(like), func.lower(QuickReply.title).like(like),
                              func.lower(QuickReply.body).like(like)))
    rows = db.scalars(stmt.order_by(QuickReply.usage_count.desc(), QuickReply.shortcut)).all()
    return [QuickReplyOut.model_validate(r) for r in rows]


def get(db: Session, property_id: str, quick_reply_id: str) -> QuickReply:
    r = db.scalar(select(QuickReply).where(QuickReply.id == quick_reply_id, QuickReply.property_id == property_id))
    if r is None:
        raise NotFound("Quick reply not found")
    return r


def _assert_shortcut_free(db: Session, property_id: str, shortcut: str, exclude_id: str | None = None) -> None:
    stmt = select(QuickReply.id).where(QuickReply.property_id == property_id, QuickReply.shortcut == shortcut)
    if exclude_id:
        stmt = stmt.where(QuickReply.id != exclude_id)
    if db.scalar(stmt):
        raise Conflict(f"Shortcut {shortcut} is already in use")


def create(db: Session, property_id: str, data: QuickReplyIn) -> QuickReply:
    _assert_shortcut_free(db, property_id, data.shortcut)
    r = QuickReply(property_id=property_id, **data.model_dump())
    db.add(r)
    db.flush()
    return r


def update(db: Session, property_id: str, quick_reply_id: str, data: QuickReplyPatch) -> QuickReply:
    r = get(db, property_id, quick_reply_id)
    changes = data.model_dump(exclude_unset=True)
    if "shortcut" in changes and changes["shortcut"]:
        _assert_shortcut_free(db, property_id, changes["shortcut"], exclude_id=r.id)
    for k, v in changes.items():
        setattr(r, k, v)
    db.flush()
    return r


def delete(db: Session, property_id: str, quick_reply_id: str) -> None:
    db.delete(get(db, property_id, quick_reply_id))


def context_for_conversation(db: Session, property_id: str, conversation_id: str, agent_user_id: str | None) -> dict:
    conv = conv_domain.get(db, property_id, conversation_id)
    guest = db.get(Guest, conv.guest_id)
    stay = db.get(Stay, conv.stay_id) if conv.stay_id else None
    prop = db.get(Property, property_id)
    agent = db.get(UserAccount, agent_user_id) if agent_user_id else None
    return {
        "guest_first_name": guest.first_name,
        "room_number": stay.room_number if stay else None,
        "property_name": prop.name,
        "agent_first_name": agent.first_name if agent else None,
        "departure_date": stay.departure_date.strftime("%A, %b %d") if stay else None,
    }


def render(db: Session, property_id: str, quick_reply_id: str, conversation_id: str,
           agent_user_id: str | None) -> RenderedQuickReply:
    r = get(db, property_id, quick_reply_id)
    body = interpolate(r.body, context_for_conversation(db, property_id, conversation_id, agent_user_id))
    r.usage_count += 1
    return RenderedQuickReply(body=body, segments=segment_count(body), characters=len(body))
```

- [ ] **Step 5: Write `app/domain/assets.py` and `app/domain/categories.py`**

`assets.py`:
```python
from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import NotFound
from app.models import DigitalAsset
from app.schemas.content import AssetIn, AssetOut, AssetPatch

ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i


def new_short_code(db: Session) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not db.scalar(select(DigitalAsset.id).where(DigitalAsset.short_code == code)):
            return code


def list(db: Session, property_id: str, include_inactive: bool = False) -> list[AssetOut]:
    stmt = select(DigitalAsset).where(DigitalAsset.property_id == property_id)
    if not include_inactive:
        stmt = stmt.where(DigitalAsset.active.is_(True))
    return [AssetOut.model_validate(a) for a in db.scalars(stmt.order_by(DigitalAsset.name)).all()]


def get(db: Session, property_id: str, asset_id: str) -> DigitalAsset:
    a = db.scalar(select(DigitalAsset).where(DigitalAsset.id == asset_id, DigitalAsset.property_id == property_id))
    if a is None:
        raise NotFound("Asset not found")
    return a


def get_by_short_code(db: Session, short_code: str) -> DigitalAsset | None:
    return db.scalar(select(DigitalAsset).where(DigitalAsset.short_code == short_code, DigitalAsset.active.is_(True)))


def create(db: Session, property_id: str, data: AssetIn) -> DigitalAsset:
    a = DigitalAsset(property_id=property_id, short_code=new_short_code(db), **data.model_dump())
    db.add(a)
    db.flush()
    return a


def update(db: Session, property_id: str, asset_id: str, data: AssetPatch) -> DigitalAsset:
    a = get(db, property_id, asset_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    db.flush()
    return a


def delete(db: Session, property_id: str, asset_id: str) -> None:
    a = get(db, property_id, asset_id)
    a.active = False  # soft: messages already sent still reference the id; the short link stops resolving
```

`categories.py`:
```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflict, NotFound
from app.models import ResolutionCategory
from app.schemas.content import CategoryIn, CategoryOut, CategoryPatch


def list_tree(db: Session, property_id: str) -> list[CategoryOut]:
    rows = db.scalars(select(ResolutionCategory).where(ResolutionCategory.property_id == property_id)
                      .order_by(ResolutionCategory.name)).all()
    nodes = {r.id: CategoryOut(id=r.id, name=r.name, parent_id=r.parent_id, active=r.active, children=[]) for r in rows}
    roots: list[CategoryOut] = []
    for r in rows:
        (nodes[r.parent_id].children if r.parent_id in nodes else roots).append(nodes[r.id])
    return roots


def get(db: Session, property_id: str, category_id: str) -> ResolutionCategory:
    c = db.scalar(select(ResolutionCategory).where(ResolutionCategory.id == category_id,
                                                   ResolutionCategory.property_id == property_id))
    if c is None:
        raise NotFound("Category not found")
    return c


def create(db: Session, property_id: str, data: CategoryIn) -> ResolutionCategory:
    if data.parent_id:
        get(db, property_id, data.parent_id)
    c = ResolutionCategory(property_id=property_id, **data.model_dump())
    db.add(c)
    db.flush()
    return c


def update(db: Session, property_id: str, category_id: str, data: CategoryPatch) -> ResolutionCategory:
    c = get(db, property_id, category_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.flush()
    return c


def delete(db: Session, property_id: str, category_id: str) -> None:
    c = get(db, property_id, category_id)
    if db.scalar(select(ResolutionCategory.id).where(ResolutionCategory.parent_id == c.id)):
        raise Conflict("Delete or move the child categories first")
    db.delete(c)
```

- [ ] **Step 6: Write the four blueprints and register them**

`app/api/quick_replies.py`:
```python
from flask import Blueprint, g, request

from app.api._util import db_session, no_content, ok, parse_body
from app.auth.decorators import require_auth, require_capability, require_property
from app.domain import quick_replies
from app.schemas.content import QuickReplyIn, QuickReplyOut, QuickReplyPatch, RenderRequest

bp = Blueprint("quick_replies", __name__, url_prefix="/api/p/<property_id>/quick-replies")


@bp.get("")
@require_auth
@require_property
def list_quick_replies(property_id: str):
    with db_session() as db:
        return ok(quick_replies.list(db, g.property_id, q=request.args.get("q"), department_id=request.args.get("dept"),
                                     include_inactive=request.args.get("includeInactive") in ("1", "true")))


@bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_quick_reply(property_id: str):
    with db_session() as db:
        return ok(QuickReplyOut.model_validate(quick_replies.create(db, g.property_id, parse_body(QuickReplyIn))), 201)


@bp.patch("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def update_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        return ok(QuickReplyOut.model_validate(quick_replies.update(db, g.property_id, quick_reply_id, parse_body(QuickReplyPatch))))


@bp.delete("/<quick_reply_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def delete_quick_reply(property_id: str, quick_reply_id: str):
    with db_session() as db:
        quick_replies.delete(db, g.property_id, quick_reply_id)
    return no_content()


@bp.post("/<quick_reply_id>/render")
@require_auth
@require_property
@require_capability("reply")
def render_quick_reply(property_id: str, quick_reply_id: str):
    body = parse_body(RenderRequest)
    with db_session() as db:
        return ok(quick_replies.render(db, g.property_id, quick_reply_id, body.conversation_id, g.user.id))
```

`app/api/assets.py` — same shape: `GET ""` (any member; `?includeInactive=`), `POST ""`, `PATCH /<asset_id>`, `DELETE /<asset_id>` all `manage_admin` except GET, url_prefix `/api/p/<property_id>/assets`, using `assets.list/create/update/delete` and `AssetOut`.

`app/api/categories.py` — same shape with url_prefix `/api/p/<property_id>/resolution-categories`, `categories.list_tree/create/update/delete`, `CategoryOut`.

`app/api/short_links.py`:
```python
from flask import Blueprint, redirect

from app.api._util import db_session
from app.domain import assets
from app.errors import NotFound

bp = Blueprint("short_links", __name__)


@bp.get("/a/<short_code>")
def resolve(short_code: str):
    with db_session() as db:
        a = assets.get_by_short_code(db, short_code)
        if a is None:
            raise NotFound("Link not found")
        return redirect(a.url, code=302)
```

Register all four in `create_app`.

- [ ] **Step 7: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): quick replies with render, digital assets with short links, resolution categories"
```

---

### Task 17: Users & memberships admin, guest detail

**Files:**
- Create: `server/app/api/guests.py`, `server/tests/test_users_admin.py`
- Modify: `server/app/schemas/users.py`, `server/app/domain/users.py`, `server/app/api/users.py`, `server/app/__init__.py`

**Interfaces:**
- Produces: `users.create_staff(db, property_id, actor_user_id, data: CreateStaffRequest) -> StaffUserOut` (creates the account if the email is new, else adds a membership; hashes password), `users.update_staff(db, property_id, actor_user_id, user_id, data: StaffPatch) -> StaffUserOut` (role, department, status, reset password; audit), `users.remove_membership(db, property_id, actor_user_id, user_id)`; `GET /api/p/<id>/guests/<guest_id>` → `GuestDetail` (guest + stays + conversation ids). Schemas: `CreateStaffRequest`, `StaffPatch`, `GuestDetail`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_users_admin.py`:
```python
def test_admin_creates_updates_and_removes_staff(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/users"
    admin = login("admin@hvh.test")
    r = admin.post(base, json={"email": "new@hvh.test", "firstName": "Nora", "lastName": "New",
                               "password": "Password123!", "role": "dept_staff", "departmentId": fx.dept_housekeeping.id})
    assert r.status_code == 201
    u = r.get_json()
    assert u["role"] == "dept_staff" and u["departmentId"] == fx.dept_housekeeping.id
    assert login("new@hvh.test").get("/api/auth/me").status_code == 200
    assert admin.patch(f"{base}/{u['id']}", json={"role": "supervisor"}).get_json()["role"] == "supervisor"
    assert admin.patch(f"{base}/{u['id']}", json={"status": "disabled"}).get_json()["status"] == "disabled"
    assert client.post("/api/auth/login", json={"email": "new@hvh.test", "password": "Password123!"}).status_code == 401
    assert admin.delete(f"{base}/{u['id']}").status_code == 204
    assert "new@hvh.test" not in {x["email"] for x in admin.get(base).get_json()}


def test_existing_account_gets_membership_not_duplicate(app, fx, login):
    base = f"/api/p/{fx.property_b.id}/users"
    admin_b = login("admin@lsi.test")
    r = admin_b.post(base, json={"email": "agent@hvh.test", "firstName": "Ava", "lastName": "Agent", "role": "agent"})
    assert r.status_code == 201
    memberships = login("agent@hvh.test").get("/api/auth/me").get_json()["memberships"]
    assert {m["propertyCode"] for m in memberships} == {"HVH", "LSI"}


def test_non_admin_cannot_manage_users(app, fx, login):
    base = f"/api/p/{fx.property_a.id}/users"
    mgr = login("manager@hvh.test")
    assert mgr.post(base, json={"email": "x@hvh.test", "firstName": "x", "lastName": "y", "role": "agent"}).status_code == 403


def test_guest_detail(app, fx, client, login):
    from tests.factories import inbound

    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hi")
    d = login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_inhouse_a.id}").get_json()
    assert d["guest"]["firstName"] == "Sarah" and d["stays"][0]["roomNumber"] == "412"
    assert len(d["conversationIds"]) == 1
    assert login("agent@hvh.test").get(f"/api/p/{fx.property_a.id}/guests/{fx.guest_b.id}").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_users_admin.py -q`
Expected: FAIL with 404/405.

- [ ] **Step 3: Extend schemas, domain, and routes**

Append to `app/schemas/users.py`:
```python
from pydantic import EmailStr, Field

from app.schemas.conversations import GuestOut, StayOut
from app.schemas.enums import UserStatus


class CreateStaffRequest(CamelModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Role
    department_id: str | None = None
    phone: str | None = None


class StaffPatch(CamelModel):
    role: Role | None = None
    department_id: str | None = None
    status: UserStatus | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    first_name: str | None = None
    last_name: str | None = None


class GuestDetail(CamelModel):
    guest: GuestOut
    stays: list[StayOut]
    conversation_ids: list[str]
```

Append to `app/domain/users.py` (imports: `hash_password`, `audit`, `Conflict, NotFound, ValidationFailed`, `Department`, `UserStatus`, schemas):
```python
def _staff_out(db: Session, property_id: str, user_id: str) -> StaffUserOut:
    row = db.execute(select(UserAccount, PropertyMembership).join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                     .where(PropertyMembership.property_id == property_id, UserAccount.id == user_id)).first()
    if row is None:
        raise NotFound("User is not a member of this property")
    u, m = row
    return StaffUserOut(id=u.id, email=u.email, first_name=u.first_name, last_name=u.last_name, avatar_url=u.avatar_url,
                        role=m.role, department_id=m.department_id, status=u.status.value)


def _check_department(db: Session, property_id: str, department_id: str | None) -> None:
    if department_id and not db.scalar(select(Department.id).where(Department.id == department_id,
                                                                    Department.property_id == property_id)):
        raise ValidationFailed("Unknown department")


def create_staff(db: Session, property_id: str, actor_user_id: str, data: CreateStaffRequest) -> StaffUserOut:
    _check_department(db, property_id, data.department_id)
    user = db.scalar(select(UserAccount).where(UserAccount.email == data.email.lower()))
    if user is None:
        if not data.password:
            raise ValidationFailed("A password is required for a new account")
        user = UserAccount(email=data.email.lower(), first_name=data.first_name, last_name=data.last_name,
                           phone=data.phone, password_hash=hash_password(data.password))
        db.add(user)
        db.flush()
    if db.scalar(select(PropertyMembership.id).where(PropertyMembership.user_id == user.id,
                                                    PropertyMembership.property_id == property_id)):
        raise Conflict("Already a member of this property")
    db.add(PropertyMembership(user_id=user.id, property_id=property_id, role=data.role, department_id=data.department_id))
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.created", "user_account", user.id,
                 after={"role": data.role.value, "department_id": data.department_id})
    return _staff_out(db, property_id, user.id)


def update_staff(db: Session, property_id: str, actor_user_id: str, user_id: str, data: StaffPatch) -> StaffUserOut:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    u = db.get(UserAccount, user_id)
    before = {"role": m.role.value, "department_id": m.department_id, "status": u.status.value}
    changes = data.model_dump(exclude_unset=True)
    if "department_id" in changes:
        _check_department(db, property_id, changes["department_id"])
        m.department_id = changes["department_id"]
    if data.role is not None:
        m.role = data.role
    if data.status is not None:
        u.status = data.status
    if data.password:
        u.password_hash = hash_password(data.password)
    if data.first_name:
        u.first_name = data.first_name
    if data.last_name:
        u.last_name = data.last_name
    db.flush()
    audit.record(db, property_id, actor_user_id, "membership.updated", "user_account", user_id, before=before,
                 after={"role": m.role.value, "department_id": m.department_id, "status": u.status.value,
                        "password_reset": bool(data.password)})
    return _staff_out(db, property_id, user_id)


def remove_membership(db: Session, property_id: str, actor_user_id: str, user_id: str) -> None:
    m = db.scalar(select(PropertyMembership).where(PropertyMembership.user_id == user_id,
                                                   PropertyMembership.property_id == property_id))
    if m is None:
        raise NotFound("User is not a member of this property")
    db.delete(m)
    audit.record(db, property_id, actor_user_id, "membership.removed", "user_account", user_id)
```

Extend `app/api/users.py` with `POST ""` (201), `PATCH /<user_id>`, `DELETE /<user_id>` (204), each `@require_capability("manage_admin")`, calling the three functions above.

`app/api/guests.py`:
```python
from flask import Blueprint, g
from sqlalchemy import select

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_property
from app.domain import guests
from app.errors import NotFound
from app.models import Conversation, Stay
from app.schemas.conversations import GuestOut, StayOut
from app.schemas.users import GuestDetail

bp = Blueprint("guests", __name__, url_prefix="/api/p/<property_id>/guests")


@bp.get("/<guest_id>")
@require_auth
@require_property
def get_guest(property_id: str, guest_id: str):
    with db_session() as db:
        guest = guests.get(db, g.property_id, guest_id)
        if guest is None:
            raise NotFound("Guest not found")
        stays = db.scalars(select(Stay).where(Stay.guest_id == guest.id).order_by(Stay.arrival_date.desc())).all()
        conv_ids = [*db.scalars(select(Conversation.id).where(Conversation.guest_id == guest.id)).all()]
        return ok(GuestDetail(guest=GuestOut.model_validate(guest), stays=[StayOut.model_validate(s) for s in stays],
                              conversation_ids=conv_ids))
```

Register `guests.bp`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): staff/membership administration and guest detail"
```

---

### Task 18: Analytics

**Files:**
- Create: `server/app/domain/analytics.py`, `server/app/schemas/analytics.py`, `server/app/api/analytics.py`, `server/tests/test_analytics.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces: `analytics.overview(db, property_id, since, until) -> Overview`; `analytics.agents(db, property_id, since, until) -> list[AgentStats]`; `analytics.percentile(values, p) -> float | None` (nearest-rank). Routes `GET analytics/overview?from=&to=` and `GET analytics/agents?from=&to=` (`view_property_analytics`; `view_own_stats` users get `agents` filtered to themselves). ISO dates or datetimes; default last 7 days.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_analytics.py`:
```python
from datetime import timedelta

from app import clock
from app.domain import analytics, work_orders
from app.schemas.enums import WorkOrderStatus, WorkOrderType
from app.schemas.work_orders import CreateWorkOrder
from tests.factories import inbound


def test_percentile_nearest_rank():
    assert analytics.percentile([], 50) is None
    assert analytics.percentile([10], 90) == 10
    assert analytics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 50) == 5
    assert analytics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9


def test_overview_and_agents(app, fx, client, database, login):
    start = clock.now()
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "AC broken")
    inbound(client, fx, fx.guest_nostay_a.phone_e164, "late checkout?")
    agent = login("agent@hvh.test")
    from sqlalchemy import select

    from app.models import Conversation

    with database.session() as db:
        sarah = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_inhouse_a.id))
        diego = db.scalar(select(Conversation.id).where(Conversation.guest_id == fx.guest_nostay_a.id))
    clock.advance(minutes=2)
    agent.post(f"/api/p/{fx.property_a.id}/conversations/{sarah}/messages", json={"body": "On it"})
    with database.session() as db:
        wo = work_orders.create(db, fx.property_a.id, fx.agent_a.id, CreateWorkOrder(
            title="AC", type=WorkOrderType.maintenance, location_ref="412", department_id=fx.dept_engineering.id,
            source_conversation_id=sarah))
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.in_progress)
    clock.advance(minutes=20)
    with database.session() as db:
        work_orders.transition(db, fx.property_a.id, wo.id, fx.engineer_a.id, WorkOrderStatus.complete)
        from app.queue.handlers.sla import sweep_once

        sweep_once(db)  # Diego is now overdue
    mgr = login("manager@hvh.test")
    base = f"/api/p/{fx.property_a.id}/analytics"
    o = mgr.get(f"{base}/overview?from={start.date()}&to={(start + timedelta(days=1)).date()}").get_json()
    assert o["conversations"] == 2 and o["inboundMessages"] == 2 and o["outboundMessages"] == 1
    assert o["firstResponseP50Seconds"] == 120 and o["firstResponseP90Seconds"] == 120
    assert o["slaBreaches"] == 1
    assert o["workOrdersCreated"] == 1 and o["workOrdersClosed"] == 1 and o["meanTimeToResolveSeconds"] == 1200
    assert o["workOrdersFromConversations"] == 1
    assert sum(b["count"] for b in o["inboundByHour"]) == 2 and len(o["inboundByHour"]) == 24
    assert o["workOrdersByDepartment"][0]["departmentName"] == "Engineering"
    a = mgr.get(f"{base}/agents?from={start.date()}&to={(start + timedelta(days=1)).date()}").get_json()
    ava = [r for r in a if r["userId"] == fx.agent_a.id][0]
    assert ava["messagesSent"] == 1 and ava["conversationsHandled"] == 1 and ava["workOrdersCreated"] == 1
    assert ava["firstResponseP50Seconds"] == 120


def test_agent_sees_only_own_stats_and_no_overview(app, fx, client, login):
    base = f"/api/p/{fx.property_a.id}/analytics"
    agent = login("agent@hvh.test")
    assert agent.get(f"{base}/overview").status_code == 403
    rows = agent.get(f"{base}/agents").get_json()
    assert [r["userId"] for r in rows] == [fx.agent_a.id]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_analytics.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write schemas, domain, route**

`app/schemas/analytics.py`:
```python
from datetime import datetime

from app.schemas.common import CamelModel


class HourBucket(CamelModel):
    hour: int
    count: int


class DayBucket(CamelModel):
    day: str
    count: int


class DepartmentBucket(CamelModel):
    department_id: str | None = None
    department_name: str
    closed: int
    mean_time_to_resolve_seconds: int | None = None


class ResponseBucket(CamelModel):
    label: str
    count: int
    share: float


class Overview(CamelModel):
    since: datetime
    until: datetime
    conversations: int
    inbound_messages: int
    outbound_messages: int
    first_response_p50_seconds: int | None = None
    first_response_p90_seconds: int | None = None
    sla_breaches: int
    sla_breach_rate: float
    work_orders_created: int
    work_orders_closed: int
    work_orders_from_conversations: int
    mean_time_to_resolve_seconds: int | None = None
    inbound_by_hour: list[HourBucket]
    inbound_by_day: list[DayBucket]
    first_response_distribution: list[ResponseBucket]
    work_orders_by_department: list[DepartmentBucket]


class AgentStats(CamelModel):
    user_id: str
    name: str
    conversations_handled: int
    messages_sent: int
    first_response_p50_seconds: int | None = None
    first_response_p90_seconds: int | None = None
    sla_breaches: int
    quick_reply_share: float | None = None
    work_orders_created: int
```

`app/domain/analytics.py`:
```python
"""Aggregations are computed in Python from narrow selects so they run identically on SQLite and Postgres."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Conversation, Department, Message, PropertyMembership, UserAccount, WorkOrder
from app.schemas.analytics import (AgentStats, DayBucket, DepartmentBucket, HourBucket, Overview, ResponseBucket)
from app.schemas.enums import AuthorType, Direction, WorkOrderStatus

CLOSED = (WorkOrderStatus.complete, WorkOrderStatus.verified)
BUCKETS = [("< 2 min", 0, 120), ("2–5 min", 120, 300), ("5–15 min", 300, 900), ("15–30 min", 900, 1800),
           ("30+ min", 1800, 10**9)]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    k = max(1, math.ceil(p / 100 * len(xs)))
    return xs[k - 1]


def default_range(since: datetime | None, until: datetime | None) -> tuple[datetime, datetime]:
    until = until or clock.now()
    since = since or (until - timedelta(days=7))
    return since, until


def overview(db: Session, property_id: str, since: datetime | None = None, until: datetime | None = None) -> Overview:
    since, until = default_range(since, until)
    convs = db.scalars(select(Conversation).where(Conversation.property_id == property_id,
                                                  Conversation.created_at >= since, Conversation.created_at < until)).all()
    msgs = db.execute(select(Message.direction, Message.sent_at, Message.author_type).where(
        Message.property_id == property_id, Message.sent_at >= since, Message.sent_at < until)).all()
    inbound = [m for m in msgs if m.direction == Direction.inbound]
    outbound = [m for m in msgs if m.direction == Direction.outbound and m.author_type == AuthorType.staff]
    frs = [c.first_response_seconds for c in convs if c.first_response_seconds is not None]
    breaches = sum(1 for c in convs if c.sla_breach_notified_at is not None)
    by_hour = Counter(m.sent_at.hour for m in inbound)
    by_day = Counter(m.sent_at.date().isoformat() for m in inbound)
    dist = [ResponseBucket(label=label, count=sum(1 for v in frs if lo <= v < hi),
                           share=(sum(1 for v in frs if lo <= v < hi) / len(frs)) if frs else 0.0)
            for label, lo, hi in BUCKETS]
    wos_created = db.scalars(select(WorkOrder).where(WorkOrder.property_id == property_id,
                                                     WorkOrder.created_at >= since, WorkOrder.created_at < until)).all()
    wos_closed = db.scalars(select(WorkOrder).where(WorkOrder.property_id == property_id, WorkOrder.status.in_(CLOSED),
                                                    WorkOrder.completed_at >= since, WorkOrder.completed_at < until)).all()
    ttr = [(w.completed_at - w.created_at).total_seconds() for w in wos_closed if w.completed_at]
    dept_names = {d.id: d.name for d in db.scalars(select(Department).where(Department.property_id == property_id)).all()}
    per_dept: dict[str | None, list[float]] = defaultdict(list)
    for w in wos_closed:
        per_dept[w.department_id].append((w.completed_at - w.created_at).total_seconds())
    dept_rows = sorted(
        [DepartmentBucket(department_id=d, department_name=dept_names.get(d, "Unassigned"), closed=len(v),
                          mean_time_to_resolve_seconds=int(sum(v) / len(v)) if v else None) for d, v in per_dept.items()],
        key=lambda r: -r.closed)
    return Overview(
        since=since, until=until, conversations=len(convs), inbound_messages=len(inbound), outbound_messages=len(outbound),
        first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
        first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
        sla_breaches=breaches, sla_breach_rate=(breaches / len(convs)) if convs else 0.0,
        work_orders_created=len(wos_created), work_orders_closed=len(wos_closed),
        work_orders_from_conversations=sum(1 for w in wos_created if w.source_conversation_id),
        mean_time_to_resolve_seconds=int(sum(ttr) / len(ttr)) if ttr else None,
        inbound_by_hour=[HourBucket(hour=h, count=by_hour.get(h, 0)) for h in range(24)],
        inbound_by_day=[DayBucket(day=d, count=n) for d, n in sorted(by_day.items())],
        first_response_distribution=dist, work_orders_by_department=dept_rows)


def agents(db: Session, property_id: str, since: datetime | None = None, until: datetime | None = None,
           only_user_id: str | None = None) -> list[AgentStats]:
    since, until = default_range(since, until)
    staff = db.execute(select(UserAccount, PropertyMembership).join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
                       .where(PropertyMembership.property_id == property_id)).all()
    sent = db.execute(select(Message.author_user_id, Message.conversation_id, Message.sent_at).where(
        Message.property_id == property_id, Message.direction == Direction.outbound, Message.author_type == AuthorType.staff,
        Message.sent_at >= since, Message.sent_at < until)).all()
    first_reply: dict[str, tuple[datetime, str]] = {}
    for author, conv_id, at in sorted(sent, key=lambda r: r.sent_at):
        first_reply.setdefault(conv_id, (at, author))
    convs = {c.id: c for c in db.scalars(select(Conversation).where(Conversation.property_id == property_id)).all()}
    wos = Counter(w.reported_by_user_id for w in db.scalars(select(WorkOrder).where(
        WorkOrder.property_id == property_id, WorkOrder.created_at >= since, WorkOrder.created_at < until)).all())
    out = []
    for u, m in staff:
        if only_user_id and u.id != only_user_id:
            continue
        mine = [r for r in sent if r.author_user_id == u.id]
        handled = {r.conversation_id for r in mine}
        frs = [convs[cid].first_response_seconds for cid, (_, author) in first_reply.items()
               if author == u.id and cid in convs and convs[cid].first_response_seconds is not None]
        out.append(AgentStats(
            user_id=u.id, name=f"{u.first_name} {u.last_name}", conversations_handled=len(handled),
            messages_sent=len(mine), first_response_p50_seconds=int(percentile(frs, 50)) if frs else None,
            first_response_p90_seconds=int(percentile(frs, 90)) if frs else None,
            sla_breaches=sum(1 for cid in handled if convs.get(cid) and convs[cid].sla_breach_notified_at),
            quick_reply_share=None, work_orders_created=wos.get(u.id, 0)))
    return sorted(out, key=lambda a: -a.messages_sent)
```

(`quick_reply_share` stays `None` in Phase 1 — messages don't record which quick reply produced them; the web plan may add a `quick_reply_id` column later.)

`app/api/analytics.py`:
```python
from datetime import datetime, time, timezone

from flask import Blueprint, g, request

from app.api._util import db_session, ok
from app.auth.decorators import require_auth, require_capability, require_property
from app.auth.permissions import has_capability
from app.domain import analytics
from app.errors import Forbidden, ValidationFailed

bp = Blueprint("analytics", __name__, url_prefix="/api/p/<property_id>/analytics")


def _parse(name: str, end_of_day: bool = False) -> datetime | None:
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as e:
        raise ValidationFailed(f"{name} must be an ISO date or datetime") from e
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), time.max if end_of_day and len(raw) == 10 else dt.time(), tzinfo=timezone.utc)
    return dt


@bp.get("/overview")
@require_auth
@require_property
@require_capability("view_property_analytics")
def overview(property_id: str):
    with db_session() as db:
        return ok(analytics.overview(db, g.property_id, _parse("from"), _parse("to", end_of_day=True)))


@bp.get("/agents")
@require_auth
@require_property
def agents(property_id: str):
    role = g.membership.role
    if has_capability(role, "view_property_analytics"):
        only = None
    elif has_capability(role, "view_own_stats"):
        only = g.user.id
    else:
        raise Forbidden("Your role cannot view analytics")
    with db_session() as db:
        return ok(analytics.agents(db, g.property_id, _parse("from"), _parse("to", end_of_day=True), only_user_id=only))
```

Register `analytics.bp`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): analytics overview and per-agent stats"
```

---

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

### Task 20: PMS adapter interface, MockPmsAdapter, idempotent event handling

**Files:**
- Create: `server/app/pms/__init__.py`, `server/app/pms/base.py`, `server/app/pms/mock_pms.py`, `server/app/pms/handle_event.py`, `server/app/queue/handlers/pms.py`, `server/tests/test_pms.py`

**Interfaces:**
- Produces: dataclasses `NormalizedGuest(first_name, last_name, phone_e164, email, loyalty_tier, vip, pms_profile_id)`, `NormalizedStay(pms_reservation_id, room_number, room_type, rate_code, status: StayStatus, arrival_date, departure_date, adults, children, is_return_guest, stay_count)`, `PmsEvent(external_id, type, property_id, guest, stay, raw)`; `PmsAdapter` Protocol (`fetch_in_house(db, property_id)`, `next_events(db, property_id) -> list[PmsEvent]`); `MockPmsAdapter.next_events` (checks in one `reserved` stay arriving today, or checks out one `checked_in` stay departing today, alternating); `handle_event(db, event, integration_key="mock") -> bool` (False when duplicate); recurring handler `pms.tick`; `MockPmsAdapter.event_for(db, property_id, stay_id, type)` for the dev endpoints (Task 21).

- [ ] **Step 1: Write the failing tests**

`server/tests/test_pms.py`:
```python
from datetime import date

from sqlalchemy import select

from app import clock
from app.models import Guest, PmsEvent, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent as Ev
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.schemas.enums import StayStatus


def _event(fx, eid="R-1", type="stay.checked_in", phone="+15553334444", room="515"):
    today = clock.now().date()
    return Ev(external_id=eid, type=type, property_id=fx.property_a.id,
              guest=NormalizedGuest(first_name="Tom", last_name="Becker", phone_e164=phone, email=None,
                                    loyalty_tier="Silver", vip=False, pms_profile_id="P-9"),
              stay=NormalizedStay(pms_reservation_id=eid, room_number=room, room_type="Queen", rate_code="BAR",
                                  status=StayStatus.checked_in, arrival_date=today,
                                  departure_date=date.fromordinal(today.toordinal() + 2), adults=1, children=0,
                                  is_return_guest=False, stay_count=1),
              raw={"source": "test"})


def test_check_in_upserts_guest_and_stay(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        g = db.scalar(select(Guest).where(Guest.phone_e164 == "+15553334444"))
        assert g.first_name == "Tom" and g.loyalty_tier == "Silver" and g.pms_profile_id == "P-9"
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert s.status == StayStatus.checked_in and s.room_number == "515" and s.actual_checkin_at is not None
        assert s.raw_pms == {"source": "test"}


def test_duplicate_event_is_ignored(app, fx, database):
    with database.session() as db:
        assert handle_event(db, _event(fx)) is True
        assert handle_event(db, _event(fx)) is False
        assert len(db.scalars(select(Stay)).all()) == 3  # 2 fixture stays + 1
        assert len(db.scalars(select(PmsEvent)).all()) == 1


def test_check_out_updates_existing_stay_and_does_not_reopen_consent(app, fx, database):
    with database.session() as db:
        handle_event(db, _event(fx))
        ev = _event(fx, eid="R-1", type="stay.checked_out")
        ev.stay.status = StayStatus.checked_out
        assert handle_event(db, ev) is True
        s = db.scalar(select(Stay).where(Stay.pms_reservation_id == "R-1"))
        assert s.status == StayStatus.checked_out and s.actual_checkout_at is not None


def test_mock_adapter_checks_in_arrivals_then_checks_out_departures(app, fx, database):
    today = clock.now().date()
    with database.session() as db:
        g = Guest(property_id=fx.property_a.id, first_name="Arriving", last_name="Guest", phone_e164="+15550009999")
        db.add(g); db.flush()
        db.add(Stay(guest_id=g.id, property_id=fx.property_a.id, pms_reservation_id="R-ARR", room_number="222",
                    status=StayStatus.reserved, arrival_date=today, departure_date=date.fromordinal(today.toordinal() + 1)))
        fx_stay = db.get(Stay, fx.stay_inhouse_a.id)
        fx_stay.departure_date = today  # Sarah departs today
    adapter = MockPmsAdapter()
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert [e.type for e in events] == ["stay.checked_in"] and events[0].stay.pms_reservation_id == "R-ARR"
        for e in events:
            handle_event(db, e)
    with database.session() as db:
        events = adapter.next_events(db, fx.property_a.id)
        assert [e.type for e in events] == ["stay.checked_out"] and events[0].stay.pms_reservation_id == "RES-412"
        for e in events:
            handle_event(db, e)
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_pms.py -q`
Expected: FAIL with `ModuleNotFoundError: app.pms`.

- [ ] **Step 3: Write `app/pms/base.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.schemas.enums import StayStatus

EventType = Literal["reservation.created", "stay.checked_in", "stay.checked_out", "stay.room_changed"]


@dataclass
class NormalizedGuest:
    first_name: str | None
    last_name: str | None
    phone_e164: str
    email: str | None = None
    loyalty_tier: str | None = None
    vip: bool = False
    pms_profile_id: str | None = None


@dataclass
class NormalizedStay:
    pms_reservation_id: str
    room_number: str | None
    room_type: str | None
    rate_code: str | None
    status: StayStatus
    arrival_date: date
    departure_date: date
    adults: int = 1
    children: int = 0
    is_return_guest: bool = False
    stay_count: int = 1


@dataclass
class PmsEvent:
    external_id: str
    type: EventType
    property_id: str
    guest: NormalizedGuest
    stay: NormalizedStay
    raw: dict = field(default_factory=dict)


class PmsAdapter(Protocol):
    integration_key: str

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]: ...

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]: ...
```

- [ ] **Step 4: Write `app/pms/handle_event.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, guests
from app.models import PmsEvent as PmsEventRow
from app.models import Stay
from app.pms.base import PmsEvent
from app.realtime.broadcast import queue_event
from app.schemas.enums import StayStatus


def handle_event(db: Session, event: PmsEvent, integration_key: str = "mock") -> bool:
    """Idempotent on (integration_key, external_id, event_type). Returns False for a duplicate."""
    dup = db.scalar(select(PmsEventRow.id).where(PmsEventRow.integration_key == integration_key,
                                                 PmsEventRow.external_id == event.external_id,
                                                 PmsEventRow.event_type == event.type))
    if dup:
        return False
    row = PmsEventRow(integration_key=integration_key, external_id=event.external_id, event_type=event.type,
                      payload=event.raw)
    db.add(row)

    guest, created = guests.find_or_create_by_phone(db, event.property_id, event.guest.phone_e164)
    for attr in ("first_name", "last_name", "email", "loyalty_tier", "vip", "pms_profile_id"):
        value = getattr(event.guest, attr)
        if value is not None:
            setattr(guest, attr, value)

    stay = db.scalar(select(Stay).where(Stay.property_id == event.property_id,
                                        Stay.pms_reservation_id == event.stay.pms_reservation_id))
    if stay is None:
        stay = Stay(guest_id=guest.id, property_id=event.property_id, pms_reservation_id=event.stay.pms_reservation_id,
                    arrival_date=event.stay.arrival_date, departure_date=event.stay.departure_date)
        db.add(stay)
    for attr in ("room_number", "room_type", "rate_code", "status", "arrival_date", "departure_date", "adults",
                 "children", "is_return_guest", "stay_count"):
        setattr(stay, attr, getattr(event.stay, attr))
    stay.raw_pms = event.raw
    now = clock.now()
    if event.type == "stay.checked_in" and stay.actual_checkin_at is None:
        stay.actual_checkin_at = now
    if event.type == "stay.checked_out":
        stay.status = StayStatus.checked_out
        stay.actual_checkout_at = stay.actual_checkout_at or now
    db.flush()
    row.processed_at = now
    audit.record(db, event.property_id, None, f"pms.{event.type}", "stay", stay.id,
                 after={"external_id": event.external_id, "room": stay.room_number})
    queue_event(db, event.property_id, "stay.updated", {"stayId": stay.id, "guestId": guest.id, "status": stay.status.value})
    return True
```

- [ ] **Step 5: Write `app/pms/mock_pms.py` and the handler**

`mock_pms.py`:
```python
"""Drives seeded stays through check-in and check-out so the inbox has a living hotel behind it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Guest, Stay
from app.pms.base import NormalizedGuest, NormalizedStay, PmsEvent
from app.schemas.enums import StayStatus


class MockPmsAdapter:
    integration_key = "mock"

    def __init__(self):
        self._flip = False

    @staticmethod
    def _event(stay: Stay, guest: Guest, type: str, status: StayStatus) -> PmsEvent:
        return PmsEvent(
            external_id=stay.pms_reservation_id or stay.id, type=type, property_id=stay.property_id,
            guest=NormalizedGuest(first_name=guest.first_name, last_name=guest.last_name, phone_e164=guest.phone_e164,
                                  email=guest.email, loyalty_tier=guest.loyalty_tier, vip=guest.vip,
                                  pms_profile_id=guest.pms_profile_id),
            stay=NormalizedStay(pms_reservation_id=stay.pms_reservation_id or stay.id, room_number=stay.room_number,
                                room_type=stay.room_type, rate_code=stay.rate_code, status=status,
                                arrival_date=stay.arrival_date, departure_date=stay.departure_date, adults=stay.adults,
                                children=stay.children, is_return_guest=stay.is_return_guest, stay_count=stay.stay_count),
            raw={"mock": True, "emitted_at": clock.now().isoformat()})

    def event_for(self, db: Session, property_id: str, stay_id: str, type: str) -> PmsEvent | None:
        stay = db.scalar(select(Stay).where(Stay.id == stay_id, Stay.property_id == property_id))
        if stay is None:
            return None
        status = StayStatus.checked_in if type == "stay.checked_in" else StayStatus.checked_out
        return self._event(stay, db.get(Guest, stay.guest_id), type, status)

    def fetch_in_house(self, db: Session, property_id: str) -> list[NormalizedStay]:
        rows = db.scalars(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.checked_in)).all()
        return [self._event(s, db.get(Guest, s.guest_id), "stay.checked_in", StayStatus.checked_in).stay for s in rows]

    def next_events(self, db: Session, property_id: str) -> list[PmsEvent]:
        today = clock.now().date()
        arrival = db.scalar(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.reserved,
                                               Stay.arrival_date <= today).order_by(Stay.arrival_date).limit(1))
        departure = db.scalar(select(Stay).where(Stay.property_id == property_id, Stay.status == StayStatus.checked_in,
                                                 Stay.departure_date <= today).order_by(Stay.departure_date).limit(1))
        self._flip = not self._flip
        order = [arrival, departure] if self._flip else [departure, arrival]
        for stay in order:
            if stay is None:
                continue
            guest = db.get(Guest, stay.guest_id)
            if stay.status == StayStatus.reserved:
                return [self._event(stay, guest, "stay.checked_in", StayStatus.checked_in)]
            return [self._event(stay, guest, "stay.checked_out", StayStatus.checked_out)]
        return []
```

`app/queue/handlers/pms.py`:
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Property
from app.pms.handle_event import handle_event
from app.pms.mock_pms import MockPmsAdapter
from app.queue.handlers import handler

adapter = MockPmsAdapter()


@handler("pms.tick")
def pms_tick(db: Session, payload: dict) -> None:
    for pid in db.scalars(select(Property.id)).all():
        for event in adapter.next_events(db, pid):
            handle_event(db, event, integration_key=adapter.integration_key)
```

Register the adapter on the app in `create_app`: `from app.queue.handlers import pms as pms_handler; app.extensions["pms_adapter"] = pms_handler.adapter` (import after `load_all()` has run inside `Worker.__init__`, or simply import the module directly — it is safe to import before the worker exists).

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): PMS adapter interface, mock PMS driving check-ins/outs, idempotent event handling"
```

---

### Task 21: Dev-only endpoints for the phone simulator and mock PMS

**Files:**
- Create: `server/app/api/dev.py`, `server/app/schemas/dev.py`, `server/tests/test_dev.py`
- Modify: `server/app/__init__.py`

**Interfaces:**
- Produces (registered only when `not config.is_production`): `GET /api/dev/sim/guests` → `list[SimGuest]` (seeded guests across properties with phone, name, room, consent, property sms number, `willFail` flag for `…0000` numbers); `GET /api/dev/sim/thread?phone=&propertyId=` → `GuestThread`; `GET /api/dev/sim/events?since=` → last 100 realtime events the server delivered (ring buffer fed by a `broadcast` listener) as `list[SimEvent]`; `POST /api/dev/pms/check-in/<stay_id>` and `POST /api/dev/pms/check-out/<stay_id>` → 204. Dev routes require no login (they are for the simulator page in development) but are absent in production.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_dev.py`:
```python
from app import create_app
from app.config import Config
from tests.factories import inbound


def test_dev_routes_absent_in_production(template_db_path, tmp_path):
    import shutil

    p = tmp_path / "prod.db"
    shutil.copy(template_db_path, p)
    app = create_app(Config(DATABASE_URL=f"sqlite:///{p.as_posix()}", ENV="production", TESTING=True))
    assert app.test_client().get("/api/dev/sim/guests").status_code == 404
    app.extensions["db"].engine.dispose()


def test_sim_guests_and_thread(app, fx, client):
    guests = client.get("/api/dev/sim/guests").get_json()
    sarah = [g for g in guests if g["phone"] == fx.guest_inhouse_a.phone_e164][0]
    assert sarah["roomNumber"] == "412" and sarah["propertyId"] == fx.property_a.id and sarah["willFail"] is False
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    t = client.get(f"/api/dev/sim/thread?phone={fx.guest_inhouse_a.phone_e164}&propertyId={fx.property_a.id}").get_json()
    assert [m["body"] for m in t["messages"]] == ["hello"] and "notes" not in t


def test_sim_events_ring_buffer(app, fx, client):
    inbound(client, fx, fx.guest_inhouse_a.phone_e164, "hello")
    events = client.get("/api/dev/sim/events").get_json()
    assert any(e["type"] == "message.created" for e in events)
    assert all({"type", "propertyId", "at", "payload"} <= set(e) for e in events)


def test_dev_pms_endpoints(app, fx, client, database):
    from sqlalchemy import select

    from app.models import Stay
    from app.schemas.enums import StayStatus

    assert client.post(f"/api/dev/pms/check-out/{fx.stay_inhouse_a.id}").status_code == 204
    with database.session() as db:
        assert db.get(Stay, fx.stay_inhouse_a.id).status == StayStatus.checked_out
    assert client.post("/api/dev/pms/check-in/nope").status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_dev.py -q`
Expected: FAIL with 404s on `/api/dev/...` in the non-production app.

- [ ] **Step 3: Write the schema and blueprint**

`app/schemas/dev.py`:
```python
from datetime import datetime
from typing import Any

from app.schemas.common import CamelModel
from app.schemas.enums import SmsConsentStatus


class SimGuest(CamelModel):
    property_id: str
    property_name: str
    property_sms_number: str | None = None
    guest_id: str
    name: str
    phone: str
    room_number: str | None = None
    in_house: bool
    sms_consent_status: SmsConsentStatus
    will_fail: bool


class SimEvent(CamelModel):
    type: str
    property_id: str
    at: datetime
    payload: dict[str, Any]
```

`app/api/dev.py`:
```python
from __future__ import annotations

from collections import deque

from flask import Blueprint, request
from sqlalchemy import select

from app.api._util import db_session, no_content, ok
from app.channels.mock_sms import FAIL_SUFFIX
from app.domain import conversations
from app.errors import NotFound, ValidationFailed
from app.models import Guest, Property, Stay
from app.pms.handle_event import handle_event
from app.queue.handlers.pms import adapter as pms_adapter
from app.realtime import broadcast
from app.schemas.dev import SimEvent, SimGuest
from app.schemas.enums import StayStatus

bp = Blueprint("dev", __name__, url_prefix="/api/dev")
_events: deque[broadcast.Event] = deque(maxlen=100)


def _record(ev: broadcast.Event) -> None:
    _events.append(ev)


def install_event_recorder() -> None:
    broadcast.remove_listener(_record)
    broadcast.add_listener(_record)


@bp.get("/sim/guests")
def sim_guests():
    with db_session() as db:
        rows = db.execute(select(Guest, Property).join(Property, Property.id == Guest.property_id)
                          .order_by(Property.name, Guest.last_name)).all()
        in_house = {s.guest_id: s for s in db.scalars(select(Stay).where(Stay.status == StayStatus.checked_in)).all()}
        out = []
        for g, p in rows:
            stay = in_house.get(g.id)
            out.append(SimGuest(property_id=p.id, property_name=p.name, property_sms_number=p.sms_number, guest_id=g.id,
                                name=f"{g.first_name or ''} {g.last_name or ''}".strip() or "Unknown", phone=g.phone_e164,
                                room_number=stay.room_number if stay else None, in_house=stay is not None,
                                sms_consent_status=g.sms_consent_status, will_fail=g.phone_e164.endswith(FAIL_SUFFIX)))
        return ok(out)


@bp.get("/sim/thread")
def sim_thread():
    phone, property_id = request.args.get("phone"), request.args.get("propertyId")
    if not phone or not property_id:
        raise ValidationFailed("phone and propertyId are required")
    with db_session() as db:
        if db.get(Property, property_id) is None:
            raise NotFound("Property not found")
        return ok(conversations.guest_thread(db, property_id, phone))


@bp.get("/sim/events")
def sim_events():
    return ok([SimEvent(type=e.type, property_id=e.property_id, at=e.at, payload=e.payload) for e in list(_events)])


def _pms(stay_id: str, type: str):
    with db_session() as db:
        stay = db.get(Stay, stay_id)
        if stay is None:
            raise NotFound("Stay not found")
        event = pms_adapter.event_for(db, stay.property_id, stay_id, type)
        handle_event(db, event, integration_key=pms_adapter.integration_key)
    return no_content()


@bp.post("/pms/check-in/<stay_id>")
def pms_check_in(stay_id: str):
    return _pms(stay_id, "stay.checked_in")


@bp.post("/pms/check-out/<stay_id>")
def pms_check_out(stay_id: str):
    return _pms(stay_id, "stay.checked_out")
```

In `create_app`:
```python
    if not config.is_production:
        from app.api import dev

        dev.install_event_recorder()
        app.register_blueprint(dev.bp)
```

Note: `handle_event` for a `stay.checked_out` of an already-processed `external_id` is deduplicated by `(integration_key, external_id, event_type)`, so pressing "check out" twice is a no-op — intended.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): dev-only simulator and mock PMS endpoints"
```

---

### Task 22: Seed script and CLI

**Files:**
- Create: `server/seed/__init__.py`, `server/seed/data.py`, `server/seed/seed.py`, `server/app/cli.py`, `server/tests/test_seed.py`
- Modify: `server/app/__init__.py` (register CLI)

**Interfaces:**
- Produces: `seed.seed.run(database_url: str, *, reset: bool = True) -> SeedSummary` (dataclass with counts); `flask --app app seed` command (also `python -m seed.seed`); deterministic via `random.Random(42)`; matches spec §8 exactly (properties, 12 staff, 85 in-house stays, 10 arriving, 10 departing, 8 checked out, 30 conversations in the stated mix, 15 open work orders with 6 linked, ~15 quick replies, 8 assets, category tree, recurring jobs).

- [ ] **Step 1: Write the failing test**

`server/tests/test_seed.py`:
```python
from sqlalchemy import func, select

from app.db import Database
from app.models import (Conversation, DigitalAsset, DraftPrompt, Guest, Message, Property, PropertyMembership,
                        QuickReply, ResolutionCategory, Stay, UserAccount, WorkOrder)
from app.schemas.enums import ConversationStatus, DeliveryStatus, SmsConsentStatus, StayStatus, WorkOrderStatus
from seed.seed import run


def test_seed_matches_spec_counts(tmp_path):
    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    summary = run(url, reset=True)
    db_ = Database(url)
    with db_.session() as db:
        count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where))  # noqa: E731
        hvh = db.scalar(select(Property).where(Property.code == "HVH"))
        lsi = db.scalar(select(Property).where(Property.code == "LSI"))
        assert hvh and lsi
        assert count(PropertyMembership, PropertyMembership.property_id == hvh.id) == 12
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_in) == 85
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.reserved) == 10
        assert count(Stay, Stay.property_id == hvh.id, Stay.status == StayStatus.checked_out) == 8
        assert count(Conversation, Conversation.property_id == hvh.id) == 30
        assert count(Conversation, Conversation.property_id == hvh.id, Conversation.status == ConversationStatus.archived) == 5
        assert count(DraftPrompt) == 2
        assert count(Guest, Guest.sms_consent_status == SmsConsentStatus.opted_out) == 1
        assert count(Message, Message.redacted.is_(True)) == 1
        assert count(WorkOrder, WorkOrder.property_id == hvh.id,
                     WorkOrder.status.in_([WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress,
                                           WorkOrderStatus.blocked, WorkOrderStatus.complete])) == 15
        assert count(WorkOrder, WorkOrder.source_conversation_id.isnot(None)) >= 6
        assert count(QuickReply, QuickReply.property_id == hvh.id) >= 15
        assert count(DigitalAsset, DigitalAsset.property_id == hvh.id) == 8
        assert count(ResolutionCategory, ResolutionCategory.property_id == hvh.id) >= 10
        assert count(Message, Message.delivery_status == DeliveryStatus.failed) >= 1
        assert db.scalar(select(UserAccount).where(UserAccount.email == "ava@hvh.test")) is not None
    db_.engine.dispose()
    assert summary.conversations == 30

    # Deterministic: running again yields identical guest phone numbers.
    url2 = f"sqlite:///{(tmp_path / 'seed2.db').as_posix()}"
    run(url2, reset=True)
    a, b = Database(url), Database(url2)
    with a.session() as da, b.session() as dbb:
        pa = sorted(da.scalars(select(Guest.phone_e164)).all())
        pb = sorted(dbb.scalars(select(Guest.phone_e164)).all())
    assert pa == pb
    a.engine.dispose(); b.engine.dispose()


def test_seeded_users_can_log_in(tmp_path):
    from app import create_app
    from app.config import Config

    url = f"sqlite:///{(tmp_path / 'seed.db').as_posix()}"
    run(url, reset=True)
    app = create_app(Config(DATABASE_URL=url, TESTING=True))
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": "ava@hvh.test", "password": "Password123!"}).status_code == 200
    body = c.get("/api/auth/me").get_json()
    assert body["memberships"][0]["role"] == "agent"
    app.extensions["db"].engine.dispose()
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_seed.py -q`
Expected: FAIL with `ModuleNotFoundError: seed`.

- [ ] **Step 3: Write `seed/data.py` — the static vocabulary**

```python
"""Static content for the seed. Names, message templates, quick replies, assets, categories."""

FIRST_NAMES = ["Sarah", "Diego", "Nia", "Priya", "Tom", "Lena", "Omar", "Grace", "Hiro", "Amara", "Luca", "Maya",
               "Jonas", "Zara", "Felix", "Ines", "Kwame", "Elena", "Rafael", "Yuki", "Noor", "Mateo", "Ivy", "Tariq",
               "Chloe", "Dmitri", "Aisha", "Ben", "Sofia", "Arjun"]
LAST_NAMES = ["Chen", "Ruiz", "Okafor", "Nair", "Becker", "Park", "Haddad", "Mensah", "Tanaka", "Silva", "Rossi",
              "Novak", "Dubois", "Khan", "Andersen", "Moreno", "Boateng", "Petrova", "Costa", "Sato", "Rahman",
              "Alvarez", "Walsh", "Hassan", "Martin", "Volkov", "Diallo", "Cohen", "Ferreira", "Iyer"]
ROOM_TYPES = ["King", "Queen", "Double Queen", "Suite", "Accessible King"]
RATE_CODES = ["BAR", "AAA", "CORP", "PKG", "GOV"]
LOYALTY = [None, None, None, "Silver", "Silver", "Gold", "Gold", "Platinum"]

# (guest message, department type for a linked work order or None, negative sentiment?)
GUEST_OPENERS = [
    ("Hi, the AC in our room isn't working at all, it's really warm in here.", "engineering", True),
    ("Can we get a late checkout tomorrow? Flight isn't until 4.", "front_desk", False),
    ("Extra towels please, and is the pool open late?", "housekeeping", False),
    ("What time does breakfast start?", None, False),
    ("The shower drain is really slow and water is pooling.", "engineering", True),
    ("Is there parking on site and how much is it?", None, False),
    ("Room hasn't been serviced today and it's 4pm.", "housekeeping", True),
    ("Could someone bring up two more pillows?", "housekeeping", False),
    ("TV remote isn't pairing with the TV in 509.", "engineering", False),
    ("Hi! Just checked in. Where's the gym?", None, False),
    ("There's a strange noise from the ceiling vent.", "engineering", True),
    ("Can I get a wake-up call at 5:30am?", "front_desk", False),
    ("Arriving around 9pm tonight, is that ok?", None, False),
    ("The wifi keeps dropping in our room.", "engineering", False),
    ("Do you have a shuttle to the airport?", None, False),
    ("Our toilet is running constantly.", "engineering", True),
    ("Is the restaurant open for dinner tonight?", None, False),
    ("Could we have the room made up while we're at lunch?", "housekeeping", False),
    ("Bill shows a minibar charge we didn't use.", "front_desk", True),
    ("Love the view! Thank you for the upgrade.", None, False),
]
STAFF_REPLIES = [
    "So sorry about that — I'm sending someone up now, they'll knock within 15 minutes.",
    "Absolutely, I've noted that for you. Anything else you need?",
    "On its way! Housekeeping will be up shortly.",
    "Breakfast is 6:30–10:30 in the Harbour Room on level 2.",
    "Self-parking is $28/night in the garage on Front St; valet is $45.",
    "Done — your checkout is extended to 2 PM at no charge.",
    "The pool and hot tub are open 7 AM–10 PM.",
    "Thank you, Sarah — we're so glad you're enjoying it!",
]
NOTES = ["Gold member, 4th stay — offer 518 if not fixed by 7:30.", "Prefers high floor, away from elevator.",
         "Feather allergy — hypoallergenic pillows pre-set.", "Travelling with infant; crib delivered.",
         "Complained last stay about noise — proactive check-in done."]

WORK_ORDERS = [
    ("AC not cooling", "maintenance", "urgent", "engineering"), ("Toilet running constantly", "maintenance", "normal", "engineering"),
    ("Bathroom faucet dripping", "maintenance", "normal", "engineering"), ("Hallway light out near 512", "maintenance", "low", "engineering"),
    ("TV remote not pairing", "maintenance", "low", "engineering"), ("Ice machine 3F not dispensing", "maintenance", "normal", "engineering"),
    ("Pool pump pressure low", "maintenance", "high", "engineering"), ("Elevator B intermittent door fault", "maintenance", "urgent", "engineering"),
    ("Door closer slams", "maintenance", "low", "engineering"), ("Extra towels + pillows", "guest_request", "normal", "housekeeping"),
    ("Deep clean after checkout — mattress rotation", "housekeeping", "normal", "housekeeping"),
    ("Carpet stain, coffee", "housekeeping", "normal", "housekeeping"), ("Room not serviced by 4pm", "housekeeping", "high", "housekeeping"),
    ("Late checkout request — 2 PM", "guest_request", "normal", "front_desk"), ("Wake-up call 5:30am", "guest_request", "low", "front_desk"),
    ("Shower drain slow", "maintenance", "normal", "engineering"), ("Bedside lamp bulb", "maintenance", "low", "engineering"),
]

QUICK_REPLIES = [
    ("/wifi", "WiFi details", "Hi {{guest_first_name}} — the network is Harbourview-Guest, no password needed. If it drops, toggle WiFi off and on.", None),
    ("/checkout", "Checkout time", "Checkout is 11 AM. Reply LATE if you'd like to request a later time and we'll do our best.", "front_desk"),
    ("/late", "Late checkout granted", "Done — {{guest_first_name}}, your checkout is extended to 2 PM at no charge.", "front_desk"),
    ("/towels", "Towels on the way", "Fresh towels are on their way to {{room_number}} — about 15 minutes.", "housekeeping"),
    ("/eng", "Engineering dispatched", "So sorry about that. Engineering is on the way to {{room_number}} and will knock within 15 minutes.", None),
    ("/parking", "Parking", "Self-parking is $28/night in the garage on Front St; valet is $45 with in-and-out privileges.", "front_desk"),
    ("/breakfast", "Breakfast hours", "Breakfast is 6:30–10:30 in the Harbour Room, level 2.", None),
    ("/pool", "Pool hours", "The pool and hot tub are open 7 AM–10 PM. Towels are poolside.", None),
    ("/gym", "Fitness centre", "The fitness centre is on level 3, open 24 hours with your room key.", None),
    ("/shuttle", "Airport shuttle", "The shuttle runs on the hour from 5 AM to 11 PM from the Front St entrance.", "front_desk"),
    ("/sorry", "Apology", "I'm so sorry, {{guest_first_name}}. That's not the experience we want for you — let me fix it.", None),
    ("/thanks", "Thanks", "Thank you, {{guest_first_name}} — it's a pleasure having you at {{property_name}}.", None),
    ("/housekeeping", "Housekeeping timing", "Housekeeping services rooms between 9 AM and 3 PM. Want us to come at a specific time?", "housekeeping"),
    ("/bill", "Folio question", "Happy to check your folio — I'll review it and text you back within 10 minutes.", "front_desk"),
    ("/restaurant", "Restaurant hours", "The Quay is open for dinner 5:30–10 PM; the bar until midnight.", None),
]

ASSETS = [
    ("WiFi card", "link", "https://example.test/harbourview/wifi.pdf", "Connectivity"),
    ("Property map", "map", "https://example.test/harbourview/map.pdf", "Wayfinding"),
    ("Breakfast menu", "menu", "https://example.test/harbourview/breakfast.pdf", "Dining"),
    ("Dinner menu — The Quay", "menu", "https://example.test/harbourview/quay.pdf", "Dining"),
    ("Spa menu", "menu", "https://example.test/harbourview/spa.pdf", "Wellness"),
    ("Local guide", "link", "https://example.test/harbourview/local.pdf", "Explore"),
    ("Express checkout", "form", "https://example.test/harbourview/checkout", "Stay"),
    ("Shuttle schedule", "file", "https://example.test/harbourview/shuttle.pdf", "Transport"),
]

CATEGORIES = {
    "Maintenance": ["HVAC", "Plumbing", "Electrical", "Elevator"],
    "Service": ["Housekeeping delay", "Front desk", "F&B"],
    "Billing": ["Disputed charge", "Rate question"],
    "Praise": [],
    "Question": ["Hours", "Amenities", "Directions"],
}
```

- [ ] **Step 4: Write `seed/seed.py`**

```python
"""Deterministic development seed. `flask seed` or `python -m seed.seed`. Matches spec §8."""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db import Database, run_migrations
from app.domain.assets import new_short_code
from app.models import (Conversation, Department, DigitalAsset, DraftPrompt, Guest, InternalNote, Message, Property,
                        PropertyMembership, QuickReply, ResolutionCategory, Stay, UserAccount, WorkOrder,
                        WorkOrderEvent)
from app.queue import jobs
from app.schemas.enums import (AssetType, AuthorType, Channel, ConversationStatus, DeliveryStatus, DepartmentType,
                               Direction, DraftPromptStatus, Priority, Role, SmsConsentStatus, StayStatus,
                               WorkOrderEventType, WorkOrderStatus, WorkOrderType)
from seed import data

PASSWORD = "Password123!"


@dataclass
class SeedSummary:
    properties: int
    users: int
    guests: int
    stays: int
    conversations: int
    messages: int
    work_orders: int


def _phone(rng: random.Random, used: set[str]) -> str:
    while True:
        p = f"+1555{rng.randint(1000000, 9999999)}"
        if p not in used and not p.endswith("0000"):
            used.add(p)
            return p


def run(database_url: str, *, reset: bool = True, now: datetime | None = None) -> SeedSummary:
    now = now or datetime.now(timezone.utc)
    today = now.date()
    rng = random.Random(42)
    if reset and database_url.startswith("sqlite:///"):
        path = Path(database_url.removeprefix("sqlite:///"))
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(path) + suffix)
            if p.exists():
                p.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(database_url)
    database = Database(database_url)
    used_phones: set[str] = set()

    with database.session() as db:
        # ---- properties & departments
        hvh = Property(name="Harbourview Hotel", code="HVH", timezone="America/New_York", sms_number="+15550100",
                       address="1 Harbour St", currency="USD", primary_color="#f0b323",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4,
                                 "help_text": "Harbourview Hotel: text us anytime, or call +1 555 0100."})
        lsi = Property(name="Lakeside Inn", code="LSI", timezone="America/Chicago", sms_number="+15550200",
                       settings={"sla_minutes": 15, "auto_resolve_hours": 4, "help_text": "Lakeside Inn: call +1 555 0200."})
        db.add_all([hvh, lsi]); db.flush()
        depts = {}
        for name, typ in [("Front Desk", DepartmentType.front_desk), ("Housekeeping", DepartmentType.housekeeping),
                          ("Engineering", DepartmentType.engineering)]:
            d = Department(property_id=hvh.id, name=name, type=typ); db.add(d); depts[typ.value] = d
        lsi_fd = Department(property_id=lsi.id, name="Front Desk", type=DepartmentType.front_desk); db.add(lsi_fd)
        db.flush()

        # ---- staff (12 at HVH + 2 at LSI)
        pw = hash_password(PASSWORD, rounds=10)

        def user(email, first, last):
            u = UserAccount(email=email, first_name=first, last_name=last, password_hash=pw); db.add(u); db.flush(); return u

        def member(u, prop, role, dept=None):
            db.add(PropertyMembership(user_id=u.id, property_id=prop.id, role=role, department_id=dept.id if dept else None))

        staff = {
            "ava": user("ava@hvh.test", "Ava", "Agent"), "marcus": user("marcus@hvh.test", "Marcus", "Reyes"),
            "jordan": user("jordan@hvh.test", "Jordan", "Tate"), "hana": user("hana@hvh.test", "Hana", "Keeper"),
            "rosa": user("rosa@hvh.test", "Rosa", "Lima"), "eli": user("eli@hvh.test", "Eli", "Engineer"),
            "noah": user("noah@hvh.test", "Noah", "Fix"), "hk_sup": user("hk.supervisor@hvh.test", "Grace", "Osei"),
            "sam": user("sam@hvh.test", "Sam", "Super"), "morgan": user("morgan@hvh.test", "Morgan", "Manager"),
            "alex": user("alex@hvh.test", "Alex", "Admin"), "casey": user("casey@group.test", "Casey", "Corp"),
        }
        member(staff["ava"], hvh, Role.agent, depts["front_desk"]); member(staff["marcus"], hvh, Role.agent, depts["front_desk"])
        member(staff["jordan"], hvh, Role.agent, depts["front_desk"])
        member(staff["hana"], hvh, Role.dept_staff, depts["housekeeping"]); member(staff["rosa"], hvh, Role.dept_staff, depts["housekeeping"])
        member(staff["eli"], hvh, Role.dept_staff, depts["engineering"]); member(staff["noah"], hvh, Role.dept_staff, depts["engineering"])
        member(staff["hk_sup"], hvh, Role.supervisor, depts["housekeeping"]); member(staff["sam"], hvh, Role.supervisor, depts["engineering"])
        member(staff["morgan"], hvh, Role.manager); member(staff["alex"], hvh, Role.admin); member(staff["casey"], hvh, Role.corporate)
        blake = user("blake@lsi.test", "Blake", "Admin"); member(blake, lsi, Role.admin)
        bea = user("bea@lsi.test", "Bea", "Agent"); member(bea, lsi, Role.agent, lsi_fd)
        member(staff["casey"], lsi, Role.corporate)

        # ---- rooms, guests, stays
        rooms = [f"{f}{n:02d}" for f in range(1, 7) for n in range(1, 21)]
        rng.shuffle(rooms)
        guests: list[Guest] = []
        stays: list[Stay] = []

        def make_guest(prop, first=None, last=None, phone=None, tier=None, consent=SmsConsentStatus.opted_in):
            g = Guest(property_id=prop.id, first_name=first or rng.choice(data.FIRST_NAMES),
                      last_name=last or rng.choice(data.LAST_NAMES), phone_e164=phone or _phone(rng, used_phones),
                      loyalty_tier=tier if tier is not None else rng.choice(data.LOYALTY),
                      vip=rng.random() < 0.05, sms_consent_status=consent,
                      sms_consent_at=now - timedelta(days=rng.randint(1, 400)), sms_consent_source="pms")
            db.add(g); db.flush(); guests.append(g); return g

        def make_stay(g, room, status, arrival, nights, res_id=None):
            s = Stay(guest_id=g.id, property_id=g.property_id, pms_reservation_id=res_id or f"RES-{room}-{rng.randint(1000, 9999)}",
                     room_number=room, room_type=rng.choice(data.ROOM_TYPES), rate_code=rng.choice(data.RATE_CODES),
                     status=status, arrival_date=arrival, departure_date=arrival + timedelta(days=nights),
                     adults=rng.choice([1, 2, 2, 2, 3]), children=rng.choice([0, 0, 0, 1, 2]),
                     is_return_guest=rng.random() < 0.3, stay_count=rng.randint(1, 6),
                     actual_checkin_at=(datetime.combine(arrival, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15))
                     if status != StayStatus.reserved else None,
                     actual_checkout_at=now - timedelta(hours=rng.randint(20, 40)) if status == StayStatus.checked_out else None,
                     raw_pms={"seed": True})
            db.add(s); db.flush(); stays.append(s); return s

        sarah = make_guest(hvh, "Sarah", "Chen", "+15551234567", "Gold")
        make_stay(sarah, "412", StayStatus.checked_in, today - timedelta(days=1), 3, res_id="RES-412")
        tom = make_guest(hvh, "Tom", "Becker", "+15552000000", "Silver")  # fails delivery on purpose
        make_stay(tom, "516", StayStatus.checked_in, today, 2)
        room_iter = iter(r for r in rooms if r not in ("412", "516"))
        for _ in range(83):
            g = make_guest(hvh); make_stay(g, next(room_iter), StayStatus.checked_in, today - timedelta(days=rng.randint(0, 4)), rng.randint(1, 5))
        for _ in range(10):
            g = make_guest(hvh); make_stay(g, next(room_iter), StayStatus.reserved, today, rng.randint(1, 4))
        departing = [s for s in stays if s.status == StayStatus.checked_in][2:12]
        for s in departing:
            s.departure_date = today
        for _ in range(7):  # + Lena below = 8 checked out
            g = make_guest(hvh); make_stay(g, rng.choice(rooms), StayStatus.checked_out, today - timedelta(days=3), 2)
        lena = make_guest(hvh, "Lena", "Park", "+15553104411", None, SmsConsentStatus.opted_out)
        lena.sms_consent_source = "sms_keyword"
        make_stay(lena, "301", StayStatus.checked_out, today - timedelta(days=4), 2)
        for _ in range(3):
            g = make_guest(lsi); make_stay(g, str(rng.randint(101, 140)), StayStatus.checked_in, today, 2)

        # ---- content
        for shortcut, title, body, dept in data.QUICK_REPLIES:
            db.add(QuickReply(property_id=hvh.id, shortcut=shortcut, title=title, body=body,
                              department_id=depts[dept].id if dept else None, usage_count=rng.randint(0, 220)))
        db.add(QuickReply(property_id=hvh.id, shortcut="/oldshuttle", title="Old shuttle", body="Retired.", active=False))
        for name, typ, url, cat in data.ASSETS:
            db.add(DigitalAsset(property_id=hvh.id, name=name, type=AssetType(typ), url=url, category=cat,
                                short_code=new_short_code(db), send_count=rng.randint(0, 80)))
        cats = {}
        for parent, children in data.CATEGORIES.items():
            p = ResolutionCategory(property_id=hvh.id, name=parent); db.add(p); db.flush(); cats[parent] = p
            for c in children:
                db.add(ResolutionCategory(property_id=hvh.id, name=c, parent_id=p.id))
        db.flush()

        # ---- conversations (30) + work orders
        in_house = [s for s in stays if s.property_id == hvh.id and s.status == StayStatus.checked_in]
        agents = [staff["ava"], staff["marcus"], staff["jordan"]]
        eng_staff = [staff["eli"], staff["noah"]]
        hk_staff = [staff["hana"], staff["rosa"]]
        convs: list[Conversation] = []
        messages = 0
        work_orders: list[WorkOrder] = []

        def add_msg(c, direction, body, at, author=None, status=DeliveryStatus.delivered, redacted=False, author_type=None):
            nonlocal messages
            m = Message(conversation_id=c.id, property_id=c.property_id, direction=direction,
                        author_type=author_type or (AuthorType.guest if direction == Direction.inbound else AuthorType.staff),
                        author_user_id=author.id if author else None, channel=Channel.sms, body=body, delivery_status=status,
                        provider_message_id=f"seed-{rng.randint(10**8, 10**9)}", redacted=redacted, sent_at=at,
                        delivered_at=at if status == DeliveryStatus.delivered else None,
                        provider_error_code="30007" if status == DeliveryStatus.failed else None,
                        provider_error_message="Carrier violation (mock)" if status == DeliveryStatus.failed else None)
            db.add(m); messages += 1; return m

        def add_wo(title, typ, prio, dept_type, status, conv=None, assignee=None, created=None):
            created = created or now - timedelta(minutes=rng.randint(10, 600))
            wo = WorkOrder(property_id=hvh.id, title=title, type=WorkOrderType(typ), priority=Priority(prio), status=status,
                           location_ref=(conv.stay.room_number if conv and conv.stay else rng.choice(rooms)),
                           department_id=depts[dept_type].id, assigned_user_id=assignee.id if assignee else None,
                           reported_by_user_id=rng.choice(agents).id, source_conversation_id=conv.id if conv else None,
                           created_at=created, updated_at=created,
                           started_at=created + timedelta(minutes=5) if status in (WorkOrderStatus.in_progress, WorkOrderStatus.blocked, WorkOrderStatus.complete) else None,
                           completed_at=created + timedelta(minutes=rng.randint(10, 60)) if status == WorkOrderStatus.complete else None)
            db.add(wo); db.flush()
            db.add(WorkOrderEvent(work_order_id=wo.id, property_id=hvh.id, user_id=wo.reported_by_user_id,
                                  type=WorkOrderEventType.created, to_value="open", created_at=created))
            work_orders.append(wo); return wo

        # 30 conversations incl. Tom's below: 7 fresh unassigned, 6 answered+assigned, 5 overdue,
        # 4 resolved-eligible, 5 archived, 2 with prompts (= 29) + Tom's failed-delivery conversation.
        openers = list(data.GUEST_OPENERS); rng.shuffle(openers)
        plan = (["fresh"] * 7 + ["answered"] * 6 + ["overdue"] * 5 + ["resolved"] * 4 + ["archived"] * 5 + ["prompt"] * 2)
        conv_stays = [s for s in in_house if s.room_number not in ("412", "516")]
        rng.shuffle(conv_stays)
        for i, kind in enumerate(plan):
            stay = conv_stays[i]
            guest = db.get(Guest, stay.guest_id)
            opener, dept_type, _neg = openers[i % len(openers)]
            c = Conversation(property_id=hvh.id, guest_id=guest.id, stay_id=stay.id, status=ConversationStatus.open,
                             channel_primary=Channel.sms)
            db.add(c); db.flush(); c.stay = stay
            if kind == "fresh":
                at = now - timedelta(minutes=rng.randint(1, 12))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at; c.sla_due_at = at + timedelta(minutes=15)
            elif kind == "answered":
                at = now - timedelta(minutes=rng.randint(20, 180)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=2), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=2)
                c.first_response_seconds = 120; c.assigned_user_id = agent.id
                dt = dept_type or "front_desk"  # every answered conversation gets a linked WO (spec: 6 linked)
                pool_for = [w for w in data.WORK_ORDERS if w[3] == dt]
                add_wo(rng.choice(pool_for)[0], "maintenance" if dt == "engineering" else "guest_request",
                       "normal", dt, WorkOrderStatus.assigned, conv=c,
                       assignee=rng.choice(eng_staff if dt == "engineering" else hk_staff if dt == "housekeeping" else agents))
            elif kind == "overdue":
                at = now - timedelta(minutes=rng.randint(20, 90))
                add_msg(c, Direction.inbound, opener, at)
                c.last_guest_message_at = at; c.sla_due_at = at + timedelta(minutes=15); c.sla_breach_notified_at = at + timedelta(minutes=16)
                c.assigned_department_id = depts[dept_type or "front_desk"].id
            elif kind == "resolved":
                at = now - timedelta(hours=rng.randint(5, 20)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=4), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=4); c.first_response_seconds = 240
            elif kind == "archived":
                at = now - timedelta(days=rng.randint(1, 3)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, rng.choice(data.STAFF_REPLIES), at + timedelta(minutes=3), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=3); c.first_response_seconds = 180
                c.status = ConversationStatus.archived; c.archived_at = at + timedelta(hours=5)
                c.resolution_category_id = rng.choice(list(cats.values())).id
            elif kind == "prompt":
                at = now - timedelta(minutes=rng.randint(30, 60)); agent = rng.choice(agents)
                add_msg(c, Direction.inbound, opener, at)
                add_msg(c, Direction.outbound, data.STAFF_REPLIES[0], at + timedelta(minutes=3), agent)
                c.last_guest_message_at = at; c.last_staff_message_at = at + timedelta(minutes=3); c.first_response_seconds = 180
                c.assigned_user_id = agent.id
                wo = add_wo("AC not cooling" if i % 2 == 0 else "Shower drain slow", "maintenance", "urgent", "engineering",
                            WorkOrderStatus.complete, conv=c, assignee=staff["eli"], created=at + timedelta(minutes=1))
                db.add(DraftPrompt(property_id=hvh.id, conversation_id=c.id, work_order_id=wo.id, status=DraftPromptStatus.pending,
                                   body=f"Hi {guest.first_name} — our team has taken care of \"{wo.title.lower()}\" in {stay.room_number}. Please text us if anything still isn't right."))
            if i % 6 == 0:
                db.add(InternalNote(conversation_id=c.id, property_id=hvh.id, author_user_id=rng.choice(agents).id,
                                    body=rng.choice(data.NOTES), mentions=[]))
            convs.append(c)

        # Sarah's showcase conversation is one of the 30: make conversation 0 hers instead of a random stay.
        # (Simplest: rewire conv[0].) Replace its guest/stay with Sarah's and give it the AC story.
        showcase = convs[0]
        sarah_stay = next(s for s in stays if s.guest_id == sarah.id)
        showcase.guest_id = sarah.id; showcase.stay_id = sarah_stay.id; showcase.stay = sarah_stay
        for m in db.scalars(select(Message).where(Message.conversation_id == showcase.id)).all():
            db.delete(m)
        db.flush()
        t0 = now - timedelta(minutes=23)
        add_msg(showcase, Direction.outbound, "Welcome to Harbourview, Sarah. You're in 412. WiFi: Harbourview-Guest, no password. Text us anytime.",
                t0 - timedelta(hours=3), author_type=AuthorType.automation)
        add_msg(showcase, Direction.inbound, "Hi, the AC in our room isn't working at all, it's really warm in here. We tried turning it off and on.", t0)
        add_msg(showcase, Direction.outbound, "So sorry about that, Sarah. I'm sending engineering up to 412 now — they'll knock in the next 15 minutes.",
                t0 + timedelta(minutes=3), staff["ava"])
        add_msg(showcase, Direction.inbound, "Thank you, someone just came by", t0 + timedelta(minutes=17))
        showcase.last_guest_message_at = t0 + timedelta(minutes=17); showcase.last_staff_message_at = t0 + timedelta(minutes=3)
        showcase.first_response_seconds = 180; showcase.assigned_user_id = staff["ava"].id
        showcase.sla_due_at = t0 + timedelta(minutes=32); showcase.status = ConversationStatus.open; showcase.archived_at = None
        db.add(InternalNote(conversation_id=showcase.id, property_id=hvh.id, author_user_id=staff["ava"].id,
                            body="Raised WO to Engineering, urgent. Sarah is Gold, 4th stay; if it's not fixed by 7:30 offer 518.", mentions=[]))

        # A failed outbound to Tom (…0000) and a redacted card message from another guest.
        tom_conv = Conversation(property_id=hvh.id, guest_id=tom.id, stay_id=next(s.id for s in stays if s.guest_id == tom.id),
                                status=ConversationStatus.open, channel_primary=Channel.sms)
        db.add(tom_conv); db.flush()
        add_msg(tom_conv, Direction.inbound, "Is late checkout possible?", now - timedelta(minutes=50))
        add_msg(tom_conv, Direction.outbound, "Of course — extended to 1 PM.", now - timedelta(minutes=48), staff["marcus"], status=DeliveryStatus.failed)
        tom_conv.last_guest_message_at = now - timedelta(minutes=50); tom_conv.last_staff_message_at = now - timedelta(minutes=48)
        tom_conv.first_response_seconds = 120; tom_conv.assigned_user_id = staff["marcus"].id
        card_conv = convs[3]
        add_msg(card_conv, Direction.inbound, "you can charge it to **** **** **** 4242", now - timedelta(minutes=5), redacted=True)
        db.flush()

        # Fill remaining open work orders to reach 15 active (not verified/cancelled).
        active = [w for w in work_orders if w.status in (WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress,
                                                            WorkOrderStatus.blocked, WorkOrderStatus.complete)]
        pool = [w for w in data.WORK_ORDERS if w[0] not in {x.title for x in active}]
        statuses = [WorkOrderStatus.open, WorkOrderStatus.assigned, WorkOrderStatus.in_progress, WorkOrderStatus.blocked, WorkOrderStatus.open]
        j = 0
        while len(active) < 15:
            title, typ, prio, dept_type = pool[j % len(pool)]; j += 1
            st = statuses[j % len(statuses)]
            assignee = None if st == WorkOrderStatus.open else rng.choice(eng_staff if dept_type == "engineering" else hk_staff)
            active.append(add_wo(title, typ, prio, dept_type, st, assignee=assignee))
        # A few closed ones for analytics history.
        for k in range(6):
            title, typ, prio, dept_type = data.WORK_ORDERS[k]
            add_wo(title, typ, prio, dept_type, WorkOrderStatus.verified, assignee=rng.choice(eng_staff), created=now - timedelta(days=rng.randint(1, 6)))

        # ---- recurring jobs
        for job_type in ("sla.sweep", "snooze.wake", "pms.tick"):
            jobs.ensure_recurring(db, job_type)

        summary = SeedSummary(properties=2, users=len(staff) + 2, guests=len(guests), stays=len(stays),
                              conversations=len(convs), messages=messages, work_orders=len(work_orders))
    database.engine.dispose()
    return summary


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    print(run(os.getenv("DATABASE_URL", "sqlite:///data/app.db")))
```

Counts the test pins: 29 planned conversations + Tom's = 30; 7 random checked-out stays + Lena = 8; the six `verified` work orders are added after `active` reaches 15 so they never count toward it.

- [ ] **Step 5: Write `app/cli.py` and register it**

```python
import click
from flask import current_app
from flask.cli import with_appcontext


@click.command("seed")
@click.option("--no-reset", is_flag=True, help="Do not delete the existing SQLite file first.")
@with_appcontext
def seed_command(no_reset: bool) -> None:
    from seed.seed import run

    cfg = current_app.config["APP"]
    summary = run(cfg.DATABASE_URL, reset=not no_reset)
    click.echo(f"Seeded {summary.properties} properties, {summary.users} users, {summary.guests} guests, "
               f"{summary.stays} stays, {summary.conversations} conversations, {summary.messages} messages, "
               f"{summary.work_orders} work orders.")
```

In `create_app`: `from app.cli import seed_command; app.cli.add_command(seed_command)`.

- [ ] **Step 6: Run the tests and the real seed**

Run: `python -m pytest -q` → all pass.
Run from `server/`: `python -m seed.seed` → prints a `SeedSummary(...)` line; `ls data/` shows `app.db`.

- [ ] **Step 7: Commit**

```bash
cd ..
git add server
git commit -m "feat(server): deterministic seed script and flask seed command"
```

---

### Task 23: JSON Schema export for the frontend

**Files:**
- Create: `server/app/schemas/export_json_schema.py`, `server/tests/test_schema_export.py`, `web/src/api/schema.json` (generated)

**Interfaces:**
- Produces: `export_json_schema.build() -> dict` (one JSON Schema document with every request/response model under `$defs`, keyed by class name); `python -m app.schemas.export_json_schema [out_path]` writes it (default `../web/src/api/schema.json`); the test fails when the committed file is stale. Consumed by the web plan's `npm run gen:types`.

- [ ] **Step 1: Write the failing test**

`server/tests/test_schema_export.py`:
```python
import json
from pathlib import Path

from app.schemas.export_json_schema import DEFAULT_OUT, build


def test_export_contains_the_public_models():
    schema = build()
    defs = schema["$defs"]
    for name in ("SessionOut", "ConversationSummary", "ConversationDetail", "GuestThread", "MessageOut",
                 "WorkOrderOut", "WorkOrderDetail", "WorkOrderPrefill", "QuickReplyOut", "AssetOut", "CategoryOut",
                 "NotificationOut", "Overview", "AgentStats", "StaffUserOut", "DepartmentOut", "SimGuest"):
        assert name in defs, name
    assert defs["GuestThread"]["additionalProperties"] is False
    assert "notes" not in defs["GuestThread"]["properties"]


def test_committed_schema_is_current():
    path = Path(DEFAULT_OUT)
    assert path.exists(), f"run: python -m app.schemas.export_json_schema  (writes {path})"
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed == build(), "web/src/api/schema.json is stale — re-run python -m app.schemas.export_json_schema"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_schema_export.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the exporter**

`app/schemas/export_json_schema.py`:
```python
"""Exports every API model as one JSON Schema document for the React client (web/src/api/schema.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from app.schemas import analytics, auth, content, conversations, dev, notifications, users, work_orders

MODULES = (auth, users, conversations, work_orders, content, notifications, analytics, dev)
DEFAULT_OUT = str(Path(__file__).resolve().parents[3] / "web" / "src" / "api" / "schema.json")


def _models() -> list[type[BaseModel]]:
    seen: dict[str, type[BaseModel]] = {}
    for mod in MODULES:
        for name, obj in vars(mod).items():
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__:
                seen[name] = obj
    return [seen[k] for k in sorted(seen)]


def build() -> dict:
    _, schema = models_json_schema([(m, "serialization") for m in _models()], ref_template="#/$defs/{model}",
                                   title="Concierge API")
    schema.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    return schema


def main(out: str | None = None) -> None:
    path = Path(out or DEFAULT_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
```

Serialization mode is used so `datetime` fields export as `format: date-time` strings and aliases are camelCase — exactly what the client receives. Request models (`LoginRequest`, `CreateWorkOrder`, …) are exported in the same pass; their camelCase aliases are what the client sends.

- [ ] **Step 4: Generate, then run the tests**

Run from `server/`: `python -m app.schemas.export_json_schema` → `wrote …/web/src/api/schema.json`.
Run: `python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
cd ..
git add server web/src/api/schema.json
git commit -m "feat(server): export API models as JSON Schema for the web client"
```

---

### Task 24: Dev entrypoint, root scripts, README, final verification

**Files:**
- Create: `server/.env.example`, `package.json` (root), `README.md`
- Modify: `server/run.py`, `server/app/__init__.py` (CORS for the Vite dev server)

**Interfaces:**
- Produces: `npm run server` (Flask dev server on :5000 with worker), `npm run seed`, `npm run test:server`; README with setup, seeded credentials, simulator instructions, Postgres switch. (`npm run dev` and `npm run web` are added by the web plan.)

- [ ] **Step 1: CORS for the SPA dev server**

Vite proxies `/api` and `/ws` to Flask, so no CORS is needed in the intended setup. Add a guard anyway for anyone hitting the API directly from `http://localhost:5173`: in `create_app`, after blueprints:
```python
    @app.after_request
    def _cors(resp):
        origin = request.headers.get("Origin")
        if origin and origin == config.CORS_ORIGIN:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Credentials"] = "true"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Mock-Secret"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
        return resp
```
with `from flask import request` at the top of `app/__init__.py`.

- [ ] **Step 2: Finish `run.py` and add `.env.example`**

`server/run.py`:
```python
"""Development entrypoint. Production: gunicorn -k gthread -w 1 --threads 16 'app:create_app()'"""
import os

from app import create_app
from app.config import Config

if __name__ == "__main__":
    os.environ.setdefault("START_WORKER", "1")
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=not cfg.is_production, threaded=True)
```

`server/.env.example`:
```
FLASK_ENV=development
PORT=5000
DATABASE_URL=sqlite:///data/app.db
SESSION_SECRET=change-me-in-production
MOCK_SMS_SECRET=dev
SMS_ADAPTER=mock
PMS_TICK_SECONDS=90
START_WORKER=1
CORS_ORIGIN=http://localhost:5173
```

- [ ] **Step 3: Root `package.json`**

```json
{
  "name": "concierge",
  "private": true,
  "scripts": {
    "server": "cd server && python run.py",
    "seed": "cd server && python -m seed.seed",
    "test:server": "cd server && python -m pytest -q",
    "schema": "cd server && python -m app.schemas.export_json_schema"
  }
}
```
(These assume the venv is activated in the shell running npm; the README says so. The web plan adds `web`, `dev` via `concurrently`, and `gen:types`.)

- [ ] **Step 4: README**

`README.md`:
```markdown
# Concierge — hotel guest engagement & operations (Phase 1)

One codebase, one database: guests text the hotel; staff answer from a shared inbox; problems become work
orders; when the work order closes, the agent is prompted to tell the guest. Spec: `docs/design.md`.
Phase 1 scope and stack decisions: `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md`.
Approved screens: `docs/mockups/` (Night Shift direction).

## Stack
Python 3.12+ · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · flask-sock · pytest — SQLite now, PostgreSQL by
changing `DATABASE_URL`. Frontend: Vite + React + TypeScript (see the web plan).

## Setup (Windows / macOS / Linux)
```bash
python -m venv .venv
# Windows Git Bash: . .venv/Scripts/activate   PowerShell: .venv\Scripts\Activate.ps1   macOS/Linux: . .venv/bin/activate
cd server && pip install -e ".[dev]" && cd ..
cp server/.env.example server/.env
npm run seed          # creates server/data/app.db with realistic data
npm run server        # http://127.0.0.1:5000  (API + WebSocket + job worker)
npm run test:server   # pytest, including the §11.1 acceptance suite
```
Note: npm ≥ 11.19 blocks package install scripts by default; the server has no native dependencies, so this
does not affect the Python side. If a Node package needs its install script, run `npm install-scripts approve <pkg>`.

## Seeded logins (password for all: `Password123!`)
| Email | Role | Lands on |
|---|---|---|
| ava@hvh.test, marcus@hvh.test, jordan@hvh.test | agent | Inbox |
| eli@hvh.test, noah@hvh.test | dept_staff (Engineering) | Board · mine |
| hana@hvh.test, rosa@hvh.test | dept_staff (Housekeeping) | Board · mine |
| sam@hvh.test (Engineering), hk.supervisor@hvh.test (Housekeeping) | supervisor | Board |
| morgan@hvh.test | manager | Analytics |
| alex@hvh.test | admin | Analytics |
| casey@group.test | corporate (HVH + LSI) | Analytics |
| blake@lsi.test / bea@lsi.test | Lakeside Inn admin / agent | — |

## Texting the hotel without Twilio
The SMS wire is mocked (`SMS_ADAPTER=mock`). Send an inbound text exactly as Twilio would:
```bash
curl -X POST http://127.0.0.1:5000/api/hooks/sms/inbound -H "X-Mock-Secret: dev" \
  -d From=+15551234567 -d To=+15550100 -d "Body=The AC in 412 is broken" -d MessageSid=SM123
```
Numbers ending in `0000` fail delivery with error `30007` so you can exercise the retry path. `STOP`, `START`
and `HELP` behave per TCPA. The React phone simulator (web plan) wraps this in a UI.

## API in one minute
`POST /api/auth/login` → cookie `sid`. Everything staff-facing lives under `/api/p/<propertyId>/…`:
`conversations`, `work-orders`, `quick-replies`, `assets`, `resolution-categories`, `users`, `departments`,
`notifications`, `analytics`, `guests`. WebSocket at `/ws` (send `{"type":"subscribe","propertyId":…}`).
Dev only: `/api/dev/sim/*`, `/api/dev/pms/*`. Models: `web/src/api/schema.json`.

## Moving to PostgreSQL
`pip install "psycopg[binary]"`, set `DATABASE_URL=postgresql+psycopg://…`, run `cd server && alembic upgrade head`.
Migrations use portable types; nothing else changes. Run one web process (`gunicorn -w 1 --threads 16`) because
presence and the realtime registry are in-memory.
```

- [ ] **Step 5: Full verification**

Run from `server/`:
```bash
python -m pytest -q
ruff check .
python -m seed.seed
START_WORKER=1 python run.py &
sleep 3
curl -s http://127.0.0.1:5000/api/health
curl -s -X POST http://127.0.0.1:5000/api/hooks/sms/inbound -H "X-Mock-Secret: dev" -d From=+15559876543 -d To=+15550100 -d "Body=Testing from curl" -d MessageSid=SM-curl-1 -o /dev/null -w "%{http_code}\n"
```
Expected: all tests pass; ruff reports no errors; health returns `{"status":"ok"}`; the webhook returns `204`. Log in as `ava@hvh.test` with curl (`-c cookies.txt`) and `GET /api/p/<HVH id>/conversations` to see the new conversation at the top. Stop the server.

- [ ] **Step 6: Commit**

```bash
cd ..
git add README.md package.json server
git commit -m "chore: dev entrypoint, root scripts, README with setup and seeded logins"
```

---

## Self-review notes (kept for the executor)

- **Spec coverage.** §4.1 domain table → Tasks 6, 7, 10–18. §4.2 channels → 9, 11. §4.3 PMS → 20. §4.4 queue → 8. §4.5 realtime → 7, 19. §4.6 auth → 4, 5. §4.7 API → 5, 7, 11, 12, 15, 16, 17, 18, 21. §4.8 type export → 23. §6 compliance → 6 (redaction), 10 (consent), 11 (send path/keywords), 4 (audit). §7 tests: criteria 1, 2, 5 → Task 11; 4 → 9 and 12; 6, 7 → 14; 8 → 13; 9 → 5; 10 → 12; 3 is the E2E in the web plan. §8 seed → 22. §9 config → 1, 24. §11 Postgres → 24 README.
- **Deliberate deviations from the spec text:** `app/clock.py` module instead of `app.clock` attribute (same purpose, thread-safe from the worker); the session table is `user_session`; `ChannelAdapter.send` takes `db` so the mock can enqueue delivery jobs; per-test DB copies instead of per-module (cheaper and simpler).
- **Names that must match across tasks:** `db_session`, `ok`, `parse_body`, `parse_query`, `no_content`, `client_meta` (Task 4); `queue_event`, `deliver`, `add_listener` (7); `jobs.enqueue`, `Worker.tick` (8); `messages.send/record_inbound/retry/update_delivery_status` (9, 11); `conversations.get/find_or_create_for_guest/list/detail/patch/guest_thread/touch_updated/assert_viewer_can_see` (11, 12); `work_orders.create/transition/assign/comment/set_priority/prefill_from_conversation/list/detail` (14, 15); `draft_prompts.create_for_completion/dismiss` (14, 15); `notifications.create/notify_user_or_department` (7); `users.list_departments/list_staff/members_of_department/create_staff/update_staff/remove_membership` (5, 17); fixture names `app, client, database, fx, login, events, worker, template_db_path` (3, 7, 8).
