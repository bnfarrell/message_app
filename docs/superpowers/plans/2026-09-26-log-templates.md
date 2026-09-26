# Hotel Log Post Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let staff post structured shift reports (AM Checklist, PM Checklist, Night Audit) to
the hotel log: admin-managed templates with typed fields and an audience, typed value rows with
label/type snapshots, a generated text body, a table on the feed card, and an Admin → Log
templates screen with usage counts.

**Architecture:** Migration `0010` adds four tables (`log_template`, `log_template_field`,
`log_template_audience`, `log_entry_field_value`) and one nullable column,
`log_entry.template_id`. A new domain module, `app/domain/log_templates.py`, owns template CRUD,
the audience rule, answer validation, the body summary and both template lists; `log.create`
calls it when a post carries `templateId`, so a templated post is still an ordinary `log_entry`
created through the one existing path. The web client adds a picker and typed fields to
`LogComposer`, a value table to `LogEntryCard`, and a `LogTemplatesAdmin` screen.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · pytest; Vite +
React + TypeScript + TanStack Query + Vitest.

**Spec:** `docs/superpowers/specs/2026-09-26-log-templates-design.md` — read it before any task.
Where this plan is more precise than the spec, "Spec clarifications" says so.

## Global Constraints

- Python by explicit path only: `cd server && ../.venv/Scripts/python.exe -m pytest -q`. Bare
  `python` is a silent Windows Store stub.
- Lint: `cd server && ../.venv/Scripts/python.exe -m ruff check .` — line length 100.
- Frontend: `cd web && npm test && npm run lint && npm run build` — all three clean.
- Engine-portable SQL only: no JSON filtering, no Postgres-only functions. The answers are rows
  (`log_entry_field_value`), never a JSON column.
- Every enum column through `enum_type()`; in the migration through the local `_enum()` helper.
  The new enum is `LogFieldType`: `short_text` · `long_text` · `integer` · `decimal` · `percent`.
- Times from `app.clock.now()` (aware UTC). Shifts through `app.domain.shifts` /
  `log.shift_for`, never a UTC wall clock.
- `ValidationFailed` is HTTP 400 `VALIDATION_FAILED`; `Forbidden` 403; `NotFound` 404.
- API models subclass `CamelModel` and live in `app/schemas/log.py`.
- No new capabilities: posting uses `post_log`, managing uses `manage_admin` (admin,
  corporate). `server/app/auth/permissions.py` and `web/src/auth/capabilities.ts` do not change.
- After any schema change: `cd server && ../.venv/Scripts/python.exe -m
  app.schemas.export_json_schema`, then `cd web && npm run gen:types`, then re-export the new
  names from `web/src/api/types.ts`. Never hand-edit `schema.json` or `types.generated.ts`.
- New API models go in `test_schema_export.py::test_export_contains_the_public_models`; new
  tables in `EXPECTED_TABLES` in `test_models.py`.
- Working-tree files are CRLF. Edit with the Edit tool (or Python text mode), not a
  Node/sed script that writes bare LF into the middle of a CRLF file.
- Commit after every task. The message is a subject line, a blank line, then the trailer
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (name the model that actually wrote
  the task if it differs). The commands below use two `-m` flags, which git joins with exactly
  that blank line. **Never push** — Task 11 stops before `git push`; pushing `main` deploys to
  production and is the user's call.

## Spec clarifications (decided while planning)

1. **Route paths.** The log blueprint's real prefix is `/api/p/<property_id>/log-entries`, not
   `/log`. So the composer's picker is **`GET /log-entries/templates`** (a static segment on the
   existing blueprint, which beats `/log-entries/<entry_id>` exactly as `/mentionables` does),
   and the admin routes are **`/log-templates`** on a second blueprint, `log.templates_bp`
   (the `staff_messages.directory_bp` precedent).
2. **`LogEntryOut` also gains `notes: str | None`** — the author's notes on a templated post,
   i.e. the stored body minus its generated summary, derived server-side by the same formatter
   that built it. The card needs "the notes part, not the generated summary" (spec §4.2), and the
   client cannot split the body itself: a long-text answer may contain a blank line. `None` on a
   free-form post.
3. **The template tag shows the template's current name** (`template: {id, name}` joins
   `log_template`). Only field labels and types are snapshots, as spec §2.1 says; a renamed
   template renames its tag on old posts, and a deactivated one is still named.
4. **Post-time failures beyond the spec's reason list:** an inactive template is a 400
   `{"templateId": "inactive"}` (it exists here, so not 404; the caller is not refused, so not
   403); `fieldValues` without `templateId` is a 400 `{"fieldValues": "no_template"}`; a field id
   sent twice is reason `duplicate`; a template post with nothing answered and no notes is the
   existing 400 "A log entry needs a body"; the combined body over 4000 is
   `{"body": "too_long"}`.
