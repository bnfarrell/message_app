"""housekeeping: room, housekeeping_assignment, room_event, housekeeping_photo

Phase 2 §6.5 (docs/superpowers/specs/2026-09-25-housekeeping-design.md). Only adds tables; no
existing table or CHECK constraint changes. The backfill is Python-side so it is portable: no
gen_random_uuid(), no INSERT ... SELECT id tricks.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25

"""
import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

HK_STATUS = ("clean", "dirty", "in_progress", "inspected", "out_of_order", "out_of_service")
SERVICE = ("departure", "stayover", "touch_up")
ASSIGNMENT = ("assigned", "in_progress", "done", "passed")
EVENT = ("status_changed", "assigned", "reassigned", "unassigned", "started", "completed",
         "inspection_passed", "inspection_failed", "marked_dirty", "rush_set", "rush_cleared")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "room",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("hk_status", _enum("ck_enum_hkstatus", *HK_STATUS), nullable=False),
        sa.Column("service_type", _enum("ck_enum_hkservicetype", *SERVICE), nullable=True),
        sa.Column("rush", sa.Boolean(), nullable=False),
        sa.Column("last_cleaned_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("last_inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("status_changed_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("unit_id", name="uq_room_unit"),
    )
    with op.batch_alter_table("room", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_property_id"), ["property_id"], unique=False)
        batch_op.create_index("ix_room_property_status", ["property_id", "hk_status"],
                              unique=False)

    op.create_table(
        "housekeeping_assignment",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("housekeeper_user_id", sa.String(length=36), nullable=False),
        sa.Column("shift_date", sa.Date(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", _enum("ck_enum_hkservicetype", *SERVICE), nullable=False),
        sa.Column("status", _enum("ck_enum_hkassignmentstatus", *ASSIGNMENT), nullable=False),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("completed_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspection_note", sa.Text(), nullable=True),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(["housekeeper_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["inspected_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("housekeeping_assignment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_property_id"),
                              ["property_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_room_id"), ["room_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_assignment_housekeeper_user_id"),
                              ["housekeeper_user_id"], unique=False)
        batch_op.create_index("ix_hk_assignment_property_day_keeper",
                              ["property_id", "shift_date", "housekeeper_user_id"], unique=False)

    op.create_table(
        "room_event",
        sa.Column("room_id", sa.String(length=36), nullable=False),
        sa.Column("assignment_id", sa.String(length=36), nullable=True),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("type", _enum("ck_enum_roomeventtype", *EVENT), nullable=False),
        sa.Column("from_value", sa.String(length=40), nullable=True),
        sa.Column("to_value", sa.String(length=40), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["room_id"], ["room.id"]),
        sa.ForeignKeyConstraint(["assignment_id"], ["housekeeping_assignment.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("room_event", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_room_event_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index("ix_room_event_room_created", ["room_id", "created_at"],
                              unique=False)

    op.create_table(
        "housekeeping_photo",
        sa.Column("assignment_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["assignment_id"], ["housekeeping_assignment.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("housekeeping_photo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_housekeeping_photo_assignment_id"),
                              ["assignment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_housekeeping_photo_property_id"), ["property_id"],
                              unique=False)

    _backfill_rooms()


def _backfill_rooms() -> None:
    """A room per active guest-room unit, starting `inspected` as of now (spec §7): `clean`
    would put every room in the inspection queue, and the before-midnight rule then means a
    mid-shift deploy never floods the board."""
    unit = sa.table("maintainable_unit", sa.column("id", sa.String),
                    sa.column("property_id", sa.String), sa.column("kind", sa.String),
                    sa.column("active", sa.Boolean))
    rows = op.get_bind().execute(
        sa.select(unit.c.id, unit.c.property_id)
        .where(unit.c.kind == "guest_room", unit.c.active.is_(True))).all()
    if not rows:
        return
    room = sa.table("room", sa.column("id", sa.String), sa.column("property_id", sa.String),
                    sa.column("unit_id", sa.String), sa.column("hk_status", sa.String),
                    sa.column("rush", sa.Boolean), sa.column("status_changed_at", sa.DateTime),
                    sa.column("created_at", sa.DateTime), sa.column("updated_at", sa.DateTime))
    now = datetime.now(UTC).replace(tzinfo=None)  # UTCDateTime stores naive UTC
    op.bulk_insert(room, [
        {"id": str(uuid.uuid4()), "property_id": property_id, "unit_id": unit_id,
         "hk_status": "inspected", "rush": False, "status_changed_at": now,
         "created_at": now, "updated_at": now}
        for unit_id, property_id in rows
    ])


def downgrade() -> None:
    # FK-safe order: children before parents. The backfill wrote only into these tables, so
    # dropping them is a true reversal.
    for table in ("housekeeping_photo", "room_event", "housekeeping_assignment", "room"):
        op.drop_table(table)
