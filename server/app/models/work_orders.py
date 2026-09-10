from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import (
    DraftPromptStatus,
    LocationType,
    Priority,
    WorkOrderEventType,
    WorkOrderStatus,
    WorkOrderType,
)


class WorkOrder(TimestampMixin, Base):
    __tablename__ = "work_order"
    __table_args__ = (Index("ix_work_order_property_status", "property_id", "status"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[WorkOrderType] = mapped_column(enum_type(WorkOrderType), nullable=False)
    priority: Mapped[Priority] = mapped_column(
        enum_type(Priority), default=Priority.normal, nullable=False
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        enum_type(WorkOrderStatus), default=WorkOrderStatus.open, nullable=False
    )
    location_type: Mapped[LocationType] = mapped_column(
        enum_type(LocationType), default=LocationType.room, nullable=False
    )
    location_ref: Mapped[str | None] = mapped_column(String(100))
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    reported_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    source_conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation.id"), index=True
    )
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey("message.id"))
    attachments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    guest_notified_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class WorkOrderEvent(TimestampMixin, Base):
    __tablename__ = "work_order_event"
    work_order_id: Mapped[str] = mapped_column(
        ForeignKey("work_order.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    type: Mapped[WorkOrderEventType] = mapped_column(enum_type(WorkOrderEventType), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(100))
    to_value: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(Text)


class DraftPrompt(TimestampMixin, Base):
    """The unsent, editable closed-loop message (design.md §6.4)."""

    __tablename__ = "draft_prompt"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id"), nullable=False, index=True
    )
    work_order_id: Mapped[str] = mapped_column(ForeignKey("work_order.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[DraftPromptStatus] = mapped_column(
        enum_type(DraftPromptStatus), default=DraftPromptStatus.pending, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
