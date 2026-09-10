from __future__ import annotations

import shutil
from datetime import datetime, timezone

import email_validator
import pytest

from app import clock, create_app
from app.config import Config
from app.db import run_migrations
from tests.fixtures import PASSWORD, load_fixture

# Fixture data uses RFC 2606 reserved test domains (e.g. "hvh.test"), which
# email-validator otherwise rejects as "special-use". Test process only.
email_validator.TEST_ENVIRONMENT = True

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
    from app.ratelimit import login_limiter, webhook_limiter

    login_limiter.reset()
    webhook_limiter.reset()

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
def events(app):
    from app.realtime import broadcast

    captured = []
    fn = captured.append  # keep one reference: a fresh bound method would not compare equal on removal
    broadcast.add_listener(fn)
    yield captured
    broadcast.remove_listener(fn)


@pytest.fixture()
def login(app):
    def _login(email: str, password: str = PASSWORD):
        c = app.test_client()
        res = c.post("/api/auth/login", json={"email": email, "password": password})
        assert res.status_code == 200, res.get_json()
        return c

    return _login
