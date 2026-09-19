from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import StaffConversationKind


class StaffConversation(TimestampMixin, Base):
    """A staff-to-staff thread: a 1:1 DM, a named editable group, or the property's singleton
    `#ALL` channel. Deliberately not the guest `conversation` table — see spec §1.

    No DB-level uniqueness enforces one `all` row per property: `get_or_create_all_conversation`
    (app/domain/staff_messages.py) checks-then-creates, and the realistic race window (two
    simultaneous first-ever requests against a brand-new property) is negligible enough that a
    stray duplicate is an acceptable outcome rather than one worth a partial-unique-index for.
    """

    __tablename__ = "staff_conversation"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    kind: Mapped[StaffConversationKind] = mapped_column(
        enum_type(StaffConversationKind), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)


class StaffConversationParticipant(TimestampMixin, Base):
    __tablename__ = "staff_conversation_participant"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_staff_participant_conv_user"),
        Index("ix_staff_participant_user", "user_id"),
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("staff_conversation.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class StaffMessage(TimestampMixin, Base):
    __tablename__ = "staff_message"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("staff_conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    photo_content_type: Mapped[str | None] = mapped_column(String(40))
    photo_byte_size: Mapped[int | None] = mapped_column(Integer)
    # Deferred for the same reason as work_order_photo.data: never drag the bytes along with a
    # plain message listing.
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