5. **Value limits:** `short_text` ≤ 200 characters, `long_text` ≤ 4000; numbers must be finite
   (`"nan"`/`"inf"` parse in Python but are `not_a_number`) and `|x| < 10^8` (the
   `Numeric(10, 2)` column's range — PostgreSQL would otherwise 500 on overflow), else
   `out_of_range`; decimals are rounded to 2 places before storing, so the body and the row
   agree. A text field given a JSON number stores its string form.
6. **`CreateLogEntryRequest.body` becomes optional** (`default=""`, still `max_length=4000`): a
   templated post may have empty notes. The free-form "needs a body" rule already lives in
   `log.create` and still fires.
7. **Field sync is log-specific** (`log_templates._sync_fields`), not
   `typed_items.sync_items`: that one is typed to PM's `TemplateItemIn` and item types and
   validates bounds/units these fields do not have. Same replace-by-list rules and the same
   `details={"fields": ...}` codes: `type_change`, `unknown_field`, `duplicate_field`, plus
   `required` for a blank label and `{"name": "required"}` for a blank name.
8. **Template `position`** is appended on create (the property's template count) and not
   settable through the API this round; there is no reorder UI.
9. **Audience refs are de-duplicated** (the table's unique key would otherwise turn a repeat into
   a 500) and must be this property's members or departments, else
   `{"audience": "unknown_user" | "unknown_department"}`. Replacing the audience deletes, flushes,
   then inserts, so a ref kept across a save never collides with its own old row.
10. **The composer sends a numeric answer as a JSON number when it parses** and as the typed
    string otherwise, so the server names the problem (`not_a_number`) instead of the client
    guessing. Server reason codes get copy in `web/src/api/fieldErrors.ts`'s `REASON_COPY`.
11. **Seed:** four templated posts (AM d-2 by Ava, PM d-2 by Marcus, Night Audit d-1 by Jordan,
    AM d-1 by Ava) are created through `log.create`, then their `created_at`/`shift` are set to
    fixed local times, as the existing seeded log entries are. Two answer all ten fields, two
    leave Notes blank: 38 value rows. `created_by_user_id` is NOT NULL.

## Review Focus

1. **A number too big for the column** (e.g. `100000000` in "Max occupied") — SQLite stores it,
   PostgreSQL raises a numeric overflow and the post 500s in production only. Expected: a 400
   naming the field (`out_of_range`) on both engines. → Task 3
   (`test_a_number_too_big_for_the_column_is_a_400_not_a_postgres_overflow`), re-proved on
   Postgres in Task 11.
2. **`"nan"`, `"inf"`, `"-Infinity"` typed into a number field** — Python's `float()` accepts all
   three. Expected: `not_a_number`, never a stored NaN. → Task 3
   (`test_not_a_number_and_infinity_are_not_numbers`).
3. **A long-text answer containing a blank line** (a two-paragraph handover) — the notes must
   still be split off correctly, not swallowed into or leaked out of the value table. → Task 4
   (`test_a_templated_entry_carries_its_template_values_and_notes`).
4. **An admin saves the audience with a repeated person, or keeps a ref across a save** —
   Expected: repeats collapse, the kept ref survives, no unique-key 500. → Task 2
   (`test_audience_is_replaced_wholesale_and_repeats_collapse`).
5. **A stale composer** — the admin deactivates the template or removes a field while a
   receptionist has the form open, then they post. Expected: a clean 400
   (`templateId: inactive` / `unknown_field`), never a 500 or a half-written post. → Task 3
   (`test_template_lookup_audience_and_active_are_enforced`,
   `test_unknown_duplicate_and_soft_deleted_field_ids_are_refused`).

## File map

**Server — create:** `alembic/versions/0010_log_templates.py`, `app/domain/log_templates.py`;
tests `tests/log_template_helpers.py`, `test_log_template_models.py`, `test_log_templates.py`,
`test_log_template_posts.py`, `test_log_template_views.py`, `test_log_template_api.py`.

**Server — modify:** `app/schemas/enums.py`, `app/models/log.py`, `app/models/__init__.py`,
`app/schemas/log.py`, `app/domain/log.py`, `app/api/log.py`, `app/__init__.py`,
`seed/seed.py`, `tests/test_models.py`, `tests/test_schema_export.py`, `tests/test_seed.py`,
`data/app.db`.

**Web — create:** `features/log/templates.ts` (+test), `features/admin/LogTemplatesAdmin.tsx`
(+test).

**Web — modify:** `api/schema.json` + `api/types.generated.ts` (regenerated), `api/types.ts`,
`api/queryKeys.ts`, `api/hooks/log.ts` (+`log.test.tsx`), `api/fieldErrors.ts` (+test),
`features/log/LogComposer.tsx` (+test), `features/log/LogPage.test.tsx`,
`features/log/LogEntryCard.tsx` (+test), `features/admin/AdminPage.tsx` (+test),
`components/navModel.ts`.

---

### Task 1: Enums, models and migration `0010`

**Files:**
- Modify: `server/app/schemas/enums.py` (append), `server/app/models/log.py`,
  `server/app/models/__init__.py`, `server/tests/test_models.py` (`EXPECTED_TABLES`)
- Create: `server/alembic/versions/0010_log_templates.py`
- Test: `server/tests/test_log_template_models.py`

**Interfaces:**
- Produces: enum `LogFieldType` in `app.schemas.enums`; models `LogTemplate`,
  `LogTemplateField`, `LogTemplateAudience`, `LogEntryFieldValue` exported from `app.models`;
  `LogEntry.template_id: str | None`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_models.py` — add to `EXPECTED_TABLES`, after the checklist line:
`"log_template", "log_template_field", "log_template_audience", "log_entry_field_value",`.

`server/tests/test_log_template_models.py`:

```python
"""Log template schema (log templates spec §2, §6)."""
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.models import (
    LogEntry,
    LogEntryFieldValue,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
)
from app.schemas.enums import LogFieldType, MentionTargetType, Shift

SERVER = Path(__file__).resolve().parent.parent


def _template(db, fx):
    t = LogTemplate(property_id=fx.property_a.id, name="Night Audit", shift=Shift.overnight,
                    position=0, created_by_user_id=fx.admin_a.id)
    db.add(t)
    db.flush()
    f = LogTemplateField(template_id=t.id, property_id=t.property_id, position=0,
                         label="Occupancy", field_type=LogFieldType.percent)
    db.add(f)
    db.flush()
    return t, f


def test_a_templated_entry_links_its_template_and_stores_a_value(database, fx):
    with database.session() as db:
        t, f = _template(db, fx)
        e = LogEntry(property_id=t.property_id, author_user_id=fx.agent_a.id, shift=Shift.am,
                     body="Occupancy: 87%", template_id=t.id)
        db.add(e)
        db.flush()
        db.add(LogEntryFieldValue(log_entry_id=e.id, property_id=t.property_id, field_id=f.id,
                                  position=0, label=f.label, field_type=f.field_type,
                                  number_value=87.5))
        db.flush()
        eid = e.id
    with database.session() as db:
        row = db.scalar(sa.select(LogEntryFieldValue).where(LogEntryFieldValue.log_entry_id == eid))
        assert (row.label, row.field_type, row.number_value) == ("Occupancy",
                                                                 LogFieldType.percent, 87.5)
        assert db.get(LogEntry, eid).template_id is not None


def test_one_value_per_field_per_entry(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        t, f = _template(db, fx)
        e = LogEntry(property_id=t.property_id, author_user_id=fx.agent_a.id, shift=Shift.am,
                     body="x", template_id=t.id)
        db.add(e)
        db.flush()
        for _ in range(2):
            db.add(LogEntryFieldValue(log_entry_id=e.id, property_id=t.property_id,
                                      field_id=f.id, position=0, label="Occupancy",
                                      field_type=LogFieldType.percent, number_value=1))
        db.flush()


def test_an_audience_target_is_listed_once(database, fx):
    with pytest.raises(IntegrityError), database.session() as db:
        t, _ = _template(db, fx)
        for _ in range(2):
            db.add(LogTemplateAudience(template_id=t.id, property_id=t.property_id,
                                       type=MentionTargetType.department,
                                       target_id=fx.dept_front_desk.id))
        db.flush()


def test_0010_downgrades_and_reupgrades_keeping_log_entries(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    cfg = AlembicConfig(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "0009")
    engine = sa.create_engine(url)
    with engine.begin() as conn:  # a pre-existing entry with a child row, as production has
        conn.execute(sa.text(
            "INSERT INTO property (id,name,code,timezone,currency,settings,created_at,updated_at)"
            " VALUES ('p1','P','PPP','UTC','USD','{}','2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO user_account (id,email,first_name,last_name,locale,status,"
            "notification_prefs,created_at,updated_at) VALUES ('u1','u@x.test','U','One','en',"
            "'active','{}','2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO log_entry (id,property_id,author_user_id,shift,body,pinned,requires_ack,"
            "ack_expected,created_at,updated_at) VALUES ('e1','p1','u1','am','Hello',0,0,'[]',"
            "'2026-09-10','2026-09-10')"))
        conn.execute(sa.text(
            "INSERT INTO log_entry_ack (id,log_entry_id,property_id,user_id,acknowledged_at,"
            "created_at,updated_at) VALUES ('a1','e1','p1','u1','2026-09-10','2026-09-10',"
            "'2026-09-10')"))
    command.upgrade(cfg, "head")
    cols = {c["name"] for c in sa.inspect(engine).get_columns("log_entry")}
    assert "template_id" in cols
    assert "log_entry_field_value" in sa.inspect(engine).get_table_names()
    command.downgrade(cfg, "0009")
    inspector = sa.inspect(engine)
    assert "template_id" not in {c["name"] for c in inspector.get_columns("log_entry")}
    assert "log_template" not in inspector.get_table_names()
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT body FROM log_entry")).scalar() == "Hello"
        assert conn.execute(sa.text("SELECT count(*) FROM log_entry_ack")).scalar() == 1
    engine.dispose()
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_models.py tests/test_models.py -q`
Expected: FAIL — `ImportError: cannot import name 'LogEntryFieldValue'` / missing tables.

- [ ] **Step 3: Append the enum** to `server/app/schemas/enums.py`:

```python
class LogFieldType(StrEnum):
    short_text = "short_text"
    long_text = "long_text"
    integer = "integer"
    decimal = "decimal"
    percent = "percent"
```

- [ ] **Step 4: Add the models** in `server/app/models/log.py`.

Replace the two import lines

```python
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import MentionTargetType, Shift
```

with

```python
from app.models.core import TimestampMixin, enum_type
from app.models.pm import READING
from app.schemas.enums import LogFieldType, MentionTargetType, Shift
```

In `LogEntry`, after `linked_conversation_id`, add:

```python
    # Set on a templated post (log templates spec §2.1); free-form posts leave it null.
    template_id: Mapped[str | None] = mapped_column(ForeignKey("log_template.id"))
```

Append to the end of the file:

```python
class LogTemplate(TimestampMixin, Base):
    """A structured shift-report form (log templates spec §2.1). Retired with `active = false`,
    never deleted, so old posts keep their link."""

    __tablename__ = "log_template"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    shift: Mapped[Shift | None] = mapped_column(enum_type(Shift))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)


class LogTemplateField(TimestampMixin, Base):
    """Soft-deleted via `active`, so a post's value rows keep the field they answered."""

    __tablename__ = "log_template_field"
    template_id: Mapped[str] = mapped_column(ForeignKey("log_template.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[LogFieldType] = mapped_column(enum_type(LogFieldType), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LogTemplateAudience(TimestampMixin, Base):
    """Who may post with a template. No rows = everyone at the property (spec §2.1)."""

    __tablename__ = "log_template_audience"
    __table_args__ = (
        UniqueConstraint("template_id", "type", "target_id",
                         name="uq_log_template_audience_target"),
    )
    template_id: Mapped[str] = mapped_column(ForeignKey("log_template.id"), nullable=False,
                                             index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    type: Mapped[MentionTargetType] = mapped_column(enum_type(MentionTargetType), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)


class LogEntryFieldValue(TimestampMixin, Base):
    """One answered field of a templated post. `label` and `field_type` are snapshots, so
    editing the template never changes a past post; written once, never updated (spec §2.1)."""

    __tablename__ = "log_entry_field_value"
    __table_args__ = (
        UniqueConstraint("log_entry_id", "field_id", name="uq_log_field_value_entry_field"),
        Index("ix_log_field_value_property_field", "property_id", "field_id"),
    )
    log_entry_id: Mapped[str] = mapped_column(ForeignKey("log_entry.id"), nullable=False,
                                              index=True)
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False)
    field_id: Mapped[str] = mapped_column(ForeignKey("log_template_field.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[LogFieldType] = mapped_column(enum_type(LogFieldType), nullable=False)
    text_value: Mapped[str | None] = mapped_column(Text)
    number_value: Mapped[float | None] = mapped_column(READING)
```

In `server/app/models/__init__.py` replace
`from app.models.log import LogEntry, LogEntryAck, LogEntryMention, LogEntryPhoto` with

```python
from app.models.log import (
    LogEntry,
    LogEntryAck,
    LogEntryFieldValue,
    LogEntryMention,
    LogEntryPhoto,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
)
```

and in `__all__` replace the line `"LogEntryAck", "LogEntryMention", "LogEntryPhoto",` with

```python
    "LogEntryAck", "LogEntryFieldValue", "LogEntryMention", "LogEntryPhoto", "LogTemplate",
    "LogTemplateAudience", "LogTemplateField",
```

- [ ] **Step 5: Create `server/alembic/versions/0010_log_templates.py`**

```python
"""log_templates: log_template, log_template_field, log_template_audience,
log_entry_field_value, and log_entry.template_id

Log templates spec §2, §6 (docs/superpowers/specs/2026-09-26-log-templates-design.md). Adds four
tables and one nullable column on log_entry — the only change to an existing table. No backfill:
every existing entry is a free-form post and keeps template_id NULL.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-26

"""
import sqlalchemy as sa

import app.db
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

SHIFT = ("am", "pm", "overnight")
FIELD_TYPE = ("short_text", "long_text", "integer", "decimal", "percent")
TARGET_TYPE = ("user", "department")

READING = sa.Numeric(10, 2, asdecimal=False)


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "log_template",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("shift", _enum("ck_enum_shift", *SHIFT), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "log_template_field",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("field_type", _enum("ck_enum_logfieldtype", *FIELD_TYPE), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["template_id"], ["log_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template_field", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_field_template_id"), ["template_id"],
                              unique=False)
        batch_op.create_index(batch_op.f("ix_log_template_field_property_id"), ["property_id"],
                              unique=False)

    op.create_table(
        "log_template_audience",
        sa.Column("template_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("type", _enum("ck_enum_mentiontargettype", *TARGET_TYPE), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.UniqueConstraint("template_id", "type", "target_id",
                            name="uq_log_template_audience_target"),
        sa.ForeignKeyConstraint(["template_id"], ["log_template.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_template_audience", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_template_audience_template_id"),
                              ["template_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_log_template_audience_property_id"),
                              ["property_id"], unique=False)

    op.create_table(
        "log_entry_field_value",
        sa.Column("log_entry_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("field_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("field_type", _enum("ck_enum_logfieldtype", *FIELD_TYPE), nullable=False),
        sa.Column("text_value", sa.Text(), nullable=True),
        sa.Column("number_value", READING, nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("log_entry_id", "field_id", name="uq_log_field_value_entry_field"),
        sa.ForeignKeyConstraint(["log_entry_id"], ["log_entry.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.ForeignKeyConstraint(["field_id"], ["log_template_field.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("log_entry_field_value", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_log_entry_field_value_log_entry_id"),
                              ["log_entry_id"], unique=False)
        batch_op.create_index("ix_log_field_value_property_field", ["property_id", "field_id"],
                              unique=False)

    # The one change to an existing table. Nullable with no default, so no backfill; the FK is
    # named so downgrade() can drop it by name on both engines (as 0003 does for pms_event).
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.add_column(sa.Column("template_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key("fk_log_entry_template_id", "log_template",
                                    ["template_id"], ["id"])


def downgrade() -> None:
    # The column first (its FK points at log_template), then the four tables children-first.
    with op.batch_alter_table("log_entry", schema=None) as batch_op:
        batch_op.drop_constraint("fk_log_entry_template_id", type_="foreignkey")
        batch_op.drop_column("template_id")
    for table in ("log_entry_field_value", "log_template_audience", "log_template_field",
                  "log_template"):
        op.drop_table(table)
```

(On SQLite the `log_entry` batch recreates the table; Alembic's own connection does not set
`PRAGMA foreign_keys`, so the child tables' rows survive the copy — the downgrade test above
proves it with an existing ack row.)

- [ ] **Step 6: Verify the migration matches the models**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_models.py tests/test_models.py -q` → PASS.
Then check drift with a throwaway command (do not commit anything):

```bash
cd server && ../.venv/Scripts/python.exe -c "
from app.db import run_migrations, Base; import app.models, sqlalchemy as sa, tempfile, os
from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata
p=os.path.join(tempfile.mkdtemp(),'d.db'); u='sqlite:///'+p.replace(os.sep,'/'); run_migrations(u)
e=sa.create_engine(u); print([d for d in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata) if 'log' in str(d)])"
```

Expected: `[]`. Fix any difference in the migration, then run the full server suite and ruff.

- [ ] **Step 7: Commit**

```bash
git add server/app/schemas/enums.py server/app/models/log.py server/app/models/__init__.py server/alembic/versions/0010_log_templates.py server/tests/test_log_template_models.py server/tests/test_models.py
git commit -m "feat(log): log template models and migration 0010" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Template wire models and the admin domain (CRUD and audience)

**Files:**
- Modify: `server/app/schemas/log.py`
- Create: `server/app/domain/log_templates.py`, `server/tests/log_template_helpers.py`
- Test: `server/tests/test_log_templates.py`

**Interfaces:**
- Consumes: Task 1's models and `LogFieldType`.
- Produces schemas (in `app.schemas.log`): `MAX_TEMPLATE_FIELDS = 50`, `LogTemplateFieldIn`
  (`id?`, `label`, `field_type`, `required`), `LogTemplateFieldOut` (+`position`, `active`),
  `LogTemplateIn`, `LogTemplatePatch`, `LogTemplateOut` (`id`, `name`, `shift`, `active`,
  `position`, `fields`, `audience: list[MentionRef]`, `used_count`).
- Produces (in `app.domain.log_templates`): `EXEMPT_ROLES`,
  `get(db, property_id, template_id) -> LogTemplate` (NotFound),
  `active_fields(db, template_id) -> list[LogTemplateField]`,
  `assert_can_use(db, property_id, user_id, template) -> None` (Forbidden),
  `to_out(db, template) -> LogTemplateOut`,
  `create(db, property_id, actor_id, data: LogTemplateIn) -> LogTemplate`,
  `patch(db, property_id, actor_id, template_id, data: LogTemplatePatch) -> LogTemplate`;
  private helpers later tasks reuse: `_audiences(db, ids) -> dict[str, list[MentionRef]]`,
  `_membership(db, pid, uid)`, `_allowed(membership, audience) -> bool`,
  `_outs(db, pid, templates) -> list[LogTemplateOut]`.
- Produces test helpers (`tests/log_template_helpers.py`): `FIELDS` (Arrivals actual integer
  required · Occupancy percent required · ADR decimal optional · Duty manager short_text
  optional · Handover long_text optional), `make_template(db, fx, *, name="Night Audit",
  shift="overnight", fields=None, audience=None, active=True)` (via `create`, actor
  `fx.admin_a`), `front_desk(fx) -> list[MentionRef]`, `field_ids(db, template) -> dict[label,
  id]` (active fields).

- [ ] **Step 1: Add the wire models** — in `server/app/schemas/log.py`, change the enums import to
`from app.schemas.enums import LogFieldType, MentionTargetType, Shift`, add
`MAX_TEMPLATE_FIELDS = 50` under `FEED_PAGE_SIZE = 50`, and append:

```python
class LogTemplateFieldIn(CamelModel):
    """`id` set = update that field in place; omitted = a new field. A saved field missing from
    the list is soft-deleted, and its type never changes (log templates spec §2.1)."""

    id: str | None = None
    label: str = Field(min_length=1, max_length=200)
    field_type: LogFieldType
    required: bool = True


class LogTemplateFieldOut(CamelModel):
    id: str
    position: int
    label: str
    field_type: LogFieldType
    required: bool
    active: bool


class LogTemplateIn(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    shift: Shift | None = None
    active: bool = True
    fields: list[LogTemplateFieldIn] = Field(min_length=1, max_length=MAX_TEMPLATE_FIELDS)
    audience: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)


class LogTemplatePatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    shift: Shift | None = None
    active: bool | None = None
    fields: list[LogTemplateFieldIn] | None = Field(default=None, min_length=1,
                                                    max_length=MAX_TEMPLATE_FIELDS)
    audience: list[MentionRef] | None = Field(default=None, max_length=MAX_MENTIONS)


class LogTemplateOut(CamelModel):
    id: str
    name: str
    shift: Shift | None = None
    active: bool
    position: int
    fields: list[LogTemplateFieldOut]
    audience: list[MentionRef]
    used_count: int
```

- [ ] **Step 2: Write the helpers and the failing test**

`server/tests/log_template_helpers.py`:

```python
"""Shared set-up for the log-template tests."""
from __future__ import annotations

from app.domain import log_templates
from app.schemas.log import LogTemplateFieldIn, LogTemplateIn, MentionRef

FIELDS = [
    LogTemplateFieldIn(label="Arrivals actual", field_type="integer"),
    LogTemplateFieldIn(label="Occupancy", field_type="percent"),
    LogTemplateFieldIn(label="ADR", field_type="decimal", required=False),
    LogTemplateFieldIn(label="Duty manager", field_type="short_text", required=False),
    LogTemplateFieldIn(label="Handover", field_type="long_text", required=False),
]


def make_template(db, fx, *, name="Night Audit", shift="overnight", fields=None,
                  audience=None, active=True):
    """Created through the domain as `fx.admin_a`. `audience` is a list of MentionRef."""
    return log_templates.create(db, fx.property_a.id, fx.admin_a.id, LogTemplateIn(
        name=name, shift=shift, active=active, fields=fields or FIELDS,
        audience=audience or []))


def front_desk(fx) -> list[MentionRef]:
    return [MentionRef(type="department", id=fx.dept_front_desk.id)]


def field_ids(db, template) -> dict[str, str]:
    """Active field id by label."""
    return {f.label: f.id for f in log_templates.active_fields(db, template.id)}
```

`server/tests/test_log_templates.py`:

```python
"""Log templates: admin create/patch and the audience rule (log templates spec §2.1, §3.1)."""
import pytest

from app.domain import log_templates
from app.errors import Forbidden, NotFound, ValidationFailed
from app.schemas.log import LogTemplateFieldIn, LogTemplatePatch, MentionRef
from tests.log_template_helpers import FIELDS, field_ids, front_desk, make_template


def test_create_round_trips_fields_in_order_and_the_audience(database, fx):
    with database.session() as db:
        out = log_templates.to_out(db, make_template(db, fx, audience=front_desk(fx)))
        assert (out.name, out.shift.value, out.active, out.used_count) == (
            "Night Audit", "overnight", True, 0)
        assert [(f.label, f.field_type.value, f.required) for f in out.fields] == [
            (f.label, f.field_type.value, f.required) for f in FIELDS]
        assert [f.position for f in out.fields] == [0, 1, 2, 3, 4]
        assert [(r.type.value, r.id) for r in out.audience] == [
            ("department", fx.dept_front_desk.id)]


def test_new_templates_are_appended_in_position_order(database, fx):
    with database.session() as db:
        first = make_template(db, fx, name="AM Checklist", shift="am")
        second = make_template(db, fx, name="PM Checklist", shift="pm")
        assert (first.position, second.position) == (0, 1)


def test_patch_renames_reorders_and_soft_deletes_a_missing_field(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
            name="Night Audit v2", shift=None, fields=[
                LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy %",
                                   field_type="percent"),
                LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals actual",
                                   field_type="integer", required=False),
            ]))
        out = log_templates.to_out(db, t)
        assert (out.name, out.shift) == ("Night Audit v2", None)
        assert [(f.label, f.required) for f in out.fields] == [("Occupancy %", True),
                                                             ("Arrivals actual", False)]
        assert set(field_ids(db, t)) == {"Occupancy %", "Arrivals actual"}  # active only


def test_a_saved_fields_type_never_changes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        with pytest.raises(ValidationFailed) as e:
            log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
                fields=[LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy",
                                           field_type="integer")]))
        assert e.value.details == {"fields": "type_change"}


def test_unknown_and_duplicate_field_ids_are_refused(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        occ = field_ids(db, t)["Occupancy"]
        for fields, reason in (
                ([LogTemplateFieldIn(id="00000000-0000-0000-0000-000000000000", label="x",
                                     field_type="integer")], "unknown_field"),
                ([LogTemplateFieldIn(id=occ, label="a", field_type="percent"),
                  LogTemplateFieldIn(id=occ, label="b", field_type="percent")],
                 "duplicate_field")):
            with pytest.raises(ValidationFailed) as e:
                log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                                    LogTemplatePatch(fields=fields))
            assert e.value.details == {"fields": reason}


def test_blank_name_or_label_is_refused(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, name="   ")
        assert e.value.details == {"name": "required"}
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, fields=[LogTemplateFieldIn(label="  ",
                                                             field_type="integer")])
        assert e.value.details == {"fields": "required"}


def test_audience_is_replaced_wholesale_and_repeats_collapse(database, fx):
    """Review focus 4: a repeat and a ref kept across a save must not hit the unique key."""
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        eli = MentionRef(type="user", id=fx.engineer_a.id)
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(
            audience=[eli, eli, *front_desk(fx)]))
        assert {(r.type.value, r.id) for r in log_templates.to_out(db, t).audience} == {
            ("user", fx.engineer_a.id), ("department", fx.dept_front_desk.id)}
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                            LogTemplatePatch(audience=[]))
        assert log_templates.to_out(db, t).audience == []


def test_audience_must_belong_to_the_property(database, fx):
    with database.session() as db:
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, audience=[MentionRef(type="user", id=fx.agent_b.id)])
        assert e.value.details == {"audience": "unknown_user"}
        with pytest.raises(ValidationFailed) as e:
            make_template(db, fx, audience=[
                MentionRef(type="department", id="00000000-0000-0000-0000-000000000000")])
        assert e.value.details == {"audience": "unknown_department"}


def test_a_template_of_another_property_is_not_found(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        with pytest.raises(NotFound):
            log_templates.get(db, fx.property_b.id, t.id)


@pytest.mark.parametrize("who,allowed", [
    ("agent_a", True),         # front desk: a member of the listed department
    ("engineer_a", False),     # another department
    ("supervisor_a", False),   # supervisors are not exempt (spec §3.1)
    ("manager_a", True), ("admin_a", True), ("corporate_a", True),  # exempt roles
])
def test_the_audience_rule(database, fx, who, allowed):
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        user_id = getattr(fx, who).id
        if allowed:
            log_templates.assert_can_use(db, fx.property_a.id, user_id, t)
        else:
            with pytest.raises(Forbidden):
                log_templates.assert_can_use(db, fx.property_a.id, user_id, t)


def test_a_listed_user_may_use_it_and_an_empty_audience_means_everyone(database, fx):
    with database.session() as db:
        shared = make_template(db, fx, audience=[MentionRef(type="user", id=fx.engineer_a.id)])
        log_templates.assert_can_use(db, fx.property_a.id, fx.engineer_a.id, shared)
        everyone = make_template(db, fx, name="General")
        log_templates.assert_can_use(db, fx.property_a.id, fx.housekeeper_a.id, everyone)
        with pytest.raises(Forbidden):  # a member of another property never can
            log_templates.assert_can_use(db, fx.property_a.id, fx.agent_b.id, everyone)
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_templates.py -q`
Expected: FAIL — `ImportError: cannot import name 'log_templates' from 'app.domain'`.

- [ ] **Step 4: Create `server/app/domain/log_templates.py`**

```python
"""Hotel log post templates (log templates spec §2, §3).

Fields sync replace-by-list with soft deletes, like checklist items, but through their own rules
rather than app.domain.typed_items: the field types are not PM's item types, and there are no
bounds or units. A saved field's type never changes — value rows already posted against it would
mean something else.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import audit
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Department,
    LogEntry,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
    PropertyMembership,
)
from app.schemas.enums import MentionTargetType, Role
from app.schemas.log import (
    LogTemplateFieldIn,
    LogTemplateFieldOut,
    LogTemplateIn,
    LogTemplateOut,
    LogTemplatePatch,
    MentionRef,
)

# Spec §3.1: these roles may use any template, whatever its audience.
EXEMPT_ROLES = {Role.manager, Role.admin, Role.corporate}


def get(db: Session, property_id: str, template_id: str) -> LogTemplate:
    t = db.scalar(select(LogTemplate).where(LogTemplate.id == template_id,
                                            LogTemplate.property_id == property_id))
    if t is None:
        raise NotFound("Log template not found")
    return t


def active_fields(db: Session, template_id: str) -> list[LogTemplateField]:
    return list(db.scalars(select(LogTemplateField).where(
        LogTemplateField.template_id == template_id,
        LogTemplateField.active.is_(True)).order_by(LogTemplateField.position)).all())


def _audiences(db: Session, template_ids: list[str]) -> dict[str, list[MentionRef]]:
    out: dict[str, list[MentionRef]] = {tid: [] for tid in template_ids}
    for row in db.scalars(select(LogTemplateAudience)
                          .where(LogTemplateAudience.template_id.in_(template_ids))
                          .order_by(LogTemplateAudience.type, LogTemplateAudience.target_id)):
        out[row.template_id].append(MentionRef(type=row.type, id=row.target_id))
    return out


def _membership(db: Session, property_id: str, user_id: str) -> PropertyMembership | None:
    return db.scalar(select(PropertyMembership).where(
        PropertyMembership.property_id == property_id, PropertyMembership.user_id == user_id))


def _allowed(membership: PropertyMembership | None, audience: list[MentionRef]) -> bool:
    """Spec §3.1: an empty audience is everyone; otherwise a listed user, a member of a listed
    department, or an exempt role."""
    if membership is None:
        return False
    if not audience or membership.role in EXEMPT_ROLES:
        return True
    for ref in audience:
        if ref.type == MentionTargetType.user and ref.id == membership.user_id:
            return True
        if (ref.type == MentionTargetType.department and membership.department_id is not None
                and ref.id == membership.department_id):
            return True
    return False


def assert_can_use(db: Session, property_id: str, user_id: str, template: LogTemplate) -> None:
    if not _allowed(_membership(db, property_id, user_id),
                    _audiences(db, [template.id])[template.id]):
        raise Forbidden("This template is not shared with you")


def _outs(db: Session, property_id: str, templates: list[LogTemplate]) -> list[LogTemplateOut]:
    """One pass over a list of templates, batching fields, audiences and usage counts."""
    ids = [t.id for t in templates]
    if not ids:
        return []
    fields: dict[str, list[LogTemplateFieldOut]] = {tid: [] for tid in ids}
    for f in db.scalars(select(LogTemplateField)
                        .where(LogTemplateField.template_id.in_(ids),
                               LogTemplateField.active.is_(True))
                        .order_by(LogTemplateField.position)):
        fields[f.template_id].append(LogTemplateFieldOut.model_validate(f, from_attributes=True))
    audiences = _audiences(db, ids)
    used = dict(db.execute(
        select(LogEntry.template_id, func.count())
        .where(LogEntry.property_id == property_id, LogEntry.template_id.in_(ids))
        .group_by(LogEntry.template_id)).all())
    return [LogTemplateOut(id=t.id, name=t.name, shift=t.shift, active=t.active,
                           position=t.position, fields=fields[t.id], audience=audiences[t.id],
                           used_count=used.get(t.id, 0))
            for t in templates]


def to_out(db: Session, t: LogTemplate) -> LogTemplateOut:
    return _outs(db, t.property_id, [t])[0]


def _name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValidationFailed("A template needs a name", details={"name": "required"})
    return name


def _clean_audience(db: Session, property_id: str, refs: list[MentionRef]) -> list[MentionRef]:
    """De-duplicated (the table's unique key would otherwise turn a repeat into a 500) and
    scoped: every user must be a member here and every department must be this property's."""
    out: list[MentionRef] = []
    for type_, target_id in dict.fromkeys((r.type, r.id) for r in refs):
        if type_ == MentionTargetType.user:
            known = _membership(db, property_id, target_id) is not None
        else:
            known = db.scalar(select(Department.id).where(
                Department.id == target_id, Department.property_id == property_id)) is not None
        if not known:
            raise ValidationFailed("Share a template only with people and departments here",
                                   details={"audience": f"unknown_{type_.value}"})
        out.append(MentionRef(type=type_, id=target_id))
    return out


def _replace_audience(db: Session, template: LogTemplate, refs: list[MentionRef]) -> None:
    for row in db.scalars(select(LogTemplateAudience)
                          .where(LogTemplateAudience.template_id == template.id)).all():
        db.delete(row)
    # Flush the deletes before the inserts: in one flush SQLAlchemy inserts first, and a ref kept
    # across the save would then collide with its own old row on the unique key.
    db.flush()
    for ref in refs:
        db.add(LogTemplateAudience(template_id=template.id, property_id=template.property_id,
                                   type=ref.type, target_id=ref.id))
    db.flush()


def _sync_fields(db: Session, template: LogTemplate, fields: list[LogTemplateFieldIn]) -> None:
    """Replace-by-list with soft deletes: a field in the list is updated or created in its
    position; a saved field missing from it is deactivated."""
    existing = {f.id: f for f in db.scalars(select(LogTemplateField).where(
        LogTemplateField.template_id == template.id)).all()}
    seen: set[str] = set()
    for data in fields:
        if not data.label.strip():
            raise ValidationFailed("Every field needs a label", details={"fields": "required"})
        if data.id:
            if data.id in seen:
                raise ValidationFailed("Duplicate field id", details={"fields": "duplicate_field"})
            seen.add(data.id)
    keep: set[str] = set()
    for position, data in enumerate(fields):
        if data.id:
            row = existing.get(data.id)
            if row is None:
                raise ValidationFailed("Unknown field", details={"fields": "unknown_field"})
            if row.field_type != data.field_type:
                raise ValidationFailed("A field's type cannot change; remove it and add a new one",
                                       details={"fields": "type_change"})
            row.position, row.label = position, data.label.strip()
            row.required, row.active = data.required, True
        else:
            row = LogTemplateField(template_id=template.id, property_id=template.property_id,
                                   position=position, label=data.label.strip(),
                                   field_type=data.field_type, required=data.required)
            db.add(row)
            db.flush()
        keep.add(row.id)
    retired = sorted((row for row in existing.values() if row.id not in keep),
                     key=lambda row: row.position)
    for n, row in enumerate(retired):
        # Pushed past the live range so a retired field never shares a position with a kept one.
        row.active = False
        row.position = 1000 + n
    db.flush()


def create(db: Session, property_id: str, actor_id: str, data: LogTemplateIn) -> LogTemplate:
    name = _name(data.name)
    audience = _clean_audience(db, property_id, data.audience)
    position = db.scalar(select(func.count()).select_from(LogTemplate)
                         .where(LogTemplate.property_id == property_id))
    t = LogTemplate(property_id=property_id, name=name, shift=data.shift, active=data.active,
                    position=position, created_by_user_id=actor_id)
    db.add(t)
    db.flush()
    _sync_fields(db, t, data.fields)
    _replace_audience(db, t, audience)
    audit.record(db, property_id, actor_id, "log_template.created", "log_template", t.id,
                 after={"name": t.name})
    return t


def patch(db: Session, property_id: str, actor_id: str, template_id: str,
          data: LogTemplatePatch) -> LogTemplate:
    t = get(db, property_id, template_id)
    provided = data.model_dump(exclude_unset=True)
    if "name" in provided:
        t.name = _name(data.name or "")
    if "shift" in provided:
        t.shift = data.shift
    if "active" in provided and data.active is not None:
        t.active = data.active
    db.flush()
    if data.fields is not None:
        _sync_fields(db, t, data.fields)
    if data.audience is not None:
        _replace_audience(db, t, _clean_audience(db, property_id, data.audience))
    audit.record(db, property_id, actor_id, "log_template.updated", "log_template", t.id,
                 after={"fields": sorted(provided)})
    return t
```

- [ ] **Step 5: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_templates.py -q` → PASS (16).
Then the full server suite and ruff.

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas/log.py server/app/domain/log_templates.py server/tests/log_template_helpers.py server/tests/test_log_templates.py
git commit -m "feat(log): log templates domain - create, patch, audience rule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Posting with a template — validation, value rows, generated body

**Files:**
- Modify: `server/app/schemas/log.py`, `server/app/domain/log_templates.py`,
  `server/app/domain/log.py` (`create`)
- Test: `server/tests/test_log_template_posts.py`

**Interfaces:**
- Consumes: Task 2's `get`, `active_fields`, `assert_can_use`; `tests/log_template_helpers.py`.
- Produces schemas: `LogFieldValueIn` (`field_id`, `value: str | float | int | None`);
  `CreateLogEntryRequest` gains `template_id: str | None` and
  `field_values: list[LogFieldValueIn]` (≤ 50, JSON-string-decoded on the multipart path) and its
  `body` becomes `Field(default="", max_length=MAX_BODY)`.
- Produces (in `app.domain.log_templates`): `MAX_SHORT_TEXT = 200`, `NUMBER_LIMIT = 10**8`,
  `NUMERIC_TYPES`, `check_values(db, template, values: list[LogFieldValueIn]) ->
  list[LogEntryFieldValue]` (unsaved rows, `log_entry_id` unset; raises `ValidationFailed` with
  `details={field_id: reason}`), `format_value(field_type, text_value, number_value) -> str`,
  `summary(values) -> str` (duck-typed over rows with `label`, `field_type`, `text_value`,
  `number_value`).
- `log.create(...)` signature unchanged; a templated entry has `template_id` set and its value
  rows written in the same flush.

- [ ] **Step 1: Write the failing test** — `server/tests/test_log_template_posts.py`:

```python
"""Posting with a template: validation, value rows and the generated body (spec §2.2, §2.3)."""
import pytest
from sqlalchemy import select

from app.domain import log as log_domain
from app.domain import log_templates
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import LogEntryFieldValue, LogTemplate, Notification
from app.schemas.enums import LogFieldType, MentionTargetType
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplatePatch,
    MentionRef,
)
from tests.log_template_helpers import field_ids, front_desk, make_template


def _post(db, fx, template, answers: dict, *, author=None, **kw):
    """`answers` maps a field label to its raw value."""
    ids = field_ids(db, template)
    return log_domain.create(db, fx.property_a.id, (author or fx.agent_a).id,
                             CreateLogEntryRequest(
                                 template_id=template.id,
                                 field_values=[LogFieldValueIn(field_id=ids[k], value=v)
                                               for k, v in answers.items()], **kw))


def _failure(db, fx, template, answers, **kw) -> dict:
    with pytest.raises(ValidationFailed) as e:
        _post(db, fx, template, answers, **kw)
    return e.value.details


def _values(db, entry_id):
    return db.scalars(select(LogEntryFieldValue).where(LogEntryFieldValue.log_entry_id == entry_id)
                      .order_by(LogEntryFieldValue.position)).all()


def test_a_templated_post_stores_one_snapshot_row_per_answered_field(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": "87.5",
                                  "Duty manager": "  Sam  "})
        db.flush()
        assert entry.template_id == t.id
        rows = _values(db, entry.id)
        assert [(r.label, r.field_type, r.text_value, r.number_value) for r in rows] == [
            ("Arrivals actual", LogFieldType.integer, None, 38.0),
            ("Occupancy", LogFieldType.percent, None, 87.5),
            ("Duty manager", LogFieldType.short_text, "Sam", None),  # trimmed
        ]  # ADR and Handover were left blank: no rows for them
        assert {r.property_id for r in rows} == {fx.property_a.id}


def test_the_body_is_the_field_summary_then_the_notes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": "38", "Occupancy": 87, "ADR": "129.5"},
                      body="  Quiet night.  ")
        assert entry.body == ("Arrivals actual: 38\nOccupancy: 87%\nADR: 129.5\n\n"
                              "Quiet night.")
        bare = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 0})
        assert bare.body == "Arrivals actual: 1\nOccupancy: 0%"  # notes are optional


@pytest.mark.parametrize("answers,reason_by_label", [
    ({"Occupancy": 87}, {"Arrivals actual": "required"}),
    ({"Arrivals actual": "  ", "Occupancy": 87}, {"Arrivals actual": "required"}),  # blank
    ({"Arrivals actual": "twelve", "Occupancy": 87}, {"Arrivals actual": "not_a_number"}),
    ({"Arrivals actual": "12.5", "Occupancy": 87}, {"Arrivals actual": "not_whole"}),
    ({"Arrivals actual": 12, "Occupancy": 100.5}, {"Occupancy": "out_of_range"}),
    ({"Arrivals actual": 12, "Occupancy": -1}, {"Occupancy": "out_of_range"}),
    ({"Arrivals actual": 12, "Occupancy": 87, "Duty manager": "x" * 201},
     {"Duty manager": "too_long"}),
    # Every failure is reported at once, each keyed by its own field.
    ({"Arrivals actual": "12.5", "Occupancy": 101},
     {"Arrivals actual": "not_whole", "Occupancy": "out_of_range"}),
])
def test_each_bad_answer_is_a_400_naming_its_field(database, fx, answers, reason_by_label):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        assert _failure(db, fx, t, answers) == {ids[k]: v for k, v in reason_by_label.items()}


def test_a_percent_of_exactly_0_or_100_and_a_whole_float_integer_are_fine(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        assert _post(db, fx, t, {"Arrivals actual": 12.0, "Occupancy": 100}).body.startswith(
            "Arrivals actual: 12\nOccupancy: 100%")


def test_not_a_number_and_infinity_are_not_numbers(database, fx):
    """float() parses both; neither is a reading anyone meant (review focus 2)."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        for raw in ("nan", "inf", "-Infinity"):
            assert _failure(db, fx, t, {"Arrivals actual": 1, "ADR": raw, "Occupancy": 5}) == {
                ids["ADR"]: "not_a_number"}


def test_a_number_too_big_for_the_column_is_a_400_not_a_postgres_overflow(database, fx):
    """number_value is Numeric(10, 2). PostgreSQL raises on 10**8 — a 500 — where SQLite
    stores it, so the domain must refuse it on both (review focus 1)."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        assert _failure(db, fx, t, {"Arrivals actual": 100_000_000, "Occupancy": 5}) == {
            ids["Arrivals actual"]: "out_of_range"}
        ok = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": 99_999_999.99})
        assert "ADR: 99999999.99" in ok.body


def test_a_decimal_is_rounded_to_what_the_column_keeps(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5, "ADR": "129.456"})
        db.flush()
        assert "ADR: 129.46" in entry.body
        assert [r.number_value for r in _values(db, entry.id)][2] == 129.46


def test_unknown_duplicate_and_soft_deleted_field_ids_are_refused(database, fx):
    """Review focus 5: a stale composer answering a field the admin has since removed."""
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        other = make_template(db, fx, name="Other")
        stranger = field_ids(db, other)["Occupancy"]
        assert _failure(db, fx, t, {}) == {ids["Arrivals actual"]: "required",
                                           ids["Occupancy"]: "required"}
        with pytest.raises(ValidationFailed) as e:
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
                template_id=t.id, field_values=[
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=1),
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=2),
                    LogFieldValueIn(field_id=ids["Occupancy"], value=5),
                    LogFieldValueIn(field_id=stranger, value=5)]))
        assert e.value.details == {ids["Arrivals actual"]: "duplicate",
                                   stranger: "unknown_field"}
        # Soft-delete ADR; answering it afterwards is answering an unknown field.
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(fields=[
            LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals actual",
                               field_type="integer"),
            LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy", field_type="percent")]))
        with pytest.raises(ValidationFailed) as e:
            log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
                template_id=t.id, field_values=[
                    LogFieldValueIn(field_id=ids["Arrivals actual"], value=1),
                    LogFieldValueIn(field_id=ids["Occupancy"], value=5),
                    LogFieldValueIn(field_id=ids["ADR"], value=3)]))
        assert e.value.details == {ids["ADR"]: "unknown_field"}


def test_a_template_with_nothing_answered_and_no_notes_is_refused(database, fx):
    with database.session() as db:
        t = make_template(db, fx, fields=[LogTemplateFieldIn(label="Walk-ins",
                                                             field_type="integer",
                                                             required=False)])
        with pytest.raises(ValidationFailed, match="needs a body"):
            _post(db, fx, t, {})


def test_the_combined_body_must_fit(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        with pytest.raises(ValidationFailed) as e:
            _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5}, body="x" * 3990)
        assert e.value.details == {"body": "too_long"}


def test_mentions_in_the_notes_still_notify(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        token = f"@[Eli Engineer](user:{fx.engineer_a.id})"
        _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5}, body=f"{token} boiler noise",
              mentions=[MentionRef(type=MentionTargetType.user, id=fx.engineer_a.id)])
        db.flush()
        n = db.scalar(select(Notification).where(Notification.user_id == fx.engineer_a.id,
                                                 Notification.type == "log.mention"))
        assert n is not None and "@Eli Engineer boiler noise" in n.body


def test_template_lookup_audience_and_active_are_enforced(database, fx):
    """Review focus 5: a template deactivated while the composer was open is a clean 400."""
    with database.session() as db:
        t = make_template(db, fx, audience=front_desk(fx))
        answers = {"Arrivals actual": 1, "Occupancy": 5}
        with pytest.raises(Forbidden):
            _post(db, fx, t, answers, author=fx.engineer_a)
        _post(db, fx, t, answers, author=fx.manager_a)  # exempt role
        db.get(LogTemplate, t.id).active = False
        db.flush()
        assert _failure(db, fx, t, answers) == {"templateId": "inactive"}
        b = LogTemplate(property_id=fx.property_b.id, name="B", position=0,
                        created_by_user_id=fx.admin_b.id)
        db.add(b)
        db.flush()
        with pytest.raises(NotFound):
            log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                              CreateLogEntryRequest(template_id=b.id))


def test_field_values_without_a_template_are_refused(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed) as e:
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
            body="hi", field_values=[LogFieldValueIn(field_id="x", value=1)]))
    assert e.value.details == {"fieldValues": "no_template"}


def test_a_free_form_post_still_needs_a_body(database, fx):
    with database.session() as db, pytest.raises(ValidationFailed, match="needs a body"):
        log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_posts.py -q`
Expected: FAIL — `ImportError: cannot import name 'LogFieldValueIn'`.

- [ ] **Step 3: Extend the request model** in `server/app/schemas/log.py`. Insert above
`class CreateLogEntryRequest`:

```python
class LogFieldValueIn(CamelModel):
    """One answer on a templated post. A JSON number or a numeric string (the multipart path
    sends strings); the domain validates it against the field's type (log templates spec §2.3)."""

    field_id: str
    value: str | float | int | None = None
```

In `CreateLogEntryRequest`: replace its docstring and `body` line with

```python
    """The non-file half of the body; a `photo` file part may arrive alongside it, exactly
    like SendStaffMessageRequest. With `template_id`, `body` is the author's optional notes and
    the domain generates the stored body (log templates spec §2.2)."""

    body: str = Field(default="", max_length=MAX_BODY)
```

add after `linked_conversation_id: str | None = None`:

```python
    template_id: str | None = None
    field_values: list[LogFieldValueIn] = Field(default_factory=list,
                                                max_length=MAX_TEMPLATE_FIELDS)
```

and in `_parse_multipart_lists` change the loop to
`for field in ("mentions", "ackAudience", "fieldValues"):`.

- [ ] **Step 4: Add answer validation and the summary** to `server/app/domain/log_templates.py`.

Replace the import block (from `from sqlalchemy import func, select` through the closing `)` of
the `app.schemas.log` import) with:

```python
import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import audit
from app.errors import Forbidden, NotFound, ValidationFailed
from app.models import (
    Department,
    LogEntry,
    LogEntryFieldValue,
    LogTemplate,
    LogTemplateAudience,
    LogTemplateField,
    PropertyMembership,
)
from app.schemas.enums import LogFieldType, MentionTargetType, Role
from app.schemas.log import (
    MAX_BODY,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplateFieldOut,
    LogTemplateIn,
    LogTemplateOut,
    LogTemplatePatch,
    MentionRef,
)
```

Append to the end of the file:

```python
# ---- posting with a template (spec §2.2, §2.3) -------------------------------------------------

MAX_SHORT_TEXT = 200
# log_entry_field_value.number_value is Numeric(10, 2): anything at or past 10**8 overflows it,
# which PostgreSQL refuses with a 500 and SQLite silently accepts. Refuse it here as a 400.
NUMBER_LIMIT = 100_000_000
NUMERIC_TYPES = {LogFieldType.integer, LogFieldType.decimal, LogFieldType.percent}


def _coerce(field_type: LogFieldType, raw: object) -> tuple[str | None, float | None, str | None]:
    """(text_value, number_value, failure reason). Both values None = unanswered."""
    if raw is None:
        return None, None, None
    if field_type not in NUMERIC_TYPES:
        text = str(raw).strip()
        if not text:
            return None, None, None
        limit = MAX_SHORT_TEXT if field_type == LogFieldType.short_text else MAX_BODY
        return (None, None, "too_long") if len(text) > limit else (text, None, None)
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None, None, None
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None, None, "not_a_number"
    if not math.isfinite(number):  # float("nan") and float("inf") both parse
        return None, None, "not_a_number"
    if field_type == LogFieldType.integer and not number.is_integer():
        return None, None, "not_whole"
    if field_type == LogFieldType.percent and not 0 <= number <= 100:
        return None, None, "out_of_range"
    if abs(number) >= NUMBER_LIMIT:
        return None, None, "out_of_range"
    return None, round(number, 2), None


def check_values(db: Session, template: LogTemplate,
                 values: list[LogFieldValueIn]) -> list[LogEntryFieldValue]:
    """Validate a post's answers against the template's active fields. Returns one unsaved value
    row per answered field, in field order, with the label and type snapshotted; the caller sets
    `log_entry_id` once the entry exists. Every failure is collected into one 400 whose details
    map each field id to its reason."""
    fields = active_fields(db, template.id)
    by_id = {f.id: f for f in fields}
    errors: dict[str, str] = {}
    given: dict[str, object] = {}
    for v in values:
        if v.field_id in given:
            errors[v.field_id] = "duplicate"
            continue
        given[v.field_id] = v.value
        if v.field_id not in by_id:
            errors[v.field_id] = "unknown_field"  # another template's, or soft-deleted
    rows: list[LogEntryFieldValue] = []
    for position, f in enumerate(fields):
        if f.id in errors:
            continue
        text, number, reason = _coerce(f.field_type, given.get(f.id))
        if reason:
            errors[f.id] = reason
        elif text is None and number is None:
            if f.required:
                errors[f.id] = "required"
        else:
            rows.append(LogEntryFieldValue(property_id=template.property_id, field_id=f.id,
                                           position=position, label=f.label,
                                           field_type=f.field_type, text_value=text,
                                           number_value=number))
    if errors:
        raise ValidationFailed("Some template fields need attention", details=errors)
    return rows


def format_value(field_type: LogFieldType, text_value: str | None,
                 number_value: float | None) -> str:
    if number_value is None:
        return text_value or ""
    shown = f"{number_value:.2f}".rstrip("0").rstrip(".")
    return f"{shown}%" if field_type == LogFieldType.percent else shown


def summary(values: list) -> str:
    """The generated half of a templated post's body: one `Label: value` line per answered
    field in position order. Duck-typed over value rows (label, field_type, text_value,
    number_value), so the read side rebuilds exactly the text the write side stored."""
    return "\n".join(f"{v.label}: {format_value(v.field_type, v.text_value, v.number_value)}"
                     for v in values)
```

- [ ] **Step 5: Wire it into `log.create`** — `server/app/domain/log.py`.

Imports: `from app.domain import audit, log_templates, notifications`; add `LogEntryFieldValue`
to the `app.models` import (alphabetically after `LogEntryAck`); add `MAX_BODY` to the
`app.schemas.log` import (after `FEED_PAGE_SIZE`).

Replace

```python
    body = data.body.strip()
    if not body:
        raise ValidationFailed("A log entry needs a body")
```

with

```python
    template = None
    values: list[LogEntryFieldValue] = []
    if data.template_id:
        template = log_templates.get(db, property_id, data.template_id)  # 404 if not here
        if not template.active:
            raise ValidationFailed("That template is no longer in use",
                                   details={"templateId": "inactive"})
        log_templates.assert_can_use(db, property_id, author_user_id, template)  # 403
        values = log_templates.check_values(db, template, data.field_values)
    elif data.field_values:
        raise ValidationFailed("Field values need a template",
                               details={"fieldValues": "no_template"})

    # A templated post's body is generated: the field summary, a blank line, then the notes
    # (log templates spec §2.2). Notification snippets, search and @mentions keep working on it.
    body = "\n\n".join(part for part in (log_templates.summary(values), data.body.strip())
                       if part)
    if not body:
        raise ValidationFailed("A log entry needs a body")
    if len(body) > MAX_BODY:
        raise ValidationFailed(f"A post must be {MAX_BODY} characters or fewer, fields included",
                               details={"body": "too_long"})
```

In the `LogEntry(...)` constructor add, after `linked_conversation_id=...`:

```python
        template_id=template.id if template else None,
```

Right after that constructor's `db.add(entry)` / `db.flush()`, add:

```python

    for value in values:
        value.log_entry_id = entry.id
        db.add(value)
```

and extend the audit `after=` to

```python
                 after={"shift": entry.shift.value, "requires_ack": entry.requires_ack,
                        "template_id": entry.template_id})
```

- [ ] **Step 6: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_posts.py tests/test_log_api.py tests/test_log_shift.py -q`
Expected: PASS — the new behaviour, and every existing hotel-log test unchanged (including
`test_a_whitespace_only_body_is_rejected`). Then the full server suite and ruff.

- [ ] **Step 7: Commit**

```bash
git add server/app/schemas/log.py server/app/domain/log_templates.py server/app/domain/log.py server/tests/test_log_template_posts.py
git commit -m "feat(log): post with a template - typed value rows and a generated body" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Read side — templated entries in the feed, the picker list, the admin list

**Files:**
- Modify: `server/app/schemas/log.py`, `server/app/domain/log_templates.py`,
  `server/app/domain/log.py` (`_to_out`)
- Test: `server/tests/test_log_template_views.py`

**Interfaces:**
- Consumes: Task 3's `summary`; Task 2's `_outs`, `_audiences`, `_membership`, `_allowed`.
- Produces schemas: `LogTemplateRef` (`id`, `name`), `LogFieldValueOut` (`field_id`, `label`,
  `field_type`, `text_value`, `number_value`); `LogEntryOut` gains
  `template: LogTemplateRef | None = None`, `field_values: list[LogFieldValueOut] = []`,
  `notes: str | None = None` (clarification 2).
- Produces (in `app.domain.log_templates`): `notes_of(body, values) -> str | None`,
  `list_admin(db, property_id) -> list[LogTemplateOut]`,
  `list_usable(db, property_id, user_id) -> list[LogTemplateOut]`.

- [ ] **Step 1: Write the failing test** — `server/tests/test_log_template_views.py`:

```python
"""The read side: templated entries in the feed, the picker list and the admin list
(log templates spec §2.1, §3.2, §4.2)."""
from app.domain import log as log_domain
from app.domain import log_templates
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFeedQuery,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplatePatch,
)
from tests.log_template_helpers import field_ids, front_desk, make_template


def _post(db, fx, template, answers, body=""):
    ids = field_ids(db, template)
    entry = log_domain.create(db, fx.property_a.id, fx.agent_a.id, CreateLogEntryRequest(
        template_id=template.id, body=body,
        field_values=[LogFieldValueIn(field_id=ids[k], value=v) for k, v in answers.items()]))
    db.flush()
    return entry


def test_a_templated_entry_carries_its_template_values_and_notes(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": 87.5,
                                  "Handover": "Line one\n\nLine two"}, body="Quiet night.")
        out = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert (out.template.id, out.template.name) == (t.id, "Night Audit")
        assert [(v.label, v.field_type.value, v.text_value, v.number_value)
                for v in out.field_values] == [
            ("Arrivals actual", "integer", None, 38.0),
            ("Occupancy", "percent", None, 87.5),
            ("Handover", "long_text", "Line one\n\nLine two", None),
        ]
        # Review focus 3: the notes survive a long-text value that itself has a blank line.
        assert out.notes == "Quiet night."
        assert out.body.endswith("\n\nQuiet night.")


def test_notes_are_none_without_notes_and_on_free_form_posts(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        bare = _post(db, fx, t, {"Arrivals actual": 1, "Occupancy": 5})
        free = log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                                 CreateLogEntryRequest(body="Plain note"))
        db.flush()
        by_id = {e.id: e for e in log_domain.feed(db, fx.property_a.id, fx.agent_a.id,
                                                  LogFeedQuery()).entries}
        assert (by_id[bare.id].notes, by_id[bare.id].template.name) == (None, "Night Audit")
        assert (by_id[free.id].template, by_id[free.id].field_values,
                by_id[free.id].notes) == (None, [], None)


def test_editing_or_retiring_the_template_never_changes_a_past_post(database, fx):
    with database.session() as db:
        t = make_template(db, fx)
        ids = field_ids(db, t)
        entry = _post(db, fx, t, {"Arrivals actual": 38, "Occupancy": 87, "ADR": 120},
                      body="Notes stay.")
        before = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        # Rename one field, drop another, then retire the template.
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id, LogTemplatePatch(fields=[
            LogTemplateFieldIn(id=ids["Arrivals actual"], label="Arrivals (actual)",
                               field_type="integer"),
            LogTemplateFieldIn(id=ids["Occupancy"], label="Occupancy", field_type="percent")]))
        log_templates.patch(db, fx.property_a.id, fx.admin_a.id, t.id,
                            LogTemplatePatch(active=False))
        after = log_domain.get_out(db, fx.property_a.id, fx.agent_a.id, entry.id)
        assert after.field_values == before.field_values  # labels and values are snapshots
        assert (after.body, after.notes) == (before.body, "Notes stay.")
        assert after.template.name == "Night Audit"  # still named although retired


def test_the_picker_lists_usable_active_templates_current_shift_first(database, fx):
    """conftest freezes 2026-09-10 12:00 UTC = 08:00 in New York: the AM shift."""
    with database.session() as db:
        night = make_template(db, fx, name="Night Audit", shift="overnight")
        am = make_template(db, fx, name="AM Checklist", shift="am")
        general = make_template(db, fx, name="General", shift=None)
        make_template(db, fx, name="Retired", shift="am", active=False)
        make_template(db, fx, name="Engineering only", shift="am",
                      audience=[{"type": "department", "id": fx.dept_engineering.id}])
        names = [t.name for t in log_templates.list_usable(db, fx.property_a.id, fx.agent_a.id)]
        assert names == ["AM Checklist", "Night Audit", "General"]
        assert (am.position, night.position, general.position) == (1, 0, 2)
        # Fields ride along, active only, in order.
        first = log_templates.list_usable(db, fx.property_a.id, fx.agent_a.id)[0]
        assert [f.label for f in first.fields][:2] == ["Arrivals actual", "Occupancy"]


def test_a_non_audience_user_does_not_see_the_template_but_an_exempt_role_does(database, fx):
    with database.session() as db:
        make_template(db, fx, audience=front_desk(fx))
        assert log_templates.list_usable(db, fx.property_a.id, fx.engineer_a.id) == []
        assert [t.name for t in log_templates.list_usable(db, fx.property_a.id,
                                                          fx.manager_a.id)] == ["Night Audit"]


def test_the_admin_list_includes_inactive_templates_and_counts_their_posts(database, fx):
    with database.session() as db:
        used = make_template(db, fx, name="Night Audit")
        make_template(db, fx, name="Retired", active=False)
        for _ in range(3):
            _post(db, fx, used, {"Arrivals actual": 1, "Occupancy": 5})
        log_domain.create(db, fx.property_a.id, fx.agent_a.id,
                          CreateLogEntryRequest(body="free-form posts count for nothing"))
        db.flush()
        rows = {t.name: t for t in log_templates.list_admin(db, fx.property_a.id)}
        assert (rows["Night Audit"].used_count, rows["Retired"].used_count) == (3, 0)
        assert rows["Retired"].active is False
        assert log_templates.list_admin(db, fx.property_b.id) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_views.py -q`
Expected: FAIL — `AttributeError: 'LogEntryOut' object has no attribute 'template'` /
`module 'app.domain.log_templates' has no attribute 'list_usable'`.

- [ ] **Step 3: Add the read models** — in `server/app/schemas/log.py`, insert above
`class LogEntryOut`:

```python
class LogTemplateRef(CamelModel):
    id: str
    name: str


class LogFieldValueOut(CamelModel):
    field_id: str
    label: str
    field_type: LogFieldType
    text_value: str | None = None
    number_value: float | None = None
```

and at the end of `LogEntryOut` (after `linked_conversation_id`):

```python
    template: LogTemplateRef | None = None
    field_values: list[LogFieldValueOut] = Field(default_factory=list)
    # The author's notes on a templated post — the body minus its generated field summary — so
    # the card can show the values as a table without repeating them (spec §4.2). None on a
    # free-form post, whose `body` is already the whole text.
    notes: str | None = None
```

- [ ] **Step 4: Add the lists and `notes_of`** to `server/app/domain/log_templates.py`.

Imports: change `from app.domain import audit` to

```python
from app import clock
from app.domain import audit, shifts
```

and add `Property,` to the `app.models` import (after `LogTemplateField,`).
(`shifts.current_shift` imports `app.domain.log` lazily, so there is no import cycle with
`log.py` importing this module.)

Append:

```python
def notes_of(body: str, values: list) -> str | None:
    """The author's notes: the body minus the generated summary and the blank line after it."""
    head = summary(values)
    rest = body[len(head):] if head and body.startswith(head) else body
    return rest.removeprefix("\n\n").strip() or None


# ---- the two lists (spec §3.2) --------------------------------------------------------------


def list_admin(db: Session, property_id: str) -> list[LogTemplateOut]:
    """Every template, inactive included, for Admin → Log templates."""
    rows = db.scalars(select(LogTemplate).where(LogTemplate.property_id == property_id)
                      .order_by(LogTemplate.position, LogTemplate.name, LogTemplate.id)).all()
    return _outs(db, property_id, list(rows))


def list_usable(db: Session, property_id: str, user_id: str) -> list[LogTemplateOut]:
    """The composer's picker: active templates the caller may post with, the current shift's
    first, then untagged and other shifts, each group by position then name."""
    rows = list(db.scalars(select(LogTemplate).where(LogTemplate.property_id == property_id,
                                                     LogTemplate.active.is_(True))).all())
    audiences = _audiences(db, [t.id for t in rows])
    membership = _membership(db, property_id, user_id)
    usable = [t for t in rows if _allowed(membership, audiences[t.id])]
    _, current = shifts.current_shift(db.get(Property, property_id), clock.now())
    usable.sort(key=lambda t: (t.shift != current, t.position, t.name, t.id))
    return _outs(db, property_id, usable)
```

- [ ] **Step 5: Fill the new fields in `_to_out`** — `server/app/domain/log.py`.

Imports: add `LogTemplate` to the `app.models` import (after `LogEntryPhoto`), and
`LogFieldValueOut` (after `LogFeedQuery`) and `LogTemplateRef` (after `LogPersonOut`) to the
`app.schemas.log` import.

After the `has_photo = ...` statement add:

```python

    # A templated post names its template by the template's current name (a deactivated one
    # included); its values come from the value rows' own snapshots (log templates spec §2.1).
    template_ids = {e.template_id for e in entries if e.template_id}
    template_names = dict(db.execute(
        select(LogTemplate.id, LogTemplate.name)
        .where(LogTemplate.property_id == property_id,
               LogTemplate.id.in_(template_ids))).all()) if template_ids else {}
    values: dict[str, list[LogEntryFieldValue]] = {i: [] for i in ids}
    for row in db.scalars(select(LogEntryFieldValue)
                          .where(LogEntryFieldValue.log_entry_id.in_(ids))
                          .order_by(LogEntryFieldValue.position)).all():
        values[row.log_entry_id].append(row)
```

and in the `LogEntryOut(...)` constructor, after `linked_conversation_id=e.linked_conversation_id,`:

```python
            template=(LogTemplateRef(id=e.template_id,
                                     name=template_names.get(e.template_id, "Template"))
                      if e.template_id else None),
            field_values=[LogFieldValueOut(field_id=v.field_id, label=v.label,
                                           field_type=v.field_type, text_value=v.text_value,
                                           number_value=v.number_value)
                          for v in values[e.id]],
            notes=log_templates.notes_of(e.body, values[e.id]) if e.template_id else None,
```

- [ ] **Step 6: Run the tests**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_views.py tests/test_log_template_posts.py tests/test_log_api.py -q` → PASS.
Then the full server suite and ruff.

- [ ] **Step 7: Commit**

```bash
git add server/app/schemas/log.py server/app/domain/log_templates.py server/app/domain/log.py server/tests/test_log_template_views.py
git commit -m "feat(log): templated entries in the feed, picker and admin template lists" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: API routes, schema export and regenerated types

**Files:**
- Modify: `server/app/api/log.py`, `server/app/__init__.py`,
  `server/tests/test_schema_export.py`; regenerate `web/src/api/schema.json`,
  `web/src/api/types.generated.ts`; modify `web/src/api/types.ts`, `web/src/api/hooks/log.ts`
  (one line)
- Test: `server/tests/test_log_template_api.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: `GET /api/p/<pid>/log-entries/templates` (`post_log`) → `LogTemplateOut[]`;
  `GET /api/p/<pid>/log-templates` (`manage_admin`) → `LogTemplateOut[]`;
  `POST /log-templates` → 201 `LogTemplateOut`; `PATCH /log-templates/<template_id>` →
  `LogTemplateOut`; `POST /log-entries` accepts `templateId` + `fieldValues`. Blueprint
  `log.templates_bp`. Web types `LogFieldType`, `LogFieldValueIn`, `LogFieldValueOut`,
  `LogTemplateFieldIn`, `LogTemplateFieldOut`, `LogTemplateIn`, `LogTemplateOut`,
  `LogTemplatePatch`, `LogTemplateRef` re-exported from `web/src/api/types.ts`.

- [ ] **Step 1: Write the failing tests** — `server/tests/test_log_template_api.py`:

```python
"""The log-templates HTTP surface (log templates spec §3)."""
import io
import json

from app.models import LogTemplate

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00IHDR-not-a-real-png-but-the-signature-is"

TEMPLATE = {
    "name": "Night Audit", "shift": "overnight",
    "fields": [{"label": "Arrivals actual", "fieldType": "integer"},
               {"label": "Occupancy", "fieldType": "percent"},
               {"label": "Notes", "fieldType": "long_text", "required": False}],
}


def _admin(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/log-templates{rest}"


def _entries(fx, rest=""):
    return f"/api/p/{fx.property_a.id}/log-entries{rest}"


def _create(login, fx, **over):
    res = login("admin@hvh.test").post(_admin(fx), json={**TEMPLATE, **over})
    assert res.status_code == 201, res.get_json()
    return res.get_json()


def test_admin_create_patch_and_list_round_trip(app, fx, login):
    admin = login("admin@hvh.test")
    created = _create(login, fx, audience=[{"type": "department", "id": fx.dept_front_desk.id}])
    assert [f["fieldType"] for f in created["fields"]] == ["integer", "percent", "long_text"]
    assert created["usedCount"] == 0
    occ = created["fields"][1]
    res = admin.patch(_admin(fx, f"/{created['id']}"), json={
        "active": False,
        "fields": [{"id": occ["id"], "label": "Occupancy %", "fieldType": "percent"}]})
    assert res.status_code == 200, res.get_json()
    listed = admin.get(_admin(fx)).get_json()
    assert [(t["name"], t["active"], [f["label"] for f in t["fields"]]) for t in listed] == [
        ("Night Audit", False, ["Occupancy %"])]


def test_patching_a_saved_fields_type_is_a_400(app, fx, login):
    created = _create(login, fx)
    occ = created["fields"][1]
    res = login("admin@hvh.test").patch(_admin(fx, f"/{created['id']}"), json={
        "fields": [{"id": occ["id"], "label": "Occupancy", "fieldType": "integer"}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {"fields": "type_change"}


def test_capabilities(app, fx, login):
    created = _create(login, fx)
    for email in ("agent@hvh.test", "supervisor@hvh.test", "manager@hvh.test"):
        c = login(email)
        assert c.get(_admin(fx)).status_code == 403, email
        assert c.post(_admin(fx), json=TEMPLATE).status_code == 403, email
        assert c.patch(_admin(fx, f"/{created['id']}"), json={}).status_code == 403, email
        assert c.get(_entries(fx, "/templates")).status_code == 200, email
    assert login("corporate@hvh.test").post(_admin(fx), json=TEMPLATE).status_code == 201


def test_the_picker_route_is_not_mistaken_for_an_entry_id(app, fx, login):
    _create(login, fx)
    rows = login("agent@hvh.test").get(_entries(fx, "/templates")).get_json()
    assert [r["name"] for r in rows] == ["Night Audit"]


def test_post_a_templated_entry_over_json_and_read_it_back(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    agent = login("agent@hvh.test")
    res = agent.post(_entries(fx), json={
        "templateId": created["id"], "body": "Quiet.",
        "fieldValues": [{"fieldId": ids[0], "value": 38}, {"fieldId": ids[1], "value": "87"}]})
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["template"] == {"id": created["id"], "name": "Night Audit"}
    assert [(v["label"], v["numberValue"]) for v in body["fieldValues"]] == [
        ("Arrivals actual", 38.0), ("Occupancy", 87.0)]
    assert (body["body"], body["notes"]) == ("Arrivals actual: 38\nOccupancy: 87%\n\nQuiet.",
                                             "Quiet.")
    feed = agent.get(_entries(fx)).get_json()["entries"]
    assert feed[0]["fieldValues"] == body["fieldValues"]
    assert login("admin@hvh.test").get(_admin(fx)).get_json()[0]["usedCount"] == 1


def test_post_a_templated_entry_over_multipart_with_a_photo(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    res = login("agent@hvh.test").post(_entries(fx), data={
        "templateId": created["id"],
        "fieldValues": json.dumps([{"fieldId": ids[0], "value": "12"},
                                   {"fieldId": ids[1], "value": "90"}]),
        "photo": (io.BytesIO(PNG), "x.png", "image/png")}, content_type="multipart/form-data")
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["photoUrl"]
    assert len(res.get_json()["fieldValues"]) == 2


def test_a_bad_answer_names_its_field_in_the_400(app, fx, login):
    created = _create(login, fx)
    ids = [f["id"] for f in created["fields"]]
    res = login("agent@hvh.test").post(_entries(fx), json={
        "templateId": created["id"],
        "fieldValues": [{"fieldId": ids[0], "value": "12.5"}, {"fieldId": ids[1], "value": 140}]})
    assert res.status_code == 400
    assert res.get_json()["error"]["details"] == {ids[0]: "not_whole", ids[1]: "out_of_range"}


def test_a_non_audience_user_is_403_and_does_not_see_it(app, fx, login):
    created = _create(login, fx, audience=[{"type": "department", "id": fx.dept_front_desk.id}])
    ids = [f["id"] for f in created["fields"]]
    eli = login("engineer@hvh.test")
    assert eli.get(_entries(fx, "/templates")).get_json() == []
    res = eli.post(_entries(fx), json={
        "templateId": created["id"],
        "fieldValues": [{"fieldId": ids[0], "value": 1}, {"fieldId": ids[1], "value": 2}]})
    assert res.status_code == 403


def test_a_template_of_another_property_is_404(app, database, fx, login):
    with database.session() as db:
        b = LogTemplate(property_id=fx.property_b.id, name="B", position=0,
                        created_by_user_id=fx.admin_b.id)
        db.add(b)
        db.flush()
        tid = b.id
    admin = login("admin@hvh.test")
    assert admin.patch(_admin(fx, f"/{tid}"), json={"name": "x"}).status_code == 404
    assert admin.post(_entries(fx), json={"templateId": tid}).status_code == 404
```

Append to the tuple in `test_schema_export.py::test_export_contains_the_public_models`:
`"LogTemplateIn", "LogTemplatePatch", "LogTemplateOut", "LogFieldValueIn", "LogFieldValueOut",
"LogTemplateRef"`.

- [ ] **Step 2: Run to verify they fail**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_api.py tests/test_schema_export.py -q`
Expected: FAIL — 404s on `/log-templates`, missing schema names, stale `schema.json`.

- [ ] **Step 3: Add the routes** — `server/app/api/log.py`.

Imports: `from app.domain import log, log_templates`, and replace the schemas import with

```python
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFeedQuery,
    LogTemplateIn,
    LogTemplatePatch,
)
```

Below `bp = Blueprint(...)` add:

```python
# Admin → Log templates lives apart from the composer's `/log-entries/templates`: the two lists
# have different capabilities and contents (log templates spec §3.2).
templates_bp = Blueprint("log_templates", __name__,
                         url_prefix="/api/p/<property_id>/log-templates")
```

Insert directly above `@bp.get("/<entry_id>")`:

```python
@bp.get("/templates")
@require_auth
@require_property
@require_capability("post_log")
def usable_templates(property_id: str):
    # A static segment, so it wins over `/<entry_id>` as `/mentionables` does.
    with db_session() as db:
        return ok(log_templates.list_usable(db, g.property_id, g.user.id))
```

Append to the end of the file:

```python
@templates_bp.get("")
@require_auth
@require_property
@require_capability("manage_admin")
def list_templates(property_id: str):
    with db_session() as db:
        return ok(log_templates.list_admin(db, g.property_id))


@templates_bp.post("")
@require_auth
@require_property
@require_capability("manage_admin")
def create_template(property_id: str):
    data = parse_body(LogTemplateIn)
    with db_session() as db:
        t = log_templates.create(db, g.property_id, g.user.id, data)
        return ok(log_templates.to_out(db, t), 201)


@templates_bp.patch("/<template_id>")
@require_auth
@require_property
@require_capability("manage_admin")
def patch_template(property_id: str, template_id: str):
    data = parse_body(LogTemplatePatch)
    with db_session() as db:
        t = log_templates.patch(db, g.property_id, g.user.id, template_id, data)
        return ok(log_templates.to_out(db, t))
```

In `server/app/__init__.py`, after `app.register_blueprint(log.bp)` add
`app.register_blueprint(log.templates_bp)`. (`log` is already in `export_json_schema.MODULES`.)

- [ ] **Step 4: Regenerate the client types**

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

In `web/src/api/types.ts`, replace the line
`  HourBucket, InspectRequest, InspectionRowOut, ListQuery, LocationType, LogEntryOut, LogFeedOut, LogMentionableOut, LoginRequest, MembershipOut,`
with

```ts
  HourBucket, InspectRequest, InspectionRowOut, ListQuery, LocationType, LogEntryOut, LogFeedOut,
  LogFieldType, LogFieldValueIn, LogFieldValueOut, LogMentionableOut, LogTemplateFieldIn,
  LogTemplateFieldOut, LogTemplateIn, LogTemplateOut, LogTemplatePatch, LogTemplateRef,
  LoginRequest, MembershipOut,
```

`CreateLogEntryRequest.body` is now optional in the generated type, so in
`web/src/api/hooks/log.ts` change `form.set('body', rest.body)` to
`form.set('body', rest.body ?? '')` or the build fails.

- [ ] **Step 5: Run everything**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_template_api.py tests/test_schema_export.py tests/test_isolation.py -q`
→ PASS (the isolation suite finds the four new rules automatically: 403 across properties,
admin never 403, anonymous 401). Full server suite + ruff; then
`cd web && npm test && npm run lint && npm run build` → PASS (`types.generated.test.ts` confirms
the regenerated file).

- [ ] **Step 6: Commit**

```bash
git add server/app/api/log.py server/app/__init__.py server/tests/test_log_template_api.py server/tests/test_schema_export.py web/src/api/schema.json web/src/api/types.generated.ts web/src/api/types.ts web/src/api/hooks/log.ts
git commit -m "feat(log): log template routes and schema export" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Seed data

**Files:** Modify `server/seed/seed.py`, `server/tests/test_seed.py`; regenerate
`server/data/app.db`.

**Interfaces:** `SeedSummary.log_templates: int`.

- [ ] **Step 1: Write the failing assertions** — `server/tests/test_seed.py`: add
`LogEntryFieldValue` and `LogTemplate` to the `app.models` import, replace

```python
        assert count(LogEntry, LogEntry.property_id == hvh.id) == 3
```

with

```python
        # 3 free-form entries + 4 templated posts (log templates spec §5)
        assert count(LogEntry, LogEntry.property_id == hvh.id) == 7
        assert count(LogTemplate, LogTemplate.property_id == hvh.id) == 3
        assert count(LogEntry, LogEntry.property_id == hvh.id,
                     LogEntry.template_id.is_not(None)) == 4
        # two posts answer all ten fields, two leave the optional Notes blank
        assert count(LogEntryFieldValue, LogEntryFieldValue.property_id == hvh.id) == 38
```

and after `assert summary.checklist_templates == 5` add `assert summary.log_templates == 3`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py -q`
Expected: FAIL — `assert 3 == 7`.

- [ ] **Step 3: Implement** — `server/seed/seed.py`.

Imports: add `log_templates,` to the `from app.domain import (...)` list (after
`hk_transitions,`); add `from app.domain.log import create as post_log_entry` above
`from app.domain.log import shift_for`; add `LogTemplate,` to the `app.models` import (after
`LogEntryMention,`); and above `from app.schemas.pm import AnswerPatch, TemplateItemIn` add

```python
from app.schemas.log import (
    CreateLogEntryRequest,
    LogFieldValueIn,
    LogTemplateFieldIn,
    LogTemplateIn,
    MentionRef,
)
```

`SeedSummary` gains `log_templates: int` after `checklist_instances: int`, and the constructor
at the end gains
`log_templates=db.scalar(select(func.count()).select_from(LogTemplate)),` after
`checklist_instances=...`.

Directly after the hotel-log block's closing `db.flush()` (the one after the overnight
`LogEntry`, just before `# ---- content`), insert:

```python
        # ---- hotel log post templates (log templates spec §5): the hotel's three shift reports,
        # each shared with Front Desk, created and posted through the domain. The posts sit on
        # the previous two local days at fixed local times, so nothing test_seed asserts depends
        # on when the seed runs.
        report_fields = [
            LogTemplateFieldIn(label=label, field_type=field_type, required=required)
            for label, field_type, required in (
                ("Number of enrollments", "integer", True),
                ("Arrivals left", "integer", True),
                ("Arrivals actual", "integer", True),
                ("Departures actual", "integer", True),
                ("Departures left", "integer", True),
                ("Walk-ins", "integer", True),
                ("Occupancy", "percent", True),
                ("Max occupied", "integer", True),
                ("Min available tonight", "integer", True),
                ("Notes", "long_text", False))]
        shift_reports = {
            name: log_templates.create(db, hvh.id, staff["alex"].id, LogTemplateIn(
                name=name, shift=shift, fields=report_fields,
                audience=[MentionRef(type=MentionTargetType.department,
                                     id=depts["front_desk"].id)]))
            for name, shift in (("AM Checklist", "am"), ("PM Checklist", "pm"),
                                ("Night Audit", "overnight"))}
        log_today = pm_cycles.local_today(hvh)
        for days_ago, name, author, hour, numbers, notes in (
                (2, "AM Checklist", "ava", 13, (2, 3, 38, 41, 0, 1, 87, 104, 16),
                 "Harlow wedding block picked up in full."),
                (2, "PM Checklist", "marcus", 20, (1, 0, 12, 2, 0, 3, 92, 110, 10), None),
                (1, "Night Audit", "jordan", 5, (0, 0, 1, 0, 0, 1, 92, 110, 10),
                 "Audit balanced first pass. 305 key encoder slow again."),
                (1, "AM Checklist", "ava", 13, (3, 5, 31, 44, 2, 0, 71, 110, 35), None)):
            template = shift_reports[name]
            answers = [*numbers, notes]
            entry = post_log_entry(db, hvh.id, staff[author].id, CreateLogEntryRequest(
                template_id=template.id,
                field_values=[LogFieldValueIn(field_id=field.id, value=value)
                              for field, value in zip(
                                  log_templates.active_fields(db, template.id), answers,
                                  strict=True)
                              if value is not None]))
            at = local_at(log_today - timedelta(days=days_ago), hour, 30)
            entry.created_at, entry.shift = at, shift_for(hvh, at)
        db.flush()
```

(`local_at`, `staff`, `depts`, `hvh`, `MentionTargetType`, `pm_cycles` and `timedelta` are all
already in scope there.)

- [ ] **Step 4: Run** `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_seed.py tests/test_dev_start.py -q` → PASS.

- [ ] **Step 5: Regenerate the fixture database**

Run: `cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('sqlite:///data/app.db', reset=True))"`
Expected: the summary ends `log_templates=3)` and shows `log_entries=7`.

- [ ] **Step 6: Full suite + ruff, then commit (including `app.db`)**

```bash
git add server/seed/seed.py server/tests/test_seed.py server/data/app.db
git commit -m "feat(log): seed the three shift-report templates and four posts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Web data layer — query keys, hooks, template helpers

**Files:**
- Modify: `web/src/api/queryKeys.ts`, `web/src/api/hooks/log.ts` (+`log.test.tsx`)
- Create: `web/src/features/log/templates.ts` (+`templates.test.ts`)

**Interfaces:**
- Consumes: Task 5's routes and types.
- Produces: `qk.logTemplatesAll(p)` = `['logTemplates', p]`, `qk.logTemplatesUsable(p)`,
  `qk.logTemplatesAdmin(p)`; hooks `useLogTemplates()` (GET `log-entries/templates`),
  `useAdminLogTemplates()` (GET `log-templates`), `useCreateLogTemplate()` (`LogTemplateIn` →
  `LogTemplateOut`), `usePatchLogTemplate()` (`LogTemplatePatch & { id }` → `LogTemplateOut`);
  `useCreateLogEntry` forwards `templateId`/`fieldValues` on multipart and invalidates
  `qk.logTemplatesAll`. `templates.ts` exports `FIELD_TYPE_LABELS: Record<LogFieldType,
  string>`, `NUMERIC_FIELD_TYPES: ReadonlySet<LogFieldType>`,
  `formatFieldValue(value: LogFieldValueOut): string`,
  `audienceSummary(audience: LogTemplateOut['audience']): string`.

- [ ] **Step 1: Write the failing tests**

`web/src/features/log/templates.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { audienceSummary, formatFieldValue } from './templates'

describe('formatFieldValue', () => {
  it('shows a percent with its sign and drops trailing zeros', () => {
    expect(formatFieldValue({ fieldId: 'f', label: 'Occupancy', fieldType: 'percent', numberValue: 87 })).toBe('87%')
    expect(formatFieldValue({ fieldId: 'f', label: 'Occupancy', fieldType: 'percent', numberValue: 87.5 })).toBe('87.5%')
    expect(formatFieldValue({ fieldId: 'f', label: 'ADR', fieldType: 'decimal', numberValue: 129.4 })).toBe('129.4')
    expect(formatFieldValue({ fieldId: 'f', label: 'Walk-ins', fieldType: 'integer', numberValue: 3 })).toBe('3')
  })

  it('shows text as written', () => {
    expect(formatFieldValue({ fieldId: 'f', label: 'Notes', fieldType: 'long_text', textValue: 'Quiet' })).toBe('Quiet')
  })
})

describe('audienceSummary', () => {
  it('says Everyone for an empty audience and counts users and departments otherwise', () => {
    expect(audienceSummary([])).toBe('Everyone')
    expect(audienceSummary([
      { type: 'user', id: 'u-1' }, { type: 'user', id: 'u-2' }, { type: 'user', id: 'u-3' },
      { type: 'department', id: 'd-1' },
    ])).toBe('3 users, 1 department')
    expect(audienceSummary([{ type: 'department', id: 'd-1' }, { type: 'department', id: 'd-2' }]))
      .toBe('2 departments')
  })
})
```

`web/src/api/hooks/log.test.tsx` — change the hooks import to
`import { useAdminLogTemplates, useCreateLogEntry, useLogTemplates, usePatchLogTemplate } from './log'`,
add this `it` inside the existing `describe('useCreateLogEntry', ...)` after the existing test:

```tsx
  it('carries templateId and fieldValues over multipart, and an empty body for notes', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'agent' }))
    const { result } = renderHook(() => useCreateLogEntry(), { wrapper: wrapper(client) })

    const photo = new File(['bytes'], 'x.png', { type: 'image/png' })
    const fieldValues = [{ fieldId: 'f-occ', value: 87 }]
    act(() => {
      result.current.mutate({ templateId: 't-night', fieldValues, photo })
    })

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled())
    const form = vi.mocked(fetch).mock.calls[0]![1]!.body as FormData
    expect(form.get('templateId')).toBe('t-night')
    expect(JSON.parse(String(form.get('fieldValues')))).toEqual(fieldValues)
    expect(form.get('body')).toBe('')
  })
```

and append a new block at the end of the file:

```tsx
describe('log template hooks', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve(200, [])
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads the picker from log-entries/templates and the admin list from log-templates', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
    renderHook(() => { useLogTemplates(); useAdminLogTemplates() }, { wrapper: wrapper(client) })

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2))
    const urls = vi.mocked(fetch).mock.calls.map(([input]) => String(input))
    expect(urls).toContain('/api/p/prop-a/log-entries/templates')
    expect(urls).toContain('/api/p/prop-a/log-templates')
  })

  it('patches by id and refreshes both template lists', async () => {
    const client = testQueryClient()
    client.setQueryData(qk.session, sessionFixture({ role: 'admin' }))
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    const { result } = renderHook(() => usePatchLogTemplate(), { wrapper: wrapper(client) })

    act(() => {
      result.current.mutate({ id: 't-1', active: false })
    })

    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['logTemplates', 'prop-a'] }))
    const [input, init] = vi.mocked(fetch).mock.calls[0]!
    expect(String(input)).toBe('/api/p/prop-a/log-templates/t-1')
    expect(init!.method).toBe('PATCH')
    expect(JSON.parse(String(init!.body))).toEqual({ active: false })
  })
})
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/log/templates.test.ts src/api/hooks/log.test.tsx`
Expected: FAIL — `Failed to resolve import "./templates"` / `useLogTemplates` is not exported.

- [ ] **Step 3: Implement**

`web/src/api/queryKeys.ts`, after `logMentionables`:

```ts
  logTemplatesAll: (propertyId: string) => ['logTemplates', propertyId] as const,
  logTemplatesUsable: (propertyId: string) => ['logTemplates', propertyId, 'usable'] as const,
  logTemplatesAdmin: (propertyId: string) => ['logTemplates', propertyId, 'admin'] as const,
```

`web/src/api/hooks/log.ts` — add `LogTemplateIn, LogTemplateOut, LogTemplatePatch` to the
`../types` import. In `useCreateLogEntry`'s multipart branch, after the `departmentId` line add

```ts
      if (rest.templateId) form.set('templateId', rest.templateId)
      if (rest.fieldValues?.length) form.set('fieldValues', JSON.stringify(rest.fieldValues))
```

and its `onSuccess` becomes

```ts
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
      // A templated post moves its template's usage count on the admin screen.
      void client.invalidateQueries({ queryKey: qk.logTemplatesAll(propertyId) })
    },
```

Then insert between `useCreateLogEntry` and `useAckLogEntry`:

```ts
/** The composer's picker: active templates the caller may post with, current shift first. */
export function useLogTemplates() {
  const { propertyId } = useSession()
  return useQuery<LogTemplateOut[], ApiError>({
    queryKey: qk.logTemplatesUsable(propertyId),
    queryFn: () => api<LogTemplateOut[]>(propertyPath(propertyId, 'log-entries/templates')),
  })
}

/** Admin → Log templates: every template, inactive included, with its usage count. */
export function useAdminLogTemplates() {
  const { propertyId } = useSession()
  return useQuery<LogTemplateOut[], ApiError>({
    queryKey: qk.logTemplatesAdmin(propertyId),
    queryFn: () => api<LogTemplateOut[]>(propertyPath(propertyId, 'log-templates')),
  })
}

/** Template edits emit no realtime event (spec §3.4), so both lists refetch from here. */
function useLogTemplateWrite<TVars>(send: (propertyId: string, vars: TVars) => Promise<LogTemplateOut>) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogTemplateOut, ApiError, TVars>({
    mutationFn: (vars) => send(propertyId, vars),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.logTemplatesAll(propertyId) })
    },
  })
}

