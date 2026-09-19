"""hotel log: log_entry, log_entry_mention, log_entry_photo, log_entry_ack

Phase 2 §6.8 (docs/superpowers/specs/2026-09-19-hotel-log-design.md).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "log_entry",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column(
            "shift",
            sa.Enum("am", "pm", "overnight", name="ck_enum_shift",
                    native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("pinned_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("pinned_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("requires_ack", sa.Boolean(), nullable=False),
        sa.Column("ack_expected", sa.JSON(), nullable=False),
        sa.Column("linked_work_order_id", sa.String(length=36), nullable=True),
        sa.Column("linked_conversation_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["pinned_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["linked_work_order_id"], ["work_order.id"]),
        sa.ForeignKeyConstraint(["linked_conversation_id"], ["conversation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_log_entry_property_id"), ["property_id"], unique=False
        )
        batch_op.create_index(
            "ix_log_entry_property_created", ["property_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_log_entry_property_pinned", ["property_id", "pinned"], unique=False
        )

    op.create_table(
        "log_entry_mention",
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column(
            "type",
            sa.Enum("user", "department", name="ck_enum_mentiontargettype",
                    native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_entry_id", "type", "target_id",
                            name="uq_log_mention_entry_target"),
    )
    with op.batch_alter_table("log_entry_mention", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_log_entry_mention_log_entry_id"), ["log_entry_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_log_entry_mention_property_id"), ["property_id"], unique=False
        )
        batch_op.create_index(
            "ix_log_mention_property_target", ["property_id", "type", "target_id"], unique=False
        )

    op.create_table(
        "log_entry_photo",
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_entry_photo", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_log_entry_photo_log_entry_id"), ["log_entry_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_log_entry_photo_property_id"), ["property_id"], unique=False
        )

    op.create_table(
        "log_entry_ack",
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("acknowledged_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_entry_id", "user_id", name="uq_log_ack_entry_user"),
    )
    with op.batch_alter_table("log_entry_ack", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_log_entry_ack_log_entry_id"), ["log_entry_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_log_entry_ack_property_id"), ["property_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("log_entry_ack", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_log_entry_ack_property_id"))
        batch_op.drop_index(batch_op.f("ix_log_entry_ack_log_entry_id"))

    op.drop_table("log_entry_ack")
    with op.batch_alter_table("log_entry_photo", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_log_entry_photo_property_id"))
        batch_op.drop_index(batch_op.f("ix_log_entry_photo_log_entry_id"))

    op.drop_table("log_entry_photo")
    with op.batch_alter_table("log_entry_mention", schema=None) as batch_op:
        batch_op.drop_index("ix_log_mention_property_target")
        batch_op.drop_index(batch_op.f("ix_log_entry_mention_property_id"))
        batch_op.drop_index(batch_op.f("ix_log_entry_mention_log_entry_id"))

    op.drop_table("log_entry_mention")
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.drop_index("ix_log_entry_property_pinned")
        batch_op.drop_index("ix_log_entry_property_created")
        batch_op.drop_index(batch_op.f("ix_log_entry_property_id"))

    op.drop_table("log_entry")
