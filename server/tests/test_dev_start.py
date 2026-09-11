"""Covers the one-click launcher's logic (server/dev_start.py), not the blocking app.run() call."""
from sqlalchemy import func, select

import dev_start
from app.db import Database
from app.models import Property


def test_ensure_data_dir_creates_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_start, "SERVER_DIR", tmp_path)
    assert not (tmp_path / "data").exists()
    dev_start.ensure_data_dir()
    assert (tmp_path / "data").is_dir()


def test_resolve_database_url_anchors_relative_sqlite_path_at_server_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_start, "SERVER_DIR", tmp_path)
    resolved = dev_start.resolve_database_url("sqlite:///data/app.db")
    assert resolved == f"sqlite:///{(tmp_path / 'data' / 'app.db').resolve().as_posix()}"


def test_resolve_database_url_leaves_absolute_and_non_sqlite_urls_alone(tmp_path):
    abs_url = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    assert dev_start.resolve_database_url(abs_url) == abs_url
    pg_url = "postgresql+psycopg://user:pw@host/db"
    assert dev_start.resolve_database_url(pg_url) == pg_url


def test_resolve_database_url_ignores_process_cwd(tmp_path, monkeypatch):
    # This is the whole point of the function: the reloader can respawn this launcher with a
    # different cwd than it started with, and the resolved sqlite path must not move with it.
    monkeypatch.setattr(dev_start, "SERVER_DIR", tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    resolved = dev_start.resolve_database_url("sqlite:///data/app.db")
    assert resolved == f"sqlite:///{(tmp_path / 'data' / 'app.db').resolve().as_posix()}"


def test_is_db_empty_before_and_after_migration_and_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_start, "SERVER_DIR", tmp_path)
    url = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    # no file yet: Database() creates it lazily, table absent -> empty
    assert dev_start.is_db_empty(url)
    seeded, summary = dev_start.prepare(url)
    assert seeded is True
    assert summary.properties > 0
    assert not dev_start.is_db_empty(url)


def test_prepare_is_idempotent_and_never_reseeds_over_existing_data(tmp_path, monkeypatch):
    # This is the launcher's core safety property: running it twice (e.g. double-clicking
    # start.bat again) must not duplicate seeded rows.
    monkeypatch.setattr(dev_start, "SERVER_DIR", tmp_path)
    url = f"sqlite:///{(tmp_path / 'app.db').as_posix()}"
    first_seeded, first_summary = dev_start.prepare(url)
    second_seeded, second_summary = dev_start.prepare(url)

    assert first_seeded is True
    assert second_seeded is False
    assert second_summary is None

    db = Database(url)
    with db.session() as session:
        count = session.scalar(select(func.count()).select_from(Property))
    db.engine.dispose()
    assert count == first_summary.properties


def test_port_is_taken_detects_a_listening_socket_and_a_free_port():
    # The guard this backs exists because werkzeug sets SO_REUSEADDR: on Windows a second dev
    # server binds an already-listening port silently, and the two processes then have separate
    # realtime connection registries, so WebSocket events are dropped with no error.
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert dev_start.port_is_taken(port) is True
    assert dev_start.port_is_taken(port) is False
