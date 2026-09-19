"""internal staff messaging: staff_conversation, staff_conversation_participant, staff_message

Net-new subsystem (docs/superpowers/specs/2026-09-19-staff-messaging-design.md), deliberately
separate from the guest conversation/message tables — see the design doc §1 for why.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_conversation",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("dm", "group", "all", name="ck_enum_staffconversationkind",
                    native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("last_message_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("staff_conversation", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_property_id"), ["property_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_last_message_at"), ["last_message_at"], unique=False
        )

    op.create_table(
        "staff_conversation_participant",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("last_read_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["staff_conversation.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_staff_participant_conv_user"),
    )
    with op.batch_alter_table("staff_conversation_participant", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_participant_conversation_id"),
            ["conversation_id"], unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_staff_participant_user"), ["user_id"], unique=False
        )

    op.create_table(
        "staff_message",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("photo_content_type", sa.String(length=40), nullable=True),
        sa.Column("photo_byte_size", sa.Integer(), nullable=True),
        sa.Column("photo_data", sa.LargeBinary(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["staff_conversation.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("staff_message", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_message_conversation_id"), ["conversation_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_staff_message_property_id"), ["property_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("staff_message")
    with op.batch_alter_table("staff_conversation_participant", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_staff_participant_user"))
        batch_op.drop_index(batch_op.f("ix_staff_conversation_participant_conversation_id"))
    op.drop_table("staff_conversation_participant")
    with op.batch_alter_table("staff_conversation", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_staff_conversation_last_message_at"))
        batch_op.drop_index(batch_op.f("ix_staff_conversation_property_id"))
    op.drop_table("staff_conversation")
