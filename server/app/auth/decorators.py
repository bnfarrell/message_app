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
