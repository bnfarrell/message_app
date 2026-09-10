from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import StatementError

from app.db import Database, run_migrations
from app.models import Conversation, Guest, Property
from app.schemas.enums import ConversationStatus, SmsConsentStatus

EXPECTED_TABLES = {
    "property", "user_account", "property_membership", "department", "guest", "stay",
    "conversation", "message", "internal_note", "resolution_category", "work_order",
    "work_order_event", "draft_prompt", "quick_reply", "digital_asset", "user_session",
    "job", "notification", "audit_log", "pms_event", "alembic_version",
}


@pytest.fixture()
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 't.db').as_posix()}"


def test_migration_creates_all_tables(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    names = set(inspect(database.engine).get_table_names())
    assert EXPECTED_TABLES <= names, EXPECTED_TABLES - names
    database.engine.dispose()


def test_sqlite_pragmas_applied(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
    database.engine.dispose()


def test_enum_values_are_stored_as_values_and_validated(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.session() as db:
        p = Property(name="Test", code="TST", timezone="UTC")
        db.add(p)
        db.flush()
        g = Guest(property_id=p.id, phone_e164="+15550001111", first_name="A", last_name="B",
                  sms_consent_status=SmsConsentStatus.opted_in)
        db.add(g)
        db.flush()
        c = Conversation(property_id=p.id, guest_id=g.id, status=ConversationStatus.open)
        db.add(c)
    with database.engine.connect() as conn:
        raw = conn.execute(text("SELECT status FROM conversation")).scalar()
        assert raw == "open"
    with pytest.raises(StatementError):
        with database.session() as db:
            db.add(Conversation(property_id=p.id, guest_id=g.id, status="bogus"))
            db.flush()
    database.engine.dispose()


def test_utc_datetime_round_trips_aware(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with database.session() as db:
        p = Property(name="Test", code="TST", timezone="UTC")
        db.add(p)
    with database.session() as db:
        loaded = db.get(Property, p.id)
        assert loaded.created_at.tzinfo is not None
        assert loaded.created_at.utcoffset().total_seconds() == 0
        assert isinstance(loaded.created_at, datetime)
        assert loaded.created_at.tzinfo == timezone.utc
    database.engine.dispose()
