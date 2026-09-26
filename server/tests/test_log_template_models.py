"""Log template schema (log templates spec §2, §6)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import (
    LogEntry,
    LogEntryFieldValue,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
)
from app.schemas.enums import LogFieldType, MentionTargetType, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx):
    t = LogTemplate(property_id=fx.property_a.id, name="Night Audit", shift=Shift.overnight,
                    position=0, created_by_user_id=fx.admin_a.id)
    db.add(t)
    db.flush()
    f = LogTemplateField(template_id=t.id, property_id=t.property_id, position=0,
                         label="Occupancy", field_type=LogFieldType.percent)
    db.add(f)
    db.flush()
    return t, f


def test_a_templated_entry_links_its_template_and_stores_a_value(database, fx):
    with database.session() as db:
        t, f = _template(db, fx)
        e = LogEntry(property_id=t.property_id, author_user_id=fx.agent_a.id, shift=Shift.am,
                     body="Occupancy: 87%", template_id=t.id)
        db.add(e)
        db.flush()
        db.add(LogEntryFieldValue(log_entry_id=e.id, property_id=t.property_id, field_id=f.id,
                                  position=0, label=f.label, field_type=f.field_type,
                                  number_value=87.5))
        db.flush()
        eid = e.id
    with database.session() as db:
        row = db.scalar(sa.select(LogEntryFieldValue).where(LogEntryFieldValue.log_entry_id == eid))
        assert (row.label, row.field_type, row.number_value) == ("Occupancy",
                                                                 LogFieldType.percent, 87.5)
        assert db.get(LogEntry, eid).template_id is not None


def test_one_value_per_field_per_entry(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        t, f = _template(db, fx)
        e = LogEntry(property_id=t.property_id, author_user_id=fx.agent_a.id, shift=Shift.am,
                     body="x", template_id=t.id)
        db.add(e)
        db.flush()
        for _ in range(2):
            db.add(LogEntryFieldValue(log_entry_id=e.id, property_id=t.property_id,
                                      field_id=f.id, position=0, label="Occupancy",
                                      field_type=LogFieldType.percent, number_value=1))
        db.flush()


def test_an_audience_target_is_listed_once(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        t, _ = _template(db, fx)
        for _ in range(2):
            db.add(LogTemplateAudience(template_id=t.id, property_id=t.property_id,
                                       type=MentionTargetType.department,
                                       target_id=fx.dept_front_desk.id))
        db.flush()


def test_0010_downgrades_and_reupgrades_keeping_log_entries(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0009")
    engine = sa.create_engine(url)
    with engine.begin() as conn:  # a pre-existing entry with a child row, as production has
        conn.execute(sa.text(
            "INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at)"
            " VALUES ('p1','P','PPP','UTC','USD','{}','2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO user_account (id,email,first_name,last_name,locale,status,"
            "notification_prefs,created_at,updated_at) VALUES ('u1','u@x.test','U','One','en',"
            "'active','{}','2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO log_entry (id,property_id,author_user_id,shift,body,pinned,requires_ack,"
            "ack_expected,created_at,updated_at) VALUES ('e1','p1','u1','am','Hello',0,0,'[]',"
            "'2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO log_entry_ack (id,log_entry_id,property_id,user_id,acknowledged_at,"
            "created_at,updated_at) VALUES ('a1','e1','p1','u1','2026-09-10','2026-09-10',"
            "'2026-09-10')"))
    command.upgrade(cfg, "head")
    cols = {c["name"] for c in sa.inspect(engine).get_columns("log_entry")}
    assert "template_id" in cols
    assert "log_entry_field_value" in sa.inspect(engine).get_table_names()
    command.downgrade(cfg, "0009")
    inspector = sa.inspect(engine)
    assert "template_id" not in {c["name"] for c in inspector.get_columns("log_entry")}
    assert "log_template" not in inspector.get_table_names()
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT body FROM log_entry")).scalar() == "Hello"
        assert conn.execute(sa.text("SELECT count(*) FROM log_entry_ack")).scalar() == 1
    engine.dispose()
