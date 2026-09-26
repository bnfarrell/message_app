"""shift_checklists: checklist_template, checklist_template_item, checklist_instance,
checklist_answer, checklist_photo

Shift checklists spec §2, §6 (docs/superpowers/specs/2026-09-25-shift-checklists-design.md). Only
adds tables; no existing table or CHECK constraint changes. No backfill.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-25

"""
import sqlalchemy as sa

import app.db
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

SCHEDULE = ("weekly", "on_demand")
SHIFT = ("am", "pm", "overnight")
ITEM_TYPE = ("checkbox", "text", "number", "photo")
STATUS = ("open", "in_progress", "complete", "missed")

READING = sa.Numeric(10, 2, asdecimal=False)


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
        "checklist_template",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=False),
        sa.Column("schedule", _enum("ck_enum_checklistschedule", *SCHEDULE), nullable=False),
        sa.Column("shift", _enum("ck_enum_shift", *SHIFT), nullable=True),
        sa.Column("weekdays", sa.Integer(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
            "AND weekdays > 0) OR "
            "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)",
            name="ck_checklist_template_schedule_fields",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_template_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "checklist_template_item",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("item_type", _enum("ck_enum_pmitemtype", *ITEM_TYPE), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("min_value", READING, nullable=True),
        sa.Column("max_value", READING, nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_template_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_template_item_template_id"),
                              ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_checklist_template_item_property_id"),
                              ["property_id"], unique=False)

    op.create_table(
        "checklist_instance",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("shift", _enum("ck_enum_shift", *SHIFT), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=True),
        sa.Column("status", _enum("ck_enum_checkliststatus", *STATUS), nullable=False),
        sa.Column("assigned_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("completed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("completed_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("template_id", "due_date", "shift", "slot",
                            name="uq_checklist_instance_slot"),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_template.id"]),
        sa.ForeignKeyConstraint(["assigned_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["completed_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_instance", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_instance_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index("ix_checklist_instance_property_due", ["property_id", "due_date"],
                              unique=False)
        batch_op.create_index("ix_checklist_instance_property_status",
                              ["property_id", "status"], unique=False)

    op.create_table(
        "checklist_answer",
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", READING, nullable=True),
        sa.Column("out_of_range", sa.Boolean(), nullable=False),
        sa.Column("answered_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("instance_id", "item_id", name="uq_checklist_answer_instance_item"),
        sa.ForeignKeyConstraint(["instance_id"], ["checklist_instance.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["checklist_template_item.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_answer", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_answer_instance_id"), ["instance_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_checklist_answer_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "checklist_photo",
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["instance_id"], ["checklist_instance.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["checklist_template_item.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_photo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_photo_instance_id"), ["instance_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_checklist_photo_property_id"), ["property_id"],
                              unique=False)


def downgrade() -> None:
    # FK-safe order: children before parents. No backfill was written, so dropping the five
    # tables is a true reversal.
    for table in ("checklist_photo", "checklist_answer", "checklist_instance",
                  "checklist_template_item", "checklist_template"):
        op.drop_table(table)
