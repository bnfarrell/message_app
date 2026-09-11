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

