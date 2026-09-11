from __future__ import annotations

from flask import Blueprint, current_app, g, make_response
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
            audit.record(db, None, user.id, "auth.login", "user_account", user.id, ip=ip,
                        user_agent=ua)
            payload = _session_out(db, user)
    if not valid:
        # Written in its own session: raising inside the block above would roll the audit row back.
        with db_session() as db:
            audit.record(db, None, None, "auth.login_failed", "user_account",
                         user.id if user else None, after={"email": body.email}, ip=ip,
                         user_agent=ua)
        raise Unauthorized("Email or password is incorrect")
    resp = make_response(ok(payload)[0], 200)
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_HOURS * 3600, httponly=True,
                    samesite="Lax", path="/",
                    secure=current_app.config["APP"].cookie_secure)
    return resp


@bp.post("/logout")
@require_auth
def logout():
    ip, ua = client_meta()
    with db_session() as db:
        revoke_session(db, g.session_token)
        audit.record(db, None, g.user.id, "auth.logout", "user_account", g.user.id, ip=ip,
                    user_agent=ua)
    resp = make_response(no_content())
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@bp.get("/me")
@require_auth
def me():
    with db_session() as db:
        user = db.get(UserAccount, g.user.id)
        return ok(_session_out(db, user))
