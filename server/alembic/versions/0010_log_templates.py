"""log_templates: log_template, log_template_field, log_template_audience,
log_entry_field_value, and log_entry.template_id

Log templates spec §2, §6 (docs/superpowers/specs/2026-09-26-log-templates-design.md). Adds four
tables and one nullable column on log_entry — the only change to an existing table. No backfill:
every existing entry is a free-form post and keeps template_id NULL.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26

"""
import sqlalchemy as sa

import app.db
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SHIFT = ("am", "pm", "overnight")
FIELD_TYPE = ("short_text", "long_text", "integer", "decimal", "percent")
TARGET_TYPE = ("user", "department")

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
        "log_template",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("shift", _enum("ck_enum_shift", *SHIFT), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "log_template_field",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("field_type", _enum("ck_enum_logfieldtype", *FIELD_TYPE), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["log_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template_field", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_field_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_log_template_field_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "log_template_audience",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("type", _enum("ck_enum_mentiontargettype", *TARGET_TYPE), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("template_id", "type", "target_id",
                            name="uq_log_template_audience_target"),
        sa.ForeignKeyConstraint(["template_id"], ["log_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template_audience", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_audience_template_id"),
                              ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_log_template_audience_property_id"),
                              ["property_id"], unique=False)

    op.create_table(
        "log_entry_field_value",
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("field_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("field_type", _enum("ck_enum_logfieldtype", *FIELD_TYPE), nullable=False),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", READING, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("log_entry_id", "field_id", name="uq_log_field_value_entry_field"),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["field_id"], ["log_template_field.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_entry_field_value", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_entry_field_value_log_entry_id"),
                              ["log_entry_id"], unique=False)
        batch_op.create_index("ix_log_field_value_property_field", ["property_id", "field_id"],
                              unique=False)

    # The one change to an existing table. Nullable with no default, so no backfill; the FK is
    # named so downgrade() can drop it by name on both engines (as 0003 does for pms_event).
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key("fk_log_entry_template_id", "log_template",
                                    ["template_id"], ["id"])


def downgrade() -> None:
    # The column first (its FK points at log_template), then the four tables children-first.
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.drop_constraint("fk_log_entry_template_id", type_="foreignkey")
        batch_op.drop_column("template_id")
    for table in ("log_entry_field_value", "log_template_audience", "log_template_field",
                  "log_template"):
        op.drop_table(table)
