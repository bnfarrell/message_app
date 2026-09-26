# Shift Checklist Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give shift checklists the structure the hotel's incumbent tool has: categories inside a
checklist (collapsible, each with its own progress), a Normal / Readings kind, templates saved
without a schedule ("Set schedule"), and a six-checklist starter library a property imports from
Admin.

**Architecture:** Migration `0011` adds one table (`checklist_template_category`), one nullable
column (`checklist_template_item.category_id`), one NOT NULL column with a server default
(`checklist_template.kind`), and rebuilds `checklist_template`'s two schedule CHECKs to admit
`unscheduled`. Categories save inside the existing template create/patch (`ck_templates`), keyed
per request by a client `key`; the shared PM item code (`TemplateItemIn`, `typed_items.sync_items`)
is untouched — checklists subclass the item model and assign categories after the shared sync. A
new `app/domain/ck_library.py` holds the six starter checklists as plain data and imports one
through `ck_templates.create`. The web client extends the shared `ItemListEditor` with an optional
category column, adds a category list, Kind and "Not scheduled yet" to the checklist template
editor, an Import-from-library dialog, and grouped, collapsible sections on the checklist page.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · pytest; Vite +
React + TypeScript + TanStack Query + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-26-checklist-structure-design.md` — read it before any
task. Background: `docs/superpowers/specs/2026-09-25-shift-checklists-design.md` and
`docs/superpowers/plans/2026-09-25-shift-checklists.md` (the shipped checklists). Where this plan
is more precise than the spec, "Spec clarifications" says so.

## Global Constraints

- Python by explicit path only: `cd server && ../.venv/Scripts/python.exe -m pytest -q`. Bare
  `python` is a silent Windows Store stub.
- Lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` — line length 100.
- Frontend: `cd web && npm test && npm run lint && npm run build` — all three clean.
- Engine-portable SQL only. Categories are a table (`checklist_template_category`) plus a nullable
  FK on the item, never a name string on each item or a JSON column.
- Every enum column through `enum_type()`. The new enum is `ChecklistKind`: `normal` ·
  `readings`. `ChecklistSchedule` gains `unscheduled` (alongside `weekly`, `on_demand`).
- The migration rebuilds `ck_enum_checklistschedule` and `ck_checklist_template_schedule_fields`
  through `batch_alter_table` (the `0004` precedent: a table rebuild on SQLite, DROP/ADD
  CONSTRAINT on PostgreSQL). The new schedule-fields CHECK is exactly
  `(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL AND weekdays > 0) OR
  (schedule IN ('on_demand', 'unscheduled') AND shift IS NULL AND weekdays IS NULL)`.
- Limits (spec §3.1): category `key` 1–64 characters, category `name` 1–120, at most 30
  categories per template, items 1–100 (unchanged).
- `ValidationFailed` is HTTP 400 `VALIDATION_FAILED`; `TransitionError` 409; `NotFound` 404.
  Category errors are exactly `{"items": "unknown_category"}`, `{"categories": "required"}`,
  `{"categories": "duplicate"}`, `{"categories": "unknown_category"}`.
- **PM is not modified.** `TemplateItemIn` / `TemplateItemOut` in `app/schemas/pm.py` and
  `typed_items.sync_items` do not change; PM's admin (`PmTemplatesAdmin`), which never passes
  categories to `ItemListEditor`, renders and behaves identically — its tests are the guard.
- API models subclass `CamelModel` and live in `app/schemas/checklists.py`.
- No new capabilities: the library routes use `manage_admin` (admin, corporate). The shipped
  checklist routes keep theirs. `server/app/auth/permissions.py` and
  `web/src/auth/capabilities.ts` do not change.
- **Every task that changes `app/schemas/` (enums included) regenerates the client types in that
  same task**: `cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema`, then
  `cd web && npm run gen:types`, then re-export any new names from `web/src/api/types.ts`, and
  add new API models to `test_schema_export.py::test_export_contains_the_public_models`.
  `test_committed_schema_is_current` fails otherwise. Never hand-edit `schema.json` or
  `types.generated.ts`. If the regenerated types break the web build (a new required field on a
  typed test fixture), the same task makes the minimal web fix.
- New tables go in `EXPECTED_TABLES` in `test_models.py`.
- Working-tree files are CRLF, including new files. Edit with the Edit tool (or Python text
  mode), not a Node/sed script that writes bare LF into a CRLF file. After creating a new file,
  convert it from the repo root with
  `.venv/Scripts/python.exe -c "import pathlib,sys;[pathlib.Path(p).write_bytes(pathlib.Path(p).read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')) for p in sys.argv[1:]]" <paths>`
  and, after `git add`, confirm `git ls-files --eol <path>` shows `w/crlf`.
- Commit after every task. The message is a subject line, a blank line, then the trailer
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (name the model that actually wrote
  the task if it differs). The commands below use two `-m` flags, which git joins with exactly
  that blank line. **Never push** — Task 12 stops before `git push`; pushing `main` deploys to
  production and is the controller's call.

## Spec clarifications (decided while planning)

1. **A patch without `categories`** keeps the saved categories, and each item's `categoryKey`
   resolves against the template's saved *active* categories keyed by their own id. The web
   client always sends both lists (a saved category's key is its id), so this only matters to a
   script, and it is what "categories are only replaced when `categories` is sent" needs to be
   usable.
2. **`duplicate`** covers a repeated `key` *and* a repeated `id` in one `categories` list. A saved
   category's `id` — even a soft-deleted one — is "a saved category of this template": it is
   updated in place and reactivated, exactly as `sync_items` treats a retired item's id. Any other
   id (unknown, or another template's) is `{"categories": "unknown_category"}`. All four category
   refusals are checked before anything is written.
3. **Invariant:** an item's `category_id` is NULL or an *active* category of its own template.
   Soft-deleting a category clears it from every item row of that template, retired items
   included, then the same save's `items` may regroup them. So the read side never meets an item
   pointing at a retired category.
4. **Two category read models.** The template's `categories` are `ChecklistCategoryOut` (`id`,
   `name`, `position`) — every active category, empty ones included (the editor shows them). The
   instance detail's `categories` are `ChecklistCategoryProgressOut` (the same plus `done`,
   `total`) — only active categories holding at least one of *this instance's* items, in category
   order, with `done` counted by `typed_items.is_answered`. An unstarted instance counts every
   item as not done. The overall `done / total` is unchanged and still includes ungrouped items.
5. **`unscheduled` with a shift or days** is a 400 `{"shift": "not_allowed"}` from the domain
   (mirroring `on_demand`), so the new CHECK never turns bad input into a 500.
6. **"The on-demand picker excludes it"** is the web's `StartOnDemand` menu, which already
   filters `schedule === 'on_demand'`; there is no server-side on-demand list. The server's
   guarantee is the 409 on `start_on_demand`; the web test pins the menu.
7. **`kind` on a patch:** omitted or `null` leaves it unchanged. On create it defaults to
   `normal`.
8. **Starter library contents.** The spec fixes names, kinds, departments, the categories of
   entries 1–3, and the items it names ("Cash drawer counted" $ 150–250; pool chlorine 1.0–3.0
   ppm, pH 7.2–7.8, pool °F, spa ≤ 104 °F, strip photo; the boiler/chiller readings and log
   photo). This
   plan fills in the rest (Task 5). Entries 4–6 have **no categories** — the spec names none, and
   they exercise the ungrouped path. Readings the spec gives no bounds for have none. A category's
   key in the generated request is `c0`, `c1`, …; a blank import `name` falls back to the
   library name.
9. **Import department suggestion.** The dialog pre-selects the first department whose `type`
   matches the entry's `departmentType`; the admin can change it. The body is
   `{ departmentId }` (the server applies the library name).
10. **Editor ordering.** With categories, `ItemListEditor` shows ungrouped items first, then each
    category's items; `onChange` always receives the items in that grouped order and the save
    sends that order, so positions match what the admin saw. ↑/↓ move an item within its group
    only; the Category select moves it between groups. A blank category name blocks the save
    client-side ("Name every category"), as a weekday-less weekly template already does.
11. **Admin chips.** "Normal N" and "Readings N" are toggle buttons (`aria-pressed`) over the
    whole list; pressing the active one clears the filter. Counts ignore the filter.
12. **Run page collapse state** is per page view (component state), not persisted. Each heading is
    a button named "`<name>`, `<done>` of `<total>` done".
13. **Migration details.** `kind` is added as `VARCHAR(32) NOT NULL DEFAULT 'normal'` with an
    explicitly created `ck_enum_checklistkind` CHECK — what `enum_type()` produces — rather than
    `_enum()` inside `add_column`; the server default stays (the model declares it too).
    `downgrade()` raises `RuntimeError` naming the count when any template is `unscheduled`, then
    otherwise drops the FK/column, restores both 0009 CHECKs, drops `kind` (its CHECK first, which
    SQLite's rebuild needs), and drops the category table. Kind and categories are lost on a
    downgrade, by design.
14. **`typed_items.sync_items` is not changed.** After it runs, the template's active items, by
    position, are exactly the request's items in order (it positions kept items `0..n-1` and
    retires the rest past 1000), so `ck_templates` zips them to assign `category_id`.

## Review Focus

1. **The migration on PostgreSQL** — the CHECK rebuild drops constraints *by name* on Postgres
   (`ck_enum_checklistschedule`, `ck_checklist_template_schedule_fields`) while SQLite recreates
   the table, so SQLite passing proves nothing about production, where a failing `0011` stops the
   service at boot. Expected: upgrade, downgrade, re-upgrade clean on PostgreSQL 18, with an
   existing template becoming `kind = 'normal'`. → Task 1
   (`test_0011_migrates_existing_templates_and_downgrades_cleanly`,
   `test_0011_upgraded_checks_accept_unscheduled_and_refuse_a_bad_kind`), re-proved on Postgres
   in Task 12.
2. **A downgrade while a template is unscheduled** — the 0009 CHECK cannot hold that row.
   Expected: a clear refusal, nothing dropped, `alembic_version` still `0011`. → Task 1
   (`test_0011_downgrade_refuses_while_a_template_is_unscheduled`), re-proved on Postgres with
   seeded data in Task 12.
3. **An admin removes a category that still has items** (or a stale page names one) — the items
   must become ungrouped, never vanish from the checklist page or sit under a ghost heading.
   Expected: items ungrouped server-side; the page shows any item whose category is not listed
   as ungrouped. → Task 3 (`test_removing_a_category_leaves_its_items_ungrouped`), Task 7
   (`never drops an item whose category is not listed`).
4. **A stale or hand-made save** — a `categoryKey` matching nothing, a blank or repeated
   category, another template's category id. Expected: the documented 400, nothing written,
   never a 500 or half a save. → Task 3 (`test_bad_categories_are_400s_and_write_nothing`,
   `test_a_category_of_another_template_is_unknown`,
   `test_an_unknown_category_key_names_the_items_field`).
5. **Editing a template while its checklist is in progress** — Expected: answers never change;
   grouping and headings follow the edit. → Task 3
   (`test_editing_categories_never_changes_a_started_checklists_answers`), Task 4
   (`test_grouping_follows_edits_but_answers_never_change`).

## File map

**Server — create:** `alembic/versions/0011_checklist_structure.py`, `app/domain/ck_library.py`;
tests `test_ck_structure_models.py`, `test_ck_unscheduled.py`, `test_ck_categories.py`,
`test_ck_structure_api.py`, `test_ck_structure_views.py`, `test_ck_library.py`.

**Server — modify:** `app/schemas/enums.py`, `app/models/checklists.py`,
`app/models/__init__.py`, `app/schemas/checklists.py`, `app/domain/ck_templates.py`,
`app/domain/ck_views.py`, `app/api/checklists.py`, `seed/seed.py`, `tests/test_models.py`,
`tests/test_schema_export.py`, `tests/test_seed.py`, `data/app.db`.

**Web — create:** `features/checklists/grouping.ts` (+`grouping.test.ts`),
`api/hooks/checklists.test.tsx`, `features/admin/CategoryListEditor.tsx`,
`features/admin/LibraryImportDialog.tsx` (+test).

**Web — modify:** `api/schema.json` + `api/types.generated.ts` (regenerated), `api/types.ts`,
`api/queryKeys.ts`, `api/hooks/checklists.ts`, `api/fieldErrors.ts` (+test),
`features/checklists/labels.ts`, `features/admin/ItemListEditor.tsx` (+test),
`features/admin/ChecklistTemplatesAdmin.tsx` (+test), `features/checklists/ChecklistRunPage.tsx`
(+`ChecklistRunPage.test.tsx`, `ChecklistRunPage.noteReset.test.tsx`),
`features/checklists/ChecklistsPage.tsx` (+test).

---

### Task 1: Enums, models and migration `0011`

**Files:**
- Modify: `server/app/schemas/enums.py`, `server/app/models/checklists.py`,
  `server/app/models/__init__.py`, `server/tests/test_models.py` (`EXPECTED_TABLES`);
  regenerate `web/src/api/schema.json`, `web/src/api/types.generated.ts`
- Create: `server/alembic/versions/0011_checklist_structure.py`
- Test: `server/tests/test_ck_structure_models.py`

**Interfaces:**
- Produces: enum `ChecklistKind` (`normal`, `readings`) and `ChecklistSchedule.unscheduled` in
  `app.schemas.enums`; model `ChecklistTemplateCategory` (`template_id`, `property_id`, `name`,
  `position`, `active`) exported from `app.models`; `ChecklistTemplate.kind: ChecklistKind`
  (default `normal`); `ChecklistTemplateItem.category_id: str | None`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_models.py` — in `EXPECTED_TABLES` replace the line `    "checklist_photo",`
with `    "checklist_photo", "checklist_template_category",`.

`server/tests/test_ck_structure_models.py`:

```python
"""Checklist structure schema (checklist structure spec §2.1, §6)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import ChecklistTemplate, ChecklistTemplateCategory, ChecklistTemplateItem
from app.schemas.enums import ChecklistKind, ChecklistSchedule, PmItemType, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx, **kw):
    t = ChecklistTemplate(property_id=fx.property_a.id, name="Night Audit",
                          department_id=fx.dept_front_desk.id, **kw)
    db.add(t)
    db.flush()
    return t


def test_unscheduled_has_neither_shift_nor_weekdays(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=Shift.am, weekdays=None)
    with pytest.raises(IntegrityError), database.session() as db:
        _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=None, weekdays=127)
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.unscheduled, shift=None, weekdays=None)
        assert t.kind == ChecklistKind.normal  # the default


def test_an_item_can_sit_in_a_category(database, fx):
    with database.session() as db:
        t = _template(db, fx, schedule=ChecklistSchedule.on_demand, kind=ChecklistKind.readings)
        c = ChecklistTemplateCategory(template_id=t.id, property_id=t.property_id,
                                      name="Payments", position=0)
        db.add(c)
        db.flush()
        db.add(ChecklistTemplateItem(template_id=t.id, property_id=t.property_id, position=0,
                                     label="Batch closed", item_type=PmItemType.checkbox,
                                     category_id=c.id))
        db.flush()
        tid, cid = t.id, c.id
    with database.session() as db:
        item = db.scalar(sa.select(ChecklistTemplateItem)
                         .where(ChecklistTemplateItem.template_id == tid))
        assert (item.category_id, db.get(ChecklistTemplate, tid).kind) == (
            cid, ChecklistKind.readings)
        assert db.get(ChecklistTemplateCategory, cid).active is True


def _cfg(url):
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _seed_0010_rows(engine):
    """A property, a department and a weekly template with one item, as production has."""
    with engine.begin() as conn:
        for sql in (
            "INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at)"
            " VALUES ('p1','P','PPP','UTC','USD','{}','2026-09-10','2026-09-10')",
            "INSERT INTO department (id,property_id,name,type,escalation_minutes,active,"
            "created_at,updated_at) VALUES ('d1','p1','Front Desk','front_desk',15,1,"
            "'2026-09-10','2026-09-10')",
            "INSERT INTO checklist_template (id,property_id,name,department_id,schedule,shift,"
            "weekdays,active,created_at,updated_at) VALUES ('t1','p1','Night Audit','d1',"
            "'weekly','overnight',127,1,'2026-09-10','2026-09-10')",
            "INSERT INTO checklist_template_item (id,template_id,property_id,position,label,"
            "item_type,required,active,created_at,updated_at) VALUES ('i1','t1','p1',0,"
            "'Audit run','checkbox',1,1,'2026-09-10','2026-09-10')",
        ):
            conn.execute(sa.text(sql))


def test_0011_migrates_existing_templates_and_downgrades_cleanly(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT kind FROM checklist_template")).scalar() == "normal"
        assert conn.execute(sa.text(
            "SELECT category_id FROM checklist_template_item")).scalar() is None
    command.downgrade(cfg, "0010")
    inspector = sa.inspect(engine)
    assert "checklist_template_category" not in inspector.get_table_names()
    assert "kind" not in {c["name"] for c in inspector.get_columns("checklist_template")}
    assert "category_id" not in {c["name"]
                                 for c in inspector.get_columns("checklist_template_item")}
    with pytest.raises(IntegrityError), engine.begin() as conn:  # the 0009 CHECK is back
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT name FROM checklist_template")).scalar() == (
            "Night Audit")
        assert conn.execute(sa.text("SELECT count(*) FROM checklist_template_item")).scalar() == 1
    engine.dispose()


def test_0011_upgraded_checks_accept_unscheduled_and_refuse_a_bad_kind(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    command.upgrade(_cfg(url), "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(_cfg(url), "head")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET shift = 'am'"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET kind = 'bogus'"))
    engine.dispose()


def test_0011_downgrade_refuses_while_a_template_is_unscheduled(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = _cfg(url)
    command.upgrade(cfg, "0010")
    engine = sa.create_engine(url)
    _seed_0010_rows(engine)
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE checklist_template SET schedule = 'unscheduled', "
                             "shift = NULL, weekdays = NULL"))
    with pytest.raises(RuntimeError, match="unscheduled"):
        command.downgrade(cfg, "0010")
    inspector = sa.inspect(engine)  # nothing was dropped
    assert "checklist_template_category" in inspector.get_table_names()
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar() == (
            "0011")
    engine.dispose()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_structure_models.py tests/test_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'ChecklistTemplateCategory'`, and
`test_migration_creates_all_tables` missing `checklist_template_category`.

- [ ] **Step 3: Extend the enums** in `server/app/schemas/enums.py`. Replace

```python
class ChecklistSchedule(StrEnum):
    weekly = "weekly"
    on_demand = "on_demand"
```

with

```python
class ChecklistSchedule(StrEnum):
    weekly = "weekly"
    on_demand = "on_demand"
    unscheduled = "unscheduled"  # no shift or days yet; never generated (structure spec §1.2)
```

and append to the end of the file:

```python
class ChecklistKind(StrEnum):
    """Drives a filter and a tag only — no behaviour differs (checklist structure spec §1.2)."""
    normal = "normal"
    readings = "readings"
```

- [ ] **Step 4: Update the models** in `server/app/models/checklists.py`.

Replace the import line
`from app.schemas.enums import ChecklistSchedule, ChecklistStatus, PmItemType, Shift` with

```python
from app.schemas.enums import ChecklistKind, ChecklistSchedule, ChecklistStatus, PmItemType, Shift
```

In `ChecklistTemplate.__table_args__` replace the line

```python
            "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)",
```

with

```python
            "(schedule IN ('on_demand', 'unscheduled') AND shift IS NULL AND weekdays IS NULL)",
```

In `ChecklistTemplate`, after its `active` column, add:

```python
    # server_default so the rows that predate migration 0011 read as normal.
    kind: Mapped[ChecklistKind] = mapped_column(
        enum_type(ChecklistKind), default=ChecklistKind.normal,
        server_default=ChecklistKind.normal.value, nullable=False)


class ChecklistTemplateCategory(TimestampMixin, Base):
    """A named, ordered section of a checklist (checklist structure spec §2.1). Groups items
    only; soft-deleted via `active`. An item's `category_id` is NULL or an active category of
    its own template — `ck_templates` keeps that true."""

    __tablename__ = "checklist_template_category"
    template_id: Mapped[str] = mapped_column(ForeignKey("checklist_template.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

In `ChecklistTemplateItem`, after its `active` column, add:

```python
    category_id: Mapped[str | None] = mapped_column(ForeignKey("checklist_template_category.id"))
```

In `server/app/models/__init__.py` replace

```python
    ChecklistTemplate,
    ChecklistTemplateItem,
)
```

(the first import block) with

```python
    ChecklistTemplate,
    ChecklistTemplateCategory,
    ChecklistTemplateItem,
)
```

and in `__all__` replace the line
`    "ChecklistTemplateItem", "Conversation", "Department", "DigitalAsset", "DraftPrompt", "Guest",`
with

```python
    "ChecklistTemplateCategory", "ChecklistTemplateItem", "Conversation", "Department",
    "DigitalAsset", "DraftPrompt", "Guest",
```

- [ ] **Step 5: Create `server/alembic/versions/0011_checklist_structure.py`**

```python
"""checklist_structure: checklist_template_category, checklist_template_item.category_id,
checklist_template.kind, and the 'unscheduled' schedule