export const useCreateLogTemplate = () =>
  useLogTemplateWrite<LogTemplateIn>((p, body) =>
    api<LogTemplateOut>(propertyPath(p, 'log-templates'), { method: 'POST', json: body }),
  )

export const usePatchLogTemplate = () =>
  useLogTemplateWrite<LogTemplatePatch & { id: string }>((p, { id, ...patch }) =>
    api<LogTemplateOut>(propertyPath(p, `log-templates/${id}`), { method: 'PATCH', json: patch }),
  )
```

Create `web/src/features/log/templates.ts`:

```ts
import type { LogFieldType, LogFieldValueOut, LogTemplateOut } from '../../api/types'

export const FIELD_TYPE_LABELS: Record<LogFieldType, string> = {
  short_text: 'Short text',
  long_text: 'Long text',
  integer: 'Whole number',
  decimal: 'Number',
  percent: 'Percent',
}

export const NUMERIC_FIELD_TYPES: ReadonlySet<LogFieldType> = new Set(['integer', 'decimal', 'percent'])

/** Mirrors the server's `log_templates.format_value`: at most two decimals, trailing zeros
 *  dropped, and a percent as `87%`. */
export function formatFieldValue(value: LogFieldValueOut): string {
  if (value.numberValue === null || value.numberValue === undefined) return value.textValue ?? ''
  const shown = String(Number(value.numberValue.toFixed(2)))
  return value.fieldType === 'percent' ? `${shown}%` : shown
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

/** "Everyone" for an empty audience, else e.g. "3 users, 1 department" (spec §4.3). */
export function audienceSummary(audience: LogTemplateOut['audience']): string {
  const users = audience.filter((ref) => ref.type === 'user').length
  const departments = audience.length - users
  const parts = [
    ...(users ? [plural(users, 'user')] : []),
    ...(departments ? [plural(departments, 'department')] : []),
  ]
  return parts.length ? parts.join(', ') : 'Everyone'
}
```

- [ ] **Step 4: Run** `cd web && npx vitest run src/features/log/templates.test.ts src/api/hooks/log.test.tsx && npm run lint && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/api/queryKeys.ts web/src/api/hooks/log.ts web/src/api/hooks/log.test.tsx web/src/features/log/templates.ts web/src/features/log/templates.test.ts
git commit -m "feat(log): web query keys, hooks and helpers for log templates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Composer — the template picker and its fields

**Files:**
- Modify: `web/src/features/log/LogComposer.tsx` (+`LogComposer.test.tsx`),
  `web/src/features/log/LogPage.test.tsx`, `web/src/api/fieldErrors.ts`
  (+`fieldErrors.test.ts`)

**Interfaces:**
- Consumes: `useLogTemplates`, `NUMERIC_FIELD_TYPES` (Task 7); `fieldErrors`.
- Produces: `LogComposer` (same props) with a "Use a template" `<select>` (shown only when the
  picker list is non-empty), one control per field labelled by the field's label (required ones
  `aria-required="true"` with a visual `*`), the message box labelled "Notes (optional)" while a
  template is chosen, Post blocked until required fields are filled, `templateId` +
  `fieldValues` on submit, server `details` beside the named field.

