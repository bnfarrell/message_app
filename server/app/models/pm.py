"""Preventative maintenance (spec §3).

Eight tables on one design rule: `pm_run` is the compliance currency. A sweep `Start` creates
one directly; an RRULE firing creates a `WorkOrder(type=pm)` with one attached. Compliance is
therefore one query over `pm_run` and never a merge of two shapes.
"""
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)

# asdecimal=False: the API and the frontend speak float. Decimal would serialise as a string in
# Pydantic's JSON mode and reach TypeScript as `string`, which is wrong for a reading.
READING = Numeric(10, 2, asdecimal=False)


class MaintainableUnit(TimestampMixin, Base):
    """A room, common/BOH area or piece of equipment that PM is performed on (spec §3.1).

    Deactivate rather than delete: historical runs reference the row. `source` + `external_id`
    are the hook for a later PMS sync, which upserts guest rooms by external id and never touches
    `manual`/`csv` rows.
    """

    __tablename__ = "maintainable_unit"
    __table_args__ = (
        UniqueConstraint("property_id", "code", name="uq_maintainable_unit_property_code"),
        Index("ix_maintainable_unit_property_kind", "property_id", "kind"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    kind: Mapped[PmUnitKind] = mapped_column(enum_type(PmUnitKind), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    floor: Mapped[int | None] = mapped_column(Integer)
    room_type: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[PmUnitSource] = mapped_column(
        enum_type(PmUnitSource), default=PmUnitSource.manual, nullable=False
    )
    external_id: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)


class PmTemplate(TimestampMixin, Base):
    """One table, two modes (spec §3.2). The CHECK keeps the mode-specific columns honest on both
    engines: a sweep row has a kind and cadence and no rrule; a scheduled row has an rrule and a
    start date and no cadence."""

    __tablename__ = "pm_template"
    __table_args__ = (
        CheckConstraint(
            "(mode = 'sweep' AND unit_kind IS NOT NULL AND cadence IS NOT NULL "
            "AND rrule IS NULL) OR "
            "(mode = 'scheduled' AND rrule IS NOT NULL AND rrule_dtstart IS NOT NULL "
            "AND cadence IS NULL)",
            name="ck_pm_template_mode_fields",
        ),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[PmTemplateMode] = mapped_column(enum_type(PmTemplateMode), nullable=False)
    department_id: Mapped[str | None] = mapped_column(ForeignKey("department.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    unit_kind: Mapped[PmUnitKind | None] = mapped_column(enum_type(PmUnitKind))
    cadence: Mapped[PmCadence | None] = mapped_column(enum_type(PmCadence))
    rrule: Mapped[str | None] = mapped_column(String(500))
    rrule_dtstart: Mapped[date | None] = mapped_column(Date)
    last_fired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmTemplateItem(TimestampMixin, Base):
    """The typed checklist (spec §3.3). Soft-deleted via `active` because `pm_run_answer`
    references it — an admin editing a template must not orphan last quarter's evidence."""

    __tablename__ = "pm_template_item"
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    item_type: Mapped[PmItemType] = mapped_column(enum_type(PmItemType), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(16))
    min_value: Mapped[float | None] = mapped_column(READING)
    max_value: Mapped[float | None] = mapped_column(READING)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PmTemplateUnit(TimestampMixin, Base):
    """Which specific units a *scheduled* template targets (spec §3.4). A table rather than a
    JSON array for the same portability reason as log_entry_mention."""

    __tablename__ = "pm_template_unit"
    __table_args__ = (
        UniqueConstraint("template_id", "unit_id", name="uq_pm_template_unit"),
    )
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    unit_id: Mapped[str] = mapped_column(
        ForeignKey("maintainable_unit.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)


class PmCycle(TimestampMixin, Base):
    """A sweep window (spec §3.5). `starts_on`/`ends_on` are property-local calendar dates, not
    instants — "Jul 01 – Sep 30" is compared against today in the property timezone, never
    against a UTC column."""

    __tablename__ = "pm_cycle"
    __table_args__ = (
        UniqueConstraint("template_id", "starts_on", name="uq_pm_cycle_template_start"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PmCycleStatus] = mapped_column(
        enum_type(PmCycleStatus), default=PmCycleStatus.open, nullable=False
    )


class PmRun(TimestampMixin, Base):
    """The compliance currency (spec §3.6).

    pending → in_progress → completed → passed | failed; `missed` is written by cycle close for
    every in-scope unit without a passed run and never transitions. `cycle_id` is set on sweep
    runs, `work_order_id` on scheduled ones; never both.
    """

    __tablename__ = "pm_run"
    __table_args__ = (
        Index("ix_pm_run_property_cycle_unit_status",
              "property_id", "cycle_id", "unit_id", "status"),
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(
        ForeignKey("pm_template.id"), nullable=False, index=True
    )
    unit_id: Mapped[str] = mapped_column(
        ForeignKey("maintainable_unit.id"), nullable=False, index=True
    )
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("pm_cycle.id"), index=True)
    work_order_id: Mapped[str | None] = mapped_column(ForeignKey("work_order.id"), index=True)
    status: Mapped[PmRunStatus] = mapped_column(enum_type(PmRunStatus), nullable=False)
    started_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspected_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    inspected_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    inspection_note: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmRunAnswer(TimestampMixin, Base):
    """One row per active item, created at Start so progress saves continuously (spec §3.7).
    `answered_at` null means not yet answered."""

    __tablename__ = "pm_run_answer"
    __table_args__ = (
        UniqueConstraint("run_id", "item_id", name="uq_pm_run_answer_run_item"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("pm_run.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("pm_template_item.id"), nullable=False)
    bool_value: Mapped[bool | None] = mapped_column(Boolean)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(READING)
    out_of_range: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PmRunPhoto(TimestampMixin, Base):
    """Bytes in the table for the same reason as work_order_photo (app/models/work_orders.py:67):
    the deployment target's filesystem is ephemeral. `data` is deferred so listing a run's photos
    never drags the blobs along. A photo with an `item_id` answers that `photo` item; one
    without is general evidence for the run (spec §3.8)."""

    __tablename__ = "pm_run_photo"
    run_id: Mapped[str] = mapped_column(ForeignKey("pm_run.id"), nullable=False, index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey("pm_template_item.id"))
    uploaded_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
