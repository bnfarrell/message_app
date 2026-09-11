"""The SPA routes exist only in the container image, where WEB_DIST names a built client."""
import pytest
from flask import Flask

from app import spa


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>shell</title>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "main-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return tmp_path


@pytest.fixture
def client(dist, monkeypatch):
    monkeypatch.setenv("WEB_DIST", str(dist))
    app = Flask(__name__)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    assert spa.install(app) is True
    return app.test_client()


def test_not_installed_without_web_dist(monkeypatch):
    monkeypatch.delenv("WEB_DIST", raising=False)
    app = Flask(__name__)
    assert spa.install(app) is False
    # GET / stays a 404 by design in development and under tests.
    assert app.test_client().get("/").status_code == 404


def test_not_installed_when_the_directory_has_no_shell(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_DIST", str(tmp_path))
    assert spa.install(Flask(__name__)) is False


def test_root_serves_the_shell_uncached(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"shell" in response.data
    # A cached shell would pin the browser to a previous deploy's fingerprinted bundles.
    assert response.headers["Cache-Control"] == "no-store"


def test_client_side_routes_fall_back_to_the_shell(client):
    for path in ("/login", "/app/inbox", "/app/admin/departments"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert b"shell" in response.data, path


def test_fingerprinted_assets_are_served_and_cached_hard(client):
    response = client.get("/assets/main-abc123.js")
    assert response.status_code == 200
    assert b"console.log(1)" in response.data
    assert "immutable" in response.headers["Cache-Control"]


def test_unknown_api_paths_stay_404_rather_than_returning_the_shell(client):
    # Falling through to the shell would answer a mistyped endpoint with 200 text/html,
    # which a client cannot tell from a real response.
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert b"shell" not in response.data


def test_a_real_api_route_still_wins_over_the_catch_all(client):
    assert client.get("/api/health").get_json() == {"status": "ok"}


def test_the_socket_path_is_not_swallowed(client):
    assert client.get("/ws").status_code == 404


def test_traversal_does_not_escape_the_dist_directory(client, tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("nope", encoding="utf-8")
    response = client.get("/../secret.txt")
    assert b"nope" not in response.data
