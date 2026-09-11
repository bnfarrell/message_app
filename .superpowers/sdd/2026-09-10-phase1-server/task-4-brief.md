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