Checklist structure spec §2.1, §6 (docs/superpowers/specs/2026-09-26-checklist-structure-design.md).
One new table, one nullable column on checklist_template_item, one NOT NULL column with a server
default on checklist_template (existing rows become 'normal'), and both of checklist_template's
schedule CHECKs rebuilt to admit 'unscheduled'. The CHECK rebuilds go through batch_alter_table,
as 0004 does: a table rebuild on SQLite, a DROP/ADD CONSTRAINT on PostgreSQL.

downgrade() refuses while any template is unscheduled: the 0009 CHECKs cannot hold such a row,
and silently rewriting its schedule would change what the hotel configured.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-26

"""
import sqlalchemy as sa

import app.db
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

KIND_CHECK = "ck_enum_checklistkind"
SCHEDULE_CHECK = "ck_enum_checklistschedule"
FIELDS_CHECK = "ck_checklist_template_schedule_fields"
ITEM_CATEGORY_FK = "fk_checklist_template_item_category_id"

OLD_SCHEDULE = ("weekly", "on_demand")
NEW_SCHEDULE = (*OLD_SCHEDULE, "unscheduled")
OLD_FIELDS = ("(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
              "AND weekdays > 0) OR "
              "(schedule = 'on_demand' AND shift IS NULL AND weekdays IS NULL)")
NEW_FIELDS = ("(schedule = 'weekly' AND shift IS NOT NULL AND weekdays IS NOT NULL "
              "AND weekdays > 0) OR "
              "(schedule IN ('on_demand', 'unscheduled') AND shift IS NULL AND weekdays IS NULL)")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
    ]


def _listed(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _set_schedule_checks(values: tuple[str, ...], fields_sql: str) -> None:
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.drop_constraint(SCHEDULE_CHECK, type_="check")
        batch_op.drop_constraint(FIELDS_CHECK, type_="check")
        batch_op.create_check_constraint(SCHEDULE_CHECK, f"schedule IN ({_listed(values)})")
        batch_op.create_check_constraint(FIELDS_CHECK, fields_sql)


def upgrade() -> None:
    op.create_table(
        "checklist_template_category",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["checklist_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("checklist_template_category", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_checklist_template_category_template_id"),
                              ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_checklist_template_category_property_id"),
                              ["property_id"], unique=False)

    # A plain VARCHAR plus an explicitly named CHECK — what enum_type() produces — rather than
    # _enum() inside add_column, whose CHECK is not reliably emitted by ALTER TABLE ADD COLUMN.
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kind", sa.String(length=32), nullable=False,
                                      server_default="normal"))
        batch_op.create_check_constraint(KIND_CHECK, "kind IN ('normal', 'readings')")
    _set_schedule_checks(NEW_SCHEDULE, NEW_FIELDS)

    # Nullable, no backfill: every existing item starts ungrouped. The FK is named so
    # downgrade() can drop it by name on both engines (as 0010 does for log_entry).
    with op.batch_alter_table("checklist_template_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(ITEM_CATEGORY_FK, "checklist_template_category",
                                    ["category_id"], ["id"])


def downgrade() -> None:
    unscheduled = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM checklist_template WHERE schedule = 'unscheduled'")).scalar()
    if unscheduled:
        raise RuntimeError(
            f"Refusing to downgrade 0011: {unscheduled} checklist template(s) are unscheduled, "
            "which the 0010 schema cannot store. Give each a weekly or on-demand schedule in "
            "Admin > Checklist templates first.")
    with op.batch_alter_table("checklist_template_item", schema=None) as batch_op:
        batch_op.drop_constraint(ITEM_CATEGORY_FK, type_="foreignkey")
        batch_op.drop_column("category_id")
    _set_schedule_checks(OLD_SCHEDULE, OLD_FIELDS)
    # The CHECK first: SQLite's table rebuild would otherwise carry a CHECK on a dropped column.
    with op.batch_alter_table("checklist_template", schema=None) as batch_op:
        batch_op.drop_constraint(KIND_CHECK, type_="check")
        batch_op.drop_column("kind")
    op.drop_table("checklist_template_category")
```

(On SQLite the batches recreate `checklist_template` and `checklist_template_item`; Alembic's own
connection does not set `PRAGMA foreign_keys`, so the child rows in `checklist_instance`,
`checklist_answer` and `checklist_photo` survive the copy, as they did for `log_entry` in 0010.)

- [ ] **Step 6: Verify the migration matches the models**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_structure_models.py tests/test_ck_models.py tests/test_models.py -q` → PASS.
Then check drift with a throwaway command (do not commit anything):

```bash
cd server && ../.venv/Scripts/python.exe -c "
from app.db import run_migrations, Base; import app.models, sqlalchemy as sa, tempfile, os
from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata
p=os.path.join(tempfile.mkdtemp(),'d.db'); u='sqlite:///'+p.replace(os.sep,'/'); run_migrations(u)
e=sa.create_engine(u); print([d for d in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata) if 'checklist' in str(d)])"
```

Expected: `[]`. Fix any difference in the migration.

- [ ] **Step 7: Regenerate the client types** — `ChecklistSchedule` is in the exported schema, so
`test_committed_schema_is_current` now fails until you do:

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

Expected: the only change in `schema.json` / `types.generated.ts` is `'unscheduled'` added to
`ChecklistSchedule`. No web code needs to change yet (nothing maps every schedule value; the
admin list shows an unscheduled row oddly until Task 9, and nothing can create one until Task 2).

- [ ] **Step 8: Run everything** — full server suite + ruff; `cd web && npm test && npm run lint && npm run build`.

- [ ] **Step 9: Commit**

```bash
git add server/app/schemas/enums.py server/app/models/checklists.py server/app/models/__init__.py server/alembic/versions/0011_checklist_structure.py server/tests/test_ck_structure_models.py server/tests/test_models.py web/src/api/schema.json web/src/api/types.generated.ts
git commit -m "feat(checklists): categories, kind and unscheduled schema - migration 0011" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The `unscheduled` schedule

**Files:**
- Modify: `server/app/domain/ck_templates.py` (`_validate_schedule` only)
- Test: `server/tests/test_ck_unscheduled.py`

**Interfaces:**
- Consumes: Task 1's `ChecklistSchedule.unscheduled`.
- Produces: `ck_templates.create` / `patch` accept `schedule="unscheduled"` with no shift or days,
  and refuse one with either as `ValidationFailed(details={"shift": "not_allowed"})`. The tick
  (`ck_tick.tick`, which only generates `weekly`) and `ck_instances.start_on_demand` (which only
  starts `on_demand`, else `TransitionError`) already exclude it; this task's tests pin that.

- [ ] **Step 1: Write the failing test** — `server/tests/test_ck_unscheduled.py`:

```python
"""The `unscheduled` schedule (checklist structure spec §1.2, §2.2): no shift, no days, never
generated, never started on demand. conftest freezes Thu 2026-09-10 12:00 UTC (AM in New York)."""
import pytest
from sqlalchemy import func, select

from app.domain import ck_instances, ck_templates, ck_tick
from app.errors import TransitionError, ValidationFailed
from app.models import ChecklistInstance
from app.schemas.checklists import ChecklistTemplateIn, ChecklistTemplatePatch
from app.schemas.enums import Role
from tests.ck_helpers import ITEMS, make_template


def test_unscheduled_takes_no_shift_or_days(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift, out.weekdays) == ("unscheduled", None, None)
        for shift, weekdays in (("am", None), (None, 127)):
            with pytest.raises(ValidationFailed) as refused:
                ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(
                    name="x", department_id=fx.dept_engineering.id, schedule="unscheduled",
                    shift=shift, weekdays=weekdays, items=ITEMS))
            assert refused.value.details == {"shift": "not_allowed"}


def test_the_tick_never_generates_an_unscheduled_template(database, fx):
    with database.session() as db:
        make_template(db, fx, name="Every day")  # weekly, AM, every day: the tick's control
        someday = make_template(db, fx, name="Someday", schedule="unscheduled")
        assert ck_tick.tick(db) == {"generated": 1, "missed": 0}
        assert db.scalar(select(func.count()).select_from(ChecklistInstance).where(
            ChecklistInstance.template_id == someday.id)) == 0


def test_an_unscheduled_template_cannot_be_started_on_demand(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        with pytest.raises(TransitionError):
            ck_instances.start_on_demand(db, fx.property_a.id, fx.engineer_a.id,
                                         Role.dept_staff, t.id)


def test_scheduling_it_later_is_an_ordinary_schedule_edit(database, fx):
    with database.session() as db:
        t = make_template(db, fx, schedule="unscheduled")
        with pytest.raises(ValidationFailed) as refused:  # weekly still needs shift + days
            ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                               ChecklistTemplatePatch(schedule="weekly"))
        assert refused.value.details == {"weekdays": "required"}
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="weekly", shift="pm", weekdays=0b0011111))
        out = ck_templates.to_out(db, t)
        assert (out.schedule.value, out.shift.value, out.weekdays) == ("weekly", "pm", 31)
        ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            schedule="unscheduled", shift=None, weekdays=None))
        assert ck_templates.to_out(db, t).schedule.value == "unscheduled"


def test_unscheduled_over_http(database, fx, login):
    admin = login("admin@hvh.test")
    base = f"/api/p/{fx.property_a.id}/checklists"
    res = admin.post(f"{base}/templates", json={
        "name": "Deep clean", "departmentId": fx.dept_engineering.id, "schedule": "unscheduled",
        "items": [{"label": "Done", "itemType": "checkbox"}]})
    assert res.status_code == 201, res.get_json()
    assert (res.get_json()["schedule"], res.get_json()["shift"]) == ("unscheduled", None)
    started = login("engineer@hvh.test").post(f"{base}/templates/{res.get_json()['id']}/start")
    assert started.status_code == 409
```

(`tests.ck_helpers.make_template` already passes `shift=None, weekdays=None` for any schedule
other than `weekly`.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_unscheduled.py -q`
Expected: `test_unscheduled_takes_no_shift_or_days` FAILS with an `IntegrityError` from the new
CHECK (the domain lets `shift="am"` through to the database — the 500 this task removes). The
tick and on-demand tests already pass: they pin behaviour the shipped code has.

- [ ] **Step 3: Implement** — in `server/app/domain/ck_templates.py`, at the end of
`_validate_schedule`, after the `on_demand` check, add:

```python
    if schedule == ChecklistSchedule.unscheduled and (shift is not None or weekdays is not None):
        raise ValidationFailed("An unscheduled checklist has no shift or days yet",
                               details={"shift": "not_allowed"})
```

- [ ] **Step 4: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_unscheduled.py tests/test_ck_templates.py tests/test_ck_tick.py tests/test_ck_instances.py -q` → PASS; then the full
server suite and ruff.

- [ ] **Step 5: Commit**

```bash
git add server/app/domain/ck_templates.py server/tests/test_ck_unscheduled.py
git commit -m "feat(checklists): save a checklist without a schedule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Template wire models, kind and category saves

**Files:**
- Modify: `server/app/schemas/checklists.py`, `server/app/domain/ck_templates.py` (replace),
  `server/tests/test_schema_export.py`; regenerate `web/src/api/schema.json`,
  `web/src/api/types.generated.ts`; modify `web/src/api/types.ts`,
  `web/src/features/checklists/ChecklistsPage.test.tsx` (one fixture)
- Test: `server/tests/test_ck_categories.py`, `server/tests/test_ck_structure_api.py`

**Interfaces:**
- Consumes: Task 1's models and `ChecklistKind`; Task 2's `_validate_schedule`.
- Produces schemas (in `app.schemas.checklists`): `MAX_CATEGORIES = 30`;
  `ChecklistItemIn(TemplateItemIn)` + `category_key: str | None` (1–64);
  `ChecklistCategoryIn` (`key` 1–64, `id: str | None`, `name` 1–120);
  `ChecklistItemOut(TemplateItemOut)` + `category_id: str | None`; `ChecklistCategoryOut`
  (`id`, `name`, `position`); `ChecklistTemplateIn` / `ChecklistTemplatePatch` gain `kind`,
  `categories`, and `items: list[ChecklistItemIn]`; `ChecklistTemplateOut` gains
  `kind: ChecklistKind`, `categories: list[ChecklistCategoryOut]`, `items:
  list[ChecklistItemOut]`.
- Produces (in `app.domain.ck_templates`): `active_categories(db, template_id) ->
  list[ChecklistTemplateCategory]` (active, by position); `to_out` fills `kind`, `categories`,
  items' `category_id`; `create` / `patch` save categories and each item's category. Existing
  `get`, `active_items`, `list_templates`, `create`, `patch` keep their signatures.
- Web types re-exported from `web/src/api/types.ts`: `ChecklistCategoryIn`,
  `ChecklistCategoryOut`, `ChecklistItemIn`, `ChecklistItemOut`, `ChecklistKind`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_ck_categories.py`:

```python
"""Categories and kind on checklist templates (checklist structure spec §2, §3.2)."""
import pytest
from sqlalchemy import select

from app.domain import ck_instances, ck_templates
from app.errors import ValidationFailed
from app.models import ChecklistAnswer, ChecklistTemplateCategory
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistItemIn,
    ChecklistTemplateIn,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistKind, Role
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today

CATEGORIES = [ChecklistCategoryIn(key="audit", name="Audit"),
              ChecklistCategoryIn(key="pay", name="Payments")]
ITEMS = [
    ChecklistItemIn(label="Night audit run", item_type="checkbox", category_key="audit"),
    ChecklistItemIn(label="Card batch closed", item_type="checkbox", category_key="pay"),
    ChecklistItemIn(label="Notes", item_type="text", required=False),
]


def _create(db, fx, **over):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(**{
        "name": "Night Audit", "department_id": fx.dept_front_desk.id, "schedule": "on_demand",
        "categories": CATEGORIES, "items": ITEMS, **over}))


def _patch(db, fx, t, **fields):
    return ck_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                              ChecklistTemplatePatch(**fields))


def _grouping(out):
    names = {c.id: c.name for c in out.categories}
    return [(i.label, names.get(i.category_id)) for i in out.items]


def _again(out, **over):
    """The saved template as a patch body: categories keyed by id, items by their category."""
    categories = [ChecklistCategoryIn(key=c.id, id=c.id, name=c.name) for c in out.categories]
    items = [ChecklistItemIn(id=i.id, label=i.label, item_type=i.item_type,
                             required=i.required, category_key=i.category_id)
             for i in out.items]
    return {"categories": categories, "items": items, **over}


def test_create_saves_categories_in_order_and_groups_the_items(database, fx):
    with database.session() as db:
        out = ck_templates.to_out(db, _create(db, fx))
        assert [(c.name, c.position) for c in out.categories] == [("Audit", 0), ("Payments", 1)]
        assert _grouping(out) == [("Night audit run", "Audit"), ("Card batch closed", "Payments"),
                                  ("Notes", None)]


def test_kind_defaults_to_normal_and_round_trips(database, fx):
    with database.session() as db:
        assert ck_templates.to_out(db, make_template(db, fx)).kind == ChecklistKind.normal
        t = _create(db, fx, kind="readings")
        assert ck_templates.to_out(db, t).kind == ChecklistKind.readings
        _patch(db, fx, t, kind="normal")
        assert ck_templates.to_out(db, t).kind == ChecklistKind.normal
        _patch(db, fx, t, name="Night Audit 2")  # kind not sent: unchanged
        assert ck_templates.to_out(db, t).kind == ChecklistKind.normal


def test_patch_renames_reorders_adds_removes_and_moves_items(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        audit, pay = out.categories
        run, batch, notes = out.items
        _patch(db, fx, t, categories=[
            ChecklistCategoryIn(key="p", id=pay.id, name="Payments & cards"),
            ChecklistCategoryIn(key="new", name="Reports"),
        ], items=[
            ChecklistItemIn(id=run.id, label=run.label, item_type="checkbox", category_key="new"),
            ChecklistItemIn(id=batch.id, label=batch.label, item_type="checkbox",
                            category_key="p"),
            ChecklistItemIn(id=notes.id, label="Notes", item_type="text", required=False,
                            category_key="p"),
        ])
        after = ck_templates.to_out(db, t)
        assert [(c.name, c.position) for c in after.categories] == [
            ("Payments & cards", 0), ("Reports", 1)]
        assert after.categories[0].id == pay.id  # updated in place, not recreated
        assert _grouping(after) == [("Night audit run", "Reports"),
                                    ("Card batch closed", "Payments & cards"),
                                    ("Notes", "Payments & cards")]
        retired = db.get(ChecklistTemplateCategory, audit.id)
        assert retired.active is False  # soft-deleted, never removed


def test_removing_a_category_leaves_its_items_ungrouped(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        _patch(db, fx, t, categories=[ChecklistCategoryIn(key="pay", id=out.categories[1].id,
                                                          name="Payments")])
        assert _grouping(ck_templates.to_out(db, t)) == [
            ("Night audit run", None), ("Card batch closed", "Payments"), ("Notes", None)]


def test_patching_items_alone_keeps_categories_and_resolves_saved_ids(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        body = _again(out)
        _patch(db, fx, t, items=[*body["items"][:2], ChecklistItemIn(
            id=out.items[2].id, label="Notes", item_type="text", required=False,
            category_key=out.categories[0].id)])
        after = ck_templates.to_out(db, t)
        assert [c.name for c in after.categories] == ["Audit", "Payments"]
        assert _grouping(after)[2] == ("Notes", "Audit")


def test_patching_categories_alone_keeps_item_assignments(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        out = ck_templates.to_out(db, t)
        _patch(db, fx, t, categories=_again(out)["categories"][::-1])  # reorder only
        after = ck_templates.to_out(db, t)
        assert [c.name for c in after.categories] == ["Payments", "Audit"]
        assert _grouping(after) == _grouping(out)


@pytest.mark.parametrize("categories, items, details", [
    (CATEGORIES, [ChecklistItemIn(label="x", item_type="checkbox", category_key="nope")],
     {"items": "unknown_category"}),
    ([ChecklistCategoryIn(key="a", name="   ")], ITEMS[2:], {"categories": "required"}),
    ([ChecklistCategoryIn(key="a", name="A"), ChecklistCategoryIn(key="a", name="B")],
     ITEMS[2:], {"categories": "duplicate"}),
    ([ChecklistCategoryIn(key="a", id="00000000-0000-0000-0000-000000000000", name="A")],
     ITEMS[2:], {"categories": "unknown_category"}),
])
def test_bad_categories_are_400s_and_write_nothing(database, fx, categories, items, details):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as refused:
            _create(db, fx, categories=categories, items=items)
        assert refused.value.details == details
        assert ck_templates.list_templates(db, fx.property_a.id) == []


def test_a_category_of_another_template_is_unknown(database, fx):
    with database.session() as db:
        other = ck_templates.to_out(db, _create(db, fx, name="Other"))
        t = _create(db, fx)
        with pytest.raises(ValidationFailed) as refused:
            _patch(db, fx, t, categories=[ChecklistCategoryIn(
                key="x", id=other.categories[0].id, name="Audit")])
        assert refused.value.details == {"categories": "unknown_category"}
        assert ck_templates.to_out(db, t).categories[0].id != other.categories[0].id


def test_editing_categories_never_changes_a_started_checklists_answers(database, fx):
    with database.session() as db:
        t = _create(db, fx)
        inst = ck_instances.start_on_demand(db, fx.property_a.id, fx.agent_a.id, Role.agent,
                                            t.id)
        before = {(a.item_id, a.bool_value) for a in db.scalars(
            select(ChecklistAnswer).where(ChecklistAnswer.instance_id == inst.id)).all()}
        first = ck_templates.to_out(db, t).items[0]
        _patch(db, fx, t, categories=[], items=[ChecklistItemIn(
            id=first.id, label=first.label, item_type="checkbox")])
        after = {(a.item_id, a.bool_value) for a in db.scalars(
            select(ChecklistAnswer).where(ChecklistAnswer.instance_id == inst.id)).all()}
        assert after == before and len(after) == 3


def test_an_old_checklist_still_saves_without_categories(database, fx):
    """Regression: the shipped create/patch path (PM's item model, no categories) is unchanged."""
    with database.session() as db:
        t = make_template(db, fx)
        assert ck_templates.to_out(db, t).categories == []
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
        assert inst.template_id == t.id
```

`server/tests/test_ck_structure_api.py`:

```python
"""Checklist structure over HTTP (checklist structure spec §3): camelCase on the wire."""

TEMPLATE = {
    "name": "Night Audit", "schedule": "on_demand", "kind": "readings",
    "categories": [{"key": "a", "name": "Audit"}, {"key": "p", "name": "Payments"}],
    "items": [{"label": "Night audit run", "itemType": "checkbox", "categoryKey": "a"},
              {"label": "Card batch closed", "itemType": "checkbox", "categoryKey": "p"},
              {"label": "Notes", "itemType": "text", "required": False}],
}


def _ck(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists{rest}"


def _create(login, fx, **over):
    body = {**TEMPLATE, "departmentId": fx.dept_front_desk.id, **over}
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json=body)
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_categories_and_kind_round_trip(app, fx, login):
    created = _create(login, fx)
    assert created["kind"] == "readings"
    assert [(c["name"], c["position"]) for c in created["categories"]] == [("Audit", 0),
                                                                          ("Payments", 1)]
    audit, pay = (c["id"] for c in created["categories"])
    assert [i["categoryId"] for i in created["items"]] == [audit, pay, None]
    listed = login("agent@hvh.test").get(_ck(fx, "/templates")).get_json()
    assert listed[0]["categories"] == created["categories"]


def test_patch_with_categories_keyed_by_saved_id(app, fx, login):
    created = _create(login, fx)
    audit, pay = created["categories"]
    items = [{"id": i["id"], "label": i["label"], "itemType": i["itemType"],
              "required": i["required"], "categoryKey": pay["id"]} for i in created["items"]]
    res = login("admin@hvh.test").patch(_ck(fx, f"/templates/{created['id']}"), json={
        "categories": [{"key": pay["id"], "id": pay["id"], "name": "Payments"}],
        "items": items})
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert [c["name"] for c in body["categories"]] == ["Payments"]
    assert {i["categoryId"] for i in body["items"]} == {pay["id"]}


def test_an_unknown_category_key_names_the_items_field(app, fx, login):
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json={
        **TEMPLATE, "departmentId": fx.dept_front_desk.id,
        "items": [{"label": "x", "itemType": "checkbox", "categoryKey": "zzz"}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"items": "unknown_category"}


def test_more_than_thirty_categories_is_a_400(app, fx, login):
    res = login("admin@hvh.test").post(_ck(fx, "/templates"), json={
        **TEMPLATE, "departmentId": fx.dept_front_desk.id,
        "categories": [{"key": f"k{n}", "name": f"C{n}"} for n in range(31)]})
    assert res.status_code == 400


def test_pm_items_still_refuse_a_category_key(app, fx, login):
    """PM's TemplateItemIn is not modified (spec §3.1): it still rejects unknown fields."""
    res = login("admin@hvh.test").post(f"/api/p/{fx.property_a.id}/pm/templates", json={
        "name": "Quarterly", "mode": "sweep", "unitKind": "guest_room", "cadence": "quarterly",
        "items": [{"label": "Filter", "itemType": "checkbox", "categoryKey": "a"}]})
    assert res.status_code == 400
```

In `server/tests/test_schema_export.py` replace
`                 "ChecklistInstanceOut", "ChecklistAssignRequest"):` with

```python
                 "ChecklistInstanceOut", "ChecklistAssignRequest",
                 "ChecklistItemIn", "ChecklistItemOut", "ChecklistCategoryIn",
                 "ChecklistCategoryOut", "ChecklistTemplatePatch"):
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_categories.py tests/test_ck_structure_api.py tests/test_schema_export.py -q`
Expected: FAIL — `ImportError: cannot import name 'ChecklistCategoryIn'`; the API tests 400 on
the unknown `kind`/`categories` fields (`extra="forbid"`); missing schema names.

- [ ] **Step 3: Add the wire models** — `server/app/schemas/checklists.py`.

Replace the import line `from app.schemas.enums import ChecklistSchedule, ChecklistStatus, Shift`
with

```python
from app.schemas.enums import ChecklistKind, ChecklistSchedule, ChecklistStatus, Shift
```

Replace the three classes `ChecklistTemplateIn`, `ChecklistTemplatePatch` and
`ChecklistTemplateOut` (everything from `class ChecklistTemplateIn(CamelModel):` down to, not
including, `class ChecklistInstanceRowOut(CamelModel):`) with:

```python
MAX_CATEGORIES = 30