- [ ] **Step 1: Write the failing tests**

`web/src/features/log/LogComposer.test.tsx` — add `LogTemplateOut` to the `../../api/types`
import and append after the existing `describe`:

```tsx
const NIGHT_AUDIT: LogTemplateOut = {
  id: 't-night',
  name: 'Night Audit',
  shift: 'overnight',
  active: true,
  position: 0,
  usedCount: 4,
  audience: [],
  fields: [
    { id: 'f-arr', position: 0, label: 'Arrivals actual', fieldType: 'integer', required: true, active: true },
    { id: 'f-occ', position: 1, label: 'Occupancy', fieldType: 'percent', required: true, active: true },
    { id: 'f-adr', position: 2, label: 'ADR', fieldType: 'decimal', required: false, active: true },
    { id: 'f-mgr', position: 3, label: 'Duty manager', fieldType: 'short_text', required: false, active: true },
    { id: 'f-hand', position: 4, label: 'Handover', fieldType: 'long_text', required: false, active: true },
  ],
}

function serveTemplates(templates: LogTemplateOut[], post?: { status: number; body: unknown }) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const reply = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    if (init?.method === 'POST') return reply(post?.body ?? CREATED, post?.status ?? 201)
    if (url.includes('/log-entries/templates')) return reply(templates)
    if (url.includes('mentionables')) return reply(MENTIONABLES)
    if (url.includes('/departments')) return reply(DEPARTMENTS)
    return reply([])
  })
}

describe('LogComposer with templates', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows no picker when no template is usable', async () => {
    serveTemplates([])
    mount()
    await screen.findByLabelText('Department')
    expect(screen.queryByLabelText('Use a template')).not.toBeInTheDocument()
  })

  it('renders each field type once a template is chosen, and clears it again', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')

    expect(screen.getByLabelText(/^Arrivals actual/)).toHaveAttribute('inputmode', 'numeric')
    expect(screen.getByLabelText(/^Occupancy/)).toHaveAttribute('inputmode', 'decimal')
    expect(screen.getByText('%')).toBeInTheDocument()
    expect(screen.getByLabelText(/^ADR/)).toHaveAttribute('inputmode', 'decimal')
    expect(screen.getByLabelText(/^Duty manager/).tagName).toBe('INPUT')
    expect(screen.getByLabelText(/^Handover/).tagName).toBe('TEXTAREA')
    expect(screen.getByLabelText(/^Arrivals actual/)).toHaveAttribute('aria-required', 'true')
    expect(screen.getByLabelText(/^ADR/)).toHaveAttribute('aria-required', 'false')
    expect(screen.getByLabelText('Notes (optional)')).toBe(screen.getByPlaceholderText('Add to the log…'))

    await userEvent.selectOptions(screen.getByLabelText('Use a template'), '')
    expect(screen.queryByLabelText(/^Arrivals actual/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Notes (optional)')).not.toBeInTheDocument()
  })

  it('keeps Post disabled until every required field is filled, notes or not', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    const post = screen.getByRole('button', { name: 'Post' })
    await userEvent.type(screen.getByPlaceholderText('Add to the log…'), 'Quiet night')
    expect(post).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    expect(post).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '   ')
    expect(post).toBeDisabled() // blank is unanswered
    await userEvent.clear(screen.getByLabelText(/^Occupancy/))
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87')
    expect(post).not.toBeDisabled()
  })

  it('sends templateId and the answered fieldValues, numbers as numbers', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87.5')
    await userEvent.type(screen.getByLabelText(/^Duty manager/), ' Sam ')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(postCalls()).toHaveLength(1))
    expect(JSON.parse(String(postCalls()[0]![1]!.body))).toMatchObject({
      body: '',
      templateId: 't-night',
      fieldValues: [
        { fieldId: 'f-arr', value: 38 },
        { fieldId: 'f-occ', value: 87.5 },
        { fieldId: 'f-mgr', value: 'Sam' },
      ],
    })
  })

  it('shows the server’s reason beside the field it names', async () => {
    serveTemplates([NIGHT_AUDIT], {
      status: 400,
      body: { error: { code: 'VALIDATION_FAILED', message: 'Some template fields need attention',
                       details: { 'f-occ': 'out_of_range', 'f-arr': 'not_whole' } } },
    })
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '12.5')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '140')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByText('That value is out of range.')).toBeInTheDocument()
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Occupancy/)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Some template fields need attention')
  })

  it('resets the template and its answers after a successful post', async () => {
    serveTemplates([NIGHT_AUDIT])
    const onPosted = mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onPosted).toHaveBeenCalledWith(CREATED))
    expect(screen.getByLabelText('Use a template')).toHaveValue('')
    expect(screen.queryByLabelText(/^Arrivals actual/)).not.toBeInTheDocument()
  })
})
```

