"""The starter checklist library (checklist structure spec §3.4): fixed definitions that ship
with Relay. A property imports one as an ordinary, unscheduled template through
`ck_templates.create`; nothing links the copy back here, so importing twice gives two copies."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import ck_templates
from app.errors import NotFound
from app.models import ChecklistTemplate
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistItemIn,
    ChecklistLibraryCategoryOut,
    ChecklistLibraryEntryOut,
    ChecklistLibraryImport,
    ChecklistTemplateIn,
)
from app.schemas.enums import ChecklistKind, ChecklistSchedule, DepartmentType, PmItemType


@dataclass(frozen=True)
class LibraryItem:
    label: str
    item_type: PmItemType
    category: str | None = None
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    required: bool = True


@dataclass(frozen=True)
class LibraryEntry:
    key: str
    name: str
    kind: ChecklistKind
    department_type: DepartmentType
    categories: tuple[str, ...]
    items: tuple[LibraryItem, ...]


def _check(label: str, category: str | None = None) -> LibraryItem:
    return LibraryItem(label, PmItemType.checkbox, category)


def _number(label: str, unit: str | None = None, min_value: float | None = None,
            max_value: float | None = None, category: str | None = None) -> LibraryItem:
    return LibraryItem(label, PmItemType.number, category, unit, min_value, max_value)


def _photo(label: str, category: str | None = None) -> LibraryItem:
    return LibraryItem(label, PmItemType.photo, category)


def _note(label: str, category: str | None = None) -> LibraryItem:
    return LibraryItem(label, PmItemType.text, category, required=False)


LIBRARY: tuple[LibraryEntry, ...] = (
    LibraryEntry(
        "front_desk_am", "Front Desk AM Opening", ChecklistKind.normal,
        DepartmentType.front_desk, ("Cash & drawer", "Systems", "Lobby"), (
            _number("Cash drawer counted", "$", 150, 250, "Cash & drawer"),
            _check("Safe deposit log checked", "Cash & drawer"),
            _check("Overnight reports reviewed", "Systems"),
            _check("Key encoder tested", "Systems"),
            _check("Card terminal online", "Systems"),
            _check("Lobby walk-through done", "Lobby"),
            _check("Coffee station stocked", "Lobby"),
        )),
    LibraryEntry(
        "front_desk_pm", "Front Desk PM Shift", ChecklistKind.normal,
        DepartmentType.front_desk, ("Arrivals", "Guest requests", "Handover"), (
            _check("Arrivals list reviewed", "Arrivals"),
            _check("VIP arrivals pre-keyed", "Arrivals"),
            _check("Late arrivals guaranteed", "Arrivals"),
            _check("Open guest requests followed up", "Guest requests"),
            _check("Wake-up calls set", "Guest requests"),
            _number("Cash drawer counted", "$", 150, 250, "Handover"),
            _note("Notes for the night shift", "Handover"),
        )),
    LibraryEntry(
        "night_audit", "Night Audit", ChecklistKind.normal, DepartmentType.front_desk,
        ("Pre-audit", "Cash & reports", "Rates & folios", "Credit cards", "Systems & backups",
         "Lobby & security", "Handover"), (
            _check("All departures checked out", "Pre-audit"),
            _check("No-shows posted", "Pre-audit"),
            _number("Cash drawer counted", "$", 150, 250, "Cash & reports"),
            _check("Shift reports printed", "Cash & reports"),
            _check("Room rates verified", "Rates & folios"),
            _check("Folio balances reviewed", "Rates & folios"),
            _check("Credit card batch closed", "Credit cards"),
            _check("Declined cards followed up", "Credit cards"),
            _check("Night audit run", "Systems & backups"),
            _check("System backup completed", "Systems & backups"),
            _check("Lobby and entrances walked", "Lobby & security"),
            _check("Exterior doors secured", "Lobby & security"),
            _photo("Audit report", "Handover"),
            _note("Notes for the AM shift", "Handover"),
        )),
    LibraryEntry(
        "pool_spa", "Pool & Spa Readings", ChecklistKind.readings, DepartmentType.engineering,
        (), (
            _number("Pool free chlorine", "ppm", 1.0, 3.0),
            _number("Pool pH", None, 7.2, 7.8),
            _number("Pool temperature", "°F"),
            _number("Spa temperature", "°F", None, 104),
            _photo("Test strip photo"),
        )),
    LibraryEntry(
        "boiler_rounds", "Boiler & Mechanical Rounds", ChecklistKind.readings,
        DepartmentType.engineering, (), (
            _number("Boiler supply temperature", "°F"),
            _number("Boiler return temperature", "°F"),
            _number("Boiler pressure", "psi"),
            _number("Chiller supply temperature", "°F"),
            _number("Chiller return temperature", "°F"),
            _photo("Log sheet photo"),
        )),
    LibraryEntry(
        "linen_par", "Housekeeping Linen Par", ChecklistKind.normal, DepartmentType.housekeeping,
        (), (
            _number("King sheet sets", "sets", 40),
            _number("Queen sheet sets", "sets", 60),
            _number("Pillowcases", None, 150),
            _number("Bath towels", None, 120),
            _number("Hand towels", None, 120),
            _number("Bath mats", None, 60),
            _check("Linen room tidy"),
        )),
)

BY_KEY = {entry.key: entry for entry in LIBRARY}


def list_entries() -> list[ChecklistLibraryEntryOut]:
    return [ChecklistLibraryEntryOut(
        key=e.key, name=e.name, kind=e.kind, department_type=e.department_type,
        categories=[ChecklistLibraryCategoryOut(
            name=c, item_count=sum(1 for i in e.items if i.category == c)) for c in e.categories],
        item_count=len(e.items)) for e in LIBRARY]


def template_in(entry: LibraryEntry, department_id: str, name: str) -> ChecklistTemplateIn:
    """The entry as an ordinary create request: unscheduled, each category keyed by position."""
    key_of = {c: f"c{n}" for n, c in enumerate(entry.categories)}
    return ChecklistTemplateIn(
        name=name, department_id=department_id, schedule=ChecklistSchedule.unscheduled,
        kind=entry.kind,
        categories=[ChecklistCategoryIn(key=key_of[c], name=c) for c in entry.categories],
        items=[ChecklistItemIn(label=i.label, item_type=i.item_type, unit=i.unit,
                               min_value=i.min_value, max_value=i.max_value,
                               required=i.required,
                               category_key=key_of[i.category] if i.category else None)
               for i in entry.items])


def import_entry(db: Session, property_id: str, actor_id: str, key: str,
                 data: ChecklistLibraryImport) -> ChecklistTemplate:
    entry = BY_KEY.get(key)
    if entry is None:
        raise NotFound("Library checklist not found")
    name = (data.name or "").strip() or entry.name
    return ck_templates.create(db, property_id, actor_id,
                               template_in(entry, data.department_id, name))
