## Task 1: Models, enums and migration

**Files:**
- Create: `server/app/models/log.py`
- Create: `server/alembic/versions/0006_hotel_log.py`
- Modify: `server/app/schemas/enums.py`, `server/app/models/__init__.py`
- Test: `server/tests/test_models.py`

**Interfaces:**
- Consumes: `TimestampMixin`, `enum_type` from `app.models.core`; `Base`, `UTCDateTime` from `app.db`
- Produces: `LogEntry`, `LogEntryMention`, `LogEntryPhoto`, `LogEntryAck` importable from `app.models`; `Shift` (`am`/`pm`/`overnight`) and `MentionTargetType` (`user`/`department`) importable from `app.schemas.enums`

- [ ] **Step 1: Write the failing test**

Append to `server/tests/test_models.py`:

```python
def test_log_entry_round_trips_with_mentions_photo_and_ack(database, fx):
    from app.models import LogEntry, LogEntryAck, LogEntryMention, LogEntryPhoto
    from app.schemas.enums import MentionTargetType, Shift

    with database.session() as db:
        entry = LogEntry(
            property_id=fx.property_a.id,
            author_user_id=fx.agent_a.id,
            department_id=fx.dept_housekeeping.id,
            shift=Shift.am,
            body="327 fridge does not work but room is clean.",
            requires_ack=True,
            ack_expected=[fx.housekeeper_a.id],
        )
        db.add(entry)
        db.flush()
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=fx.property_a.id,
                               type=MentionTargetType.department,
                               target_id=fx.dept_housekeeping.id, position=0))
        db.add(LogEntryMention(log_entry_id=entry.id, property_id=fx.property_a.id,
                               type=MentionTargetType.user,
                               target_id=fx.engineer_a.id, position=1))
        db.add(LogEntryPhoto(log_entry_id=entry.id, property_id=fx.property_a.id,
                             uploaded_by_user_id=fx.agent_a.id,
                             content_type="image/png", byte_size=3, data=b"abc"))
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        db.flush()
        entry_id = entry.id

    with database.session() as db:
        row = db.get(LogEntry, entry_id)
        assert row.shift == Shift.am
        assert row.pinned is False
        assert row.ack_expected == [fx.housekeeper_a.id]
        mentions = db.scalars(
            select(LogEntryMention)
            .where(LogEntryMention.log_entry_id == entry_id)
            .order_by(LogEntryMention.position)
        ).all()
        assert [m.type for m in mentions] == [MentionTargetType.department, MentionTargetType.user]
        photo = db.scalar(select(LogEntryPhoto)
                          .where(LogEntryPhoto.log_entry_id == entry_id))
        assert photo.data == b"abc"


def test_log_entry_ack_is_unique_per_user(database, fx):
    from sqlalchemy.exc import IntegrityError

    from app.models import LogEntry, LogEntryAck
    from app.schemas.enums import Shift

    with database.session() as db:
        entry = LogEntry(property_id=fx.property_a.id, author_user_id=fx.agent_a.id,
                         shift=Shift.pm, body="x")
        db.add(entry)
        db.flush()
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        db.flush()
        db.add(LogEntryAck(log_entry_id=entry.id, property_id=fx.property_a.id,
                           user_id=fx.housekeeper_a.id, acknowledged_at=clock.now()))
        with pytest.raises(IntegrityError):
            db.flush()
```

Check the top of `test_models.py` for the imports it already has; add `pytest`, `from sqlalchemy import select`, and `from app import clock` only if they are not already there.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_models.py -q -k log_entry`
Expected: FAIL with `ImportError: cannot import name 'LogEntry' from 'app.models'`

- [ ] **Step 3: Add the enums**

In `server/app/schemas/enums.py`, append:

```python
class Shift(StrEnum):
    am = "am"
    pm = "pm"
    overnight = "overnight"


class MentionTargetType(StrEnum):
    user = "user"
    department = "department"
```

- [ ] **Step 4: Write the models**

Create `server/app/models/log.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import MentionTargetType, Shift


