"""A managed provider's Postgres URL must reach the driver this project actually ships."""
import pytest

from app.config import Config, normalise_database_url


@pytest.mark.parametrize("raw", [
    # What Railway, Heroku and Fly hand out. SQLAlchemy resolves both to psycopg2, which is
    # not a dependency here, so pasting one verbatim used to fail at the first connection
    # with a ModuleNotFoundError that names neither the URL nor the driver.
    "postgresql://user:pw@host:5432/railway",
    "postgres://user:pw@host:5432/railway",
])
def test_bare_postgres_urls_are_pointed_at_psycopg3(raw):
    assert normalise_database_url(raw).startswith("postgresql+psycopg://")


def test_the_rest_of_the_url_survives_untouched():
    got = normalise_database_url("postgresql://u:p%40ss@some.host:5432/db?sslmode=require")
    assert got == "postgresql+psycopg://u:p%40ss@some.host:5432/db?sslmode=require"


def test_an_explicit_driver_is_left_alone():
    # Choosing psycopg2 on purpose must keep working.
    for url in ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg://u:p@h/db"):
        assert normalise_database_url(url) == url


def test_sqlite_is_untouched():
    assert normalise_database_url("sqlite:///data/app.db") == "sqlite:///data/app.db"


def test_from_env_normalises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    assert Config.from_env().DATABASE_URL == "postgresql+psycopg://u:p@h:5432/db"


def test_the_default_is_still_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert Config.from_env().DATABASE_URL.startswith("sqlite:")
