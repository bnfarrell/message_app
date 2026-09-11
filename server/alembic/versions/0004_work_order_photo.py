"""work-order photos, stored as bytes in the database

The deployment target's filesystem is ephemeral, so a disk-backed photo would disappear on the
next redeploy and leave the work order referencing an image that no longer exists. A BLOB/BYTEA
column survives wherever DATABASE_URL points and needs no new infrastructure.

`work_order_event.type` also gains `photo_attached`: attaching a photo is a timeline event
(docs/mockups/WorkOrder.dc.html:111). The column is a VARCHAR with a named CHECK constraint on
both dialects (Enum(native_enum=False)), so the constraint is dropped and recreated with the new
value; batch_alter_table makes that a table rebuild on SQLite and a plain ALTER on PostgreSQL.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

EVENT_TYPE_CHECK = "ck_enum_workordereventtype"
OLD_EVENT_TYPES = ("created", "status_changed", "assigned", "commented", "priority_changed")
NEW_EVENT_TYPES = (*OLD_EVENT_TYPES, "photo_attached")


def _set_event_types(values: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{v}'" for v in values)
    with op.batch_alter_table("work_order_event", schema=None) as batch_op:
        batch_op.drop_constraint(EVENT_TYPE_CHECK, type_="check")
        batch_op.create_check_constraint(EVENT_TYPE_CHECK, f"type IN ({listed})")


def upgrade() -> None:
    op.create_table(
        "work_order_photo",
        sa.Column("work_order_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "before",
                "after",
                name="ck_enum_workorderphotokind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("work_order_photo", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_work_order_photo_property_id"), ["property_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_work_order_photo_work_order_id"), ["work_order_id"], unique=False
        )
    _set_event_types(NEW_EVENT_TYPES)


def downgrade() -> None:
    op.execute(f"DELETE FROM work_order_event WHERE type = '{NEW_EVENT_TYPES[-1]}'")
    _set_event_types(OLD_EVENT_TYPES)
    with op.batch_alter_table("work_order_photo", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_order_photo_work_order_id"))
        batch_op.drop_index(batch_op.f("ix_work_order_photo_property_id"))
    op.drop_table("work_order_photo")
