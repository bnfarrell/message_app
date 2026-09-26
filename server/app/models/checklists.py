"""Shift checklists (checklists spec §2). Items and answers carry exactly PM's typed columns so
app.domain.typed_items serves both features."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.models.pm import READING
from app.schemas.enums import ChecklistSchedule, ChecklistStatus, PmItemType, Shift


class ChecklistTemplate(TimestampMixin, Base):
    __tablename__ = "checklist_template"
    __table_args__ = (
        CheckConstraint(
            "(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
            "AND weekdays > 0) OR "
            "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)",
            name="ck_checklist_template_schedule_fields",
        ),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    department_id: Mapped[str] = mapped_column(ForeignKey("department.id"), nullable=False)
    schedule: Mapped[ChecklistSchedule] = mapped_column(enum_type(ChecklistSchedule),
                                                        nullable=False)
    shift: Mapped[Shift | None] = mapped_column(enum_type(Shift))
    # Bit 0 = Monday … bit 6 = Sunday (date.weekday()); an integer, not JSON, for portability.
    weekdays: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChecklistTemplateItem(TimestampMixin, Base):
    """PM's item columns exactly; soft-deleted via `active` so old answers keep their item."""

    __tablename__ = "checklist_template_item"
    template_id: Mapped[str] = mapped_column(ForeignKey("checklist_template.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type: Mapped[PmItemType] = mapped_column(enum_type(PmItemType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    min_value: Mapped[float | None] = mapped_column(READING)
    max_value: Mapped[float | None] = mapped_column(READING)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChecklistInstance(TimestampMixin, Base):
    """`slot` is 0 on scheduled instances and NULL on on-demand ones: the unique key below makes
    generation idempotent while NULLs (distinct on both engines) let on-demand runs repeat."""

    __tablename__ = "checklist_instance"
    __table_args__ = (
        UniqueConstraint("template_id", "due_date", "shift", "slot",
                         name="uq_checklist_instance_slot"),
        Index("ix_checklist_instance_property_due", "property_id", "due_date"),
        Index("ix_checklist_instance_property_status", "property_id", "status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False)
    template_id: Mapped[str] = mapped_column(ForeignKey("checklist_template.id"), nullable=False,
                                             index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[Shift] = mapped_column(enum_type(Shift), nullable=False)
    slot: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ChecklistStatus] = mapped_column(
        enum_type(ChecklistStatus), default=ChecklistStatus.open, nullable=False)
    assigned_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    completed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    comment: Mapped[str | None] = mapped_column(Text)


class ChecklistAnswer(TimestampMixin, Base):
    __tablename__ = "checklist_answer"
    __table_args__ = (
        UniqueConstraint("instance_id", "item_id", name="uq_checklist_answer_instance_item"),
    )
    instance_id: Mapped[str] = mapped_column(ForeignKey("checklist_instance.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("checklist_template_item.id"), nullable=False)
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(READING)
    out_of_range: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class ChecklistPhoto(TimestampMixin, Base):
    """Bytes in the table, `data` deferred and NOT NULL — as every photo table."""

    __tablename__ = "checklist_photo"
    instance_id: Mapped[str] = mapped_column(ForeignKey("checklist_instance.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("checklist_template_item.id"))
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
