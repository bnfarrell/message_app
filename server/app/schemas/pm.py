"""Preventative maintenance wire models (spec §5). Readings are float on the wire — see
app/models/pm.py READING."""
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import (
    PmCadence,
    PmCycleStatus,
    PmItemType,
    PmRunStatus,
    PmTemplateMode,
    PmUnitKind,
    PmUnitSource,
)

MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 1024 * 1024


# ---- inventory ---------------------------------------------------------------------------

class UnitIn(CamelModel):
    kind: PmUnitKind
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    floor: int | None = None
    room_type: str | None = Field(default=None, max_length=20)
    external_id: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class UnitPatch(CamelModel):
    kind: PmUnitKind | None = None
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    floor: int | None = None
    room_type: str | None = Field(default=None, max_length=20)
    active: bool | None = None
    external_id: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class UnitOut(CamelModel):
    id: str
    kind: PmUnitKind
    code: str
    name: str
    floor: int | None = None
    room_type: str | None = None
    active: bool
    source: PmUnitSource
    external_id: str | None = None
    notes: str | None = None
    created_at: datetime


class UnitListQuery(CamelModel):
    kind: PmUnitKind | None = None
    active: bool | None = None
    q: str | None = None


class UnitImportError(CamelModel):
    line: int
    field: str
    message: str


class UnitImportOut(CamelModel):
    created: int
    updated: int
    errors: list[UnitImportError] = Field(default_factory=list)


# ---- templates ---------------------------------------------------------------------------

class TemplateItemIn(CamelModel):
    """`id` set = update that item in place; omitted = a new item. An item missing from the
    list is soft-deleted (spec §4.5)."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    item_type: PmItemType
    unit: str | None = Field(default=None, max_length=16)
    min_value: float | None = None
    max_value: float | None = None
    required: bool = True


class TemplateItemOut(CamelModel):
    id: str
    position: int
    label: str
    item_type: PmItemType
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    required: bool
    active: bool


class TemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    mode: PmTemplateMode
    department_id: str | None = None
    active: bool = True
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = Field(default=None, max_length=500)
    rrule_dtstart: date | None = None
    unit_ids: list[str] = Field(default_factory=list, max_length=500)
    items: list[TemplateItemIn] = Field(default_factory=list, max_length=100)


class TemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    mode: PmTemplateMode | None = None
    department_id: str | None = None
    active: bool | None = None
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = Field(default=None, max_length=500)
    rrule_dtstart: date | None = None
    unit_ids: list[str] | None = Field(default=None, max_length=500)
    items: list[TemplateItemIn] | None = Field(default=None, max_length=100)


class TemplateOut(CamelModel):
    id: str
    name: str
    mode: PmTemplateMode
    department_id: str | None = None
    active: bool
    unit_kind: PmUnitKind | None = None
    cadence: PmCadence | None = None
    rrule: str | None = None
    rrule_dtstart: date | None = None
    last_fired_at: datetime | None = None
    unit_ids: list[str] = Field(default_factory=list)
    items: list[TemplateItemOut] = Field(default_factory=list)
    has_runs: bool
    created_at: datetime


# ---- cycles and the sweep page ----------------------------------------------------------

class CycleOut(CamelModel):
    id: str
    template_id: str
    ordinal: int
    starts_on: date
    ends_on: date
    status: PmCycleStatus
    days_left: int
    passed: int
    missed: int
    total: int


class SweepQuery(CamelModel):
    kind: PmUnitKind
    status: Literal["remaining", "completed"] | None = None
    q: str | None = None
    sort: Literal["code", "floor", "days_since_last_pm"] = "code"


class SweepTemplateOut(CamelModel):
    id: str
    name: str
    cadence: PmCadence


class SweepCycleOut(CamelModel):
    id: str
    ordinal: int
    starts_on: date
    ends_on: date
    days_left: int


class SweepCounts(CamelModel):
    remaining: int
    completed: int
    total: int


class SweepRunBrief(CamelModel):
    id: str
    status: PmRunStatus
    started_by_user_id: str | None = None
    started_by_name: str | None = None


class SweepUnitOut(CamelModel):
    id: str
    code: str
    name: str
    floor: int | None = None
    room_type: str | None = None
    last_passed_at: datetime | None = None
    last_passed_by_name: str | None = None
    passed_this_cycle: bool
    current_run: SweepRunBrief | None = None


class SweepOut(CamelModel):
    template: SweepTemplateOut | None = None
    cycle: SweepCycleOut | None = None
    counts: SweepCounts
    units: list[SweepUnitOut] = Field(default_factory=list)


# ---- runs --------------------------------------------------------------------------------

class StartRunRequest(CamelModel):
    template_id: str
    unit_id: str


class AnswerPatch(CamelModel):
    """Exactly one of these, matching the item's type (spec §4.2)."""

    bool_value: bool | None = None
    text_value: str | None = Field(default=None, max_length=2000)
    number_value: float | None = None