`web/src/api/fieldErrors.test.ts` — extend `SERVER_CODES` to

```ts
    const SERVER_CODES = ['required', 'invalid_phone_number', 'invalid_timezone',
      'not_a_number', 'not_whole', 'out_of_range', 'too_long', 'unknown_field', 'duplicate']
```

`web/src/features/log/LogPage.test.tsx` — the composer now fetches `log-entries/templates`,
which contains "log-entries" and would be answered with a feed page (and would consume a page in
`servePages`). In **both** `serve` and `servePages` replace
`if (url.includes('mentionables')) return jsonResponse([])` with

```ts
    if (url.includes('mentionables') || url.includes('log-entries/templates')) return jsonResponse([])
```

and replace `feedCalls` (with its comment) by

```ts
// Excludes the mentionables and templates fetches, which also contain the substring "log-entries".
function feedCalls() {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([input]) => String(input).includes('log-entries')
      && !String(input).includes('mentionables') && !String(input).includes('log-entries/templates'))
}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/log src/api/fieldErrors.test.ts`
Expected: FAIL — no "Use a template" control; `not_a_number` etc. worded as raw codes.

- [ ] **Step 3: Add the reason copy** — in `web/src/api/fieldErrors.ts`, at the end of
`REASON_COPY`:

```ts
  // A templated log post's answers (log templates spec §2.3), keyed by field id.
  not_a_number: 'Enter a number.',
  not_whole: 'Enter a whole number.',
  out_of_range: 'That value is out of range.',
  too_long: 'That is too long.',
  unknown_field: 'This field is no longer on the template.',
  duplicate: 'This field was answered twice.',
```

