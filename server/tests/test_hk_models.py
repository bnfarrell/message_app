"""Housekeeping schema (spec §2, §7)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError, StatementError

from alembic import command
from app.models import MaintainableUnit, Room
from app.schemas.enums import HkStatus, PmUnitKind

SERVER = Path(__file__).resolve().parent.parent
T = "2026-09-10 12:00:00"


def _alembic(url: str) -> AlembicConfig:
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _room_count(engine) -> int:
    with engine.connect() as c:
        return c.execute(sa.text("SELECT COUNT(*) FROM room")).scalar()


def test_0008_backfills_active_guest_rooms_and_downgrades_cleanly(tmp_path):
    """An empty database would hide a backfill bug (spec §7), so units exist before 0008."""
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _alembic(url)
    command.upgrade(cfg, "0007")
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO property (id, name, code, timezone, currency, settings, created_at, "
            "updated_at) VALUES ('p1', 'P', 'PPP', 'UTC', 'USD', '{}', :t, :t)"), {"t": T})
        for i, (kind, active) in enumerate([("guest_room", True), ("guest_room", True),
                                            ("guest_room", False), ("equipment", True)]):
            c.execute(sa.text(
                "INSERT INTO maintainable_unit (id, property_id, kind, code, name, active, "
                "source, created_at, updated_at) VALUES (:id, 'p1', :kind, :code, :code, "
                ":active, 'manual', :t, :t)"),
                {"id": f"u{i}", "kind": kind, "code": f"C{i}", "active": active, "t": T})

    command.upgrade(cfg, "head")
    assert _room_count(engine) == 2
    with engine.connect() as c:
        rows = c.execute(sa.text("SELECT unit_id, hk_status, rush FROM room")).all()
    assert {r.unit_id for r in rows} == {"u0", "u1"}
    assert {r.hk_status for r in rows} == {"inspected"}  # never `clean` (spec §7)
    assert not any(r.rush for r in rows)

    command.downgrade(cfg, "0007")
    assert "room" not in sa.inspect(engine).get_table_names()
    command.upgrade(cfg, "head")
    assert _room_count(engine) == 2
    engine.dispose()


def test_room_unit_id_is_unique(database, fx):
    from app.domain import hk_rooms  # arrives in Task 3; imported here so collection works now
    with pytest.raises(IntegrityError), database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="204", name="Room 204", floor=2)
        db.add(unit)
        db.flush()
        hk_rooms.ensure_rooms(db, fx.property_a.id)
        db.add(Room(property_id=fx.property_a.id, unit_id=unit.id))
        db.flush()


def test_hk_status_round_trips_and_rejects_unknown_values(database, fx):
    from app.domain import hk_rooms  # arrives in Task 3
    with database.session() as db:
        unit = MaintainableUnit(property_id=fx.property_a.id, kind=PmUnitKind.guest_room,
                                code="205", name="Room 205", floor=2)
        db.add(unit)
        db.flush()
        (room,) = hk_rooms.ensure_rooms(db, fx.property_a.id)
        room.hk_status = HkStatus.out_of_service
        db.flush()
        db.expire(room)
        assert room.hk_status is HkStatus.out_of_service
    with pytest.raises(StatementError), database.session() as db:
        db.execute(sa.update(Room).values(hk_status="sparkling"))
