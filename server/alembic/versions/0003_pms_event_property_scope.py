"""scope the pms_event idempotency key by property

Stay is unique on (property_id, pms_reservation_id) because most PMSs number reservations per
property, so two properties legitimately send the same external_id. With a global
(integration_key, external_id, event_type) key the second property's event was swallowed as a
duplicate of the first's and never processed.

pms_event is a pure idempotency ledger with no rows anything else references, and existing rows
carry no property to backfill from, so the upgrade clears it before adding the NOT NULL column:
the only consequence is that a PMS replaying a pre-migration event would be processed once more.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10

"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM pms_event")
    with op.batch_alter_table("pms_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("property_id", sa.String(length=36), nullable=False))
        batch_op.drop_constraint("uq_pms_event_idem", type_="unique")
        batch_op.create_unique_constraint(
            "uq_pms_event_idem",
            ["property_id", "integration_key", "external_id", "event_type"],
        )
        batch_op.create_index("ix_pms_event_property_id", ["property_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_pms_event_property_id", "property", ["property_id"], ["id"]
        )


def downgrade() -> None:
    op.execute("DELETE FROM pms_event")
    with op.batch_alter_table("pms_event", schema=None) as batch_op:
        batch_op.drop_constraint("fk_pms_event_property_id", type_="foreignkey")
        batch_op.drop_index("ix_pms_event_property_id")
        batch_op.drop_constraint("uq_pms_event_idem", type_="unique")
        batch_op.create_unique_constraint(
            "uq_pms_event_idem", ["integration_key", "external_id", "event_type"]
        )
        batch_op.drop_column("property_id")