- [ ] **Step 4: Replace `web/src/features/log/LogComposer.tsx`** with:

```tsx
import { useRef, useState, type FormEvent } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useCreateLogEntry, useLogMentionables, useLogTemplates } from '../../api/hooks/log'
import { useDepartments } from '../../api/hooks/users'
import type { LogEntryOut, LogFieldValueIn, LogTemplateFieldOut, LogTemplateOut } from '../../api/types'
import { Button, Input, Textarea } from '../../components/ui'
import { MentionInput, TOKEN_RE, type MentionRef } from './MentionInput'
import { NUMERIC_FIELD_TYPES } from './templates'

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']
const FIELD = 'mb-1 block text-xs font-bold uppercase tracking-widest text-text3'
const SELECT =
  'h-11 w-full rounded border border-border3 bg-surface2 px-3 text-sm text-text focus:border-accent focus:outline-none'

/**
 * A pick records a `MentionRef` immediately, but nothing removes it if the user then
 * deletes the token text it points at — so a stale mention would still ride along and
 * notify someone about an entry that no longer mentions them (Task 10 review defect).
 * Filtering against the tokens still present in `text` at submit time closes that gap.
 */
function pruneMentions(text: string, mentions: MentionRef[]): MentionRef[] {
  const present = new Set<string>()
  for (const match of text.matchAll(TOKEN_RE)) {
    present.add(`${match[2]}:${match[3]}`)
  }
  return mentions.filter((m) => present.has(`${m.type}:${m.id}`))
}

/** Answers by field id, exactly as typed; blank means unanswered, as on the server. */
type Answers = Record<string, string>

function answered(answers: Answers, field: LogTemplateFieldOut): boolean {
  return (answers[field.id] ?? '').trim() !== ''
}

/** A number that parses goes over as a JSON number; anything else goes over as typed, so the
 *  server can name what is wrong with it (`not_a_number`) rather than the client guessing. */
function toFieldValues(template: LogTemplateOut, answers: Answers): LogFieldValueIn[] {
  return template.fields.filter((f) => answered(answers, f)).map((f) => {
    const raw = answers[f.id]!.trim()
    const number = Number(raw)
    return { fieldId: f.id, value: NUMERIC_FIELD_TYPES.has(f.fieldType) && Number.isFinite(number) ? number : raw }
  })
}

function TemplateField({ field, value, error, onChange }: {
  field: LogTemplateFieldOut
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  const id = `log-field-${field.id}`
  const common = { id, value, 'aria-required': field.required, 'aria-invalid': Boolean(error) }
  return (
    <div>
      <label className={FIELD} htmlFor={id}>
        {field.label}
        {field.required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {field.fieldType === 'long_text' ? (
        <Textarea {...common} rows={3} onChange={(e) => onChange(e.target.value)} />
      ) : field.fieldType === 'short_text' ? (
        <Input {...common} maxLength={200} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <div className="flex items-center gap-2">
          <Input
            {...common}
            inputMode={field.fieldType === 'integer' ? 'numeric' : 'decimal'}
            onChange={(e) => onChange(e.target.value)}
          />
          {field.fieldType === 'percent' ? <span className="text-sm text-text3">%</span> : null}
        </div>
      )}
      {error ? <p className="mt-1 text-xs text-dangerText">{error}</p> : null}
    </div>
  )
}

export function LogComposer({ onPosted }: { onPosted?: (entry: LogEntryOut) => void }) {
  const { data: mentionables } = useLogMentionables()
  const { data: departments } = useDepartments()
  const { data: templates } = useLogTemplates()
  const create = useCreateLogEntry()

  const [body, setBody] = useState('')
  const [mentions, setMentions] = useState<MentionRef[]>([])
  const [departmentId, setDepartmentId] = useState('')
  const [photo, setPhoto] = useState<File | null>(null)
  const [requiresAck, setRequiresAck] = useState(false)
  const [audienceText, setAudienceText] = useState('')
  const [audienceMentions, setAudienceMentions] = useState<MentionRef[]>([])
  const [templateId, setTemplateId] = useState('')
  const [answers, setAnswers] = useState<Answers>({})
  const fileInput = useRef<HTMLInputElement>(null)

  const available = templates ?? []
  const template = available.find((t) => t.id === templateId)
  const fields = fieldErrors(create.error)
  const ready = template
    ? template.fields.every((f) => !f.required || answered(answers, f))
      && (template.fields.some((f) => answered(answers, f)) || body.trim() !== '')
    : body.trim() !== ''

  function toggleRequiresAck(checked: boolean) {
    setRequiresAck(checked)
    if (!checked) {
      // Otherwise a re-check later would submit whatever audience was picked before the
      // person changed their mind, rather than starting clean.
      setAudienceText('')
      setAudienceMentions([])
    }
  }

  function chooseTemplate(id: string) {
    // "No template" clears the form; switching templates starts the new one blank.
    setTemplateId(id)
    setAnswers({})
    create.reset()
  }

  function clearPhoto() {
    setPhoto(null)
    if (fileInput.current) fileInput.current.value = ''
  }

  function reset() {
    setBody('')
    setMentions([])
    setDepartmentId('')
    clearPhoto()
    setRequiresAck(false)
    setAudienceText('')
    setAudienceMentions([])
    setTemplateId('')
    setAnswers({})
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!ready || create.isPending) return
    create.mutate(
      {
        body,
        departmentId: departmentId || undefined,
        mentions: pruneMentions(body, mentions),
        requiresAck,
        ackAudience: requiresAck ? pruneMentions(audienceText, audienceMentions) : undefined,
        photo: photo ?? undefined,
        ...(template ? { templateId: template.id, fieldValues: toFieldValues(template, answers) } : {}),
      },
      { onSuccess: (entry) => { reset(); onPosted?.(entry) } },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t border-border p-3">
      {create.error ? (
        <p role="alert" className="rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {create.error.message}
        </p>
      ) : null}

      {available.length > 0 ? (
        <div>
          <label className={FIELD} htmlFor="log-template">Use a template</label>
          <select
            id="log-template"
            className={SELECT}
            value={templateId}
            onChange={(event) => chooseTemplate(event.target.value)}
          >
            <option value="">No template</option>
            {available.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      ) : null}

      {template ? (
        <div className="grid grid-cols-2 gap-3">
          {template.fields.map((field) => (
            <div key={field.id} className={field.fieldType === 'long_text' ? 'col-span-2' : undefined}>
              <TemplateField
                field={field}
                value={answers[field.id] ?? ''}
                error={fields[field.id]}
                onChange={(value) => setAnswers({ ...answers, [field.id]: value })}
              />
            </div>
          ))}
        </div>
      ) : null}

      {template ? <label className={FIELD} htmlFor="log-body">Notes (optional)</label> : null}
      <MentionInput
        id="log-body"
        value={body}
        mentions={mentions}
        options={mentionables ?? []}
        onChange={(value, next) => { setBody(value); setMentions(next) }}
        placeholder="Add to the log…"
      />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={FIELD} htmlFor="log-department">Department</label>
          <select
            id="log-department"
            className={SELECT}
            value={departmentId}
            onChange={(event) => setDepartmentId(event.target.value)}
          >
            <option value="">No department</option>
            {(departments ?? []).map((d) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={FIELD} htmlFor="log-photo">Photo</label>
          <input
            ref={fileInput}
            id="log-photo"
            type="file"
            accept={ACCEPTED.join(',')}
            onChange={(event) => setPhoto(event.target.files?.[0] ?? null)}
            className="block w-full text-xs text-text3"
          />
          {photo ? (
            <p className="mt-1 flex items-center gap-2 text-xs text-text3">
              {photo.name}
              <button type="button" onClick={clearPhoto} className="font-semibold underline">
                Clear
              </button>
            </p>
          ) : null}
        </div>
      </div>

      <label className="flex items-center gap-2 text-xs font-semibold text-text3">
        <input
          type="checkbox"
          checked={requiresAck}
          onChange={(event) => toggleRequiresAck(event.target.checked)}
        />
        Requires acknowledgement
      </label>

      {requiresAck ? (
        <MentionInput
          value={audienceText}
          mentions={audienceMentions}
          options={mentionables ?? []}
          onChange={(value, next) => { setAudienceText(value); setAudienceMentions(next) }}
          placeholder="Who needs to acknowledge this?"
        />
      ) : null}

      <Button
        type="submit"
        variant="primary"
        className="self-end"
        loading={create.isPending}
        disabled={create.isPending || !ready}
      >
        Post
      </Button>
    </form>
  )
}
```

