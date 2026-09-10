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
