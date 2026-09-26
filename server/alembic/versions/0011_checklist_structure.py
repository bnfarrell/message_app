"""checklist_structure: checklist_template_category, checklist_template_item.category_id,
checklist_template.kind, and the 'unscheduled' schedule

Checklist structure spec §2.1, §6 (docs/superpowers/specs/2026-09-26-checklist-structure-design.md).
One new table, one nullable column on checklist_template_item, one NOT NULL column with a server
default on checklist_template (existing rows become 'normal'), and both of checklist_template's
schedule CHECKs rebuilt to admit 'unscheduled'. The CHECK rebuilds go through batch_alter_table,
as 0004 does: a table rebuild on SQLite, a DROP/ADD CONSTRAINT on PostgreSQL.

downgrade() refuses while any template is unscheduled: the 0009 CHECKs cannot hold such a row,
and silently rewriting its schedule would change what the hotel configured.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-26

"""
import sqlalchemy as sa

import app.db
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

KIND_CHECK = "ck_enum_checklistkind"
SCHEDULE_CHECK = "ck_enum_checklistschedule"
FIELDS_CHECK = "ck_checklist_template_schedule_fields"
ITEM_CATEGORY_FK = "fk_checklist_template_item_category_id"

OLD_SCHEDULE = ("weekly", "on_demand")
NEW_SCHEDULE = (*OLD_SCHEDULE, "unscheduled")
OLD_FIELDS = ("(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
              "AND weekdays > 0) OR "
              "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)")
NEW_FIELDS = ("(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
              "AND weekdays > 0) OR "
              "(schedule IN ('on_demand', 'unscheduled') AND shift IS NULL AND weekdays IS NULL)")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
    ]


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _set_schedule_checks(values: tuple[str, ...], fields_sql: str) -> None:
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.drop_constraint(SCHEDULE_CHECK, type_="check")
        batch_op.drop_constraint(FIELDS_CHECK, type_="check")
        batch_op.create_check_constraint(SCHEDULE_CHECK, f"schedule IN ({_listed(values)})")
        batch_op.create_check_constraint(FIELDS_CHECK, fields_sql)


def upgrade() -> None:
    op.create_table(
        "checklist_template_category",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_template_category", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_template_category_template_id"),
                              ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_checklist_template_category_property_id"),
                              ["property_id"], unique=False)

    # A plain VARCHAR plus an explicitly named CHECK — what enum_type() produces — rather than
    # _enum() inside add_column, whose CHECK is not reliably emitted by ALTER TABLE ADD COLUMN.
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(length=32), nullable=False,
                                      server_default="normal"))
        batch_op.create_check_constraint(KIND_CHECK, "kind IN ('normal', 'readings')")
    _set_schedule_checks(NEW_SCHEDULE, NEW_FIELDS)

    # Nullable, no backfill: every existing item starts ungrouped. The FK is named so
    # downgrade() can drop it by name on both engines (as 0010 does for log_entry).
    with op.batch_alter_table("checklist_template_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(ITEM_CATEGORY_FK, "checklist_template_category",
                                    ["category_id"], ["id"])


def downgrade() -> None:
    unscheduled = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM checklist_template WHERE schedule = 'unscheduled'")).scalar()
    if unscheduled:
        raise RuntimeError(
            f"Refusing to downgrade 0011: {unscheduled} checklist template(s) are unscheduled, "
            "which the 0010 schema cannot store. Give each a weekly or on-demand schedule in "
            "Admin > Checklist templates first.")
    with op.batch_alter_table("checklist_template_item", schema=None) as batch_op:
        batch_op.drop_constraint(ITEM_CATEGORY_FK, type_="foreignkey")
        batch_op.drop_column("category_id")
    _set_schedule_checks(OLD_SCHEDULE, OLD_FIELDS)
    # The CHECK first: SQLite's table rebuild would otherwise carry a CHECK on a dropped column.
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.drop_constraint(KIND_CHECK, type_="check")
        batch_op.drop_column("kind")
    op.drop_table("checklist_template_category")