- [ ] **Step 5: Run** `cd web && npx vitest run src/features/log src/api && npm run lint && npm run build` → PASS
(the existing composer tests are unchanged: with no template chosen the request body is exactly
what it was).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/log/LogComposer.tsx web/src/features/log/LogComposer.test.tsx web/src/features/log/LogPage.test.tsx web/src/api/fieldErrors.ts web/src/api/fieldErrors.test.ts
git commit -m "feat(log): post with a template from the composer" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Feed card — template tag, value table, notes

**Files:** Modify `web/src/features/log/LogEntryCard.tsx` (+`LogEntryCard.test.tsx`).

**Interfaces:** Consumes `formatFieldValue` (Task 7) and `LogEntryOut.template` /
`fieldValues` / `notes` (Task 4). Produces no new exports.

- [ ] **Step 1: Write the failing test** — in `LogEntryCard.test.tsx` change the first import to
`import { screen, within } from '@testing-library/react'` and append inside the top-level
`describe('LogEntryCard', ...)`, after its last `it`:

```tsx
  describe('a templated post', () => {
    const TEMPLATED: LogEntryOut = {
      ...BASE,
      body: 'Arrivals actual: 38\nOccupancy: 87.5%\n\nQuiet night.',
      template: { id: 't-night', name: 'Night Audit' },
      fieldValues: [
        { fieldId: 'f-arr', label: 'Arrivals actual', fieldType: 'integer', numberValue: 38 },
        { fieldId: 'f-occ', label: 'Occupancy', fieldType: 'percent', numberValue: 87.5 },
      ],
      notes: 'Quiet night.',
    }

    it('shows the template tag and a label/value table with percent formatting', () => {
      mount(TEMPLATED)
      expect(screen.getByText('Night Audit')).toBeInTheDocument()
      const table = screen.getByText('Arrivals actual').closest('dl')!
      expect(table).not.toBeNull()
      expect(within(table).getByText('38')).toBeInTheDocument()
      expect(within(table).getByText('87.5%')).toBeInTheDocument()
    })

    it('renders the notes under the table, never the generated summary', () => {
      mount(TEMPLATED)
      expect(screen.getByText('Quiet night.')).toBeInTheDocument()
      expect(screen.queryByText(/Arrivals actual: 38/)).toBeNull()
    })

    it('renders no body paragraph at all when there are no notes', () => {
      mount({ ...TEMPLATED, body: 'Arrivals actual: 38\nOccupancy: 87.5%', notes: null })
      expect(screen.queryByText(/Arrivals actual:/)).toBeNull()
      expect(screen.getByText('87.5%')).toBeInTheDocument()
    })
  })
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/features/log/LogEntryCard.test.tsx`
Expected: FAIL — no "Night Audit" tag; the raw summary is rendered.

- [ ] **Step 3: Implement** — `web/src/features/log/LogEntryCard.tsx`:

- first line becomes `import { Fragment, type ReactNode } from 'react'`; add
  `import { formatFieldValue } from './templates'` after the `./MentionInput` import;
- after `const setPinned = useSetLogPinned()` add

```tsx
  const fieldValues = entry.fieldValues ?? []
  const text = fieldValues.length > 0 ? entry.notes ?? '' : entry.body
```

- after the department badge line add
  `{entry.template ? <Badge tone="note">{entry.template.name}</Badge> : null}`;
- replace `<p className="whitespace-pre-wrap text-sm">{renderBody(entry.body)}</p>` with

```tsx
      {fieldValues.length > 0 ? (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
          {fieldValues.map((value) => (
            <Fragment key={value.fieldId}>
              <dt className="text-text3">{value.label}</dt>
              <dd className="whitespace-pre-wrap font-mono">{formatFieldValue(value)}</dd>
            </Fragment>
          ))}
        </dl>
      ) : null}

      {/* A templated post's body repeats its values as text; the card shows the table above
          and only the author's notes here (spec §4.2). */}
      {text ? <p className="whitespace-pre-wrap text-sm">{renderBody(text)}</p> : null}
```

Acknowledgements, pinning and links are untouched.

- [ ] **Step 4: Run** `cd web && npx vitest run src/features/log && npm run lint && npm run build` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/log/LogEntryCard.tsx web/src/features/log/LogEntryCard.test.tsx
git commit -m "feat(log): templated posts render as a value table on the feed card" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Admin → Log templates and nav

**Files:**
- Create: `web/src/features/admin/LogTemplatesAdmin.tsx` (+`LogTemplatesAdmin.test.tsx`)
- Modify: `web/src/features/admin/AdminPage.tsx` (+`AdminPage.test.tsx`),
  `web/src/components/navModel.ts` (`ADMIN_SECTIONS`)

**Interfaces:** Consumes `useAdminLogTemplates`, `useCreateLogTemplate`, `usePatchLogTemplate`,
`FIELD_TYPE_LABELS`, `audienceSummary` (Task 7); `useDepartments`, `useStaff`;
`SHIFT_LABELS` (`features/checklists/labels`); `FieldError`, `LABEL`, `SELECT`
(`./ItemListEditor`); `AdminTable`, `EditPanel`. Produces `LogTemplatesAdmin` at
`/app/admin/log-templates`.

- [ ] **Step 1: Write the failing tests**

`web/src/features/admin/LogTemplatesAdmin.test.tsx`:

```tsx
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LogTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LogTemplatesAdmin } from './LogTemplatesAdmin'

const NIGHT_AUDIT: LogTemplateOut = {
  id: 't-night',
  name: 'Night Audit',
  shift: 'overnight',
  active: true,
  position: 0,
  usedCount: 6,
  audience: [
    { type: 'user', id: 'u-1' }, { type: 'user', id: 'u-2' }, { type: 'user', id: 'u-3' },
    { type: 'department', id: 'dept-fd' },
  ],
  fields: [
    { id: 'f-occ', position: 0, label: 'Occupancy', fieldType: 'percent', required: true, active: true },
    { id: 'f-notes', position: 1, label: 'Notes', fieldType: 'long_text', required: false, active: true },
  ],
}
const GENERAL: LogTemplateOut = {
  ...NIGHT_AUDIT, id: 't-gen', name: 'General', shift: null, active: false, usedCount: 0, audience: [],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'POST' || init?.method === 'PATCH') return json(NIGHT_AUDIT, init.method === 'POST' ? 201 : 200)
    if (url.includes('/departments')) return json([aDepartment({ id: 'dept-fd', name: 'Front Desk', type: 'front_desk' })])
    if (url.endsWith('/users')) return json([aStaffUser(), aStaffUser({ id: 'u-off', firstName: 'Old', status: 'disabled' })])
    if (url.includes('/log-templates')) return json([NIGHT_AUDIT, GENERAL])
    return json([])
  })
}

function sent(method: 'POST' | 'PATCH') {
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === method)
  return call ? { url: String(call[0]), body: JSON.parse(String(call[1]!.body)) } : undefined
}

function mount() {
  renderWithProviders(
    <SessionProvider>
      <LogTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

describe('LogTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('lists name, shift, field count, who it is shared with, usage and active', async () => {
    mount()
    const night = (await screen.findByText('Night Audit')).closest('tr')!
    expect(within(night).getByText('Overnight')).toBeInTheDocument()
    expect(within(night).getByText('2')).toBeInTheDocument()
    expect(within(night).getByText('3 users, 1 department')).toBeInTheDocument()
    expect(within(night).getByText('6')).toBeInTheDocument()
    expect(within(night).getByText('on')).toBeInTheDocument()
    const general = screen.getByText('General').closest('tr')!
    expect(within(general).getByText('Any')).toBeInTheDocument()
    expect(within(general).getByText('Everyone')).toBeInTheDocument()
    expect(within(general).getByText('off')).toBeInTheDocument()
  })

  it('creates a template with ordered fields and an audience', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'AM Checklist')
    await userEvent.selectOptions(screen.getByLabelText('Shift'), 'am')
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    await userEvent.type(screen.getByLabelText('Label for field 1'), 'Walk-ins')
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    await userEvent.type(screen.getByLabelText('Label for field 2'), 'Occupancy')
    await userEvent.selectOptions(screen.getByLabelText('Type for field 2'), 'percent')
    await userEvent.click(screen.getByRole('button', { name: 'Move field 2 up' }))
    await userEvent.click(screen.getByLabelText('Field 2 required'))
    await userEvent.click(await screen.findByRole('checkbox', { name: 'Front Desk' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Ava Nolan' }))
    expect(screen.queryByRole('checkbox', { name: /Old/ })).not.toBeInTheDocument() // disabled
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(sent('POST')?.body).toEqual({
      name: 'AM Checklist', shift: 'am', active: true,
      fields: [
        { label: 'Occupancy', fieldType: 'percent', required: true },
        { label: 'Walk-ins', fieldType: 'integer', required: false },
      ],
      audience: [{ type: 'department', id: 'dept-fd' }, { type: 'user', id: 'u-ava' }],
    }))
    expect(sent('POST')!.url).toBe('/api/p/prop-a/log-templates')
  })

  it('edits a saved template: its field types are locked and ids ride along', async () => {
    mount()
    await userEvent.click(await screen.findByText('Night Audit'))
    expect(screen.getByLabelText('Type for field 1')).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Add field' }))
    expect(screen.getByLabelText('Type for field 3')).not.toBeDisabled()
    await userEvent.type(screen.getByLabelText('Label for field 3'), 'Walk-ins')
    await userEvent.click(screen.getByRole('button', { name: 'Remove field 2' }))
    await userEvent.selectOptions(screen.getByLabelText('Shift'), '')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(sent('PATCH')).toBeDefined())
    expect(sent('PATCH')!.url).toBe('/api/p/prop-a/log-templates/t-night')
    expect(sent('PATCH')!.body).toMatchObject({
      name: 'Night Audit', shift: null,
      fields: [
        { id: 'f-occ', label: 'Occupancy', fieldType: 'percent', required: true },
        { label: 'Walk-ins', fieldType: 'integer', required: true },
      ],
    })
    expect(sent('PATCH')!.body.audience).toHaveLength(4)
  })

  it('shows a server field error under the field list', async () => {
    vi.mocked(fetch).mockImplementation((_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return json({ error: { code: 'VALIDATION_FAILED', message: 'Every field needs a label',
                               details: { fields: 'required' } } }, 400)
      }
      return json([])
    })
    mount()
    await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
    await userEvent.type(screen.getByLabelText('Name'), 'X')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('This field is required.')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Every field needs a label')
  })
})
```

`web/src/features/admin/AdminPage.test.tsx` — append inside `describe('AdminPage', ...)`:

