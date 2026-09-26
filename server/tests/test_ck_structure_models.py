"""Checklist structure schema (checklist structure spec §2.1, §6)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import ChecklistTemplate, ChecklistTemplateCategory, ChecklistTemplateItem
from app.schemas.enums import ChecklistKind, ChecklistSchedule, PmItemType, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx, **kw):
    t = ChecklistTemplate(property_id=fx.property_a.id, name="Night Audit",
                          department_id=fx.dept_front_desk.id, **kw)
    db.add(t)
    db.flush()
    return t


def test_unscheduled_has_neither_shift_nor_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=Shift.am, weekdays=None)
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=None, weekdays=127)
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=None, weekdays=None)
        assert t.kind == ChecklistKind.normal  # the default


def test_an_item_can_sit_in_a_category(database, fx):
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.on_demand, kind=ChecklistKind.readings)
        c = ChecklistTemplateCategory(template_id=t.id, property_id=t.property_id,
                                      name="Payments", position=0)
        db.add(c)
        db.flush()
        db.add(ChecklistTemplateItem(template_id=t.id, property_id=t.property_id, position=0,
                                     label="Batch closed", item_type=PmItemType.checkbox,
                                     category_id=c.id))
        db.flush()
        tid, cid = t.id, c.id
    with database.session() as db:
        item = db.scalar(sa.select(ChecklistTemplateItem)
                         .where(ChecklistTemplateItem.template_id == tid))
        assert (item.category_id, db.get(ChecklistTemplate, tid).kind) == (
            cid, ChecklistKind.readings)
        assert db.get(ChecklistTemplateCategory, cid).active is True


def _cfg(url):
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_0010_rows(engine):
    """A property, a department and a weekly template with one item, as production has."""
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at)"
            " VALUES ('p1','P','PPP','UTC','USD','{}','2026-09-10','2026-09-10')",
            "INSERT INTO department (id,property_id,name,type,escalation_minutes,active,"
            "created_at,updated_at) VALUES ('d1','p1','Front Desk','front_desk',15,1,"
            "'2026-09-10','2026-09-10')",
            "INSERT INTO checklist_template (id,property_id,name,department_id,schedule,shift,"
            "weekdays,active,created_at,updated_at) VALUES ('t1','p1','Night Audit','d1',"
            "'weekly','overnight',127,1,'2026-09-10','2026-09-10')",
            "INSERT INTO checklist_template_item (id,template_id,property_id,position,label,"
            "item_type,required,active,created_at,updated_at) VALUES ('i1','t1','p1',0,"
            "'Audit run','checkbox',1,1,'2026-09-10','2026-09-10')",
        ):
            conn.execute(sa.text(sql))


def test_0011_migrates_existing_templates_and_downgrades_cleanly(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT kind FROM checklist_template")).scalar() == "normal"
        assert conn.execute(sa.text(
            "SELECT category_id FROM checklist_template_item")).scalar() is None
    command.downgrade(cfg, "0010")
    inspector = sa.inspect(engine)
    assert "checklist_template_category" not in inspector.get_table_names()
    assert "kind" not in {c["name"] for c in inspector.get_columns("checklist_template")}
    assert "category_id" not in {c["name"]
                                 for c in inspector.get_columns("checklist_template_item")}
    with pytest.raises(IntegrityError), engine.begin() as conn:  # the 0009 CHECK is back
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT name FROM checklist_template")).scalar() == (
            "Night Audit")
        assert conn.execute(sa.text("SELECT count(*) FROM checklist_template_item")).scalar() == 1
    engine.dispose()


def test_0011_upgraded_checks_accept_unscheduled_and_refuse_a_bad_kind(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_cfg(url), "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(_cfg(url), "head")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET shift = 'am'"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET kind = 'bogus'"))
    engine.dispose()


def test_0011_downgrade_refuses_while_a_template_is_unscheduled(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    with pytest.raises(RuntimeError, match="unscheduled"):
        command.downgrade(cfg, "0010")
    inspector = sa.inspect(engine)  # nothing was dropped
    assert "checklist_template_category" in inspector.get_table_names()
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == (
            "0011")
    engine.dispose()
