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
