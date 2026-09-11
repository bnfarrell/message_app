from sqlalchemy import select

from app import clock
from app.models import AuditLog


def test_login_sets_cookie_and_me_returns_memberships(app, fx, client):
    res = client.post("/api/auth/login",
                      json={"email": "agent@hvh.test", "password": "Password123!"})
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
    unknown = client.post("/api/auth/login",
                          json={"email": "ghost@hvh.test", "password": "Password123!"})
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
    res = client.post("/api/auth/login",
                      json={"email": "agent@hvh.test", "password": "Password123!"})
    assert res.status_code == 401
