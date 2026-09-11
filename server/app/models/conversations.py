from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.models.guests import Guest, Stay
from app.schemas.enums import AuthorType, Channel, ConversationStatus, DeliveryStatus, Direction


class ResolutionCategory(TimestampMixin, Base):
    __tablename__ = "resolution_category"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("resolution_category.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (
        Index("ix_conversation_property_status", "property_id", "status"),
        Index("ix_conversation_property_sla", "property_id", "sla_due_at"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guest.id"), nullable=False, index=True)
    stay_id: Mapped[str | None] = mapped_column(ForeignKey("stay.id"))
    status: Mapped[ConversationStatus] = mapped_column(
        enum_type(ConversationStatus), default=ConversationStatus.open, nullable=False
    )
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    assigned_department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    channel_primary: Mapped[Channel] = mapped_column(
        enum_type(Channel), default=Channel.sms, nullable=False
    )
    last_guest_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_staff_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_response_seconds: Mapped[int | None] = mapped_column(Integer)
    sla_due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sla_breach_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_category_id: Mapped[str | None] = mapped_column(ForeignKey("resolution_category.id"))
    snoozed_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    guest: Mapped[Guest] = relationship(Guest, lazy="joined")
    stay: Mapped[Stay | None] = relationship(Stay, lazy="joined")


class Message(TimestampMixin, Base):
    __tablename__ = "message"
    __table_args__ = (
        Index("ix_message_conversation_sent", "conversation_id", "sent_at"),
        UniqueConstraint("property_id", "provider_message_id", name="uq_message_property_provider"),
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    direction: Mapped[Direction] = mapped_column(enum_type(Direction), nullable=False)
    author_type: Mapped[AuthorType] = mapped_column(enum_type(AuthorType), nullable=False)
    author_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    channel: Mapped[Channel] = mapped_column(enum_type(Channel), default=Channel.sms,
                                             nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    digital_asset_id: Mapped[str | None] = mapped_column(ForeignKey("digital_asset.id"))
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        enum_type(DeliveryStatus), default=DeliveryStatus.queued, nullable=False
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    provider_error_code: Mapped[str | None] = mapped_column(String(50))
    provider_error_message: Mapped[str | None] = mapped_column(String(500))
    redacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class InternalNote(TimestampMixin, Base):
    """NEVER joined into any guest-facing query. Separate table by design (spec §3.2)."""

    __tablename__ = "internal_note"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
