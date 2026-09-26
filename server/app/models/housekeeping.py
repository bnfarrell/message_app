"""Housekeeping (spec §2).

Built on `maintainable_unit` (kind guest_room), not a second room list — spec §1.2. Number,
floor and room type live on the unit; `room` holds only the housekeeping state.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, utcnow
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import HkAssignmentStatus, HkServiceType, HkStatus, RoomEventType


class Room(TimestampMixin, Base):
    """One row per guest-room unit. Occupancy is derived from `stay`, never stored."""

    __tablename__ = "room"
    __table_args__ = (
        UniqueConstraint("unit_id", name="uq_room_unit"),
        Index("ix_room_property_status", "property_id", "hk_status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("maintainable_unit.id"), nullable=False)
    hk_status: Mapped[HkStatus] = mapped_column(
        enum_type(HkStatus), default=HkStatus.inspected, nullable=False)
    service_type: Mapped[HkServiceType | None] = mapped_column(enum_type(HkServiceType))
    rush: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_cleaned_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status_changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow,
                                                        nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class HousekeepingAssignment(TimestampMixin, Base):
    """One housekeeper's task on one room for one property-local day (spec §2.2). A failed
    inspection returns this same row to `assigned` rather than creating another."""

    __tablename__ = "housekeeping_assignment"
    __table_args__ = (
        Index("ix_hk_assignment_property_day_keeper",
              "property_id", "shift_date", "housekeeper_user_id"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"), nullable=False, index=True)
    housekeeper_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"),
                                                     nullable=False, index=True)
    shift_date: Mapped[date] = mapped_column(Date, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[HkServiceType] = mapped_column(enum_type(HkServiceType), nullable=False)
    status: Mapped[HkAssignmentStatus] = mapped_column(
        enum_type(HkAssignmentStatus), default=HkAssignmentStatus.assigned, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspection_note: Mapped[str | None] = mapped_column(Text)
    fail_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class RoomEvent(TimestampMixin, Base):
    """The audit trail, shaped like work_order_event (spec §2.3)."""

    __tablename__ = "room_event"
    __table_args__ = (Index("ix_room_event_room_created", "room_id", "created_at"),)
    room_id: Mapped[str] = mapped_column(ForeignKey("room.id"), nullable=False)
    assignment_id: Mapped[str | None] = mapped_column(ForeignKey("housekeeping_assignment.id"))
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    type: Mapped[RoomEventType] = mapped_column(enum_type(RoomEventType), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(40))
    to_value: Mapped[str | None] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(Text)


class HousekeepingPhoto(TimestampMixin, Base):
    """Bytes in the table, `data` deferred — same reason as work_order_photo: the deployment
    filesystem is ephemeral (spec §2.4)."""

    __tablename__ = "housekeeping_photo"
    assignment_id: Mapped[str] = mapped_column(ForeignKey("housekeeping_assignment.id"),
                                               nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
