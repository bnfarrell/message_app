from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime, new_id, utcnow
from app.schemas.enums import DepartmentType, Role, UserStatus


def enum_type(enum_cls: type[StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        validate_strings=True,
        length=32,
        create_constraint=True,
        name=f"ck_enum_{enum_cls.__name__.lower()}",
        values_callable=lambda e: [m.value for m in e],
    )


class TimestampMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Property(TimestampMixin, Base):
    __tablename__ = "property"
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    address: Mapped[str | None] = mapped_column(String(400))
    phone: Mapped[str | None] = mapped_column(String(32))
    sms_number: Mapped[str | None] = mapped_column(String(32))
    brand: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    primary_color: Mapped[str | None] = mapped_column(String(16))
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class UserAccount(TimestampMixin, Base):
    __tablename__ = "user_account"
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus), default=UserStatus.active, nullable=False
    )
    password_hash: Mapped[str | None] = mapped_column(String(200))
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class Department(TimestampMixin, Base):
    __tablename__ = "department"
    property_id: Mapped[str] = mapped_column(
        ForeignKey("property.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[DepartmentType] = mapped_column(enum_type(DepartmentType), nullable=False)
    escalation_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PropertyMembership(TimestampMixin, Base):
    __tablename__ = "property_membership"
    __table_args__ = (UniqueConstraint("user_id", "property_id", name="uq_membership_user_property"),)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("property.id"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(enum_type(Role), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
