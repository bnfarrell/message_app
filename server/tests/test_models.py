from datetime import UTC, datetime
from enum import StrEnum

import pytest
from sqlalchemy import Column, MetaData, String, Table, inspect, select, text
from sqlalchemy.exc import StatementError

from app import clock
from app.db import Database, run_migrations
from app.models import Conversation, Guest, Property
from app.models.core import enum_type
from app.schemas.enums import ConversationStatus, SmsConsentStatus

EXPECTED_TABLES = {
    "property", "user_account", "property_membership", "department", "guest", "stay",
    "conversation", "message", "internal_note", "resolution_category", "work_order",
    "work_order_event", "work_order_photo", "draft_prompt", "quick_reply", "digital_asset",
    "user_session",
    "job", "notification", "audit_log", "pms_event", "alembic_version",
    "staff_conversation", "staff_conversation_participant", "staff_message",
    "log_entry", "log_entry_mention", "log_entry_photo", "log_entry_ack",
    "maintainable_unit", "pm_template", "pm_template_item", "pm_template_unit",
    "pm_cycle", "pm_run", "pm_run_answer", "pm_run_photo",
    "room", "housekeeping_assignment", "room_event", "housekeeping_photo",
    "checklist_template", "checklist_template_item", "checklist_instance", "checklist_answer",
    "checklist_photo",
    "log_template", "log_template_field", "log_template_audience", "log_entry_field_value",
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


def test_enum_stores_value_not_name(db_url):
    """Every app enum member has name == value, which can't distinguish value-storage
    from name-storage. Use a throwaway enum/table where they differ to prove it."""
    run_migrations(db_url)
    database = Database(db_url)

    class _T(StrEnum):
        a_b = "a-b"

    metadata = MetaData()
    table = Table(
        "_test_enum_value",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("val", enum_type(_T), nullable=False),
    )
    metadata.create_all(database.engine)
    with database.engine.begin() as conn:
        conn.execute(table.insert().values(id="1", val=_T.a_b))
    with database.engine.connect() as conn:
        raw = conn.execute(text("SELECT val FROM _test_enum_value")).scalar()
    assert raw == "a-b"
    database.engine.dispose()


def test_utc_datetime_rejects_naive(db_url):
    run_migrations(db_url)
    database = Database(db_url)
    with pytest.raises(StatementError):
        with database.session() as db:
            p = Property(
                name="Test", code="TST", timezone="UTC", created_at=datetime(2026, 1, 1)
            )
            db.add(p)
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
        assert loaded.created_at.tzinfo == UTC
    database.engine.dispose()


def test_staff_conversation_round_trip(database, fx):
    from app.models import StaffConversation, StaffConversationParticipant, StaffMessage
    from app.schemas.enums import StaffConversationKind

    with database.session() as db:
        conv = StaffConversation(property_id=fx.property_a.id, kind=StaffConversationKind.dm)
        db.add(conv)
        db.flush()
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=fx.agent_a.id))
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=fx.engineer_a.id))
        db.add(StaffMessage(conversation_id=conv.id, property_id=fx.property_a.id,
                            author_user_id=fx.agent_a.id, body="hi"))
        conv_id = conv.id

    with database.session() as db:
        loaded = db.get(StaffConversation, conv_id)
        assert loaded.kind == StaffConversationKind.dm


def test_log_entry_round_trips_with_mentions_photo_and_ack(database, fx):
    from app.models import LogEntry, LogEntryAck, LogEntryMention, LogEntryPhoto
    from app.schemas.enums import MentionTargetType, Shift

    with database.session() as db:
        entry = LogEntry(
            property_id=fx.property_a.id,
            author_user_id=fx.agent_a.id,
            department_id=fx.dept_housekeeping.id,
            shift=Shift.am,
            body="327 fridge does not work but room is clean.",
            requires_ack=True,
            ack_expected=[fx.housekeeper_a.id],
        )
        db.add(entry)
        db.flush()
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=fx.property_a.id,
                               type=MentionTargetType.department,
                               target_id=fx.dept_housekeeping.id, position=0))
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=fx.property_a.id,
                               type=MentionTargetType.user,
                               target_id=fx.engineer_a.id, position=1))
        db.add(LogEntryPhoto(log_entry_id=entry.id, property_id=fx.property_a.id,
                             uploaded_by_user_id=fx.agent_a.id,
                             content_type="image/png", byte_size=3, data=b"abc"))
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        db.flush()
        entry_id = entry.id

    with database.session() as db:
        row = db.get(LogEntry, entry_id)
        assert row.shift == Shift.am
        assert row.pinned is False
        assert row.ack_expected == [fx.housekeeper_a.id]
        mentions = db.scalars(
            select(LogEntryMention)
            .where(LogEntryMention.log_entry_id == entry_id)
            .order_by(LogEntryMention.position)
        ).all()
        assert [m.type for m in mentions] == [MentionTargetType.department, MentionTargetType.user]
        photo = db.scalar(select(LogEntryPhoto)
                          .where(LogEntryPhoto.log_entry_id == entry_id))
        assert photo.data == b"abc"


def test_log_entry_ack_is_unique_per_user(database, fx):
    from sqlalchemy.exc import IntegrityError

    from app.models import LogEntry, LogEntryAck
    from app.schemas.enums import Shift

    with database.session() as db:
        entry = LogEntry(property_id=fx.property_a.id, author_user_id=fx.agent_a.id,
                         shift=Shift.pm, body="x")
        db.add(entry)
        db.flush()
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        db.flush()
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        with pytest.raises(IntegrityError):
            db.flush()
        # The failed flush poisons the session; without this rollback the context
        # manager's commit on exit raises PendingRollbackError and the test fails
        # for a reason that has nothing to do with the constraint being tested.
        db.rollback()