class LogEntry(TimestampMixin, Base):
    """One hotel-log post: the shift-handover record (spec §3).

    Deliberately immutable after creation apart from `pinned` and its acks — an
    acknowledgement means nothing if the text it acknowledged can change afterwards, so no
    route updates `body` (spec §4.4).
    """

    __tablename__ = "log_entry"
    __table_args__ = (
        Index("ix_log_entry_property_created", "property_id", "created_at"),
        Index("ix_log_entry_property_pinned", "property_id", "pinned"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    shift: Mapped[Shift] = mapped_column(enum_type(Shift), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pinned_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    pinned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A frozen snapshot of resolved user ids, not a live department query: a supervisor's
    # "7 of 9" must not change when somebody joins the department tomorrow (spec §3.2).
    ack_expected: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    linked_work_order_id: Mapped[str | None] = mapped_column(ForeignKey("work_order.id"))
    linked_conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversation.id"))


class LogEntryMention(TimestampMixin, Base):
    """A table rather than the `mentions uuid[]` column of design.md §5.4, because the
    `mentioning_me` filter would otherwise need `json_each` on SQLite and
    `jsonb_array_elements` on PostgreSQL — and §10.1 commits to swapping engines by changing
    DATABASE_URL alone. `position` preserves the author's insertion order for rendering.
    """

    __tablename__ = "log_entry_mention"
    __table_args__ = (
        UniqueConstraint("log_entry_id", "type", "target_id", name="uq_log_mention_entry_target"),
        Index("ix_log_mention_property_target", "property_id", "type", "target_id"),
    )
    log_entry_id: Mapped[str] = mapped_column(
        ForeignKey("log_entry.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    type: Mapped[MentionTargetType] = mapped_column(
        enum_type(MentionTargetType), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class LogEntryPhoto(TimestampMixin, Base):
    """Bytes in the table for the same reason as work_order_photo
    (app/models/work_orders.py:67): the deployment target's filesystem is ephemeral, so a
    disk-backed photo vanishes on redeploy. `data` is deferred so the feed query never drags
    blobs along with the metadata.
    """

    __tablename__ = "log_entry_photo"
    log_entry_id: Mapped[str] = mapped_column(
        ForeignKey("log_entry.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class LogEntryAck(TimestampMixin, Base):
    __tablename__ = "log_entry_ack"
    __table_args__ = (
        UniqueConstraint("log_entry_id", "user_id", name="uq_log_ack_entry_user"),
    )
    log_entry_id: Mapped[str] = mapped_column(
        ForeignKey("log_entry.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
```

- [ ] **Step 5: Export the models**

In `server/app/models/__init__.py`, add the import and the four names to `__all__`, keeping both alphabetical:

```python
from app.models.log import LogEntry, LogEntryAck, LogEntryMention, LogEntryPhoto
```

- [ ] **Step 6: Write the migration**

Create `server/alembic/versions/0006_hotel_log.py`. Read `0005_staff_messaging.py` first and match its style exactly — same import block, same `sa.Enum(..., native_enum=False, create_constraint=True, length=32)` shape, same `app.db.UTCDateTime()` for datetime columns.

```python
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
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("shift",
                  sa.Enum("am", "pm", "overnight", name="ck_enum_shift",
                          native_enum=False, create_constraint=True, length=32),
                  nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("pinned_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("pinned_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("requires_ack", sa.Boolean(), nullable=False),
        sa.Column("ack_expected", sa.JSON(), nullable=False),
        sa.Column("linked_work_order_id", sa.String(length=36), nullable=True),
        sa.Column("linked_conversation_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"]),
        sa.ForeignKeyConstraint(["pinned_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["linked_work_order_id"], ["work_order.id"]),
        sa.ForeignKeyConstraint(["linked_conversation_id"], ["conversation.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_log_entry_property_id", "log_entry", ["property_id"])
    op.create_index("ix_log_entry_property_created", "log_entry", ["property_id", "created_at"])
    op.create_index("ix_log_entry_property_pinned", "log_entry", ["property_id", "pinned"])

    op.create_table(
        "log_entry_mention",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("type",
                  sa.Enum("user", "department", name="ck_enum_mentiontargettype",
                          native_enum=False, create_constraint=True, length=32),
                  nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_entry_id", "type", "target_id",
                            name="uq_log_mention_entry_target"),
    )
    op.create_index("ix_log_entry_mention_log_entry_id", "log_entry_mention", ["log_entry_id"])
    op.create_index("ix_log_entry_mention_property_id", "log_entry_mention", ["property_id"])
    op.create_index("ix_log_mention_property_target", "log_entry_mention",
                    ["property_id", "type", "target_id"])

    op.create_table(
        "log_entry_photo",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("uploaded_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=40), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=True),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_log_entry_photo_log_entry_id", "log_entry_photo", ["log_entry_id"])
    op.create_index("ix_log_entry_photo_property_id", "log_entry_photo", ["property_id"])

    op.create_table(
        "log_entry_ack",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("acknowledged_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("log_entry_id", "user_id", name="uq_log_ack_entry_user"),
    )
    op.create_index("ix_log_entry_ack_log_entry_id", "log_entry_ack", ["log_entry_id"])
    op.create_index("ix_log_entry_ack_property_id", "log_entry_ack", ["property_id"])


def downgrade() -> None:
    op.drop_table("log_entry_ack")
    op.drop_table("log_entry_photo")
    op.drop_table("log_entry_mention")
    op.drop_table("log_entry")
```

- [ ] **Step 7: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, including the two new tests. The `template_db_path` fixture runs migrations, so a broken migration surfaces here as a collection-time error.

- [ ] **Step 8: Lint**

Run: `cd server && ../.venv/Scripts/python.exe -m ruff check .`
Expected: no findings.

- [ ] **Step 9: Commit**

```bash
git add server/app/models/log.py server/app/models/__init__.py server/app/schemas/enums.py server/alembic/versions/0006_hotel_log.py server/tests/test_models.py
git commit -m "feat(server): hotel log tables, enums and migration 0006"
```

---

