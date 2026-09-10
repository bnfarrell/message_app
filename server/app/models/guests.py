from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import SmsConsentStatus, StayStatus


class Guest(TimestampMixin, Base):
    __tablename__ = "guest"
    __table_args__ = (UniqueConstraint("property_id", "phone_e164", name="uq_guest_property_phone"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    phone_e164: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    loyalty_program: Mapped[str | None] = mapped_column(String(50))
    loyalty_tier: Mapped[str | None] = mapped_column(String(50))
    loyalty_number: Mapped[str | None] = mapped_column(String(50))
    vip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pms_profile_id: Mapped[str | None] = mapped_column(String(100))
    sms_consent_status: Mapped[SmsConsentStatus] = mapped_column(
        enum_type(SmsConsentStatus), default=SmsConsentStatus.unknown, nullable=False
    )
    sms_consent_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    sms_consent_source: Mapped[str | None] = mapped_column(String(50))
    notes_summary: Mapped[str | None] = mapped_column(String(2000))


class Stay(TimestampMixin, Base):
    __tablename__ = "stay"
    __table_args__ = (Index("ix_stay_property_status", "property_id", "status"),)
    guest_id: Mapped[str] = mapped_column(ForeignKey("guest.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    pms_reservation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    room_number: Mapped[str | None] = mapped_column(String(10))
    room_type: Mapped[str | None] = mapped_column(String(50))
    rate_code: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[StayStatus] = mapped_column(
        enum_type(StayStatus), default=StayStatus.reserved, nullable=False
    )
    arrival_date: Mapped[date] = mapped_column(Date, nullable=False)
    departure_date: Mapped[date] = mapped_column(Date, nullable=False)
    actual_checkin_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    actual_checkout_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    adults: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    children: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    group_code: Mapped[str | None] = mapped_column(String(50))
    market_segment: Mapped[str | None] = mapped_column(String(50))
    is_return_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stay_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_pms: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