```tsx
  it('links Log templates after Checklist templates and routes to its screen', async () => {
    vi.mocked(fetch).mockImplementation(() => Promise.resolve(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } })))
    mount('/app/admin/log-templates')

    const link = await screen.findByRole('link', { name: 'Log templates' })
    expect(link).toHaveAttribute('aria-current', 'page')
    const rendered = screen.getAllByRole('link').map((l) => l.textContent)
    expect(rendered.indexOf('Log templates')).toBe(rendered.indexOf('Checklist templates') + 1)
    expect(await screen.findByRole('heading', { name: 'Log templates' })).toBeInTheDocument()
  })
```

(`mockImplementation`, not `mockResolvedValue`: the screen makes three requests and a `Response`
body can be read only once.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npx vitest run src/features/admin/LogTemplatesAdmin.test.tsx src/features/admin/AdminPage.test.tsx`
Expected: FAIL — `Failed to resolve import "./LogTemplatesAdmin"`.

- [ ] **Step 3: Create `web/src/features/admin/LogTemplatesAdmin.tsx`**

```tsx
import { useState } from 'react'
import { fieldErrors } from '../../api/fieldErrors'
import { useAdminLogTemplates, useCreateLogTemplate, usePatchLogTemplate } from '../../api/hooks/log'
import { useDepartments, useStaff } from '../../api/hooks/users'
import type { LogFieldType, LogTemplateIn, LogTemplateOut, Shift } from '../../api/types'
import { Badge, Button, EmptyState, Input, Spinner } from '../../components/ui'
import { SHIFT_LABELS } from '../checklists/labels'
import { FIELD_TYPE_LABELS, audienceSummary } from '../log/templates'
import { AdminTable, type Column } from './AdminTable'
import { EditPanel } from './EditPanel'
import { FieldError, LABEL, SELECT } from './ItemListEditor'

type FieldDraft = { id?: string; label: string; fieldType: LogFieldType; required: boolean }

type Draft = {
  id?: string
  name: string
  shift: Shift | ''
  active: boolean
  fields: FieldDraft[]
  departmentIds: string[]
  userIds: string[]
}

const EMPTY: Draft = { name: '', shift: '', active: true, fields: [], departmentIds: [], userIds: [] }
const NEW_FIELD: FieldDraft = { label: '', fieldType: 'integer', required: true }

function fromTemplate(t: LogTemplateOut): Draft {
  return {
    id: t.id, name: t.name, shift: t.shift ?? '', active: t.active,
    fields: t.fields.map((f) => ({ id: f.id, label: f.label, fieldType: f.fieldType, required: f.required })),
    departmentIds: t.audience.filter((r) => r.type === 'department').map((r) => r.id),
    userIds: t.audience.filter((r) => r.type === 'user').map((r) => r.id),
  }
}

function toggle(list: string[], id: string, on: boolean): string[] {
  return on ? [...list, id] : list.filter((x) => x !== id)
}

/** Specific to this screen rather than a bent ItemListEditor: log fields have their own types and
 *  no bounds or units (spec §4.3). A saved field's type is locked, as the server requires. */
function FieldListEditor({ fields, onChange, error }: {
  fields: FieldDraft[]
  onChange: (fields: FieldDraft[]) => void
  error?: string
}) {
  const edit = (index: number, change: Partial<FieldDraft>) =>
    onChange(fields.map((f, i) => (i === index ? { ...f, ...change } : f)))
  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= fields.length) return
    const next = [...fields]
    const held = next[index]!
    next[index] = next[target]!
    next[target] = held
    onChange(next)
  }

  return (
    <div>
      <div className="mb-1 flex items-center">
        <p className={LABEL}>Fields</p>
        <Button className="ml-auto" onClick={() => onChange([...fields, { ...NEW_FIELD }])}>
          Add field
        </Button>
      </div>
      <FieldError message={error} />
      <ol className="flex flex-col gap-2">
        {fields.map((field, index) => {
          const n = index + 1
          return (
            <li key={field.id ?? `new-${index}`} className="rounded border border-border2 p-2">
              <div className="flex flex-col gap-2">
                <Input aria-label={`Label for field ${n}`} value={field.label} maxLength={200}
                       placeholder="Label" onChange={(e) => edit(index, { label: e.target.value })} />
                <div className="flex gap-2">
                  <select aria-label={`Type for field ${n}`} className={SELECT} value={field.fieldType}
                          disabled={Boolean(field.id)}
                          onChange={(e) => edit(index, { fieldType: e.target.value as LogFieldType })}>
                    {(Object.keys(FIELD_TYPE_LABELS) as LogFieldType[]).map((t) => (
                      <option key={t} value={t}>{FIELD_TYPE_LABELS[t]}</option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1 text-xs">
                    <input type="checkbox" aria-label={`Field ${n} required`} checked={field.required}
                           onChange={(e) => edit(index, { required: e.target.checked })} />
                    Required
                  </label>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" aria-label={`Move field ${n} up`} onClick={() => move(index, -1)}>↑</Button>
                  <Button variant="ghost" aria-label={`Move field ${n} down`} onClick={() => move(index, 1)}>↓</Button>
                  <Button variant="ghost" className="ml-auto text-dangerText" aria-label={`Remove field ${n}`}
                          onClick={() => onChange(fields.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

export function LogTemplatesAdmin() {
  const { data, isPending, error } = useAdminLogTemplates()
  const { data: departments } = useDepartments()
  const { data: staff } = useStaff()
  const create = useCreateLogTemplate()
  const patch = usePatchLogTemplate()
  const [draft, setDraft] = useState<Draft | null>(null)
  const [selected, setSelected] = useState<LogTemplateOut | null>(null)

  const rows = data ?? []
  const pending = create.isPending || patch.isPending
  const failed = create.error ?? patch.error
  const fields = fieldErrors(failed)
  const people = (staff ?? []).filter((u) => u.status === 'active')

  const columns: Column<LogTemplateOut>[] = [
    { key: 'name', head: 'Name', render: (r) => r.name },
    { key: 'shift', head: 'Shift', render: (r) => (r.shift ? SHIFT_LABELS[r.shift] : 'Any') },
    { key: 'fields', head: 'Fields', mono: true, render: (r) => r.fields.length },
    { key: 'audience', head: 'Shared with', render: (r) => audienceSummary(r.audience) },
    { key: 'used', head: 'Used', mono: true, render: (r) => r.usedCount },
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

  function open(template: LogTemplateOut) {
    clearFailures()
    setSelected(template)
    setDraft(fromTemplate(template))
  }

  function save() {
    if (!draft || !draft.name.trim()) return
    const body: LogTemplateIn = {
      name: draft.name.trim(),
      shift: draft.shift || null,
      active: draft.active,
      // `fields` is a non-empty tuple in the generated type; the server enforces "at least one
      // field" itself (a 400 on save), so the cast mirrors that contract.
      fields: draft.fields.map((f) => ({
        ...(f.id ? { id: f.id } : {}), label: f.label.trim(), fieldType: f.fieldType, required: f.required,
      })) as LogTemplateIn['fields'],
      audience: [
        ...draft.departmentIds.map((id) => ({ type: 'department' as const, id })),
        ...draft.userIds.map((id) => ({ type: 'user' as const, id })),
      ],
    }
    if (draft.id) patch.mutate({ ...body, id: draft.id }, { onSuccess: close })
    else create.mutate(body, { onSuccess: close })
  }

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Log templates</h1>
          <Button
            variant="primary"
            className="ml-auto"
            onClick={() => {
              clearFailures()
              setSelected(null)
              setDraft({ ...EMPTY, fields: [], departmentIds: [], userIds: [] })
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
            <EmptyState title="No log templates" hint="A template is a structured shift report staff fill in instead of free text." />
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
            <label className={LABEL} htmlFor="log-tpl-name">Name</label>
            <Input id="log-tpl-name" value={draft.name} maxLength={200} onChange={(e) => edit({ name: e.target.value })} />
            <FieldError message={fields.name} />
          </div>
          <div>
            <label className={LABEL} htmlFor="log-tpl-shift">Shift</label>
            <select id="log-tpl-shift" className={SELECT} value={draft.shift}
                    onChange={(e) => edit({ shift: e.target.value as Shift | '' })}>
              <option value="">Any</option>
              {(Object.keys(SHIFT_LABELS) as Shift[]).map((s) => (
                <option key={s} value={s}>{SHIFT_LABELS[s]}</option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={draft.active} onChange={(e) => edit({ active: e.target.checked })} />
            Active
          </label>

          <FieldListEditor fields={draft.fields} onChange={(next) => edit({ fields: next })} error={fields.fields} />

          <fieldset>
            <legend className={LABEL}>Shared with</legend>
            <p className="mb-2 text-xs text-text3">Nobody ticked means everyone at the property.</p>
            <FieldError message={fields.audience} />
            <p className="mb-1 text-xs font-semibold text-text3">Departments</p>
            <div className="mb-2 flex flex-col gap-1">
              {(departments ?? []).map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={draft.departmentIds.includes(d.id)}
                         onChange={(e) => edit({ departmentIds: toggle(draft.departmentIds, d.id, e.target.checked) })} />
                  {d.name}
                </label>
              ))}
            </div>
            <p className="mb-1 text-xs font-semibold text-text3">People</p>
            <div className="flex max-h-48 flex-col gap-1 overflow-y-auto">
              {people.map((u) => (
                <label key={u.id} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={draft.userIds.includes(u.id)}
                         onChange={(e) => edit({ userIds: toggle(draft.userIds, u.id, e.target.checked) })} />
                  {u.firstName} {u.lastName}
                </label>
              ))}
            </div>
          </fieldset>
        </EditPanel>
      ) : null}
    </div>
  )
}
```

- [ ] **Step 4: Wire it in**

`web/src/components/navModel.ts` — `ADMIN_SECTIONS` gains, after the Checklist templates entry:

```ts
  { to: '/app/admin/log-templates', label: 'Log templates' },
```

`web/src/features/admin/AdminPage.tsx` — add `import { LogTemplatesAdmin } from './LogTemplatesAdmin'`
after the `DepartmentsAdmin` import, and after the checklist-templates route:

```tsx
        <Route path="log-templates" element={<LogTemplatesAdmin />} />
```

- [ ] **Step 5: Run** `cd web && npm test && npm run lint && npm run build` → PASS (the whole suite:
the Ctrl+K palette and rail read `ADMIN_SECTIONS`, so they pick the entry up with no further
change).

- [ ] **Step 6: Commit**

```bash
git add web/src/features/admin/LogTemplatesAdmin.tsx web/src/features/admin/LogTemplatesAdmin.test.tsx web/src/features/admin/AdminPage.tsx web/src/features/admin/AdminPage.test.tsx web/src/components/navModel.ts
git commit -m "feat(log): Admin - Log templates screen" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Postgres 18 verification and full check — stop before pushing

Nothing in this task is committed except fixes it forces.

- [ ] **Step 1: Everything green locally** — `cd server && ../.venv/Scripts/python.exe -m pytest -q`
and `../.venv/Scripts/python.exe -m ruff check .`; `cd web && npm test && npm run lint && npm run build`.
Regenerate the schema and types and confirm `git status --short web/src/api` shows nothing.

- [ ] **Step 2: Migrate a Postgres 18 database up, down and up again** (Docker Desktop must be
running; start it from `C:\Users\bryan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`
if `docker info` fails). Reuse the existing container rather than removing it — it may hold the
user's dev data:

```bash
docker start relay-pg18 2>/dev/null || docker run -d --name relay-pg18 -e POSTGRES_PASSWORD=relaydev -e POSTGRES_USER=relay -e POSTGRES_DB=relay_test -p 55432:5432 postgres:18
# wait for: docker exec relay-pg18 pg_isready -U relay
docker exec relay-pg18 psql -U relay -d postgres -c "DROP DATABASE IF EXISTS relay_logtpl" -c "CREATE DATABASE relay_logtpl"
cd server && export DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_logtpl"
../.venv/Scripts/python.exe -m alembic upgrade head
../.venv/Scripts/python.exe -m alembic downgrade 0009
docker exec relay-pg18 psql -U relay -d relay_logtpl -c "\dt log*"          # → the four log_entry* tables only
docker exec relay-pg18 psql -U relay -d relay_logtpl -c "\d log_entry" | grep -i template   # → nothing
../.venv/Scripts/python.exe -m alembic upgrade head
docker exec relay-pg18 psql -U relay -d relay_logtpl -c "\d log_entry" | grep -i template
```

Expected after the re-upgrade: `template_id | character varying(36)` and
`"fk_log_entry_template_id" FOREIGN KEY (template_id) REFERENCES log_template(id)`.

Check drift against Postgres too:

```bash
cd server && ../.venv/Scripts/python.exe -c "
from app.db import Base; import app.models, sqlalchemy as sa
from alembic.migration import MigrationContext; from alembic.autogenerate import compare_metadata
e=sa.create_engine('postgresql+psycopg://relay:relaydev@localhost:55432/relay_logtpl'); print([d for d in compare_metadata(MigrationContext.configure(e.connect()), Base.metadata) if 'log' in str(d)]); e.dispose()"
```

Expected: `[]`.

- [ ] **Step 3: Seed and exercise the app on Postgres 18** — recreate `relay_logtpl`, seed it
through the normal path, and drive the real routes. Save this as `pg_smoke.py` in the session
scratchpad directory (outside the repo) — do not commit it:

```python
"""Throwaway Postgres smoke check for log templates (plan Task 11). Not committed."""
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


ava = login("ava@hvh.test")
pid = next(m["propertyId"] for m in ava.get("/api/auth/me").get_json()["memberships"]
           if m["propertyCode"] == "HVH")
base = f"/api/p/{pid}"
usable = ava.get(f"{base}/log-entries/templates").get_json()
print("usable:", [t["name"] for t in usable])
assert len(usable) == 3
feed = ava.get(f"{base}/log-entries").get_json()["entries"]
templated = [e for e in feed if e["template"]]
print("templated in feed:", [(e["template"]["name"], len(e["fieldValues"])) for e in templated])
assert len(templated) == 4
night = next(t for t in usable if t["name"] == "Night Audit")
ids = {f["label"]: f["id"] for f in night["fields"]}
answers = {"Number of enrollments": 0, "Arrivals left": 0, "Arrivals actual": 1,
           "Departures actual": 0, "Departures left": 0, "Walk-ins": 0, "Occupancy": "87.5",
           "Max occupied": 100, "Min available tonight": 20}
post = ava.post(f"{base}/log-entries", json={
    "templateId": night["id"], "body": "Smoke test",
    "fieldValues": [{"fieldId": ids[k], "value": v} for k, v in answers.items()]})
print("post:", post.status_code, post.get_json().get("notes"))
assert post.status_code == 201
too_big = ava.post(f"{base}/log-entries", json={
    "templateId": night["id"],
    "fieldValues": [{"fieldId": ids[k], "value": 100_000_000 if k == "Max occupied" else v}
                    for k, v in answers.items()]})
print("overflow:", too_big.status_code, too_big.get_json()["error"].get("details"))
assert too_big.status_code == 400  # review focus 1, on the engine where it would 500
eli = login("eli@hvh.test")  # engineering: not in the Front Desk audience
assert eli.get(f"{base}/log-entries/templates").get_json() == []
assert eli.post(f"{base}/log-entries", json={"templateId": night["id"]}).status_code == 403
admin = login("alex@hvh.test")
rows = admin.get(f"{base}/log-templates").get_json()
print("admin:", [(t["name"], t["usedCount"]) for t in rows])
assert {t["name"]: t["usedCount"] for t in rows}["Night Audit"] == 2
occ = next(f for f in night["fields"] if f["label"] == "Occupancy")
retype = admin.patch(f"{base}/log-templates/{night['id']}", json={
    "fields": [{"id": occ["id"], "label": "Occupancy", "fieldType": "integer"}]})
assert retype.status_code == 400, retype.get_json()
print("OK")
app.extensions["db"].engine.dispose()
```

```bash
docker exec relay-pg18 psql -U relay -d postgres -c "DROP DATABASE IF EXISTS relay_logtpl" -c "CREATE DATABASE relay_logtpl"
cd server && ../.venv/Scripts/python.exe -c "from seed.seed import run; print(run('postgresql+psycopg://relay:relaydev@localhost:55432/relay_logtpl', reset=False))"
../.venv/Scripts/python.exe "$SCRATCHPAD/pg_smoke.py" "postgresql+psycopg://relay:relaydev@localhost:55432/relay_logtpl"   # SCRATCHPAD = the session scratchpad directory the script was saved in
```

Expected: the seed summary shows `log_entries=7 … log_templates=3`; the script prints `OK`.
Optionally also run the full app on it (`DATABASE_URL=".../relay_logtpl"
.venv/Scripts/python.exe server/dev_start.py` and `cd web && npm run dev`), log in as
`ava@hvh.test` / `Password123!`, post a Night Audit from the composer and see its card; log in
as `alex@hvh.test` and open Admin → Log templates. Afterwards drop `relay_logtpl`.

- [ ] **Step 4: STOP — ask the user before any push.** Show `git log --oneline origin/main..HEAD`
and the verification results. Do **not** run `git push`: pushing `main` deploys to production,
and that is the user's call. If they approve later, the deploy must be verified as `CLAUDE.md`
says — the deployment for the new head with reason `deploy`, its log showing
`==> alembic upgrade head` before `==> gunicorn`, `/api/health` ok, and
`SELECT version_num FROM alembic_version` returning `0010` with the four new tables present and
empty (production is never seeded; the hotel's admin creates the templates in Admin → Log
templates).
