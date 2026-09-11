from tests.fixtures import PASSWORD


def test_me_exposes_notification_prefs(client, fx, login):
    c = login(fx.agent_a.email)
    body = c.get("/api/auth/me").get_json()
    assert body["user"]["notificationPrefs"] == {}


def test_login_exposes_notification_prefs(client, fx):
    res = client.post("/api/auth/login",
                      json={"email": fx.agent_a.email, "password": PASSWORD})
    assert res.status_code == 200
    assert res.get_json()["user"]["notificationPrefs"] == {}


def test_patch_prefs_persists_the_theme_and_returns_the_session(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "light"})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["user"]["notificationPrefs"]["theme"] == "light"
    # A fresh request sees it: this is the whole point — the theme follows the user.
    assert c.get("/api/auth/me").get_json()["user"]["notificationPrefs"]["theme"] == "light"


def test_patch_prefs_survives_a_new_session(fx, login):
    """The value must be on the row, not in the session — this is the whole point of R1."""
    login(fx.agent_a.email).patch("/api/auth/prefs", json={"theme": "light"})
    fresh = login(fx.agent_a.email)
    assert fresh.get("/api/auth/me").get_json()["user"]["notificationPrefs"]["theme"] == "light"


def test_patch_prefs_merges_rather_than_replacing(fx, login):
    c = login(fx.agent_a.email)
    c.patch("/api/auth/prefs", json={"theme": "light"})
    c.patch("/api/auth/prefs", json={"theme": "dark"})
    prefs = c.get("/api/auth/me").get_json()["user"]["notificationPrefs"]
    assert prefs["theme"] == "dark"


def test_patch_prefs_rejects_an_unknown_theme(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "sepia"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "VALIDATION_FAILED"


def test_patch_prefs_rejects_unknown_keys(fx, login):
    c = login(fx.agent_a.email)
    res = c.patch("/api/auth/prefs", json={"theme": "light", "isAdmin": True})
    assert res.status_code == 400


def test_patch_prefs_requires_a_session(client):
    res = client.patch("/api/auth/prefs", json={"theme": "light"})
    assert res.status_code == 401


def test_patch_prefs_only_touches_the_caller(fx, login):
    login(fx.agent_a.email).patch("/api/auth/prefs", json={"theme": "light"})
    other = login(fx.agent_a2.email)
    assert other.get("/api/auth/me").get_json()["user"]["notificationPrefs"] == {}
