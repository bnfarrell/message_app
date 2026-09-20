"""preventative maintenance: maintainable_unit, pm_template, pm_template_item, pm_template_unit,
pm_cycle, pm_run, pm_run_answer, pm_run_photo

Phase 2 §6.6 (docs/superpowers/specs/2026-09-19-preventative-maintenance-design.md).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-19

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


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
        "maintainable_unit",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("kind", _enum("ck_enum_pmunitkind", "guest_room", "common_area", "equipment"),
                  nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("room_type", sa.String(length=20), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source", _enum("ck_enum_pmunitsource", "manual", "csv", "pms"),
                  nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "code", name="uq_maintainable_unit_property_code"),
    )
    with op.batch_alter_table("maintainable_unit", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_maintainable_unit_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index("ix_maintainable_unit_property_kind", ["property_id", "kind"],
                              unique=False)

    op.create_table(
        "pm_template",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("mode", _enum("ck_enum_pmtemplatemode", "sweep", "scheduled"), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("unit_kind",
                  _enum("ck_enum_pmunitkind", "guest_room", "common_area", "equipment"),
                  nullable=True),
        sa.Column("cadence",
                  _enum("ck_enum_pmcadence", "monthly", "quarterly", "semiannual", "annual"),
                  nullable=True),
        sa.Column("rrule", sa.String(length=500), nullable=True),
        sa.Column("rrule_dtstart", sa.Date(), nullable=True),
        sa.Column("last_fired_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(mode = 'sweep' AND unit_kind IS NOT NULL AND cadence IS NOT NULL "
            "AND rrule IS NULL) OR "
            "(mode = 'scheduled' AND rrule IS NOT NULL AND rrule_dtstart IS NOT NULL "
            "AND cadence IS NULL)",
            name="ck_pm_template_mode_fields",
        ),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_template_item",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("item_type", _enum("ck_enum_pmitemtype", "checkbox", "text", "number", "photo"),
                  nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("min_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("max_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_template_item", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_item_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_item_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_template_unit",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "unit_id", name="uq_pm_template_unit"),
    )
    with op.batch_alter_table("pm_template_unit", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_template_unit_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_unit_unit_id"), ["unit_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_template_unit_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_cycle",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("status", _enum("ck_enum_pmcyclestatus", "open", "closed"), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_id", "starts_on", name="uq_pm_cycle_template_start"),
    )
    with op.batch_alter_table("pm_cycle", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_cycle_property_id"), ["property_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_pm_cycle_template_id"), ["template_id"],
                              unique=False)

    op.create_table(
        "pm_run",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=True),
        sa.Column("work_order_id", sa.String(length=36), nullable=True),
        sa.Column("status",
                  _enum("ck_enum_pmrunstatus", "pending", "in_progress", "completed", "passed",
                        "failed", "missed"),
                  nullable=False),
        sa.Column("started_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("completed_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspected_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("inspected_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("inspection_note", sa.Text(), nullable=True),
        sa.Column("due_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["pm_template.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["maintainable_unit.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["pm_cycle.id"]),
        sa.ForeignKeyConstraint(["work_order_id"], ["work_order.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["inspected_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_run", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_property_id"), ["property_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_template_id"), ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_unit_id"), ["unit_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_cycle_id"), ["cycle_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_work_order_id"), ["work_order_id"],
                              unique=False)
        batch_op.create_index("ix_pm_run_property_cycle_unit_status",
                              ["property_id", "cycle_id", "unit_id", "status"], unique=False)

    op.create_table(
        "pm_run_answer",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("out_of_range", sa.Boolean(), nullable=False),
        sa.Column("answered_at", app.db.UTCDateTime(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["run_id"], ["pm_run.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["pm_template_item.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "item_id", name="uq_pm_run_answer_run_item"),
    )
    with op.batch_alter_table("pm_run_answer", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_answer_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_answer_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "pm_run_photo",
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["run_id"], ["pm_run.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["pm_template_item.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pm_run_photo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_pm_run_photo_run_id"), ["run_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_pm_run_photo_property_id"), ["property_id"],
                              unique=False)


def downgrade() -> None:
    # FK-safe order: children before parents.
    for table in ("pm_run_photo", "pm_run_answer", "pm_run", "pm_cycle", "pm_template_unit",
                  "pm_template_item", "pm_template", "maintainable_unit"):
        op.drop_table(table)