class RunAnswerOut(CamelModel):
    id: str
    item_id: str
    bool_value: bool | None = None
    text_value: str | None = None
    number_value: float | None = None
    out_of_range: bool
    answered_at: datetime | None = None


class RunPhotoOut(CamelModel):
    id: str
    item_id: str | None = None
    content_type: str
    byte_size: int
    uploaded_by_user_id: str | None = None
    url: str
    created_at: datetime


class RunOut(CamelModel):
    id: str
    template_id: str
    template_name: str
    unit_id: str
    unit_code: str
    unit_name: str
    unit_kind: PmUnitKind
    cycle_id: str | None = None
    work_order_id: str | None = None
    status: PmRunStatus
    started_by_user_id: str | None = None
    started_by_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    inspected_by_user_id: str | None = None
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None
    inspection_note: str | None = None
    due_at: datetime | None = None
    items: list[TemplateItemOut] = Field(default_factory=list)
    answers: list[RunAnswerOut] = Field(default_factory=list)
    photos: list[RunPhotoOut] = Field(default_factory=list)
    # Item ids that still block Complete. Empty once the run can be completed.
    missing_required: list[str] = Field(default_factory=list)


class InspectRequest(CamelModel):
    result: Literal["pass", "fail"]
    note: str | None = Field(default=None, max_length=2000)


class InspectionQuery(CamelModel):
    kind: PmUnitKind | None = None
    status: Literal["available", "inspected"] = "available"
    sort: Literal["days_since_last_pm", "completed_at"] = "completed_at"


class InspectionRowOut(CamelModel):
    run_id: str
    unit_id: str
    unit_code: str
    unit_name: str
    unit_kind: PmUnitKind
    template_name: str
    completed_by_name: str | None = None
    completed_at: datetime | None = None
    # Days since this unit's previous passed PM (not counting this run). None = never.
    days_since_last_pm: int | None = None
    status: PmRunStatus
    inspected_by_name: str | None = None
    inspected_at: datetime | None = None


# ---- compliance --------------------------------------------------------------------------

class ComplianceQuery(CamelModel):
    from_: str = Field(alias="from")
    to: str


class ComplianceCycleOut(CamelModel):
    ordinal: int
    starts_on: date
    ends_on: date
    status: PmCycleStatus
    passed: int
    missed: int
    total: int
    on_time_pct: float


class ComplianceRunsOut(CamelModel):
    due: int
    passed: int
    failed: int
    overdue: int


class ComplianceTemplateOut(CamelModel):
    id: str
    name: str
    mode: PmTemplateMode
    unit_kind: PmUnitKind | None = None
    cycles: list[ComplianceCycleOut] = Field(default_factory=list)
    runs: ComplianceRunsOut | None = None
    inspection_pass_rate: float | None = None


class ComplianceOut(CamelModel):
    templates: list[ComplianceTemplateOut] = Field(default_factory=list)