class ChecklistItemIn(TemplateItemIn):
    """PM's item plus the category it sits under, named by a `key` from the same request's
    `categories` (checklist structure spec §3.2). PM's own TemplateItemIn is unchanged."""

    category_key: str | None = Field(default=None, min_length=1, max_length=64)


class ChecklistCategoryIn(CamelModel):
    """`key` is the client's handle for this category within one request; `id` names a saved
    category to update in place. A saved category missing from the list is soft-deleted."""

    key: str = Field(min_length=1, max_length=64)
    id: str | None = None
    name: str = Field(min_length=1, max_length=120)


class ChecklistItemOut(TemplateItemOut):
    category_id: str | None = None


class ChecklistCategoryOut(CamelModel):
    id: str
    name: str
    position: int


class ChecklistTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    department_id: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool = True
    kind: ChecklistKind = ChecklistKind.normal
    categories: list[ChecklistCategoryIn] = Field(default_factory=list,
                                                  max_length=MAX_CATEGORIES)
    items: list[ChecklistItemIn] = Field(min_length=1, max_length=100)


class ChecklistTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    department_id: str | None = None
    schedule: ChecklistSchedule | None = None
    shift: Shift | None = None
    weekdays: int | None = Field(default=None, ge=1, le=127)
    active: bool | None = None
    kind: ChecklistKind | None = None
    categories: list[ChecklistCategoryIn] | None = Field(default=None, max_length=MAX_CATEGORIES)
    items: list[ChecklistItemIn] | None = Field(default=None, min_length=1, max_length=100)


class ChecklistTemplateOut(CamelModel):
    id: str
    name: str
    department_id: str
    department_name: str
    schedule: ChecklistSchedule
    shift: Shift | None = None
    weekdays: int | None = None
    active: bool
    kind: ChecklistKind
    categories: list[ChecklistCategoryOut]
    items: list[ChecklistItemOut]


