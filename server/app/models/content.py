from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import AssetType


class QuickReply(TimestampMixin, Base):
    __tablename__ = "quick_reply"
    __table_args__ = (UniqueConstraint("property_id", "shortcut", name="uq_quick_reply_shortcut"),)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    shortcut: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class DigitalAsset(TimestampMixin, Base):
    __tablename__ = "digital_asset"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50))
    type: Mapped[AssetType] = mapped_column(enum_type(AssetType), default=AssetType.link, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    short_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(UTCDateTime)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    send_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