```

(`CamelModel` has `from_attributes=True`, so existing callers that pass PM's `TemplateItemIn`
objects — `tests/ck_helpers.py`, the seed — still validate as `ChecklistItemIn` with no category.)

- [ ] **Step 4: Replace `server/app/domain/ck_templates.py`** with:

```python
"""Checklist templates (checklists spec §2.1, §3.4). Items sync through the same shared rules as
PM templates: replace-by-list, soft deletes, an item's type never changes. Categories (checklist
structure spec §3.2) save in the same request: replace-by-list with soft deletes, and each item
names its category by a request-local `key`.

Invariant: an item's `category_id` is NULL or an *active* category of its own template —
retiring a category clears it from every item that pointed at it."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import audit, typed_items
from app.errors import NotFound, ValidationFailed
from app.models import (
    ChecklistTemplate,
    ChecklistTemplateCategory,
    ChecklistTemplateItem,
    Department,
)
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistCategoryOut,
    ChecklistItemIn,
    ChecklistItemOut,
    ChecklistTemplateIn,
    ChecklistTemplateOut,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistSchedule


def get(db: Session, property_id: str, template_id: str) -> ChecklistTemplate:
    t = db.scalar(select(ChecklistTemplate).where(ChecklistTemplate.id == template_id,
                                                  ChecklistTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Checklist template not found")
    return t


def active_items(db: Session, template_id: str) -> list[ChecklistTemplateItem]:
    return list(db.scalars(select(ChecklistTemplateItem).where(
        ChecklistTemplateItem.template_id == template_id,
        ChecklistTemplateItem.active.is_(True)).order_by(ChecklistTemplateItem.position)).all())


def active_categories(db: Session, template_id: str) -> list[ChecklistTemplateCategory]:
    return list(db.scalars(select(ChecklistTemplateCategory).where(
        ChecklistTemplateCategory.template_id == template_id,
        ChecklistTemplateCategory.active.is_(True))
        .order_by(ChecklistTemplateCategory.position)).all())


def to_out(db: Session, t: ChecklistTemplate) -> ChecklistTemplateOut:
    dept = db.get(Department, t.department_id)
    return ChecklistTemplateOut(
        id=t.id, name=t.name, department_id=t.department_id, department_name=dept.name,
        schedule=t.schedule, shift=t.shift, weekdays=t.weekdays, active=t.active, kind=t.kind,
        categories=[ChecklistCategoryOut.model_validate(c, from_attributes=True)
                    for c in active_categories(db, t.id)],
        items=[ChecklistItemOut.model_validate(i, from_attributes=True)
               for i in active_items(db, t.id)])


def list_templates(db: Session, property_id: str) -> list[ChecklistTemplateOut]:
    rows = db.scalars(select(ChecklistTemplate).where(ChecklistTemplate.property_id == property_id)
                      .order_by(ChecklistTemplate.name, ChecklistTemplate.id)).all()
    return [to_out(db, t) for t in rows]


def _validate_schedule(schedule, shift, weekdays) -> None:
    if schedule == ChecklistSchedule.weekly and (shift is None or not weekdays):
        raise ValidationFailed("A weekly checklist needs a shift and at least one day",
                               details={"weekdays": "required"})
    if schedule == ChecklistSchedule.on_demand and (shift is not None or weekdays is not None):
        raise ValidationFailed("An on-demand checklist has no shift or days — it takes the shift "
                               "it is started in", details={"shift": "not_allowed"})
    if schedule == ChecklistSchedule.unscheduled and (shift is not None or weekdays is not None):
        raise ValidationFailed("An unscheduled checklist has no shift or days yet",
                               details={"shift": "not_allowed"})


def _assert_department(db: Session, property_id: str, department_id: str) -> None:
    if db.scalar(select(Department.id).where(Department.id == department_id,
                                             Department.property_id == property_id)) is None:
        raise ValidationFailed("Unknown department", details={"departmentId": "unknown"})


def _check_categories(db: Session, template_id: str | None,
                      categories: list[ChecklistCategoryIn]) -> None:
    """Every refusal before any write (spec §3.2), so a 400 never leaves half a save behind."""
    keys: set[str] = set()
    ids: set[str] = set()
    for c in categories:
        if c.key in keys or (c.id is not None and c.id in ids):
            raise ValidationFailed("A category is listed twice",
                                   details={"categories": "duplicate"})
        keys.add(c.key)
        if c.id is not None:
            ids.add(c.id)
        if not c.name.strip():
            raise ValidationFailed("A category needs a name", details={"categories": "required"})
    saved = set() if template_id is None else set(db.scalars(
        select(ChecklistTemplateCategory.id).where(
            ChecklistTemplateCategory.template_id == template_id)).all())
    if ids - saved:
        raise ValidationFailed("That category is not part of this checklist",
                               details={"categories": "unknown_category"})


def _check_item_keys(items: list[ChecklistItemIn], keys: set[str]) -> None:
    if any(i.category_key is not None and i.category_key not in keys for i in items):
        raise ValidationFailed("An item names a category that is not in this checklist",
                               details={"items": "unknown_category"})


def _sync_categories(db: Session, template: ChecklistTemplate,
                     categories: list[ChecklistCategoryIn]) -> dict[str, str]:
    """Replace-by-list with soft deletes. Returns the category id for each request `key`."""
    existing = {c.id: c for c in db.scalars(select(ChecklistTemplateCategory).where(
        ChecklistTemplateCategory.template_id == template.id)).all()}
    by_key: dict[str, str] = {}
    for position, data in enumerate(categories):
        row = existing.get(data.id) if data.id else None
        if row is None:
            row = ChecklistTemplateCategory(template_id=template.id,
                                            property_id=template.property_id,
                                            name=data.name.strip(), position=position)
            db.add(row)
            db.flush()
        else:
            row.name, row.position, row.active = data.name.strip(), position, True
        by_key[data.key] = row.id
    retired = {row.id for row in existing.values() if row.id not in by_key.values()}
    for row in existing.values():
        if row.id in retired:
            row.active = False
    if retired:  # its items become ungrouped unless this same save regroups them
        for item in db.scalars(select(ChecklistTemplateItem).where(
                ChecklistTemplateItem.template_id == template.id,
                ChecklistTemplateItem.category_id.in_(retired))).all():
            item.category_id = None
    db.flush()
    return by_key


def _sync_items(db: Session, template: ChecklistTemplate, items: list[ChecklistItemIn],
                by_key: dict[str, str]) -> None:
    typed_items.sync_items(db, ChecklistTemplateItem, template, items)
    # sync_items gives the kept items positions 0..n-1 in request order and retires the rest,
    # so the active items, by position, line up one-to-one with the request.
    for row, data in zip(active_items(db, template.id), items, strict=True):
        row.category_id = by_key[data.category_key] if data.category_key else None
    db.flush()


def create(db: Session, property_id: str, actor_id: str,
           data: ChecklistTemplateIn) -> ChecklistTemplate:
    _validate_schedule(data.schedule, data.shift, data.weekdays)
    _assert_department(db, property_id, data.department_id)
    _check_categories(db, None, data.categories)
    _check_item_keys(data.items, {c.key for c in data.categories})
    t = ChecklistTemplate(property_id=property_id, name=data.name.strip(),
                          department_id=data.department_id, schedule=data.schedule,
                          shift=data.shift, weekdays=data.weekdays, active=data.active,
                          kind=data.kind)
    db.add(t)
    db.flush()
    by_key = _sync_categories(db, t, data.categories)
    _sync_items(db, t, data.items, by_key)
    audit.record(db, property_id, actor_id, "checklist_template.created", "checklist_template",
                 t.id, after={"name": t.name})
    return t


def patch(db: Session, property_id: str, actor_id: str, template_id: str,
          data: ChecklistTemplatePatch) -> ChecklistTemplate:
    t = get(db, property_id, template_id)
    provided = data.model_dump(exclude_unset=True)
    schedule = provided.get("schedule", t.schedule)
    shift = provided["shift"] if "shift" in provided else t.shift
    weekdays = provided["weekdays"] if "weekdays" in provided else t.weekdays
    _validate_schedule(schedule, shift, weekdays)
    if data.categories is not None:
        _check_categories(db, t.id, data.categories)
        keys = {c.key for c in data.categories}
    else:  # categories not sent: they stand as saved, each keyed by its own id (clarification 1)
        keys = {c.id for c in active_categories(db, t.id)}
    if data.items is not None:
        _check_item_keys(data.items, keys)
    if "department_id" in provided:
        _assert_department(db, property_id, data.department_id)
        t.department_id = data.department_id
    if "name" in provided:
        t.name = data.name.strip()
    if "active" in provided:
        t.active = data.active
    if data.kind is not None:
        t.kind = data.kind
    t.schedule, t.shift, t.weekdays = schedule, shift, weekdays
    db.flush()
    by_key = (_sync_categories(db, t, data.categories) if data.categories is not None
              else {key: key for key in keys})
    if data.items is not None:
        _sync_items(db, t, data.items, by_key)
    audit.record(db, property_id, actor_id, "checklist_template.updated", "checklist_template",
                 t.id, after={"fields": sorted(provided)})
    return t
```

- [ ] **Step 5: Run the server tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_categories.py tests/test_ck_structure_api.py tests/test_ck_templates.py tests/test_ck_unscheduled.py tests/test_pm_templates.py -q`
→ PASS (except `test_schema_export.py`, fixed next). Then ruff.

- [ ] **Step 6: Regenerate the client types and fix the one typed web fixture**

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

In `web/src/api/types.ts` replace the line
`  ChecklistTemplateIn, ChecklistTemplateOut, ChecklistTemplatePatch,` with

```ts
  ChecklistTemplateIn, ChecklistTemplateOut, ChecklistTemplatePatch,
  ChecklistCategoryIn, ChecklistCategoryOut, ChecklistItemIn, ChecklistItemOut, ChecklistKind,
```

`ChecklistTemplateOut` now requires `kind` and `categories`, so `npm run build` fails on the
typed fixture in `web/src/features/checklists/ChecklistsPage.test.tsx`. Replace

```ts
  schedule: 'on_demand', shift: null, weekdays: null, active: true, items: [],
}
```

with

```ts
  schedule: 'on_demand', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [], items: [],
}
```

(`ChecklistTemplatesAdmin.tsx` still compiles: `kind` and `categories` are optional on
`ChecklistTemplateIn`, and `categoryKey` is optional on `ChecklistItemIn`.)

- [ ] **Step 7: Run everything**

Run the full server suite (`test_schema_export.py` and `test_isolation.py` included) + ruff; then
`cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 8: Commit**

```bash
git add server/app/schemas/checklists.py server/app/domain/ck_templates.py server/tests/test_ck_categories.py server/tests/test_ck_structure_api.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts web/src/features/checklists/ChecklistsPage.test.tsx
git commit -m "feat(checklists): template kind and categories, saved with the items" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Read side — per-category progress on the checklist, the kind on every row

**Files:**
- Modify: `server/app/schemas/checklists.py`, `server/app/domain/ck_views.py`,
  `server/tests/test_schema_export.py`; regenerate `web/src/api/schema.json`,
  `web/src/api/types.generated.ts`; modify `web/src/api/types.ts`,
  `web/src/features/checklists/ChecklistRunPage.test.tsx`,
  `web/src/features/checklists/ChecklistRunPage.noteReset.test.tsx`,
  `web/src/features/checklists/ChecklistsPage.test.tsx` (typed fixtures only)
- Test: `server/tests/test_ck_structure_views.py`

**Interfaces:**
- Consumes: Task 3's `ChecklistItemOut`, `ChecklistCategoryOut`, `ck_templates.active_categories`.
- Produces: `ChecklistCategoryProgressOut(ChecklistCategoryOut)` + `done: int`, `total: int`;
  `ChecklistInstanceRowOut.kind: ChecklistKind` (so the missed list and the instance detail carry
  it too); `ChecklistInstanceOut.categories: list[ChecklistCategoryProgressOut]` (clarification
  4) and `ChecklistInstanceOut.items: list[ChecklistItemOut]`. Web type
  `ChecklistCategoryProgressOut` re-exported from `web/src/api/types.ts`.

- [ ] **Step 1: Write the failing test** — `server/tests/test_ck_structure_views.py`:

```python
"""Read side of checklist structure (spec §2.2): per-category progress and the kind on rows."""
from app.domain import ck_instances, ck_templates, ck_views
from app.schemas.checklists import (
    ChecklistCategoryIn,
    ChecklistInstanceQuery,
    ChecklistItemIn,
    ChecklistTemplateIn,
    ChecklistTemplatePatch,
)
from app.schemas.enums import ChecklistKind, Role
from app.schemas.pm import AnswerPatch
from tests.ck_helpers import make_template
from tests.hk_helpers import local_today


def _night_audit(db, fx, **over):
    return ck_templates.create(db, fx.property_a.id, fx.admin_a.id, ChecklistTemplateIn(**{
        "name": "Night Audit", "department_id": fx.dept_front_desk.id, "schedule": "weekly",
        "shift": "am", "weekdays": 127,
        "categories": [ChecklistCategoryIn(key="a", name="Audit"),
                       ChecklistCategoryIn(key="p", name="Payments"),
                       ChecklistCategoryIn(key="e", name="Empty")],
        "items": [
            ChecklistItemIn(label="Night audit run", item_type="checkbox", category_key="a"),
            ChecklistItemIn(label="Audit total", item_type="number", category_key="a"),
            ChecklistItemIn(label="Card batch closed", item_type="checkbox", category_key="p"),
            ChecklistItemIn(label="Notes", item_type="text", required=False),
        ], **over}))


def _progress(detail):
    return [(c.name, c.done, c.total) for c in detail.categories]


def test_an_unstarted_checklist_shows_every_category_at_zero(database, fx):
    with database.session() as db:
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, fx.property_a.id))
        detail = ck_views.detail(db, fx.property_a.id, inst.id)
        # "Empty" holds no items, so it has no heading; "Notes" is ungrouped
        assert _progress(detail) == [("Audit", 0, 2), ("Payments", 0, 1)]
        names = {c.id: c.name for c in detail.categories}
        assert [(i.label, names.get(i.category_id)) for i in detail.items] == [
            ("Night audit run", "Audit"), ("Audit total", "Audit"),
            ("Card batch closed", "Payments"), ("Notes", None)]


def test_progress_counts_answered_items_per_category(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, pid))
        ck_instances.start(db, pid, fx.agent_a.id, Role.agent, inst.id)
        detail = ck_views.detail(db, pid, inst.id)
        answer_for = {a.item_id: a.id for a in detail.answers}
        by_label = {i.label: i.id for i in detail.items}
        for label, patch in (("Night audit run", AnswerPatch(bool_value=True)),
                             ("Notes", AnswerPatch(text_value="Quiet night"))):
            ck_instances.save_answer(db, pid, fx.agent_a.id, Role.agent, inst.id,
                                     answer_for[by_label[label]], patch)
        detail = ck_views.detail(db, pid, inst.id)
        assert _progress(detail) == [("Audit", 1, 2), ("Payments", 0, 1)]
        assert (detail.done, detail.total) == (2, 4)  # the ungrouped answer still counts overall


def test_grouping_follows_edits_but_answers_never_change(database, fx):
    with database.session() as db:
        pid = fx.property_a.id
        t = _night_audit(db, fx)
        inst, _ = ck_instances.ensure_instance(db, t, local_today(db, pid))
        ck_instances.start(db, pid, fx.agent_a.id, Role.agent, inst.id)
        before = ck_views.detail(db, pid, inst.id)
        audit = before.categories[0]
        ck_templates.patch(db, pid, fx.admin_a.id, t.id, ChecklistTemplatePatch(
            categories=[ChecklistCategoryIn(key="a", id=audit.id, name="Audit & reports")]))
        after = ck_views.detail(db, pid, inst.id)
        assert _progress(after) == [("Audit & reports", 0, 2)]  # Payments retired: ungrouped
        assert after.answers == before.answers
        assert [i.id for i in after.items] == [i.id for i in before.items]


def test_rows_carry_the_kind(database, fx):
    with database.session() as db:
        pid, today = fx.property_a.id, local_today(db, fx.property_a.id)
        ck_instances.ensure_instance(db, make_template(db, fx, name="Rounds"), today)
        ck_instances.ensure_instance(db, _night_audit(db, fx, kind="readings"), today)
        rows = ck_views.list_instances(db, pid, ChecklistInstanceQuery())
        assert {(r.template_name, r.kind) for r in rows} == {
            ("Rounds", ChecklistKind.normal), ("Night Audit", ChecklistKind.readings)}


def test_the_kind_is_on_the_detail_over_http(database, fx, login):
    with database.session() as db:
        inst, _ = ck_instances.ensure_instance(db, _night_audit(db, fx, kind="readings"),
                                               local_today(db, fx.property_a.id))
        iid = inst.id
    body = login("agent@hvh.test").get(
        f"/api/p/{fx.property_a.id}/checklists/instances/{iid}").get_json()
    assert body["kind"] == "readings"
    assert [(c["name"], c["done"], c["total"]) for c in body["categories"]] == [
        ("Audit", 0, 2), ("Payments", 0, 1)]
    assert body["items"][0]["categoryId"] == body["categories"][0]["id"]
```

In `server/tests/test_schema_export.py` replace
`                 "ChecklistCategoryOut", "ChecklistTemplatePatch"):` with

```python
                 "ChecklistCategoryOut", "ChecklistTemplatePatch",
                 "ChecklistCategoryProgressOut"):
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_structure_views.py -q`
Expected: FAIL — `AttributeError: 'ChecklistInstanceOut' object has no attribute 'categories'`
/ `'ChecklistInstanceRowOut' object has no attribute 'kind'`.

- [ ] **Step 3: Extend the read models** — `server/app/schemas/checklists.py`.

Insert directly above `class ChecklistInstanceRowOut(CamelModel):`:

```python
class ChecklistCategoryProgressOut(ChecklistCategoryOut):
    """A category heading on the checklist page: `done / total` over its items."""

    done: int
    total: int


```

In `ChecklistInstanceRowOut` replace

```python
    status: ChecklistStatus
    assigned_user_id: str | None = None
```

with

```python
    status: ChecklistStatus
    kind: ChecklistKind
    assigned_user_id: str | None = None
```

In `ChecklistInstanceOut` replace

```python
    comment: str | None = None
    items: list[TemplateItemOut]
```

with

```python
    comment: str | None = None
    categories: list[ChecklistCategoryProgressOut]
    items: list[ChecklistItemOut]
```

- [ ] **Step 4: Fill them in** — `server/app/domain/ck_views.py`.

Replace the three schema imports (from `from app.schemas.checklists import (` through
`from app.schemas.pm import RunAnswerOut, RunPhotoOut, TemplateItemOut`) with:

```python
from app.schemas.checklists import (
    ChecklistCategoryProgressOut,
    ChecklistInstanceOut,
    ChecklistInstanceQuery,
    ChecklistInstanceRowOut,
    ChecklistItemOut,
    ChecklistMissedQuery,
)
from app.schemas.enums import ChecklistStatus, Shift
from app.schemas.pm import RunAnswerOut, RunPhotoOut
```

In `_row_fields` replace

```python
        shift=inst.shift, on_demand=inst.slot is None, status=inst.status,
```

with

```python
        shift=inst.shift, on_demand=inst.slot is None, status=inst.status, kind=template.kind,
```

Insert directly above `def detail(`:

```python
def _category_progress(db: Session, template: ChecklistTemplate, items, rows,
                       photographed: set[str]) -> list[ChecklistCategoryProgressOut]:
    """One heading per active category that holds any of this checklist's items, in category
    order (checklist structure spec §2.2). Ungrouped items belong to no heading. An unstarted
    checklist has no answers yet, so everything counts as not done."""
    answer_for = {item.id: answer for answer, item in rows}
    out = []
    for category in ck_templates.active_categories(db, template.id):
        members = [i for i in items if i.category_id == category.id]
        if not members:
            continue
        done = sum(1 for i in members if i.id in answer_for
                   and typed_items.is_answered(i, answer_for[i.id], photographed))
        out.append(ChecklistCategoryProgressOut(id=category.id, name=category.name,
                                                position=category.position, done=done,
                                                total=len(members)))
    return out


```

In `detail`, replace

```python
    photos = ck_photos.photos_for(db, inst.id)
    return ChecklistInstanceOut(
```

with

```python
    photos = ck_photos.photos_for(db, inst.id)
    photographed = {p.item_id for p in photos if p.item_id}
    return ChecklistInstanceOut(
```

and replace

```python
        items=[TemplateItemOut.model_validate(i, from_attributes=True) for i in items],
```

with

```python
        categories=_category_progress(db, template, items, rows, photographed),
        items=[ChecklistItemOut.model_validate(i, from_attributes=True) for i in items],
```

(Items keep following their *current* `category_id`, exactly as their labels already follow
edits; answers are untouched — spec §2.2 "Snapshot unchanged".)

- [ ] **Step 5: Run the server tests** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_structure_views.py tests/test_ck_views.py tests/test_ck_api.py -q` → PASS; ruff.

- [ ] **Step 6: Regenerate the client types and fix the typed web fixtures**

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

In `web/src/api/types.ts` replace the line
`  ChecklistCategoryIn, ChecklistCategoryOut, ChecklistItemIn, ChecklistItemOut, ChecklistKind,`
with

```ts
  ChecklistCategoryIn, ChecklistCategoryOut, ChecklistItemIn, ChecklistItemOut, ChecklistKind,
  ChecklistCategoryProgressOut,
```

`kind` and `categories` are now required on the instance types, so three typed fixtures stop
compiling. In **both** `web/src/features/checklists/ChecklistRunPage.test.tsx` and
`web/src/features/checklists/ChecklistRunPage.noteReset.test.tsx`, in `BASE`, replace

```ts
  status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
```

with

```ts
  status: 'in_progress', kind: 'normal', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
```

and

```ts
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null,
```

with

```ts
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null, categories: [],
```

In `web/src/features/checklists/ChecklistsPage.test.tsx`, in `row()`, replace

```ts
    onDemand: false, status: 'open', assignedUserId: null, assignedName: null,
```

with

```ts
    onDemand: false, status: 'open', kind: 'normal', assignedUserId: null, assignedName: null,
```

(`ChecklistRunPage.tsx` itself still compiles: `ChecklistItemOut` is a `TemplateItemOut` plus an
optional `categoryId`, which PM's `ChecklistItem` accepts.)

- [ ] **Step 7: Run everything** — full server suite + ruff; `cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 8: Commit**

```bash
git add server/app/schemas/checklists.py server/app/domain/ck_views.py server/tests/test_ck_structure_views.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts web/src/features/checklists/ChecklistRunPage.test.tsx web/src/features/checklists/ChecklistRunPage.noteReset.test.tsx web/src/features/checklists/ChecklistsPage.test.tsx
git commit -m "feat(checklists): per-category progress on the checklist and the kind on rows" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The starter library — data, list and import, routes

**Files:**
- Create: `server/app/domain/ck_library.py`
- Modify: `server/app/schemas/checklists.py`, `server/app/api/checklists.py`,
  `server/tests/test_schema_export.py`; regenerate `web/src/api/schema.json`,
  `web/src/api/types.generated.ts`; modify `web/src/api/types.ts`
- Test: `server/tests/test_ck_library.py`

**Interfaces:**
- Consumes: Task 3's `ChecklistTemplateIn`, `ChecklistCategoryIn`, `ChecklistItemIn`,
  `ck_templates.create`, `ck_templates.to_out`.
- Produces schemas: `ChecklistLibraryCategoryOut` (`name`, `item_count`),
  `ChecklistLibraryEntryOut` (`key`, `name`, `kind`, `department_type: DepartmentType`,
  `categories: list[ChecklistLibraryCategoryOut]`, `item_count`), `ChecklistLibraryImport`
  (`department_id`, `name: str | None` 1–200).
- Produces (in `app.domain.ck_library`): dataclasses `LibraryItem`, `LibraryEntry`; `LIBRARY:
  tuple[LibraryEntry, ...]` (six, in spec order); `BY_KEY: dict[str, LibraryEntry]`;
  `list_entries() -> list[ChecklistLibraryEntryOut]`; `template_in(entry, department_id, name) ->
  ChecklistTemplateIn`; `import_entry(db, property_id, actor_id, key, data:
  ChecklistLibraryImport) -> ChecklistTemplate` (NotFound for an unknown key; the department
  check is `ck_templates.create`'s, `{"departmentId": "unknown"}`).
- Produces routes: `GET /api/p/<pid>/checklists/library` (`manage_admin`) →
  `ChecklistLibraryEntryOut[]`; `POST /api/p/<pid>/checklists/library/<key>/import`
  (`manage_admin`) → 201 `ChecklistTemplateOut`. Web types `ChecklistLibraryCategoryOut`,
  `ChecklistLibraryEntryOut`, `ChecklistLibraryImport` re-exported from `web/src/api/types.ts`.

- [ ] **Step 1: Write the failing test** — `server/tests/test_ck_library.py`:

```python
"""The starter checklist library and its import (checklist structure spec §3.3, §3.4)."""
import pytest

from app.domain import ck_library, ck_templates
from app.errors import NotFound, ValidationFailed
from app.models import Department
from app.schemas.checklists import ChecklistLibraryImport
from app.schemas.enums import ChecklistKind, DepartmentType, PmItemType

READING_LIMIT = 10 ** 8  # Numeric(10, 2): PostgreSQL overflows at |x| >= 10^8


def _lib(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/checklists/library{rest}"


def test_the_library_holds_the_six_starter_checklists():
    assert [(e.key, e.kind, e.department_type) for e in ck_library.LIBRARY] == [
        ("front_desk_am", ChecklistKind.normal, DepartmentType.front_desk),
        ("front_desk_pm", ChecklistKind.normal, DepartmentType.front_desk),
        ("night_audit", ChecklistKind.normal, DepartmentType.front_desk),
        ("pool_spa", ChecklistKind.readings, DepartmentType.engineering),
        ("boiler_rounds", ChecklistKind.readings, DepartmentType.engineering),
        ("linen_par", ChecklistKind.normal, DepartmentType.housekeeping),
    ]
    assert len(ck_library.BY_KEY["night_audit"].categories) == 7


@pytest.mark.parametrize("entry", ck_library.LIBRARY, ids=lambda e: e.key)
def test_every_entry_is_valid_input_for_create(database, fx, entry):
    assert len(set(entry.categories)) == len(entry.categories)
    for category in entry.categories:
        assert 0 < len(category) <= 120
        assert any(i.category == category for i in entry.items), f"{category} has no items"
    for item in entry.items:
        assert item.category is None or item.category in entry.categories, item.label
        bounds = [b for b in (item.min_value, item.max_value) if b is not None]
        assert item.item_type == PmItemType.number or not (bounds or item.unit), item.label
        assert all(abs(b) < READING_LIMIT for b in bounds), item.label
        if len(bounds) == 2:
            assert item.min_value <= item.max_value, item.label
        assert item.unit is None or len(item.unit) <= 16, item.label
    with database.session() as db:
        t = ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, entry.key,
                                    ChecklistLibraryImport(department_id=fx.dept_engineering.id))
        out = ck_templates.to_out(db, t)
        assert (out.name, out.kind, out.schedule.value) == (entry.name, entry.kind,
                                                             "unscheduled")
        assert [c.name for c in out.categories] == list(entry.categories)
        names = {c.id: c.name for c in out.categories}
        assert [(i.label, i.item_type, i.unit, i.min_value, i.max_value, i.required,
                 names.get(i.category_id)) for i in out.items] == [
            (i.label, i.item_type, i.unit, i.min_value, i.max_value, i.required, i.category)
            for i in entry.items]


def test_the_list_summarises_each_entry():
    entries = {e.key: e for e in ck_library.list_entries()}
    am = entries["front_desk_am"]
    assert (am.name, am.item_count) == ("Front Desk AM Opening", 7)
    assert [(c.name, c.item_count) for c in am.categories] == [
        ("Cash & drawer", 2), ("Systems", 3), ("Lobby", 2)]
    assert entries["pool_spa"].categories == []


def test_import_takes_a_name_and_twice_gives_two_copies(database, fx):
    with database.session() as db:
        pid, fd = fx.property_a.id, fx.dept_front_desk.id
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd))
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd, name="Night Audit B"))
        ck_library.import_entry(db, pid, fx.admin_a.id, "night_audit",
                                ChecklistLibraryImport(department_id=fd, name="   "))
        assert sorted(t.name for t in ck_templates.list_templates(db, pid)) == [
            "Night Audit", "Night Audit", "Night Audit B"]


def test_unknown_key_and_foreign_department(database, fx):
    with database.session() as db:
        with pytest.raises(NotFound):
            ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, "nope",
                                    ChecklistLibraryImport(department_id=fx.dept_front_desk.id))
        other = Department(property_id=fx.property_b.id, name="Engineering",
                           type=DepartmentType.engineering)
        db.add(other)
        db.flush()
        with pytest.raises(ValidationFailed) as refused:
            ck_library.import_entry(db, fx.property_a.id, fx.admin_a.id, "pool_spa",
                                    ChecklistLibraryImport(department_id=other.id))
        assert refused.value.details == {"departmentId": "unknown"}


def test_library_routes(app, fx, login):
    admin = login("admin@hvh.test")
    listed = admin.get(_lib(fx)).get_json()
    assert [e["key"] for e in listed][:1] == ["front_desk_am"]
    assert listed[0]["departmentType"] == "front_desk"
    assert listed[0]["categories"][0] == {"name": "Cash & drawer", "itemCount": 2}
    res = admin.post(_lib(fx, "/pool_spa/import"), json={"departmentId": fx.dept_engineering.id})
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert (body["name"], body["kind"], body["schedule"], len(body["items"])) == (
        "Pool & Spa Readings", "readings", "unscheduled", 5)
    assert admin.post(_lib(fx, "/nope/import"),
                      json={"departmentId": fx.dept_engineering.id}).status_code == 404
    assert admin.post(_lib(fx, "/pool_spa/import"), json={}).status_code == 400


def test_library_needs_manage_admin(app, fx, login):
    for email in ("agent@hvh.test", "supervisor@hvh.test", "manager@hvh.test"):
        c = login(email)
        assert c.get(_lib(fx)).status_code == 403, email
        assert c.post(_lib(fx, "/pool_spa/import"),
                      json={"departmentId": fx.dept_engineering.id}).status_code == 403, email
    assert login("corporate@hvh.test").get(_lib(fx)).status_code == 200
```

In `server/tests/test_schema_export.py` replace
`                 "ChecklistCategoryProgressOut"):` with

```python
                 "ChecklistCategoryProgressOut", "ChecklistLibraryEntryOut",
                 "ChecklistLibraryCategoryOut", "ChecklistLibraryImport"):
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_library.py -q`
Expected: FAIL — `ImportError: cannot import name 'ck_library'`.

- [ ] **Step 3: Add the wire models** — `server/app/schemas/checklists.py`.

Replace the import line
`from app.schemas.enums import ChecklistKind, ChecklistSchedule, ChecklistStatus, Shift` with

```python
from app.schemas.enums import (
    ChecklistKind,
    ChecklistSchedule,
    ChecklistStatus,
    DepartmentType,
    Shift,
)
```

Insert directly above `class ChecklistAssignRequest(CamelModel):`:

```python
class ChecklistLibraryCategoryOut(CamelModel):
    name: str
    item_count: int


class ChecklistLibraryEntryOut(CamelModel):
    key: str
    name: str
    kind: ChecklistKind
    department_type: DepartmentType
    categories: list[ChecklistLibraryCategoryOut]
    item_count: int


class ChecklistLibraryImport(CamelModel):
    department_id: str
    name: str | None = Field(default=None, min_length=1, max_length=200)


```

- [ ] **Step 4: Create `server/app/domain/ck_library.py`**

```python
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
```

- [ ] **Step 5: Add the routes** — `server/app/api/checklists.py`.

Replace `from app.domain import ck_instances, ck_photos, ck_templates, ck_views` with
`from app.domain import ck_instances, ck_library, ck_photos, ck_templates, ck_views`, and in the
schemas import add `ChecklistLibraryImport,` after `ChecklistInstanceQuery,`.

Insert directly above `@bp.post("/templates/<template_id>/start")`:

```python
@bp.get("/library")
@require_auth
@require_property
@require_capability("manage_admin")
def library(property_id: str):
    return ok(ck_library.list_entries())


@bp.post("/library/<key>/import")
@require_auth
@require_property
@require_capability("manage_admin")
def import_from_library(property_id: str, key: str):
    data = parse_body(ChecklistLibraryImport)
    with db_session() as db:
        t = ck_library.import_entry(db, g.property_id, g.user.id, key, data)
        return ok(ck_templates.to_out(db, t), 201)


```

- [ ] **Step 6: Regenerate the client types**

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

In `web/src/api/types.ts` replace the line `  ChecklistCategoryProgressOut,` with

```ts
  ChecklistCategoryProgressOut, ChecklistLibraryCategoryOut, ChecklistLibraryEntryOut,
  ChecklistLibraryImport,
```

- [ ] **Step 7: Run everything**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_ck_library.py tests/test_schema_export.py tests/test_isolation.py -q`
→ PASS (the isolation suite finds both new rules automatically: 403 across properties, admin
never 403 — the import answers a dummy key with 400/404, anonymous 401). Full server suite +
ruff; then `cd web && npm test && npm run lint && npm run build` → PASS.

- [ ] **Step 8: Commit**

```bash
git add server/app/domain/ck_library.py server/app/schemas/checklists.py server/app/api/checklists.py server/tests/test_ck_library.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts
git commit -m "feat(checklists): starter checklist library and its import" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Seed data

**Files:** Modify `server/seed/seed.py`, `server/tests/test_seed.py`; regenerate
`server/data/app.db`.

**Interfaces:** Consumes Task 3's `ChecklistCategoryIn`, `ChecklistItemIn`, `kind`, and
`ck_templates.active_categories`. `SeedSummary` is unchanged (`checklist_templates=5`).

- [ ] **Step 1: Write the failing assertions** — `server/tests/test_seed.py`.

Replace `from app.domain import pm_cycles` with `from app.domain import ck_templates, pm_cycles`;
add `ChecklistTemplateItem,` to the `app.models` import after `ChecklistTemplate,`; add
`ChecklistKind,` to the `app.schemas.enums` import before `ChecklistStatus,`. After the line

```python
        assert count(WorkOrder, WorkOrder.title.like("Pool pH 8.1 out of range%")) == 1
```

add

```python
        # checklist structure (spec §5): one readings checklist, the Night Audit in 3 categories
        assert db.scalars(select(ChecklistTemplate.name).where(
            ChecklistTemplate.property_id == hvh.id,
            ChecklistTemplate.kind == ChecklistKind.readings)).all() == ["Engineering AM Rounds"]
        night = db.scalar(select(ChecklistTemplate).where(
            ChecklistTemplate.name == "Front Desk Overnight Night Audit"))
        assert [c.name for c in ck_templates.active_categories(db, night.id)] == [
            "Audit", "Payments", "Reports"]
        assert count(ChecklistTemplateItem, ChecklistTemplateItem.template_id == night.id,
                     ChecklistTemplateItem.category_id.is_(None)) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q`
Expected: FAIL — `assert [] == ['Engineering AM Rounds']`.

- [ ] **Step 3: Implement** — `server/seed/seed.py`.

Replace `from app.schemas.checklists import ChecklistTemplateIn` with

```python
from app.schemas.checklists import ChecklistCategoryIn, ChecklistItemIn, ChecklistTemplateIn
```

and `from app.schemas.pm import AnswerPatch, TemplateItemIn` with
`from app.schemas.pm import AnswerPatch` (the checklist helper below was its only user).

Replace the `ck_template` helper

```python
        def ck_template(name, dept, schedule, shift, weekdays, items):
            return ck_templates.create(db, hvh.id, staff["alex"].id, ChecklistTemplateIn(
                name=name, department_id=depts[dept].id, schedule=schedule, shift=shift,
                weekdays=weekdays, items=[TemplateItemIn(**i) for i in items]))
```

with

```python
        def ck_template(name, dept, schedule, shift, weekdays, items, *, kind="normal",
                        categories=()):
            # Checklist structure spec §5: a category's key is its name, and each item names
            # its category by that key.
            return ck_templates.create(db, hvh.id, staff["alex"].id, ChecklistTemplateIn(
                name=name, department_id=depts[dept].id, schedule=schedule, shift=shift,
                weekdays=weekdays, kind=kind,
                categories=[ChecklistCategoryIn(key=c, name=c) for c in categories],
                items=[ChecklistItemIn(**i) for i in items]))
```

Replace the Night Audit's item list

```python
                    every_day, [
                        {"label": "Night audit run", "item_type": "checkbox"},
                        {"label": "Credit card batch closed", "item_type": "checkbox"},
                        {"label": "Audit report", "item_type": "photo"}])
```

with

```python
                    every_day, [
                        {"label": "Night audit run", "item_type": "checkbox",
                         "category_key": "Audit"},
                        {"label": "Credit card batch closed", "item_type": "checkbox",
                         "category_key": "Payments"},
                        {"label": "Audit report", "item_type": "photo",
                         "category_key": "Reports"}],
                    categories=("Audit", "Payments", "Reports"))
```

and the end of Engineering AM Rounds

```python
            {"label": "Boiler supply temp", "item_type": "number", "unit": "°F",
             "min_value": 140, "max_value": 180}])
```

with

```python
            {"label": "Boiler supply temp", "item_type": "number", "unit": "°F",
             "min_value": 140, "max_value": 180}], kind="readings")
```

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py tests/test_dev_start.py -q` → PASS.

- [ ] **Step 5: Regenerate the fixture database**

Run: `cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('sqlite:///data/app.db', reset=True))"`
Expected: the summary shows `checklist_templates=5` (unchanged).

- [ ] **Step 6: Full suite + ruff, then commit (including `app.db`)**

```bash
git add server/seed/seed.py server/tests/test_seed.py server/data/app.db
git commit -m "feat(checklists): seed a readings checklist and a categorised Night Audit" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Web data layer — library hooks, labels, grouping, error copy

**Files:**
- Modify: `web/src/api/queryKeys.ts`, `web/src/api/hooks/checklists.ts`,
  `web/src/api/fieldErrors.ts` (+`fieldErrors.test.ts`), `web/src/features/checklists/labels.ts`
- Create: `web/src/features/checklists/grouping.ts` (+`grouping.test.ts`),
  `web/src/api/hooks/checklists.test.tsx`

**Interfaces:**
- Consumes: Task 5's routes and the types re-exported in Tasks 3–5.
- Produces: `qk.ckLibrary(p)` = `['ck', p, 'library']` (under `qk.ckAll`); hooks
  `useChecklistLibrary(enabled: boolean)` (GET `checklists/library` →
  `ChecklistLibraryEntryOut[]`) and `useImportChecklist()` (`ChecklistLibraryImport & { key:
  string }` → `ChecklistTemplateOut`, POST `checklists/library/<key>/import`, invalidates
  `qk.ckAll`); in `features/checklists/labels.ts`: `KIND_LABELS: Record<ChecklistKind, string>`
  and `scheduleLabel(t: { schedule; shift?; weekdays? }): string` ("On demand", "Set schedule",
  or "`<shift>` · `<days>`"); in `features/checklists/grouping.ts`: `type CategoryGroup<T>` and
  `groupByCategory<T extends { categoryId?: string | null }>(items: T[], categories:
  ChecklistCategoryProgressOut[]) => { ungrouped: T[]; groups: CategoryGroup<T>[] }`; reason
  copy for `unknown_category`.

- [ ] **Step 1: Write the failing tests**

`web/src/features/checklists/grouping.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { groupByCategory } from './grouping'
import { KIND_LABELS, scheduleLabel } from './labels'

const CATEGORIES = [
  { id: 'c-audit', name: 'Audit', position: 0, done: 1, total: 2 },
  { id: 'c-pay', name: 'Payments', position: 1, done: 0, total: 1 },
]

describe('groupByCategory', () => {
  it('puts ungrouped items first and keeps each group in the server order', () => {
    const items = [
      { id: 'a', categoryId: 'c-audit' },
      { id: 'n', categoryId: null },
      { id: 'p', categoryId: 'c-pay' },
      { id: 'b', categoryId: 'c-audit' },
    ]
    const { ungrouped, groups } = groupByCategory(items, CATEGORIES)
    expect(ungrouped.map((i) => i.id)).toEqual(['n'])
    expect(groups.map((g) => [g.name, g.done, g.total, g.items.map((i) => i.id)])).toEqual([
      ['Audit', 1, 2, ['a', 'b']],
      ['Payments', 0, 1, ['p']],
    ])
  })

  it('never drops an item whose category is not listed', () => {
    const { ungrouped } = groupByCategory([{ id: 'x', categoryId: 'c-gone' }, { id: 'y' }], [])
    expect(ungrouped.map((i) => i.id)).toEqual(['x', 'y'])
  })
})

describe('schedule and kind labels', () => {
  it('reads an unscheduled template as a call to action', () => {
    expect(scheduleLabel({ schedule: 'unscheduled', shift: null, weekdays: null })).toBe('Set schedule')
    expect(scheduleLabel({ schedule: 'on_demand' })).toBe('On demand')
    expect(scheduleLabel({ schedule: 'weekly', shift: 'am', weekdays: 127 })).toBe('AM · Every day')
    expect(KIND_LABELS.readings).toBe('Readings')
  })
})
```

`web/src/api/hooks/checklists.test.tsx`:

```tsx
import { QueryClientProvider, type QueryClient } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { sessionFixture, testQueryClient } from '../../test/harness'
import { qk } from '../queryKeys'
import { useChecklistLibrary, useImportChecklist } from './checklists'

function serve(body: unknown, status = 200) {
  vi.mocked(fetch).mockImplementation(() =>
    Promise.resolve(new Response(JSON.stringify(body), { status })),
  )
}

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <SessionProvider>{children}</SessionProvider>
      </QueryClientProvider>
    )
  }
}

function adminClient() {
  const client = testQueryClient()
  client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
  return client
}

describe('checklist library hooks', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => vi.unstubAllGlobals())

  it('loads the library only when asked', async () => {
    serve([{ key: 'night_audit' }])
    const client = adminClient()
    const { result, rerender } = renderHook(({ on }) => useChecklistLibrary(on), {
      wrapper: wrapper(client), initialProps: { on: false },
    })
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
    rerender({ on: true })
    await waitFor(() => expect(result.current.data).toEqual([{ key: 'night_audit' }]))
    expect(String(vi.mocked(fetch).mock.calls[0]![0])).toBe('/api/p/prop-a/checklists/library')
  })

  it('imports by key with the department and name in the body, then refreshes checklists', async () => {
    serve({ id: 't-new' }, 201)
    const client = adminClient()
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => useImportChecklist(), { wrapper: wrapper(client) })
    act(() => {
      result.current.mutate({ key: 'night_audit', departmentId: 'dept-fd', name: 'Night Audit' })
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
    expect(String(url)).toBe('/api/p/prop-a/checklists/library/night_audit/import')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ departmentId: 'dept-fd', name: 'Night Audit' })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: qk.ckAll('prop-a') })
  })
})
```

In `web/src/api/fieldErrors.test.ts`, in `SERVER_CODES`, replace `      'no_template']` with
`      'no_template', 'unknown_category']`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/checklists/grouping.test.ts src/api/hooks/checklists.test.tsx src/api/fieldErrors.test.ts`
Expected: FAIL — `./grouping` does not exist; `useChecklistLibrary` is not exported;
`unknown_category` is shown raw.

- [ ] **Step 3: Implement**

`web/src/api/queryKeys.ts` — after the `ckMissedAll` line add:

```ts
  ckLibrary: (propertyId: string) => ['ck', propertyId, 'library'] as const,
```

`web/src/api/hooks/checklists.ts` — in the type import add `ChecklistLibraryEntryOut,` and
`ChecklistLibraryImport,` after `ChecklistInstanceRowOut,`, and insert directly above the
`// ---- instances ----` comment line:

```ts
// ---- starter library (checklist structure spec §3.3) --------------------------------------

export function useChecklistLibrary(enabled: boolean) {
  const { propertyId } = useSession()
  return useQuery<ChecklistLibraryEntryOut[], ApiError>({
    queryKey: qk.ckLibrary(propertyId),
    queryFn: () => api<ChecklistLibraryEntryOut[]>(ckPath(propertyId, 'library')),
    enabled,
  })
}

export const useImportChecklist = () =>
  useCkMutation<ChecklistLibraryImport & { key: string }, ChecklistTemplateOut>(
    (p, { key, ...body }) =>
      api(ckPath(p, `library/${encodeURIComponent(key)}/import`), { method: 'POST', json: body }),
  )

```

`web/src/api/fieldErrors.ts` — in `REASON_COPY`, after the `no_template` entry add:

```ts
  // Checklist template categories (`app/domain/ck_templates.py`).
  unknown_category: 'That category is no longer on this checklist. Reload and try again.',
```

`web/src/features/checklists/labels.ts` — replace the first line with

```ts
import type { ChecklistKind, ChecklistSchedule, ChecklistStatus, Shift } from '../../api/types'
```

insert above `export const WEEKDAYS`:

```ts
export const KIND_LABELS: Record<ChecklistKind, string> = {
  normal: 'Normal',
  readings: 'Readings',
}

```

and append to the end of the file:

```ts

/** How a template's schedule reads in a list. An unscheduled one is a call to action
 *  (checklist structure spec §4.1). */
export function scheduleLabel(t: {
  schedule: ChecklistSchedule
  shift?: Shift | null
  weekdays?: number | null
}): string {
  if (t.schedule === 'on_demand') return 'On demand'
  if (t.schedule === 'unscheduled') return 'Set schedule'
  return `${t.shift ? SHIFT_LABELS[t.shift] : ''} · ${weekdayLabel(t.weekdays)}`
}
```

Create `web/src/features/checklists/grouping.ts`:

```ts
import type { ChecklistCategoryProgressOut } from '../../api/types'

export type CategoryGroup<T> = ChecklistCategoryProgressOut & { items: T[] }

/**
 * A checklist's items as the checklist page shows them (checklist structure spec §2.2): the
 * ungrouped ones first, with no heading, then one group per category in the server's category
 * order. An item naming a category the server did not list counts as ungrouped, so nothing is
 * ever dropped from the page. Item order inside each part is the server's.
 */
export function groupByCategory<T extends { categoryId?: string | null }>(
  items: T[],
  categories: ChecklistCategoryProgressOut[],
): { ungrouped: T[]; groups: CategoryGroup<T>[] } {
  const known = new Set(categories.map((c) => c.id))
  return {
    ungrouped: items.filter((i) => !i.categoryId || !known.has(i.categoryId)),
    groups: categories.map((c) => ({ ...c, items: items.filter((i) => i.categoryId === c.id) })),
  }
}
```

- [ ] **Step 4: Run** `cd web && npx vitest run src/features/checklists src/api && npm run lint && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/queryKeys.ts web/src/api/hooks/checklists.ts web/src/api/hooks/checklists.test.tsx web/src/api/fieldErrors.ts web/src/api/fieldErrors.test.ts web/src/features/checklists/labels.ts web/src/features/checklists/grouping.ts web/src/features/checklists/grouping.test.ts
git commit -m "feat(checklists): web hooks and helpers for the library, kinds and categories" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `ItemListEditor` — an optional category column (PM unchanged)

**Files:**
- Modify: `web/src/features/admin/ItemListEditor.tsx` (replace), `web/src/features/admin/ItemListEditor.test.tsx` (replace)

**Interfaces:**
- Produces: `ItemDraft` gains optional `categoryKey?: string | null`; `type CategoryOption = {
  key: string; name: string }`; `orderByCategory(items: ItemDraft[], categories:
  CategoryOption[]): ItemDraft[]`; `ItemListEditor` gains an optional `categories?:
  CategoryOption[]` prop. `NEW_ITEM`, `LABEL`, `SELECT`, `toItemIn`, `itemDraftFrom`,
  `FieldError` are unchanged — `toItemIn` still emits exactly PM's `TemplateItemIn` (PM's server
  model forbids unknown fields, so it must never carry `categoryKey`).

- [ ] **Step 1: Write the failing tests** — replace `web/src/features/admin/ItemListEditor.test.tsx`
with (the first two tests are the existing ones, unchanged):

```tsx
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { ItemListEditor, orderByCategory, type CategoryOption, type ItemDraft } from './ItemListEditor'

function Harness({ initial = [] as ItemDraft[], categories }: {
  initial?: ItemDraft[]
  categories?: CategoryOption[]
}) {
  const [items, setItems] = useState(initial)
  return (
    <>
      <ItemListEditor items={items} onChange={setItems} categories={categories} />
      <output data-testid="labels">{items.map((i) => i.label).join('|')}</output>
      <output data-testid="groups">{items.map((i) => i.categoryKey ?? '-').join('|')}</output>
    </>
  )
}

const saved: ItemDraft = { id: 'i-1', label: 'Pool pH', itemType: 'number', unit: '',
  minValue: '7.2', maxValue: '7.8', required: true }

const CATEGORIES: CategoryOption[] = [{ key: 'c-audit', name: 'Audit' }, { key: 'c-pay', name: 'Payments' }]
const check = (id: string, label: string, categoryKey: string | null): ItemDraft => ({
  id, label, itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true, categoryKey,
})

describe('ItemListEditor', () => {
  it('adds an item and shows bounds only for numbers', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Add item' }))
    await user.type(screen.getByLabelText('Label for item 1'), 'Boiler temp')
    expect(screen.queryByLabelText('Min for item 1')).not.toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Type for item 1'), 'number')
    expect(screen.getByLabelText('Min for item 1')).toBeInTheDocument()
    expect(screen.getByTestId('labels')).toHaveTextContent('Boiler temp')
  })

  it('locks the type of a saved item, and reorders and removes', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[saved, { ...saved, id: 'i-2', label: 'Chlorine' }]} />)
    expect(screen.getByLabelText('Type for item 1')).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Chlorine|Pool pH')
    await user.click(screen.getByRole('button', { name: 'Remove item 1' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Pool pH')
  })

  it('has no category control when no categories are passed (PM)', () => {
    render(<Harness initial={[saved]} />)
    expect(screen.queryByLabelText('Category for item 1')).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3 })).not.toBeInTheDocument()
  })

  it('groups items under their category headings, ungrouped first', () => {
    render(<Harness categories={CATEGORIES} initial={[
      check('a', 'Card batch', 'c-pay'), check('b', 'Notes', null), check('c', 'Audit run', 'c-audit'),
    ]} />)
    expect(screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(['Audit', 'Payments'])
    const audit = screen.getByRole('region', { name: 'Items in Audit' })
    expect(within(audit).getByDisplayValue('Audit run')).toBeInTheDocument()
    // numbering follows what is shown: Notes (ungrouped) is item 1
    expect(screen.getByLabelText('Label for item 1')).toHaveValue('Notes')
    expect(screen.getByLabelText('Category for item 3')).toHaveValue('c-pay')
  })

  it('moves an item between categories with its select, and keeps moves inside a group', async () => {
    const user = userEvent.setup()
    render(<Harness categories={CATEGORIES} initial={[
      check('a', 'Audit run', 'c-audit'), check('b', 'Card batch', 'c-pay'),
    ]} />)
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' })) // across a boundary: no-op
    expect(screen.getByTestId('labels')).toHaveTextContent('Audit run|Card batch')
    await user.selectOptions(screen.getByLabelText('Category for item 2'), 'c-audit')
    expect(screen.getByTestId('groups')).toHaveTextContent('c-audit|c-audit')
    await user.click(screen.getByRole('button', { name: 'Move item 2 up' }))
    expect(screen.getByTestId('labels')).toHaveTextContent('Card batch|Audit run')
    await user.selectOptions(screen.getByLabelText('Category for item 1'), '')
    expect(screen.getByTestId('groups')).toHaveTextContent('-|c-audit')
  })
})

describe('orderByCategory', () => {
  it('is a stable sort by category order, unknown categories counting as ungrouped', () => {
    const ordered = orderByCategory([
      check('1', 'p1', 'c-pay'), check('2', 'a1', 'c-audit'), check('3', 'x', 'gone'),
      check('4', 'p2', 'c-pay'), check('5', 'n', null),
    ], CATEGORIES)
    expect(ordered.map((i) => i.label)).toEqual(['x', 'n', 'a1', 'p1', 'p2'])
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/admin/ItemListEditor.test.tsx`
Expected: FAIL — `orderByCategory` is not exported; no "Category for item" control.

- [ ] **Step 3: Replace `web/src/features/admin/ItemListEditor.tsx`** with:

```tsx
import type { PmItemType, TemplateItemIn, TemplateItemOut } from '../../api/types'
import { Button, Input } from '../../components/ui'
import { ITEM_TYPE_LABELS } from '../pm/labels'

export type ItemDraft = {
  id?: string
  label: string
  itemType: PmItemType
  unit: string
  minValue: string
  maxValue: string
  required: boolean
  /** Checklists only: the `key` of the category this item sits under. PM never sets it. */
  categoryKey?: string | null
}

/** A category as the item editor needs it: the client-side key items point at, and a name. */
export type CategoryOption = { key: string; name: string }

export const NEW_ITEM: ItemDraft = { label: '', itemType: 'checkbox', unit: '', minValue: '', maxValue: '', required: true }

export const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
export const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

export function toItemIn(item: ItemDraft): TemplateItemIn {
  const number = item.itemType === 'number'
  return {
    ...(item.id ? { id: item.id } : {}),
    label: item.label.trim(),
    itemType: item.itemType,
    unit: number && item.unit.trim() ? item.unit.trim() : null,
    minValue: number && item.minValue.trim() !== '' ? Number(item.minValue) : null,
    maxValue: number && item.maxValue.trim() !== '' ? Number(item.maxValue) : null,
    required: item.required,
  }
}

export function itemDraftFrom(i: TemplateItemOut): ItemDraft {
  return {
    id: i.id, label: i.label, itemType: i.itemType, unit: i.unit ?? '',
    minValue: i.minValue === null || i.minValue === undefined ? '' : String(i.minValue),
    maxValue: i.maxValue === null || i.maxValue === undefined ? '' : String(i.maxValue),
    required: i.required,
  }
}

/**
 * Items in the order the grouped editor shows them: ungrouped first, then each category's items
 * in category order; a stable sort, so items keep their relative order within a group. An item
 * naming a category that is not in `categories` counts as ungrouped.
 */
export function orderByCategory(items: ItemDraft[], categories: CategoryOption[]): ItemDraft[] {
  const rank = new Map(categories.map((c, i) => [c.key, i]))
  const groupOf = (item: ItemDraft) =>
    item.categoryKey != null && rank.has(item.categoryKey) ? rank.get(item.categoryKey)! : -1
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => groupOf(a.item) - groupOf(b.item) || a.index - b.index)
    .map(({ item }) => item)
}

export function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-dangerText">{message}</p>
}

/**
 * The typed item list shared by PM and checklist templates. `categories` is optional: PM never
 * passes it and gets exactly the flat list it always had. With it, each item gains a Category
 * select and the list renders grouped — ungrouped items first, then one heading per category —
 * and `onChange` always receives the items in that grouped order, so what is saved is what is
 * shown. Moving an item up or down stays inside its group; the select moves it between groups.
 */
export function ItemListEditor({ items, onChange, error, categories }: {
  items: ItemDraft[]
  onChange: (items: ItemDraft[]) => void
  error?: string
  categories?: CategoryOption[]
}) {
  const list = categories ? orderByCategory(items, categories) : items
  const known = new Set((categories ?? []).map((c) => c.key))
  const groupKey = (item: ItemDraft) =>
    item.categoryKey != null && known.has(item.categoryKey) ? item.categoryKey : null
  const editItem = (index: number, change: Partial<ItemDraft>) =>
    onChange(list.map((item, i) => (i === index ? { ...item, ...change } : item)))
  const moveItem = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= list.length) return
    if (categories && groupKey(list[index]!) !== groupKey(list[target]!)) return
    const next = [...list]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  const renderItem = (item: ItemDraft, index: number) => {
    const n = index + 1
    return (
      <li key={item.id ?? `new-${index}`} className="rounded border border-border2 p-2">
        <div className="flex flex-col gap-2">
          <Input aria-label={`Label for item ${n}`} value={item.label} maxLength={200}
                 placeholder="Label" onChange={(e) => editItem(index, { label: e.target.value })} />
          <div className="flex gap-2">
            <select aria-label={`Type for item ${n}`} className={SELECT} value={item.itemType}
                    disabled={Boolean(item.id)}
                    onChange={(e) => editItem(index, { itemType: e.target.value as PmItemType })}>
              {(Object.keys(ITEM_TYPE_LABELS) as PmItemType[]).map((t) => (
                <option key={t} value={t}>{ITEM_TYPE_LABELS[t]}</option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input type="checkbox" checked={item.required}
                     onChange={(e) => editItem(index, { required: e.target.checked })} />
              Required
            </label>
          </div>
          {categories ? (
            <select aria-label={`Category for item ${n}`} className={SELECT}
                    value={groupKey(item) ?? ''}
                    onChange={(e) => editItem(index, { categoryKey: e.target.value || null })}>
              <option value="">None</option>
              {categories.map((c) => (
                <option key={c.key} value={c.key}>{c.name.trim() || 'Untitled category'}</option>
              ))}
            </select>
          ) : null}
          {item.itemType === 'number' ? (
            <div className="flex gap-2">
              <Input aria-label={`Unit for item ${n}`} placeholder="Unit" className="w-20" maxLength={16}
                     value={item.unit} onChange={(e) => editItem(index, { unit: e.target.value })} />
              <Input aria-label={`Min for item ${n}`} type="number" placeholder="Min" step="any"
                     value={item.minValue} onChange={(e) => editItem(index, { minValue: e.target.value })} />
              <Input aria-label={`Max for item ${n}`} type="number" placeholder="Max" step="any"
                     value={item.maxValue} onChange={(e) => editItem(index, { maxValue: e.target.value })} />
            </div>
          ) : null}
          <div className="flex gap-1">
            <Button variant="ghost" aria-label={`Move item ${n} up`} onClick={() => moveItem(index, -1)}>↑</Button>
            <Button variant="ghost" aria-label={`Move item ${n} down`} onClick={() => moveItem(index, 1)}>↓</Button>
            <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove item ${n}`}
                    onClick={() => onChange(list.filter((_, i) => i !== index))}>
              Remove
            </Button>
          </div>
        </div>
      </li>
    )
  }

  const indexed = list.map((item, index) => ({ item, index }))
  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Checklist</p>
        <Button className="ml-auto" onClick={() => onChange([...list, { ...NEW_ITEM }])}>
          Add item
        </Button>
      </div>
      <FieldError message={error} />
      {categories ? (
        <div className="flex flex-col gap-3">
          <ol className="flex flex-col gap-2">
            {indexed.filter(({ item }) => groupKey(item) === null)
              .map(({ item, index }) => renderItem(item, index))}
          </ol>
          {categories.map((category) => {
            const members = indexed.filter(({ item }) => groupKey(item) === category.key)
            return (
              <section key={category.key} aria-label={`Items in ${category.name.trim() || 'Untitled category'}`}>
                <h3 className="mb-1 text-xs font-bold text-text2">{category.name.trim() || 'Untitled category'}</h3>
                {members.length === 0 ? (
                  <p className="text-xs text-text3">No items yet — pick this category on an item.</p>
                ) : (
                  <ol className="flex flex-col gap-2">
                    {members.map(({ item, index }) => renderItem(item, index))}
                  </ol>
                )}
              </section>
            )
          })}
        </div>
      ) : (
        <ol className="flex flex-col gap-2">
          {list.map((item, index) => renderItem(item, index))}
        </ol>
      )}
    </div>
  )
}
```

(Without `categories` the markup is the same single `<ol>` of the same `<li>` rows as before;
`list` is `items` itself, so every PM `onChange` receives exactly what it did.)

- [ ] **Step 4: Run** `cd web && npx vitest run src/features/admin && npm run lint && npm run build` → PASS —
including `PmTemplatesAdmin.test.tsx` and `ChecklistTemplatesAdmin.test.tsx` unchanged.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/admin/ItemListEditor.tsx web/src/features/admin/ItemListEditor.test.tsx
git commit -m "feat(admin): optional category column in the shared item editor" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Admin → Checklist templates — kind, "Not scheduled yet", categories, list chips

**Files:**
- Create: `web/src/features/admin/CategoryListEditor.tsx`
- Modify: `web/src/features/admin/ChecklistTemplatesAdmin.tsx` (replace),
  `web/src/features/admin/ChecklistTemplatesAdmin.test.tsx` (replace)

**Interfaces:**
- Consumes: Task 7's `KIND_LABELS`, `scheduleLabel`; Task 8's `ItemListEditor` `categories`
  prop, `orderByCategory`, `CategoryOption`; the Task 3–4 types.
- Produces: `type CategoryDraft = CategoryOption & { id?: string }`, `newCategoryKey(): string`
  and `CategoryListEditor({ categories, onChange, error })` in `CategoryListEditor.tsx`;
  `ChecklistTemplatesAdmin` keeps its export and gains an internal `open(template)` that Task 10
  calls after an import.

- [ ] **Step 1: Write the failing tests** — replace
`web/src/features/admin/ChecklistTemplatesAdmin.test.tsx` with (the first, second and fourth
tests are the existing ones; the first's expected body gains `kind`, `categories` and
`categoryKey`):

```tsx
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChecklistItemOut, ChecklistTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

const item = (id: string, label: string, categoryId: string | null, position: number): ChecklistItemOut => ({
  id, position, label, itemType: 'checkbox', unit: null, minValue: null, maxValue: null,
  required: true, active: true, categoryId,
})

const NIGHT: ChecklistTemplateOut = {
  id: 't-night', name: 'Night Audit', departmentId: 'dept-eng', departmentName: 'Engineering',
  schedule: 'unscheduled', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [{ id: 'c-audit', name: 'Audit', position: 0 }, { id: 'c-pay', name: 'Payments', position: 1 }],
  items: [item('i-run', 'Night audit run', 'c-audit', 0), item('i-batch', 'Card batch closed', 'c-pay', 1),
          item('i-notes', 'Notes checked', null, 2)],
}
const POOL: ChecklistTemplateOut = {
  ...NIGHT, id: 't-pool', name: 'Pool Readings', kind: 'readings', schedule: 'weekly', shift: 'am',
  weekdays: 127, categories: [], items: [item('i-ph', 'Pool pH', null, 0)],
}

let templates: ChecklistTemplateOut[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (init?.method === 'POST') return json({ id: 't-new' }, 201)
    if (init?.method === 'PATCH') return json(NIGHT)
    return json(templates)
  })
}

function sent(method: 'POST' | 'PATCH') {
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === method)
  return call ? JSON.parse(String(call[1]!.body)) : undefined
}
const posted = () => sent('POST')

function mount() {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

async function startNew(name: string) {
  mount()
  await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
  await userEvent.type(screen.getByLabelText('Name'), name)
  await userEvent.selectOptions(await screen.findByLabelText('Department'), 'dept-eng')
}

async function addCheckbox(label: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
  await userEvent.type(screen.getByLabelText('Label for item 1'), label)
}

describe('ChecklistTemplatesAdmin', () => {
  beforeEach(() => {
    templates = []
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('creates a weekly template with the chosen days as a bitmask', async () => {
    await startNew('AM Rounds')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sat' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sun' }))
    await addCheckbox('Skimmers')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toEqual({
      name: 'AM Rounds', departmentId: 'dept-eng', schedule: 'weekly', shift: 'am',
      weekdays: 0b0011111, active: true, kind: 'normal', categories: [],
      items: [{ label: 'Skimmers', itemType: 'checkbox', unit: null, minValue: null,
                maxValue: null, required: true, categoryKey: null }],
    }))
  })

  it('sends no shift or days for an on-demand template', async () => {
    await startNew('Outage')
    await userEvent.click(screen.getByRole('radio', { name: 'On demand' }))
    expect(screen.queryByLabelText('Shift')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Mon' })).not.toBeInTheDocument()
    await addCheckbox('Generator started')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toMatchObject(
      { schedule: 'on_demand', shift: null, weekdays: null }))
  })

  it('saves a readings template without a schedule yet', async () => {
    await startNew('Pool')
    await userEvent.click(screen.getByRole('radio', { name: 'Readings' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Not scheduled yet' }))
    expect(screen.queryByLabelText('Shift')).not.toBeInTheDocument()
    await addCheckbox('Strip photo taken')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toMatchObject(
      { kind: 'readings', schedule: 'unscheduled', shift: null, weekdays: null }))
  })

  it('blocks saving a weekly template with no day ticked', async () => {
    await startNew('AM Rounds')
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      await userEvent.click(screen.getByRole('checkbox', { name: day }))
    }
    await addCheckbox('Skimmers')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Pick at least one day')).toBeInTheDocument()
    expect(posted()).toBeUndefined()
  })

  it('creates categories and files items under them', async () => {
    await startNew('Night Audit')
    await userEvent.click(screen.getByRole('button', { name: 'Add category' }))
    await userEvent.type(screen.getByLabelText('Name for category 1'), 'Audit')
    await addCheckbox('Night audit run')
    await userEvent.selectOptions(screen.getByLabelText('Category for item 1'), 'Audit')
    expect(within(screen.getByRole('region', { name: 'Items in Audit' }))
      .getByDisplayValue('Night audit run')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toBeDefined())
    const body = posted()
    expect(body.categories).toEqual([{ key: expect.any(String), name: 'Audit' }])
    expect(body.items[0].categoryKey).toBe(body.categories[0].key)
  })

  it('blocks saving a category with no name', async () => {
    await startNew('Night Audit')
    await userEvent.click(screen.getByRole('button', { name: 'Add category' }))
    await addCheckbox('Night audit run')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Name every category')).toBeInTheDocument()
    expect(posted()).toBeUndefined()
  })

  it('reorders, renames and removes saved categories, ungrouping the removed one\'s items', async () => {
    templates = [NIGHT]
    mount()
    await userEvent.click(await screen.findByText('Night Audit'))
    await userEvent.click(screen.getByRole('button', { name: 'Move category 2 up' }))
    await userEvent.clear(screen.getByLabelText('Name for category 1'))
    await userEvent.type(screen.getByLabelText('Name for category 1'), 'Payments & cards')
    await userEvent.click(screen.getByRole('button', { name: 'Remove category 2' })) // Audit
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(sent('PATCH')).toBeDefined())
    const body = sent('PATCH')
    expect(body.categories).toEqual([{ key: 'c-pay', id: 'c-pay', name: 'Payments & cards' }])
    expect(body.items.map((i: { id: string; categoryKey: string | null }) => [i.id, i.categoryKey]))
      .toEqual([['i-run', null], ['i-notes', null], ['i-batch', 'c-pay']])
  })

  it('lists kind, categories and "Set schedule", and filters by kind', async () => {
    templates = [NIGHT, POOL]
    mount()
    const night = (await screen.findByText('Night Audit')).closest('tr')!
    expect(within(night).getByText('Normal')).toBeInTheDocument()
    expect(within(night).getByText('Set schedule')).toBeInTheDocument()
    expect(within(night).getByText('2')).toBeInTheDocument() // categories (it has 3 items)
    const pool = screen.getByText('Pool Readings').closest('tr')!
    expect(within(pool).getByText('Readings')).toBeInTheDocument()
    expect(within(pool).getByText('AM · Every day')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Readings 1' }))
    expect(screen.queryByText('Night Audit')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Readings 1' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Readings 1' }))
    expect(screen.getByText('Night Audit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Normal 1' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/admin/ChecklistTemplatesAdmin.test.tsx`
Expected: FAIL — the posted body lacks `kind`/`categories`; no "Readings" / "Not scheduled yet"
radios, no "Add category", no chips.

- [ ] **Step 3: Create `web/src/features/admin/CategoryListEditor.tsx`**

```tsx
import { Button, Input } from '../../components/ui'
import { FieldError, LABEL, type CategoryOption } from './ItemListEditor'

/** A category being edited: `key` is what items point at; `id` is set once it is saved. */
export type CategoryDraft = CategoryOption & { id?: string }

let lastKey = 0

/** A request-local key for a category that has no id yet (checklist structure spec §3.2). */
export function newCategoryKey(): string {
  lastKey += 1
  return `new-${lastKey}`
}

/** Add, rename, reorder and remove a checklist's categories (spec §4.1). */
export function CategoryListEditor({ categories, onChange, error }: {
  categories: CategoryDraft[]
  onChange: (categories: CategoryDraft[]) => void
  error?: string
}) {
  const rename = (index: number, name: string) =>
    onChange(categories.map((c, i) => (i === index ? { ...c, name } : c)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= categories.length) return
    const next = [...categories]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Categories</p>
        <Button className="ml-auto" onClick={() => onChange([...categories, { key: newCategoryKey(), name: '' }])}>
          Add category
        </Button>
      </div>
      <FieldError message={error} />
      {categories.length === 0 ? (
        <p className="text-xs text-text3">None — every item shows in one list.</p>
      ) : (
        <ol className="flex flex-col gap-2">
          {categories.map((category, index) => {
            const n = index + 1
            return (
              <li key={category.key} className="flex items-center gap-1">
                <Input aria-label={`Name for category ${n}`} value={category.name} maxLength={120}
                       placeholder="Category name" onChange={(e) => rename(index, e.target.value)} />
                <Button variant="ghost" aria-label={`Move category ${n} up`} onClick={() => move(index, -1)}>↑</Button>
                <Button variant="ghost" aria-label={`Move category ${n} down`} onClick={() => move(index, 1)}>↓</Button>
                <Button variant="ghost" className="text-dangerText" aria-label={`Remove category ${n}`}
                        onClick={() => onChange(categories.filter((_, i) => i !== index))}>
                  Remove
                </Button>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Replace `web/src/features/admin/ChecklistTemplatesAdmin.tsx`** with:

```tsx
import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateChecklistTemplate, usePatchChecklistTemplate, useChecklistTemplates } from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import type { ChecklistKind, ChecklistSchedule, ChecklistTemplateIn, ChecklistTemplateOut, Shift } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'
import { KIND_LABELS, SHIFT_LABELS, WEEKDAYS, scheduleLabel } from '../checklists/labels'
import { AdminTable, type Column } from './AdminTable'
import { CategoryListEditor, type CategoryDraft } from './CategoryListEditor'
import { EditPanel } from './EditPanel'
import { FieldError, ItemListEditor, itemDraftFrom, orderByCategory, toItemIn, type ItemDraft } from './ItemListEditor'

type Draft = {
  id?: string
  name: string
  departmentId: string
  schedule: ChecklistSchedule
  shift: Shift
  days: boolean[]
  active: boolean
  kind: ChecklistKind
  categories: CategoryDraft[]
  items: ItemDraft[]
}

const EMPTY: Draft = {
  name: '', departmentId: '', schedule: 'weekly', shift: 'am',
  days: [true, true, true, true, true, true, true], active: true, kind: 'normal', categories: [], items: [],
}

const LABEL = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT = 'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

const SCHEDULES: [ChecklistSchedule, string][] = [
  ['weekly', 'Weekly'], ['on_demand', 'On demand'], ['unscheduled', 'Not scheduled yet'],
]
const KINDS: ChecklistKind[] = ['normal', 'readings']

function fromTemplate(t: ChecklistTemplateOut): Draft {
  const mask = t.weekdays ?? 0
  return {
    id: t.id, name: t.name, departmentId: t.departmentId ?? '', schedule: t.schedule,
    shift: t.shift ?? 'am',
    days: WEEKDAYS.map((_, i) => Boolean((mask >> i) & 1)),
    active: t.active,
    kind: t.kind,
    // A saved category's key is its id, so the items' categoryId can point straight at it.
    categories: t.categories.map((c) => ({ key: c.id, id: c.id, name: c.name })),
    items: (t.items ?? []).map((i) => ({ ...itemDraftFrom(i), categoryKey: i.categoryId ?? null })),
  }
}

export function ChecklistTemplatesAdmin() {
  const { data, isPending, error } = useChecklistTemplates()
  const { data: departments } = useDepartments()
  const create = useCreateChecklistTemplate()
  const patch = usePatchChecklistTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<ChecklistTemplateOut | null>(null)
  const [kindFilter, setKindFilter] = useState<ChecklistKind | null>(null)

  const all = data ?? []
  const rows = kindFilter ? all.filter((r) => r.kind === kindFilter) : all
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)
  const noDaysTicked = draft?.schedule === 'weekly' && !draft.days.some(Boolean)
  const unnamedCategory = Boolean(draft?.categories.some((c) => !c.name.trim()))

  const columns: Column<ChecklistTemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    {
      key: 'kind', head: 'Kind',
      render: (r) => <Badge tone={r.kind === 'readings' ? 'note' : 'neutral'}>{KIND_LABELS[r.kind]}</Badge>,
    },
    { key: 'department', head: 'Department', render: (r) => r.departmentName ?? '' },
    {
      key: 'schedule', head: 'Schedule',
      render: (r) => r.schedule === 'unscheduled'
        ? <span className="font-semibold text-accent">{scheduleLabel(r)}</span>
        : scheduleLabel(r),
    },
    { key: 'categories', head: 'Categories', mono: true, render: (r) => r.categories.length },
    { key: 'items', head: 'Items', mono: true, render: (r) => (r.items ?? []).length },
    { key: 'active', head: 'Active', render: (r) => (r.active ? <Badge tone="ok">on</Badge> : <Badge>off</Badge>) },
  ]

  function clearFailures() {
    create.reset()
    patch.reset()
  }

  function close() {
    clearFailures()
    setDraft(null)
    setSelected(null)
  }

  function edit(change: Partial<Draft>) {
    if (draft) setDraft({ ...draft, ...change })
  }

  /** Removing a category leaves its items ungrouped (checklist structure spec §2.2). */
  function editCategories(categories: CategoryDraft[]) {
    if (!draft) return
    const keys = new Set(categories.map((c) => c.key))
    setDraft({
      ...draft, categories,
      items: draft.items.map((i) => (i.categoryKey && !keys.has(i.categoryKey) ? { ...i, categoryKey: null } : i)),
    })
  }

  function open(template: ChecklistTemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim() || noDaysTicked || unnamedCategory) return
    const weekly = draft.schedule === 'weekly'
    const keys = new Set(draft.categories.map((c) => c.key))
    const body: ChecklistTemplateIn = {
      name: draft.name.trim(), departmentId: draft.departmentId, schedule: draft.schedule,
      shift: weekly ? draft.shift : null,
      weekdays: weekly
        ? draft.days.reduce((mask, on, i) => (on ? mask | (1 << i) : mask), 0) : null,
      active: draft.active, kind: draft.kind,
      categories: draft.categories.map((c) => ({ key: c.key, ...(c.id ? { id: c.id } : {}), name: c.name.trim() })),
      // Items1 is a non-empty tuple; the server itself enforces "at least one item"
      // (ValidationFailed on save), so a cast here is safe and mirrors that contract.
      // Saved in the grouped order the editor shows, so positions match what the admin saw.
      items: orderByCategory(draft.items, draft.categories).map((i) => ({
        ...toItemIn(i),
        categoryKey: i.categoryKey && keys.has(i.categoryKey) ? i.categoryKey : null,
      })) as ChecklistTemplateIn['items'],
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Checklist templates</h1>
          <div className="flex gap-1.5">
            {KINDS.map((kind) => (
              <button
                key={kind}
                type="button"
                aria-pressed={kindFilter === kind}
                onClick={() => setKindFilter(kindFilter === kind ? null : kind)}
                className={cn(
                  'inline-flex h-8 items-center rounded px-3 text-xs font-semibold',
                  kindFilter === kind ? 'bg-accent text-accentText' : 'bg-surface2 text-text3 hover:text-text',
                )}
              >
                {KIND_LABELS[kind]} {all.filter((r) => r.kind === kind).length}
              </button>
            ))}
          </div>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, categories: [], items: [] })
            }}
          >
            New template
          </Button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {isPending ? (
            <Spinner />
          ) : error ? (
            <EmptyState title="Could not load templates" hint={error.message} />
          ) : rows.length === 0 ? (
            <EmptyState title="No checklist templates" hint="A weekly template repeats on a shift and chosen days; an on-demand one is started manually." />
          ) : (
            <div className="rounded-card border border-border2 bg-surface">
              <AdminTable columns={columns} rows={rows} selectedId={selected?.id ?? null} onSelect={open} />
            </div>
          )}
        </div>
      </div>

      {draft ? (
        <EditPanel
          subjectId={draft.id ?? 'new'}
          title={draft.id ? 'Edit template' : 'New template'}
          saving={pending}
          error={failed?.message ?? null}
          onSave={save}
          onCancel={close}
        >
          <div>
            <label className={LABEL} htmlFor="tpl-name">Name</label>
            <Input id="tpl-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="tpl-dept">Department</label>
            <select id="tpl-dept" aria-label="Department" className={SELECT} value={draft.departmentId}
                    onChange={(e) => edit({ departmentId: e.target.value })}>
              <option value="">None</option>
              {(departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
            <FieldError message={fields.departmentId} />
          </div>

          <div>
            <p className={LABEL}>Kind</p>
            <div className="flex gap-4">
              {KINDS.map((kind) => (
                <label key={kind} className="flex items-center gap-2 text-sm">
                  <input type="radio" name="kind" checked={draft.kind === kind}
                         onChange={() => edit({ kind })} />
                  {KIND_LABELS[kind]}
                </label>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-4">
            {SCHEDULES.map(([schedule, label]) => (
              <label key={schedule} className="flex items-center gap-2 text-sm">
                <input type="radio" name="schedule" checked={draft.schedule === schedule}
                       onChange={() => edit({ schedule })} />
                {label}
              </label>
            ))}
          </div>

          {draft.schedule === 'weekly' ? (
            <>
              <div>
                <label className={LABEL} htmlFor="tpl-shift">Shift</label>
                <select id="tpl-shift" aria-label="Shift" className={SELECT} value={draft.shift}
                        onChange={(e) => edit({ shift: e.target.value as Shift })}>
                  {(Object.keys(SHIFT_LABELS) as Shift[]).map((s) => (
                    <option key={s} value={s}>{SHIFT_LABELS[s]}</option>
                  ))}
                </select>
                <FieldError message={fields.shift} />
              </div>
              <div>
                <p className={LABEL}>Days</p>
                <div className="flex flex-wrap gap-3">
                  {WEEKDAYS.map((day, i) => (
                    <label key={day} className="flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={draft.days[i]}
                        onChange={(e) =>
                          edit({ days: draft.days.map((d, j) => (j === i ? e.target.checked : d)) })
                        }
                      />
                      {day}
                    </label>
                  ))}
                </div>
                <FieldError message={fields.weekdays ?? (noDaysTicked ? 'Pick at least one day' : undefined)} />
              </div>
            </>
          ) : draft.schedule === 'unscheduled' ? (
            <p className="text-xs text-text3">
              Saved without a schedule, it never appears on the Checklists page. Pick Weekly or On
              demand when it is ready.
            </p>
          ) : null}

          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <CategoryListEditor
            categories={draft.categories}
            onChange={editCategories}
            error={fields.categories ?? (unnamedCategory ? 'Name every category' : undefined)}
          />

          <ItemListEditor items={draft.items} onChange={(items) => edit({ items })} error={fields.items}
                          categories={draft.categories} />
        </EditPanel>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 5: Run** `cd web && npx vitest run src/features/admin && npm run lint && npm run build` → PASS
(`PmTemplatesAdmin.test.tsx` included, unchanged).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/admin/CategoryListEditor.tsx web/src/features/admin/ChecklistTemplatesAdmin.tsx web/src/features/admin/ChecklistTemplatesAdmin.test.tsx
git commit -m "feat(checklists): admin editor for kind, categories and unscheduled templates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Import from library

**Files:**
- Create: `web/src/features/admin/LibraryImportDialog.tsx` (+`LibraryImportDialog.test.tsx`)
- Modify: `web/src/features/admin/ChecklistTemplatesAdmin.tsx`

**Interfaces:**
- Consumes: Task 7's `useChecklistLibrary`, `useImportChecklist`, `KIND_LABELS`; Task 9's
  `ChecklistTemplatesAdmin` and its `open(template)`; `Dialog` from `components/ui`; `SELECT`
  from `ItemListEditor`.
- Produces: `LibraryImportDialog({ open, onClose, onImported }: { open: boolean; onClose: () =>
  void; onImported: (template: ChecklistTemplateOut) => void })`; an "Import from library"
  button beside "New template".

- [ ] **Step 1: Write the failing test** — `web/src/features/admin/LibraryImportDialog.test.tsx`
(it drives the whole flow through the admin screen: pick → department → lands in the editor):

```tsx
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChecklistLibraryEntryOut, ChecklistTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

const LIBRARY: ChecklistLibraryEntryOut[] = [
  { key: 'night_audit', name: 'Night Audit', kind: 'normal', departmentType: 'front_desk',
    categories: [{ name: 'Pre-audit', itemCount: 2 }, { name: 'Handover', itemCount: 2 }], itemCount: 4 },
  { key: 'pool_spa', name: 'Pool & Spa Readings', kind: 'readings', departmentType: 'engineering',
    categories: [], itemCount: 5 },
]

const IMPORTED: ChecklistTemplateOut = {
  id: 't-new', name: 'Night Audit', departmentId: 'dept-fd', departmentName: 'Front Desk',
  schedule: 'unscheduled', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [{ id: 'c-pre', name: 'Pre-audit', position: 0 }],
  items: [{ id: 'i-1', position: 0, label: 'No-shows posted', itemType: 'checkbox', unit: null,
            minValue: null, maxValue: null, required: true, active: true, categoryId: 'c-pre' }],
}

let importStatus = 201

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    const reply = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status }))
    if (url.includes('/departments')) {
      return reply([aDepartment(), aDepartment({ id: 'dept-fd', name: 'Front Desk', type: 'front_desk' })])
    }
    if (url.endsWith('/checklists/library')) return reply(LIBRARY)
    if (url.includes('/import')) {
      return importStatus === 201
        ? reply(IMPORTED, 201)
        : reply({ error: { code: 'VALIDATION_FAILED', message: 'Unknown department',
                           details: { departmentId: 'unknown' } } }, importStatus)
    }
    return reply([])
  })
}

function mount() {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

function importCall() {
  const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes('/import'))
  return call ? { url: String(call[0]), body: JSON.parse(String(call[1]!.body)) } : undefined
}

describe('Import from library', () => {
  beforeEach(() => {
    importStatus = 201
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists the starter checklists with their kind, categories and item count', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    expect(await screen.findByText('Pool & Spa Readings')).toBeInTheDocument()
    expect(screen.getByText('Pre-audit · Handover — 4 items')).toBeInTheDocument()
    expect(screen.getByText('5 items')).toBeInTheDocument()
    expect(screen.getByText('Readings')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled()
  })

  it('imports into the chosen department and opens the copy in the editor', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    await user.click(await screen.findByRole('radio', { name: /Night Audit/ }))
    // the entry's department type is suggested
    expect(screen.getByLabelText('Department', { selector: '#library-dept' })).toHaveValue('dept-fd')
    await user.click(screen.getByRole('button', { name: 'Import' }))
    await waitFor(() => expect(importCall()).toEqual({
      url: '/api/p/prop-a/checklists/library/night_audit/import', body: { departmentId: 'dept-fd' } }))
    expect(await screen.findByText('Edit template')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Import from library' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveValue('Night Audit')
    expect(screen.getByRole('radio', { name: 'Not scheduled yet' })).toBeChecked()
    expect(screen.getByLabelText('Name for category 1')).toHaveValue('Pre-audit')
  })

  it('shows a refused import inside the dialog', async () => {
    importStatus = 400
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: 'Import from library' }))
    await user.click(await screen.findByRole('radio', { name: /Night Audit/ }))
    await user.click(screen.getByRole('button', { name: 'Import' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Unknown department')
    expect(screen.getByRole('dialog', { name: 'Import from library' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/features/admin/LibraryImportDialog.test.tsx`
Expected: FAIL — no "Import from library" button.

- [ ] **Step 3: Create `web/src/features/admin/LibraryImportDialog.tsx`**

```tsx
import { useState } from 'react'
import { useChecklistLibrary, useImportChecklist } from '../../api/hooks/checklists'
import { useDepartments } from '../../api/hooks/users'
import type { ChecklistLibraryEntryOut, ChecklistTemplateOut } from '../../api/types'
import { Badge, Button, Dialog, Spinner } from '../../components/ui'
import { KIND_LABELS } from '../checklists/labels'
import { SELECT } from './ItemListEditor'

function summary(entry: ChecklistLibraryEntryOut): string {
  const categories = entry.categories.map((c) => c.name).join(' · ')
  const items = `${entry.itemCount} item${entry.itemCount === 1 ? '' : 's'}`
  return categories ? `${categories} — ${items}` : items
}

/**
 * Import From Library (checklist structure spec §4.1): pick a starter checklist and a department;
 * the copy arrives unscheduled and `onImported` opens it in the editor to review and schedule.
 */
export function LibraryImportDialog({ open, onClose, onImported }: {
  open: boolean
  onClose: () => void
  onImported: (template: ChecklistTemplateOut) => void
}) {
  const { data: entries, isPending, error } = useChecklistLibrary(open)
  const { data: departments } = useDepartments()
  const importChecklist = useImportChecklist()
  const [key, setKey] = useState('')
  const [departmentId, setDepartmentId] = useState('')

  function close() {
    importChecklist.reset()
    setKey('')
    setDepartmentId('')
    onClose()
  }

  function choose(entry: ChecklistLibraryEntryOut) {
    setKey(entry.key)
    // Suggest the first department of the entry's type; the admin can pick another.
    const match = (departments ?? []).find((d) => d.type === entry.departmentType)
    if (match) setDepartmentId(match.id)
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title="Import from library"
      wide
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            disabled={!key || !departmentId}
            loading={importChecklist.isPending}
            onClick={() =>
              importChecklist.mutate({ key, departmentId }, {
                onSuccess: (template) => {
                  importChecklist.reset()
                  setKey('')
                  setDepartmentId('')
                  onImported(template)
                },
              })
            }
          >
            Import
          </Button>
        </>
      }
    >
      <p className="text-xs text-text3">
        A starter checklist is copied into this property without a schedule. Review it, then pick
        Weekly or On demand.
      </p>
      {isPending ? (
        <Spinner />
      ) : error ? (
        <p role="alert" className="text-sm text-dangerText">{error.message}</p>
      ) : (
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">Starter checklists</legend>
          {entries.map((entry) => (
            <label key={entry.key} className="flex items-start gap-2 rounded border border-border2 p-2 text-sm">
              <input type="radio" name="library-entry" className="mt-1" checked={key === entry.key}
                     onChange={() => choose(entry)} />
              <span className="flex flex-col gap-1">
                <span className="flex items-center gap-2 font-semibold">
                  {entry.name}
                  {entry.kind === 'readings' ? <Badge tone="note">{KIND_LABELS.readings}</Badge> : null}
                </span>
                <span className="text-xs text-text3">{summary(entry)}</span>
              </span>
            </label>
          ))}
        </fieldset>
      )}
      <div>
        <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-text3" htmlFor="library-dept">
          Department
        </label>
        <select id="library-dept" className={SELECT} value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}>
          <option value="">Choose a department</option>
          {(departments ?? []).map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>
      {importChecklist.error ? (
        <p role="alert" className="text-sm text-dangerText">{importChecklist.error.message}</p>
      ) : null}
    </Dialog>
  )
}
```

- [ ] **Step 4: Wire it into `web/src/features/admin/ChecklistTemplatesAdmin.tsx`**

After the `ItemListEditor` import add `import { LibraryImportDialog } from './LibraryImportDialog'`.

After `const [kindFilter, setKindFilter] = useState<ChecklistKind | null>(null)` add
`  const [importing, setImporting] = useState(false)`.

Replace

```tsx
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
```

with

```tsx
          <Button className="ml-auto" onClick={() => setImporting(true)}>
            Import from library
          </Button>
          <Button
            variant="primary"
            onClick={() => {
```

and replace

```tsx
      {draft ? (
        <EditPanel
```

with

```tsx
      <LibraryImportDialog
        open={importing}
        onClose={() => setImporting(false)}
        onImported={(template) => {
          setImporting(false)
          open(template)
        }}
      />

      {draft ? (
        <EditPanel
```

- [ ] **Step 5: Run** `cd web && npx vitest run src/features/admin && npm run lint && npm run build` → PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/admin/LibraryImportDialog.tsx web/src/features/admin/LibraryImportDialog.test.tsx web/src/features/admin/ChecklistTemplatesAdmin.tsx
git commit -m "feat(checklists): import a starter checklist from the library" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Checklist page — grouped, collapsible sections; Readings tags

**Files:**
- Modify: `web/src/features/checklists/ChecklistRunPage.tsx`,
  `web/src/features/checklists/ChecklistRunPage.test.tsx`,
  `web/src/features/checklists/ChecklistsPage.tsx`,
  `web/src/features/checklists/ChecklistsPage.test.tsx`

**Interfaces:**
- Consumes: Task 4's `ChecklistInstanceOut.categories` / `kind`, `ChecklistInstanceRowOut.kind`;
  Task 7's `groupByCategory`, `KIND_LABELS`. PM's `ChecklistItem` renders every row unchanged.

- [ ] **Step 1: Write the failing tests**

`web/src/features/checklists/ChecklistRunPage.test.tsx` — replace the first import line with
`import { screen, waitFor, within } from '@testing-library/react'`; directly above
`let instance: ChecklistInstanceOut = BASE` add:

```tsx
// Checklist structure spec §2.2: Skimmers ungrouped, Pool pH under "Pool" (answered, so 1 / 1).
const GROUPED: ChecklistInstanceOut = {
  ...BASE, kind: 'readings',
  categories: [{ id: 'c-pool', name: 'Pool', position: 0, done: 1, total: 1 }],
  items: [{ ...BASE.items[0]!, categoryId: null }, { ...BASE.items[1]!, categoryId: 'c-pool' }],
}

```

and directly above `  it('shows a failed save inline', async () => {` add:

```tsx
  it('shows a checklist without categories as one list with no headings', async () => {
    mount()
    await screen.findByRole('checkbox', { name: /Skimmers/ })
    expect(screen.queryByRole('button', { name: /done$/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Readings')).not.toBeInTheDocument()
  })

  it('groups items under collapsible category headings with progress, ungrouped first', async () => {
    instance = GROUPED
    const user = userEvent.setup()
    mount()
    const heading = await screen.findByRole('button', { name: 'Pool, 1 of 1 done' })
    expect(heading).toHaveAttribute('aria-expanded', 'true')
    expect(within(heading).getByText('1 / 1')).toBeInTheDocument()
    const pool = screen.getByRole('region', { name: 'Pool' })
    expect(within(pool).getByText(/Pool pH/)).toBeInTheDocument()
    expect(within(pool).queryByText(/Skimmers/)).not.toBeInTheDocument()
    // the ungrouped item is above the first heading
    const skimmers = screen.getByRole('checkbox', { name: /Skimmers/ })
    expect(skimmers.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.click(heading)
    expect(heading).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/Pool pH/)).not.toBeInTheDocument()
    await user.click(heading)
    expect(screen.getByText(/Pool pH/)).toBeInTheDocument()
  })

  it('tags a readings checklist in the header', async () => {
    instance = GROUPED
    mount()
    expect(await screen.findByText('Readings')).toBeInTheDocument()
  })

```

`web/src/features/checklists/ChecklistsPage.test.tsx` — make the PM Walk row a readings
checklist: in `TODAY` replace

```tsx
        status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer', done: 2,
        total: 5, outOfRangeCount: 1 }),
```

with

```tsx
        status: 'in_progress', kind: 'readings', assignedUserId: 'u-eli',
        assignedName: 'Eli Engineer', done: 2, total: 5, outOfRangeCount: 1 }),
```

and directly above `  it('asks the server for my department by default', async () => {` add:

```tsx
  it('tags a readings checklist card', async () => {
    mount('dept_staff')
    const pm = (await screen.findByText('Engineering PM Walk')).closest('li')!
    expect(within(pm).getByText('Readings')).toBeInTheDocument()
    const am = screen.getByText('Engineering AM Rounds').closest('li')!
    expect(within(am).queryByText('Readings')).not.toBeInTheDocument()
  })

  it('never offers an unscheduled template in the on-demand menu', async () => {
    const unscheduled: ChecklistTemplateOut = { ...ON_DEMAND, id: 't-later', name: 'Deep Clean',
                                                schedule: 'unscheduled' }
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      const body = url.includes('/departments') ? [aDepartment()]
        : url.includes('staff-directory') ? []
        : url.includes('/checklists/templates') && method === 'GET' ? [ON_DEMAND, unscheduled]
        : TODAY
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    })
    mount('dept_staff')
    const menu = await screen.findByLabelText('Start a checklist')
    expect(within(menu).getAllByRole('option').map((o) => o.textContent))
      .toEqual(['Choose one', 'Power Outage'])
  })

```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/checklists`
Expected: FAIL — no "Pool, 1 of 1 done" heading and no "Readings" tag. (The on-demand menu
test already passes: `StartOnDemand` filters on `schedule === 'on_demand'`; it pins that.)

- [ ] **Step 3: Group the checklist page** — `web/src/features/checklists/ChecklistRunPage.tsx`.

Replace

```tsx
import { ChecklistItem } from '../pm/ChecklistItem'
import { SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'
```

with

```tsx
import type { ChecklistItemOut } from '../../api/types'
import { ChecklistItem } from '../pm/ChecklistItem'
import { groupByCategory } from './grouping'
import { KIND_LABELS, SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'
```

After `  const [actionError, setActionError] = useState<string | null>(null)` add

```tsx
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set())
```

After `  const general = photos.filter((p) => !p.itemId)` add

```tsx
  const { ungrouped, groups } = groupByCategory(items, instance.categories ?? [])
  const toggle = (categoryId: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev)
      if (next.has(categoryId)) next.delete(categoryId)
      else next.add(categoryId)
      return next
    })

  const renderItem = (item: ChecklistItemOut) => (
    <ChecklistItem
      key={item.id}
      item={item}
      answer={answerFor(item.id)}
      photos={photos.filter((p) => p.itemId === item.id)}
      readOnly={readOnly}
      missing={missing.has(item.id)}
      onSave={(patch) => {
        const answer = answerFor(item.id)
        if (answer) {
          save.mutate({ instanceId: instance.id, answerId: answer.id, patch }, { onError: fail })
        }
      }}
      onUpload={(file) =>
        upload.mutate({ instanceId: instance.id, file, itemId: item.id }, { onError: fail })
      }
    />
  )
```

After the status badge line
`        <Badge tone={STATUS_TONE[instance.status]}>{STATUS_LABELS[instance.status]}</Badge>` add

```tsx
        {instance.kind === 'readings' ? <Badge tone="note">{KIND_LABELS.readings}</Badge> : null}
```

Replace the item list (the `) : (` branch after the "waiting to be started" states, from
`          <ol className="flex flex-col gap-3">` through its closing `          </ol>`) with:

```tsx
          <>
            {/* Ungrouped items first, with no heading: a checklist without categories looks
                exactly as it always has (checklist structure spec §2.2). */}
            {ungrouped.length > 0 ? (
              <ol className="flex flex-col gap-3">{ungrouped.map(renderItem)}</ol>
            ) : null}
            {groups.map((group) => {
              const open = !collapsed.has(group.id)
              return (
                <section key={group.id} aria-label={group.name} className="flex flex-col gap-2">
                  <button
                    type="button"
                    aria-expanded={open}
                    aria-label={`${group.name}, ${group.done} of ${group.total} done`}
                    onClick={() => toggle(group.id)}
                    className="flex items-center gap-2 text-left text-xs font-bold uppercase tracking-widest text-text3 hover:text-text"
                  >
                    <span aria-hidden="true">{open ? '▾' : '▸'}</span>
                    <span>{group.name}</span>
                    <span className="ml-auto font-mono normal-case tracking-normal">
                      {group.done} / {group.total}
                    </span>
                  </button>
                  {open ? <ol className="flex flex-col gap-3">{group.items.map(renderItem)}</ol> : null}
                </section>
              )
            })}
          </>
```

(The `useState` for `collapsed` sits with the other hooks, above the early returns.)

- [ ] **Step 4: Tag readings cards** — `web/src/features/checklists/ChecklistsPage.tsx`: replace
`import { SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'` with
`import { KIND_LABELS, SHIFT_LABELS, STATUS_LABELS, STATUS_TONE } from './labels'`, and after
`        <span className="text-sm font-semibold">{row.templateName}</span>` add

```tsx
        {row.kind === 'readings' ? <Badge tone="note">{KIND_LABELS.readings}</Badge> : null}
```

- [ ] **Step 5: Run** `cd web && npm test && npm run lint && npm run build` → PASS (the whole suite).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/checklists/ChecklistRunPage.tsx web/src/features/checklists/ChecklistRunPage.test.tsx web/src/features/checklists/ChecklistsPage.tsx web/src/features/checklists/ChecklistsPage.test.tsx
git commit -m "feat(checklists): grouped, collapsible categories on the checklist page and Readings tags" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Postgres 18 verification and full check — stop before pushing

Nothing in this task is committed except fixes it forces.

- [ ] **Step 1: Everything green locally** — `cd server && ../.venv/Scripts/python.exe -m pytest -q`
and `../.venv/Scripts/python.exe -m ruff check .`; `cd web && npm test && npm run lint && npm run build`.
Regenerate the schema and types and confirm `git status --short web/src/api` shows nothing.
Confirm `git ls-files --eol` reports `w/crlf` for every file this branch created.

- [ ] **Step 2: Migrate a fresh Postgres 18 database up, down and up again** (Docker Desktop must
be running; start it from `C:\Users\bryan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`
if `docker info` fails). Reuse the existing `relay-pg18` container — **never** `docker rm -f` it,
and never touch the `relay_dev` database in it; work only in a throwaway `relay_ckstruct`:

```bash
docker start relay-pg18 2>/dev/null || docker run -d --name relay-pg18 -e POSTGRES_PASSWORD=relaydev -e POSTGRES_USER=relay -e POSTGRES_DB=relay_test -p 55432:5432 postgres:18
# wait for: docker exec relay-pg18 pg_isready -U relay
docker exec relay-pg18 psql -U relay -d postgres -c "DROP DATABASE IF EXISTS relay_ckstruct" -c "CREATE DATABASE relay_ckstruct"
cd server && export DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_ckstruct"
../.venv/Scripts/python.exe -m alembic upgrade 0010
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at) VALUES ('p1','P','PPP','UTC','USD','{}','2026-09-10','2026-09-10')" -c "INSERT INTO department (id,property_id,name,type,escalation_minutes,active,created_at,updated_at) VALUES ('d1','p1','FD','front_desk',15,true,'2026-09-10','2026-09-10')" -c "INSERT INTO checklist_template (id,property_id,name,department_id,schedule,shift,weekdays,active,created_at,updated_at) VALUES ('t1','p1','NA','d1','weekly','overnight',127,true,'2026-09-10','2026-09-10')"
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "SELECT kind FROM checklist_template" -c "\d checklist_template" -c "\d checklist_template_item"
```

Expected: `kind = normal` for the pre-existing row; `\d checklist_template` lists
`ck_enum_checklistkind`, `ck_enum_checklistschedule` with `'unscheduled'`, and
`ck_checklist_template_schedule_fields` with `schedule IN ('on_demand', 'unscheduled')` (Postgres
prints it as `= ANY (ARRAY[...])`); `\d checklist_template_item` lists `category_id` and
`fk_checklist_template_item_category_id`. Then prove the CHECK and the downgrade refusal:

```bash
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "UPDATE checklist_template SET schedule='unscheduled', shift=NULL, weekdays=NULL"
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "UPDATE checklist_template SET shift='am'"          # → ERROR: violates check constraint "ck_checklist_template_schedule_fields"
../.venv/Scripts/python.exe -m alembic downgrade 0010                                                          # → RuntimeError: Refusing to downgrade 0011: 1 checklist template(s) are unscheduled ...
docker exec relay-pg18 psql -U relay -d relay_ckstruct -tAc "SELECT version_num FROM alembic_version"          # → 0011
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "UPDATE checklist_template SET schedule='weekly', shift='overnight', weekdays=127"
../.venv/Scripts/python.exe -m alembic downgrade 0010
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "\dt checklist*" -c "\d checklist_template"         # → five tables, no kind, the 0009 CHECKs
../.venv/Scripts/python.exe -m alembic upgrade head
```

Check drift against Postgres too:

```bash
cd server && ../.venv/Scripts/python.exe -c "
from app.db import Base; import app.models, sqlalchemy as sa
from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata
e=sa.create_engine('postgresql+psycopg://relay:relaydev@localhost:55432/relay_ckstruct'); print([d for d in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata) if 'checklist' in str(d)]); e.dispose()"
```

Expected: `[]`.

- [ ] **Step 3: Seed and exercise the app on Postgres 18** — recreate `relay_ckstruct`, seed it
through the normal path, and drive the real routes. Save this as `pg_smoke.py` in the session
scratchpad directory (outside the repo) — do not commit it:

```python
"""Throwaway Postgres smoke check for checklist structure (plan Task 12). Not committed."""
import sys

from app import create_app
from app.config import Config

URL = sys.argv[1]
app = create_app(Config(DATABASE_URL=URL, TESTING=True, START_WORKER=False, ENV="testing",
                        PMS_TICK_SECONDS=0))


def login(email):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"email": email,
                                           "password": "Password123!"}).status_code == 200
    return c


admin = login("alex@hvh.test")
pid = next(m["propertyId"] for m in admin.get("/api/auth/me").get_json()["memberships"]
           if m["propertyCode"] == "HVH")
base = f"/api/p/{pid}/checklists"
templates = {t["name"]: t for t in admin.get(f"{base}/templates").get_json()}
night = templates["Front Desk Overnight Night Audit"]
print("night audit categories:", [c["name"] for c in night["categories"]])
assert [c["name"] for c in night["categories"]] == ["Audit", "Payments", "Reports"]
assert templates["Engineering AM Rounds"]["kind"] == "readings"
library = admin.get(f"{base}/library").get_json()
print("library:", [e["key"] for e in library])
assert len(library) == 6
engineering = templates["Engineering AM Rounds"]["departmentId"]
imported = admin.post(f"{base}/library/boiler_rounds/import", json={"departmentId": engineering})
print("import:", imported.status_code, imported.get_json().get("schedule"))
assert imported.status_code == 201 and imported.get_json()["schedule"] == "unscheduled"
tid = imported.get_json()["id"]
# the unscheduled row passes the rebuilt CHECK; with a shift it must be a clean 400, not a 500
bad = admin.patch(f"{base}/templates/{tid}", json={"shift": "am"})
print("unscheduled + shift:", bad.status_code)
assert bad.status_code == 400
eli = login("eli@hvh.test")
assert eli.post(f"{base}/templates/{tid}/start").status_code == 409
night_items = night["items"]
moved = admin.patch(f"{base}/templates/{night['id']}", json={
    "categories": [{"key": c["id"], "id": c["id"], "name": c["name"]}
                   for c in night["categories"][:2]],
    "items": [{"id": i["id"], "label": i["label"], "itemType": i["itemType"],
               "required": i["required"], "categoryKey": i["categoryId"]}
              for i in night_items[:2]] + [
        {"id": night_items[2]["id"], "label": night_items[2]["label"],
         "itemType": night_items[2]["itemType"], "required": night_items[2]["required"]}]})
print("drop Reports:", moved.status_code, [i["categoryId"] for i in moved.get_json()["items"]])
assert moved.status_code == 200 and moved.get_json()["items"][2]["categoryId"] is None
schedule = admin.patch(f"{base}/templates/{tid}", json={
    "schedule": "weekly", "shift": "am", "weekdays": 127})
assert schedule.status_code == 200, schedule.get_json()
pool = admin.post(f"{base}/library/pool_spa/import", json={"departmentId": engineering})
assert pool.status_code == 201  # left unscheduled on purpose: Step 4 needs one
rows = login("ava@hvh.test").get(f"{base}/instances").get_json()
print("row kinds:", sorted({r["kind"] for r in rows}))
assert all(r["kind"] in ("normal", "readings") for r in rows)
print("OK")
app.extensions["db"].engine.dispose()
```

```bash
docker exec relay-pg18 psql -U relay -d postgres -c "DROP DATABASE IF EXISTS relay_ckstruct" -c "CREATE DATABASE relay_ckstruct"
cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('postgresql+psycopg://relay:relaydev@localhost:55432/relay_ckstruct', reset=False))"
../.venv/Scripts/python.exe "$SCRATCHPAD/pg_smoke.py" "postgresql+psycopg://relay:relaydev@localhost:55432/relay_ckstruct"   # SCRATCHPAD = the session scratchpad directory the script was saved in
```

Expected: the seed summary shows `checklist_templates=5`; the script prints `OK`. Optionally
also run the full app on it (`DATABASE_URL=".../relay_ckstruct" .venv/Scripts/python.exe
server/dev_start.py` and `cd web && npm run dev`), log in as `alex@hvh.test` / `Password123!`,
open Admin → Checklist templates (chips, "Set schedule", Import from library), then as
`jordan@hvh.test` open tonight's Night Audit and collapse a category.

- [ ] **Step 4: The downgrade refusal on real, seeded data** — the smoke left Pool & Spa
Readings unscheduled:

```bash
cd server && export DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_ckstruct"
../.venv/Scripts/python.exe -m alembic downgrade 0010                                                 # → RuntimeError: Refusing to downgrade 0011: 1 checklist template(s) ...
docker exec relay-pg18 psql -U relay -d relay_ckstruct -tAc "SELECT version_num FROM alembic_version" # → 0011
docker exec relay-pg18 psql -U relay -d relay_ckstruct -c "UPDATE checklist_template SET schedule = 'on_demand' WHERE schedule = 'unscheduled'"
../.venv/Scripts/python.exe -m alembic downgrade 0010
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_ckstruct -tAc "SELECT kind, count(*) FROM checklist_template GROUP BY kind"   # → normal|7 (kind and categories are dropped by a downgrade, by design)
```

Afterwards drop `relay_ckstruct` (`docker exec relay-pg18 psql -U relay -d postgres -c "DROP
DATABASE relay_ckstruct"`); leave the container and `relay_dev` alone.

- [ ] **Step 5: STOP — report, do not push.** Show `git log --oneline origin/main..HEAD` and the
verification results to the controller. Do **not** run `git push`: pushing `main` deploys to
production, and the controller pushes. After the push, the deploy must be verified as
`CLAUDE.md` says — the deployment for the new head with reason `deploy`, its log showing
`==> alembic upgrade head` before `==> gunicorn`, `/api/health` ok, and
`SELECT version_num FROM alembic_version` returning `0011` with `checklist_template_category`
present and empty and every existing template `kind = 'normal'` (production is never seeded; the
hotel's admin imports starter checklists from Admin → Checklist templates).

---

## Self-review

- **Spec coverage.** §2.1 model and migration → Task 1; §2.2 grouping and progress → Tasks 4,
  11; snapshot unchanged → Tasks 3, 4; removing a category → Tasks 3, 9; unscheduled (tick,
  picker, 409, "Set schedule", switching) → Tasks 1, 2, 9, 11; readings kind (chip, tag on rows,
  cards and the checklist page) → Tasks 3, 4, 9, 11; §3.1 wire models → Tasks 3, 4, 5; §3.2 save
  semantics and the four errors → Task 3; §3.3 routes, 404/400, default name, isolation → Task 5;
  §3.4 the six entries and the validity test → Task 5; §4.1 list, editor, import → Tasks 8, 9,
  10; §4.2 checklist page → Task 11; §4.3 cards → Task 11; §5 seed → Task 6; §6 Postgres → Task
  12; §7 testing → every task. Deferred items (per-category ownership, optional categories,
  portfolio sharing, multilingual) have no task, by the spec.
- **PM regression.** `TemplateItemIn`, `TemplateItemOut` and `typed_items.sync_items` are not
  edited; `test_pm_items_still_refuse_a_category_key` (Task 3) and PM's admin tests (Tasks 8, 9)
  guard it.
- **Types.** `ChecklistCategoryIn.key` / `ChecklistItemIn.categoryKey` / `ChecklistItemOut.
  categoryId` / `ChecklistCategoryProgressOut.done|total` / `ChecklistInstanceRowOut.kind` /
  `ChecklistLibraryEntryOut.departmentType|itemCount` are named the same in every task that
  uses them; `CategoryOption`, `CategoryDraft`, `orderByCategory`, `groupByCategory`,
  `scheduleLabel`, `KIND_LABELS`, `useChecklistLibrary(enabled)`, `useImportChecklist()` match
  between producer and consumer tasks.
