# Internal Staff Messaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build internal staff-to-staff messaging — 1:1 DMs, editable named groups, and an auto-provisioned property-wide `#ALL` channel — as a new subsystem alongside Relay's existing guest Inbox.

**Architecture:** New SQLAlchemy models (`StaffConversation`, `StaffConversationParticipant`, `StaffMessage`) and a parallel domain/API/frontend stack, deliberately independent of the guest `conversation`/`message` tables. Realtime reuses the existing property-wide WebSocket event bus unchanged (thin `{id}` payloads; clients refetch over authorized REST). New-message pushes reuse the existing `Notification` model and notification centre.

**Tech Stack:** Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 (server); Vite + React 18 + TypeScript + TanStack Query (web). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-19-staff-messaging-design.md`

## Global Constraints

- Server code lives under `server/`, web code under `web/`; all paths below are relative to those unless stated.
- Pydantic request/response models are `CamelModel` (from `app.schemas.common`) — camelCase on the wire, snake_case in Python, `extra="forbid"`.
- Every route needs `@require_auth` then `@require_property`; staff messaging adds **no new capability** — any property member (all of `STAFF` in `app.auth.permissions`) can use it.
- A conversation id is a guessable handle: every lookup scopes by `property_id` **and** participant membership, and a non-participant gets 404, never 403 (matches the existing property-isolation convention).
- Enums are `StrEnum` in `app/schemas/enums.py`, mapped via `app.models.core.enum_type`.
- All new tables get `TimestampMixin` (`id`, `created_at`, `updated_at`) per `app/models/core.py`.
- Realtime events: `queue_event(db, property_id, type, payload)` with a thin payload (ids only, no message content) — never hand-roll WebSocket sends.
- Run backend tests from `server/`: `python -m pytest`. Run frontend tests from `web/`: `npm run test`. Run frontend build/typecheck from `web/`: `npm run build`.

---

## Task 1: Enum, models, and migration

**Files:**
- Modify: `server/app/schemas/enums.py` (append `StaffConversationKind`)
- Create: `server/app/models/staff_messages.py`
- Modify: `server/app/models/__init__.py` (export new models)
- Create: `server/alembic/versions/0005_staff_messaging.py`
- Test: `server/tests/test_models.py` (append a smoke test)

**Interfaces:**
- Produces: `StaffConversationKind` enum (`dm`, `group`, `all`); models `StaffConversation`, `StaffConversationParticipant`, `StaffMessage` with the fields below, importable from `app.models`.

- [ ] **Step 1: Add the enum**

Append to `server/app/schemas/enums.py`:

```python
class StaffConversationKind(StrEnum):
    dm = "dm"
    group = "group"
    all = "all"
```

- [ ] **Step 2: Write the model file**

Create `server/app/models/staff_messages.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models.core import TimestampMixin, enum_type
from app.schemas.enums import StaffConversationKind


class StaffConversation(TimestampMixin, Base):
    """A staff-to-staff thread: a 1:1 DM, a named editable group, or the property's singleton
    `#ALL` channel. Deliberately not the guest `conversation` table — see spec §1.

    No DB-level uniqueness enforces one `all` row per property: `get_or_create_all_conversation`
    (app/domain/staff_messages.py) checks-then-creates, and the realistic race window (two
    simultaneous first-ever requests against a brand-new property) is negligible enough that a
    stray duplicate is an acceptable outcome rather than one worth a partial-unique-index for.
    """

    __tablename__ = "staff_conversation"
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    kind: Mapped[StaffConversationKind] = mapped_column(
        enum_type(StaffConversationKind), nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("user_account.id"))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)


class StaffConversationParticipant(TimestampMixin, Base):
    __tablename__ = "staff_conversation_participant"
    __table_args__ = (
        UniqueConstraint("conversation_id", "user_id", name="uq_staff_participant_conv_user"),
        Index("ix_staff_participant_user", "user_id"),
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("staff_conversation.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class StaffMessage(TimestampMixin, Base):
    __tablename__ = "staff_message"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("staff_conversation.id"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(ForeignKey("property.id"), nullable=False, index=True)
    author_user_id: Mapped[str] = mapped_column(ForeignKey("user_account.id"), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    photo_content_type: Mapped[str | None] = mapped_column(String(40))
    photo_byte_size: Mapped[int | None] = mapped_column(Integer)
    # Deferred for the same reason as work_order_photo.data: never drag the bytes along with a
    # plain message listing.
    photo_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
```

- [ ] **Step 3: Export from the models package**

In `server/app/models/__init__.py`, add the import and `__all__` entries:

```python
from app.models.staff_messages import StaffConversation, StaffConversationParticipant, StaffMessage
```

Add `"StaffConversation", "StaffConversationParticipant", "StaffMessage"` to `__all__`, keeping the list alphabetical.

- [ ] **Step 4: Write the migration**

Create `server/alembic/versions/0005_staff_messaging.py`. Follow the exact style of `0004_work_order_photo.py` (same header shape, same `batch_alter_table` conventions where relevant — none needed here since these are new tables, not column changes on an existing one):

```python
"""internal staff messaging: staff_conversation, staff_conversation_participant, staff_message

Net-new subsystem (docs/superpowers/specs/2026-09-19-staff-messaging-design.md), deliberately
separate from the guest conversation/message tables — see the design doc §1 for why.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-19

"""

import sqlalchemy as sa

import app.db
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_conversation",
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("dm", "group", "all", name="ck_enum_staffconversationkind",
                    native_enum=False, create_constraint=True, length=32),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("avatar_url", sa.String(length=500), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("last_message_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("staff_conversation", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_property_id"), ["property_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_last_message_at"), ["last_message_at"], unique=False
        )

    op.create_table(
        "staff_conversation_participant",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("last_read_at", app.db.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["staff_conversation.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id", "user_id", name="uq_staff_participant_conv_user"),
    )
    with op.batch_alter_table("staff_conversation_participant", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_conversation_participant_conversation_id"),
            ["conversation_id"], unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_staff_participant_user"), ["user_id"], unique=False
        )

    op.create_table(
        "staff_message",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("property_id", sa.String(length=36), nullable=False),
        sa.Column("author_user_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("photo_content_type", sa.String(length=40), nullable=True),
        sa.Column("photo_byte_size", sa.Integer(), nullable=True),
        sa.Column("photo_data", sa.LargeBinary(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", app.db.UTCDateTime(), nullable=False),
        sa.Column("updated_at", app.db.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["user_account.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["staff_conversation.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["property.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("staff_message", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_staff_message_conversation_id"), ["conversation_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_staff_message_property_id"), ["property_id"], unique=False
        )


def downgrade() -> None:
    op.drop_table("staff_message")
    with op.batch_alter_table("staff_conversation_participant", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_staff_participant_user"))
        batch_op.drop_index(batch_op.f("ix_staff_conversation_participant_conversation_id"))
    op.drop_table("staff_conversation_participant")
    with op.batch_alter_table("staff_conversation", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_staff_conversation_last_message_at"))
        batch_op.drop_index(batch_op.f("ix_staff_conversation_property_id"))
    op.drop_table("staff_conversation")
```

- [ ] **Step 5: Write a model smoke test**

Append to `server/tests/test_models.py` (open it first to match its existing style of test — it constructs a row per model and asserts round-trip persistence; add a matching one):

```python
def test_staff_conversation_round_trip(database, fx):
    from app.models import StaffConversation, StaffConversationParticipant, StaffMessage
    from app.schemas.enums import StaffConversationKind

    with database.session() as db:
        conv = StaffConversation(property_id=fx.property_a.id, kind=StaffConversationKind.dm)
        db.add(conv)
        db.flush()
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=fx.agent_a.id))
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=fx.engineer_a.id))
        db.add(StaffMessage(conversation_id=conv.id, property_id=fx.property_a.id,
                            author_user_id=fx.agent_a.id, body="hi"))
        conv_id = conv.id

    with database.session() as db:
        loaded = db.get(StaffConversation, conv_id)
        assert loaded.kind == StaffConversationKind.dm
```

- [ ] **Step 6: Run migration + test**

Run: `cd server && python -m pytest tests/test_models.py -v`
Expected: PASS (the `template_db_path` session fixture runs `alembic upgrade head`, which now includes revision `0005`; if the migration has an error this test fails with a clear alembic traceback).

- [ ] **Step 7: Commit**

```bash
cd server
git add app/schemas/enums.py app/models/staff_messages.py app/models/__init__.py alembic/versions/0005_staff_messaging.py tests/test_models.py
git commit -m "feat(server): add staff messaging data model"
```

---

## Task 2: Pydantic schemas and JSON Schema export

**Files:**
- Create: `server/app/schemas/staff_messages.py`
- Modify: `server/app/schemas/export_json_schema.py` (add module to `MODULES`)
- Test: `server/tests/test_schema_export.py` (open first — it's a small file; add one assertion in its existing style)

**Interfaces:**
- Consumes: `StaffConversationKind` from Task 1.
- Produces: `CreateDmRequest`, `CreateGroupRequest`, `CreateStaffConversationRequest`, `GroupPatch`, `AddParticipantsRequest`, `SendStaffMessageRequest`, `StaffParticipantOut`, `StaffConversationOut`, `StaffConversationDetail`, `StaffMessageOut`, `StaffDirectoryEntryOut` — all importable from `app.schemas.staff_messages`, all consumed by Task 3-6's domain/API code.

- [ ] **Step 1: Write the schemas**

Create `server/app/schemas/staff_messages.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import Role, StaffConversationKind


class CreateStaffConversationRequest(CamelModel):
    """POST /staff-conversations. `kind` picks which of the other fields apply; validated
    together in app.domain.staff_messages.create_conversation rather than as two separate
    Pydantic models, so the route stays a single endpoint (spec §3)."""

    kind: Literal[StaffConversationKind.dm, StaffConversationKind.group]
    user_id: str | None = None          # required, kind=dm
    name: str | None = Field(default=None, min_length=1, max_length=100)  # required, kind=group
    user_ids: list[str] | None = None   # required, kind=group


class GroupPatch(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = None


class AddParticipantsRequest(CamelModel):
    user_ids: list[str] = Field(min_length=1)


class SendStaffMessageRequest(CamelModel):
    """The non-file half of the multipart body; a `photo` file part arrives alongside it,
    exactly like WorkOrderPhotoUpload."""

    body: str | None = Field(default=None, max_length=4000)


class StaffParticipantOut(CamelModel):
    user_id: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None


class StaffMessageOut(CamelModel):
    id: str
    conversation_id: str
    author_user_id: str
    author_name: str
    body: str | None = None
    photo_url: str | None = None
    created_at: datetime


class StaffConversationOut(CamelModel):
    id: str
    kind: StaffConversationKind
    name: str | None = None
    avatar_url: str | None = None
    display_name: str
    other_user_id: str | None = None   # set only for kind=dm
    participants: list[StaffParticipantOut]
    last_message_at: datetime | None = None
    last_message_preview: str | None = None
    unread: bool
    created_at: datetime
    updated_at: datetime


class StaffConversationDetail(StaffConversationOut):
    messages: list[StaffMessageOut]


class StaffDirectoryEntryOut(CamelModel):
    user_id: str
    first_name: str
    last_name: str
    avatar_url: str | None = None
    role: Role
    department_id: str | None = None
    department_name: str | None = None
```

- [ ] **Step 2: Wire into the JSON Schema export**

In `server/app/schemas/export_json_schema.py`, add `staff_messages` to the import list and to `MODULES`:

```python
from app.schemas import (
    analytics,
    auth,
    content,
    conversations,
    dev,
    notifications,
    properties,
    staff_messages,
    users,
    work_orders,
)

MODULES = (auth, users, conversations, work_orders, content, notifications, analytics,
           properties, staff_messages, dev)
```

- [ ] **Step 3: Open and extend the existing schema-export test**

Read `server/tests/test_schema_export.py` first to match its assertion style (it likely asserts specific model names appear in the built schema's `$defs`). Add an assertion that `StaffConversationOut` and `StaffMessageOut` are present in the exported schema, following whatever pattern the existing assertions use.

- [ ] **Step 4: Run test**

Run: `cd server && python -m pytest tests/test_schema_export.py -v`
Expected: PASS

- [ ] **Step 5: Regenerate `schema.json`**

Run: `cd server && python -m app.schemas.export_json_schema`
Expected: `wrote .../web/src/api/schema.json` printed, and `git status` in `web/src/api/` shows `schema.json` changed.

- [ ] **Step 6: Commit**

```bash
cd server
git add app/schemas/staff_messages.py app/schemas/export_json_schema.py tests/test_schema_export.py ../web/src/api/schema.json
git commit -m "feat(server): add staff messaging API schemas"
```

---

## Task 3: Domain + API — list, create, and the directory

This is the first end-to-end slice: creating DMs and groups, listing "my conversations," and the staff directory that backs "New Conversations." Includes the lazy `#ALL` provisioning every later task depends on.

**Files:**
- Create: `server/app/domain/staff_messages.py`
- Create: `server/app/api/staff_messages.py`
- Modify: `server/app/__init__.py` (register blueprint)
- Test: `server/tests/test_staff_messages_api.py`

**Interfaces:**
- Consumes: models/schemas from Tasks 1-2; `app.auth.decorators.{require_auth,require_property}`; `app.api._util.{db_session,ok,parse_body}`; `app.domain.users.list_staff` (for directory role/department info) and `app.models.Department` (for department name).
- Produces: `app.domain.staff_messages.{get_or_create_all_conversation, ensure_participant, create_conversation, list_conversations_for_user, get_for_participant, directory}` — consumed by Tasks 4-6.

- [ ] **Step 1: Write the failing API tests**

Create `server/tests/test_staff_messages_api.py`:

```python
def test_all_channel_is_auto_created_and_listed(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    rows = agent.get(base).get_json()
    all_channel = next(r for r in rows if r["kind"] == "all")
    assert all_channel["displayName"] == "#ALL"
    assert fx.agent_a.id in [p["userId"] for p in all_channel["participants"]]
    # A second staff member's first request also sees it and is auto-joined.
    eng = login("engineer@hvh.test")
    rows2 = eng.get(base).get_json()
    all_2 = next(r for r in rows2 if r["kind"] == "all")
    assert fx.engineer_a.id in [p["userId"] for p in all_2["participants"]]


def test_create_dm_dedupes_to_existing_thread(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    first = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id})
    assert first.status_code == 201
    conv = first.get_json()
    assert conv["kind"] == "dm" and conv["otherUserId"] == fx.engineer_a.id
    second = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id})
    assert second.status_code == 200
    assert second.get_json()["id"] == conv["id"]
    # The other side sees the same thread too, with otherUserId flipped to the agent.
    eng = login("engineer@hvh.test")
    eng_view = eng.get(f"{base}/{conv['id']}")
    assert eng_view.status_code == 200
    assert eng_view.get_json()["otherUserId"] == fx.agent_a.id


def test_create_group_includes_creator_and_is_visible_to_members(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    sup = login("supervisor@hvh.test")
    res = sup.post(base, json={"kind": "group", "name": "Engineering huddle",
                               "userIds": [fx.engineer_a.id, fx.housekeeper_a.id]})
    assert res.status_code == 201
    group = res.get_json()
    assert group["kind"] == "group" and group["displayName"] == "Engineering huddle"
    member_ids = {p["userId"] for p in group["participants"]}
    assert member_ids == {fx.supervisor_a.id, fx.engineer_a.id, fx.housekeeper_a.id}
    eng = login("engineer@hvh.test")
    listed = eng.get(base).get_json()
    assert group["id"] in [r["id"] for r in listed]


def test_non_participant_gets_404(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    outsider = login("supervisor@hvh.test")
    assert outsider.get(f"{base}/{conv['id']}").status_code == 404


def test_cross_property_isolation(app, fx, client, database, login):
    base_a = f"/api/p/{fx.property_a.id}/staff-conversations"
    base_b = f"/api/p/{fx.property_b.id}/staff-conversations"
    agent_a = login("agent@hvh.test")
    agent_b = login("agent@lsi.test")
    ids_a = {r["id"] for r in agent_a.get(base_a).get_json()}
    ids_b = {r["id"] for r in agent_b.get(base_b).get_json()}
    assert ids_a.isdisjoint(ids_b)  # the two #ALL channels are different rows
    assert agent_b.get(base_a).status_code == 403  # no membership at property A at all


def test_directory_excludes_self_and_includes_role_department(app, fx, client, database, login):
    agent = login("agent@hvh.test")
    rows = agent.get(f"/api/p/{fx.property_a.id}/staff-directory").get_json()
    ids = {r["userId"] for r in rows}
    assert fx.agent_a.id not in ids
    eng = next(r for r in rows if r["userId"] == fx.engineer_a.id)
    assert eng["role"] == "dept_staff" and eng["departmentName"] == "Engineering"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v`
Expected: FAIL (404 — no such blueprint/route yet)

- [ ] **Step 3: Write the domain module**

Create `server/app/domain/staff_messages.py`:

```python
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import clock
from app.domain import audit, notifications
from app.errors import NotFound, ValidationFailed
from app.models import Department, PropertyMembership, StaffConversation, StaffConversationParticipant, StaffMessage, UserAccount
from app.realtime.broadcast import queue_event
from app.schemas.enums import StaffConversationKind
from app.schemas.staff_messages import (
    CreateStaffConversationRequest,
    StaffConversationDetail,
    StaffConversationOut,
    StaffDirectoryEntryOut,
    StaffMessageOut,
    StaffParticipantOut,
)

MAX_MESSAGES = 200


def _assert_member(db: Session, property_id: str, user_id: str) -> None:
    if not db.scalar(select(PropertyMembership.id).where(
            PropertyMembership.property_id == property_id, PropertyMembership.user_id == user_id)):
        raise ValidationFailed("User is not a member of this property")


def get_or_create_all_conversation(db: Session, property_id: str) -> StaffConversation:
    conv = db.scalar(select(StaffConversation).where(
        StaffConversation.property_id == property_id,
        StaffConversation.kind == StaffConversationKind.all))
    if conv is not None:
        return conv
    conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.all, name="#ALL")
    db.add(conv)
    db.flush()
    return conv


def ensure_participant(db: Session, conversation_id: str, user_id: str) -> StaffConversationParticipant:
    row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conversation_id,
        StaffConversationParticipant.user_id == user_id))
    if row is not None:
        return row
    row = StaffConversationParticipant(conversation_id=conversation_id, user_id=user_id)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Concurrent double-join (e.g. two tabs both opening #ALL for the first time).
        row = db.scalar(select(StaffConversationParticipant).where(
            StaffConversationParticipant.conversation_id == conversation_id,
            StaffConversationParticipant.user_id == user_id))
    return row


def find_dm(db: Session, property_id: str, user_a: str, user_b: str) -> StaffConversation | None:
    P = StaffConversationParticipant
    matching = (
        select(P.conversation_id)
        .join(StaffConversation, StaffConversation.id == P.conversation_id)
        .where(StaffConversation.property_id == property_id,
               StaffConversation.kind == StaffConversationKind.dm,
               P.user_id.in_([user_a, user_b]))
        .group_by(P.conversation_id)
        .having(func.count(func.distinct(P.user_id)) == 2)
    )
    # A dm conversation has exactly 2 participants by construction (never gains more — only
    # groups are editable), so both ids present among its (exactly 2) participants means the
    # pair is exactly {user_a, user_b}.
    return db.scalar(select(StaffConversation).where(StaffConversation.id.in_(matching)))


def create_conversation(db: Session, property_id: str, actor_user_id: str,
                        data: CreateStaffConversationRequest) -> tuple[StaffConversation, bool]:
    """Returns (conversation, created) — `created=False` when a dm request deduped to an
    existing thread, so the API layer can answer 200 instead of 201."""
    if data.kind == StaffConversationKind.dm:
        if not data.user_id:
            raise ValidationFailed("userId is required for a dm")
        if data.user_id == actor_user_id:
            raise ValidationFailed("Cannot start a dm with yourself")
        _assert_member(db, property_id, data.user_id)
        existing = find_dm(db, property_id, actor_user_id, data.user_id)
        if existing is not None:
            return existing, False
        conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.dm,
                                 created_by_user_id=actor_user_id)
        db.add(conv)
        db.flush()
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=actor_user_id))
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=data.user_id))
        db.flush()
        queue_event(db, property_id, "staff_conversation.created", {"id": conv.id})
        return conv, True

    if not data.name or not data.user_ids:
        raise ValidationFailed("name and userIds are required for a group")
    for uid in data.user_ids:
        _assert_member(db, property_id, uid)
    conv = StaffConversation(property_id=property_id, kind=StaffConversationKind.group,
                             name=data.name.strip(), created_by_user_id=actor_user_id)
    db.add(conv)
    db.flush()
    member_ids = dict.fromkeys([actor_user_id, *data.user_ids])  # de-dupe, keep order
    for uid in member_ids:
        db.add(StaffConversationParticipant(conversation_id=conv.id, user_id=uid))
    db.flush()
    queue_event(db, property_id, "staff_conversation.created", {"id": conv.id})
    return conv, True


def get(db: Session, property_id: str, conversation_id: str) -> StaffConversation:
    conv = db.scalar(select(StaffConversation).where(
        StaffConversation.id == conversation_id, StaffConversation.property_id == property_id))
    if conv is None:
        raise NotFound("Conversation not found")
    return conv


def get_for_participant(db: Session, property_id: str, conversation_id: str,
                        user_id: str) -> StaffConversation:
    conv = get(db, property_id, conversation_id)
    is_participant = db.scalar(select(StaffConversationParticipant.id).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == user_id))
    # #ALL is implicitly open to every property member: joining lazily here, rather than
    # 404ing until some earlier list-view happened to trigger the join, means a direct link to
    # the all-channel works for a user who has never opened Messages before.
    if is_participant is None and conv.kind == StaffConversationKind.all:
        ensure_participant(db, conv.id, user_id)
    elif is_participant is None:
        raise NotFound("Conversation not found")
    return conv


def _display(conv: StaffConversation, participants: list[StaffParticipantOut],
            viewer_user_id: str) -> tuple[str, str | None, str | None]:
    """(display_name, avatar_url, other_user_id) for a viewer."""
    if conv.kind == StaffConversationKind.dm:
        other = next((p for p in participants if p.user_id != viewer_user_id), None)
        name = f"{other.first_name} {other.last_name}" if other else "Unknown"
        return name, other.avatar_url if other else None, other.user_id if other else None
    return conv.name or "Group", conv.avatar_url, None


def _participants_out(db: Session, conversation_id: str) -> list[StaffParticipantOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership)
        .join(StaffConversationParticipant, StaffConversationParticipant.user_id == UserAccount.id)
        .join(PropertyMembership, (PropertyMembership.user_id == UserAccount.id))
        .where(StaffConversationParticipant.conversation_id == conversation_id)
    ).all()
    # A user can hold memberships at several properties; keep the row scoped by matching the
    # conversation's own property rather than trusting the join above to have narrowed it.
    conv_property_id = None
    seen: dict[str, StaffParticipantOut] = {}
    for u, m in rows:
        if conv_property_id is None:
            conv_property_id = m.property_id
        if m.property_id != conv_property_id:
            continue
        seen[u.id] = StaffParticipantOut(user_id=u.id, first_name=u.first_name,
                                         last_name=u.last_name, avatar_url=u.avatar_url,
                                         role=m.role, department_id=m.department_id)
    return list(seen.values())


def _out(db: Session, conv: StaffConversation, viewer_user_id: str) -> StaffConversationOut:
    participants = _participants_out(db, conv.id)
    display_name, avatar_url, other_user_id = _display(conv, participants, viewer_user_id)
    last = db.scalar(select(StaffMessage).where(StaffMessage.conversation_id == conv.id)
                     .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc()).limit(1))
    if last is not None:
        preview = last.body.strip() if last.body else ("Sent a photo" if last.photo_data else None)
    else:
        preview = None
    participant_row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == viewer_user_id))
    last_read = participant_row.last_read_at if participant_row else None
    unread = bool(conv.last_message_at and (last_read is None or conv.last_message_at > last_read))
    return StaffConversationOut(
        id=conv.id, kind=conv.kind, name=conv.name, avatar_url=conv.avatar_url,
        display_name=display_name, other_user_id=other_user_id, participants=participants,
        last_message_at=conv.last_message_at, last_message_preview=preview, unread=unread,
        created_at=conv.created_at, updated_at=conv.updated_at)


def list_conversations_for_user(db: Session, property_id: str,
                                user_id: str) -> list[StaffConversationOut]:
    all_conv = get_or_create_all_conversation(db, property_id)
    ensure_participant(db, all_conv.id, user_id)
    rows = db.scalars(
        select(StaffConversation)
        .join(StaffConversationParticipant,
             StaffConversationParticipant.conversation_id == StaffConversation.id)
        .where(StaffConversation.property_id == property_id,
               StaffConversationParticipant.user_id == user_id)
    ).all()
    out = [_out(db, c, user_id) for c in rows]
    out.sort(key=lambda c: c.last_message_at or c.created_at, reverse=True)
    return out


def detail(db: Session, property_id: str, conversation_id: str,
          viewer_user_id: str) -> StaffConversationDetail:
    conv = get_for_participant(db, property_id, conversation_id, viewer_user_id)
    base = _out(db, conv, viewer_user_id)
    rows = db.execute(
        select(StaffMessage, UserAccount)
        .join(UserAccount, UserAccount.id == StaffMessage.author_user_id)
        .where(StaffMessage.conversation_id == conv.id)
        .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc())
        .limit(MAX_MESSAGES)
    ).all()
    messages = [
        StaffMessageOut(id=m.id, conversation_id=m.conversation_id, author_user_id=m.author_user_id,
                        author_name=f"{u.first_name} {u.last_name}", body=m.body,
                        photo_url=(photo_url(property_id, m.conversation_id, m.id)
                                  if m.photo_content_type else None),
                        created_at=m.created_at)
        for m, u in reversed(rows)
    ]
    return StaffConversationDetail(**base.model_dump(), messages=messages)


def photo_url(property_id: str, conversation_id: str, message_id: str) -> str:
    return f"/api/p/{property_id}/staff-conversations/{conversation_id}/messages/{message_id}/photo"


def directory(db: Session, property_id: str, viewer_user_id: str) -> list[StaffDirectoryEntryOut]:
    rows = db.execute(
        select(UserAccount, PropertyMembership, Department)
        .join(PropertyMembership, PropertyMembership.user_id == UserAccount.id)
        .outerjoin(Department, Department.id == PropertyMembership.department_id)
        .where(PropertyMembership.property_id == property_id, UserAccount.id != viewer_user_id)
        .order_by(UserAccount.first_name, UserAccount.last_name)
    ).all()
    return [StaffDirectoryEntryOut(user_id=u.id, first_name=u.first_name, last_name=u.last_name,
                                   avatar_url=u.avatar_url, role=m.role,
                                   department_id=m.department_id,
                                   department_name=d.name if d else None) for u, m, d in rows]
```

- [ ] **Step 4: Write the API blueprint**

Create `server/app/api/staff_messages.py`:

```python
from flask import Blueprint, g

from app.api._util import db_session, ok, parse_body
from app.auth.decorators import require_auth, require_property
from app.domain import staff_messages
from app.schemas.staff_messages import CreateStaffConversationRequest, StaffDirectoryEntryOut

bp = Blueprint("staff_messages", __name__, url_prefix="/api/p/<property_id>/staff-conversations")
directory_bp = Blueprint("staff_directory", __name__, url_prefix="/api/p/<property_id>")


@bp.get("")
@require_auth
@require_property
def list_conversations(property_id: str):
    with db_session() as db:
        return ok(staff_messages.list_conversations_for_user(db, g.property_id, g.user.id))


@bp.post("")
@require_auth
@require_property
def create_conversation(property_id: str):
    data = parse_body(CreateStaffConversationRequest)
    with db_session() as db:
        conv, created = staff_messages.create_conversation(db, g.property_id, g.user.id, data)
        out = staff_messages.detail(db, g.property_id, conv.id, g.user.id)
        return ok(out, 201 if created else 200)


@bp.get("/<conversation_id>")
@require_auth
@require_property
def get_conversation(property_id: str, conversation_id: str):
    with db_session() as db:
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@directory_bp.get("/staff-directory")
@require_auth
@require_property
def get_directory(property_id: str):
    with db_session() as db:
        return ok(staff_messages.directory(db, g.property_id, g.user.id))
```

- [ ] **Step 5: Register the blueprints**

In `server/app/__init__.py`, add `staff_messages` to the `from app.api import (...)` block (alphabetical) and register both blueprints alongside the others:

```python
    from app.api import (
        analytics,
        assets,
        auth,
        categories,
        conversations,
        departments,
        guests,
        health,
        hooks,
        notifications,
        properties,
        quick_replies,
        short_links,
        staff_messages,
        users,
        work_orders,
    )

    app.register_blueprint(health.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(departments.bp)
    app.register_blueprint(properties.bp)
    app.register_blueprint(users.bp)
    app.register_blueprint(guests.bp)
    app.register_blueprint(notifications.bp)
    app.register_blueprint(conversations.bp)
    app.register_blueprint(work_orders.bp)
    app.register_blueprint(quick_replies.bp)
    app.register_blueprint(assets.bp)
    app.register_blueprint(categories.bp)
    app.register_blueprint(short_links.bp)
    app.register_blueprint(hooks.bp)
    app.register_blueprint(analytics.bp)
    app.register_blueprint(staff_messages.bp)
    app.register_blueprint(staff_messages.directory_bp)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v`
Expected: PASS (all 5 tests)

- [ ] **Step 7: Run the full backend suite to check for regressions**

Run: `cd server && python -m pytest -q`
Expected: PASS, same count as before plus the new tests.

- [ ] **Step 8: Commit**

```bash
cd server
git add app/domain/staff_messages.py app/api/staff_messages.py app/__init__.py tests/test_staff_messages_api.py
git commit -m "feat(server): staff conversation listing, creation, and directory"
```

---

## Task 4: Domain + API — messages, unread, realtime, notifications

**Files:**
- Modify: `server/app/domain/staff_messages.py` (add `send_message`, `mark_read`)
- Modify: `server/app/api/staff_messages.py` (add routes)
- Test: `server/tests/test_staff_messages_api.py` (append)

**Interfaces:**
- Consumes: everything from Task 3; `app.domain.notifications.notify_users`.
- Produces: `staff_messages.send_message(db, property_id, conversation_id, actor_user_id, body=None) -> StaffMessage`, `staff_messages.mark_read(db, property_id, conversation_id, user_id) -> None` — `send_message` here covers text only; Task 6 extends it with a photo.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_staff_messages_api.py`:

```python
def test_send_message_updates_list_and_unread(app, fx, client, database, login, events):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    eng = login("engineer@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    send = agent.post(f"{base}/{conv['id']}/messages", data={"body": "AC in 412 is out"})
    assert send.status_code == 201
    msg = send.get_json()
    assert msg["body"] == "AC in 412 is out" and msg["authorName"] == "Ava Agent"
    assert any(e.type == "staff_message.created" for e in events)

    listed = eng.get(base).get_json()
    row = next(r for r in listed if r["id"] == conv["id"])
    assert row["unread"] is True and row["lastMessagePreview"] == "AC in 412 is out"

    eng.post(f"{base}/{conv['id']}/read")
    listed_after = eng.get(base).get_json()
    row_after = next(r for r in listed_after if r["id"] == conv["id"])
    assert row_after["unread"] is False

    # The sender was never unread on their own message.
    sender_view = agent.get(base).get_json()
    sender_row = next(r for r in sender_view if r["id"] == conv["id"])
    assert sender_row["unread"] is False


def test_send_message_notifies_other_participants(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    agent.post(f"{base}/{conv['id']}/messages", data={"body": "ping"})
    eng = login("engineer@hvh.test")
    notes = eng.get(f"/api/p/{fx.property_a.id}/notifications").get_json()
    assert any(n["type"] == "staff_message" and n["entityId"] == conv["id"] for n in notes)


def test_send_message_requires_body_or_photo(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    res = agent.post(f"{base}/{conv['id']}/messages", data={})
    assert res.status_code == 400


def test_non_participant_cannot_send_or_read(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    outsider = login("supervisor@hvh.test")
    assert outsider.post(f"{base}/{conv['id']}/messages",
                         data={"body": "hi"}).status_code == 404
    assert outsider.post(f"{base}/{conv['id']}/read").status_code == 404


def test_all_channel_message_reaches_every_member(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    admin = login("admin@hvh.test")
    all_channel = next(r for r in admin.get(base).get_json() if r["kind"] == "all")
    admin.post(f"{base}/{all_channel['id']}/messages", data={"body": "Welcome"})
    eng = login("engineer@hvh.test")
    listed = eng.get(base).get_json()
    row = next(r for r in listed if r["kind"] == "all")
    assert row["unread"] is True and row["lastMessagePreview"] == "Welcome"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v -k "message or notif or non_participant_cannot or all_channel_message"`
Expected: FAIL (404 — routes not defined)

- [ ] **Step 3: Add `send_message` and `mark_read` to the domain module**

Append to `server/app/domain/staff_messages.py`:

```python
def send_message(db: Session, property_id: str, conversation_id: str, actor_user_id: str, *,
                 body: str | None = None, photo_content_type: str | None = None,
                 photo_byte_size: int | None = None, photo_data: bytes | None = None) -> StaffMessage:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    body = body.strip() if body else None
    if not body and not photo_data:
        raise ValidationFailed("A message needs text or a photo")
    msg = StaffMessage(conversation_id=conv.id, property_id=property_id,
                       author_user_id=actor_user_id, body=body,
                       photo_content_type=photo_content_type, photo_byte_size=photo_byte_size,
                       photo_data=photo_data)
    db.add(msg)
    conv.last_message_at = clock.now()
    db.flush()
    ensure_participant(db, conv.id, actor_user_id).last_read_at = clock.now()
    audit.record(db, property_id, actor_user_id, "staff_message.sent", "staff_conversation",
                conv.id)
    queue_event(db, property_id, "staff_message.created", {"conversationId": conv.id})
    other_ids = [p.user_id for p in _participants_out(db, conv.id) if p.user_id != actor_user_id]
    if other_ids:
        sender = db.get(UserAccount, actor_user_id)
        preview = body or "Sent a photo"
        notifications.notify_users(db, property_id, other_ids, "staff_message",
                                   f"{sender.first_name} {sender.last_name}", body=preview,
                                   entity_type="staff_conversation", entity_id=conv.id)
    return msg


def mark_read(db: Session, property_id: str, conversation_id: str, user_id: str) -> None:
    conv = get_for_participant(db, property_id, conversation_id, user_id)
    participant = ensure_participant(db, conv.id, user_id)
    participant.last_read_at = clock.now()
```

- [ ] **Step 4: Add the routes**

In `server/app/api/staff_messages.py`, update the top imports (only two lines change from Task 3's version — `no_content` joins the `_util` import, and the schemas import grows):

```python
from app.api._util import db_session, no_content, ok, parse_body
from app.schemas.staff_messages import (
    CreateStaffConversationRequest,
    SendStaffMessageRequest,
    StaffDirectoryEntryOut,
    StaffMessageOut,
)
```

then, after `get_conversation`:

```python
@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
def send_message(property_id: str, conversation_id: str):
    data = parse_body(SendStaffMessageRequest)
    with db_session() as db:
        msg = staff_messages.send_message(db, g.property_id, conversation_id, g.user.id,
                                          body=data.body)
        author = g.user
        return ok(StaffMessageOut(id=msg.id, conversation_id=msg.conversation_id,
                                  author_user_id=msg.author_user_id,
                                  author_name=f"{author.first_name} {author.last_name}",
                                  body=msg.body, photo_url=None, created_at=msg.created_at), 201)


@bp.post("/<conversation_id>/read")
@require_auth
@require_property
def mark_read(property_id: str, conversation_id: str):
    with db_session() as db:
        staff_messages.mark_read(db, g.property_id, conversation_id, g.user.id)
    return no_content()
```

- [ ] **Step 5: Run tests**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Run full backend suite**

Run: `cd server && python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd server
git add app/domain/staff_messages.py app/api/staff_messages.py tests/test_staff_messages_api.py
git commit -m "feat(server): send staff messages, unread state, notifications"
```

---

## Task 5: Domain + API — group management

**Files:**
- Modify: `server/app/domain/staff_messages.py` (add `update_group`, `add_participants`, `remove_participant`)
- Modify: `server/app/api/staff_messages.py` (add routes)
- Test: `server/tests/test_staff_messages_api.py` (append)

**Interfaces:**
- Produces: `staff_messages.{update_group, add_participants, remove_participant}`.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_staff_messages_api.py`:

```python
def test_group_rename_add_and_remove_participant(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    sup = login("supervisor@hvh.test")
    group = sup.post(base, json={"kind": "group", "name": "Eng team",
                                 "userIds": [fx.engineer_a.id]}).get_json()
    renamed = sup.patch(f"{base}/{group['id']}", json={"name": "Engineering"})
    assert renamed.status_code == 200 and renamed.get_json()["displayName"] == "Engineering"

    added = sup.post(f"{base}/{group['id']}/participants",
                     json={"userIds": [fx.housekeeper_a.id]})
    assert added.status_code == 200
    member_ids = {p["userId"] for p in added.get_json()["participants"]}
    assert fx.housekeeper_a.id in member_ids

    hk = login("housekeeper@hvh.test")
    assert hk.get(f"{base}/{group['id']}").status_code == 200  # newly added member can see it

    removed = sup.delete(f"{base}/{group['id']}/participants/{fx.housekeeper_a.id}")
    assert removed.status_code == 200
    assert fx.housekeeper_a.id not in {p["userId"] for p in removed.get_json()["participants"]}
    assert hk.get(f"{base}/{group['id']}").status_code == 404  # removed member loses access


def test_all_channel_rejects_rename_and_remove(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    admin = login("admin@hvh.test")
    all_channel = next(r for r in admin.get(base).get_json() if r["kind"] == "all")
    assert admin.patch(f"{base}/{all_channel['id']}",
                       json={"name": "renamed"}).status_code == 400
    assert admin.delete(
        f"{base}/{all_channel['id']}/participants/{fx.engineer_a.id}"
    ).status_code == 400


def test_dm_rejects_rename_and_participant_changes(app, fx, client, database, login):
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    assert agent.patch(f"{base}/{conv['id']}", json={"name": "x"}).status_code == 400
    assert agent.post(f"{base}/{conv['id']}/participants",
                      json={"userIds": [fx.housekeeper_a.id]}).status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v -k "group or all_channel_rejects or dm_rejects"`
Expected: FAIL (404 — routes not defined)

- [ ] **Step 3: Add group-management functions to the domain module**

Append to `server/app/domain/staff_messages.py`:

```python
from app.schemas.staff_messages import AddParticipantsRequest, GroupPatch  # add to existing import


def _assert_group(conv: StaffConversation) -> None:
    if conv.kind != StaffConversationKind.group:
        raise ValidationFailed("Only group conversations can be edited this way")


def update_group(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                 data: GroupPatch) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    if data.name is not None:
        conv.name = data.name.strip()
    if data.avatar_url is not None:
        conv.avatar_url = data.avatar_url
    db.flush()
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv


def add_participants(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                     data: AddParticipantsRequest) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    for uid in data.user_ids:
        _assert_member(db, property_id, uid)
        ensure_participant(db, conv.id, uid)
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv


def remove_participant(db: Session, property_id: str, conversation_id: str, actor_user_id: str,
                       target_user_id: str) -> StaffConversation:
    conv = get_for_participant(db, property_id, conversation_id, actor_user_id)
    _assert_group(conv)
    row = db.scalar(select(StaffConversationParticipant).where(
        StaffConversationParticipant.conversation_id == conv.id,
        StaffConversationParticipant.user_id == target_user_id))
    if row is not None:
        db.delete(row)
        db.flush()
    queue_event(db, property_id, "staff_conversation.updated", {"id": conv.id})
    return conv
```

- [ ] **Step 4: Add the routes**

In `server/app/api/staff_messages.py`, extend the imports with `AddParticipantsRequest, GroupPatch`, then append:

```python
@bp.patch("/<conversation_id>")
@require_auth
@require_property
def patch_conversation(property_id: str, conversation_id: str):
    data = parse_body(GroupPatch)
    with db_session() as db:
        staff_messages.update_group(db, g.property_id, conversation_id, g.user.id, data)
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@bp.post("/<conversation_id>/participants")
@require_auth
@require_property
def add_participants(property_id: str, conversation_id: str):
    data = parse_body(AddParticipantsRequest)
    with db_session() as db:
        staff_messages.add_participants(db, g.property_id, conversation_id, g.user.id, data)
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))


@bp.delete("/<conversation_id>/participants/<user_id>")
@require_auth
@require_property
def remove_participant(property_id: str, conversation_id: str, user_id: str):
    with db_session() as db:
        staff_messages.remove_participant(db, g.property_id, conversation_id, g.user.id, user_id)
        # The remover themself may be the one leaving — detail() would then 404 for them, so
        # only re-fetch when someone else was removed.
        if user_id == g.user.id:
            return no_content()
        return ok(staff_messages.detail(db, g.property_id, conversation_id, g.user.id))
```

- [ ] **Step 5: Run tests**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v`
Expected: PASS (all tests)

- [ ] **Step 6: Run full backend suite**

Run: `cd server && python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd server
git add app/domain/staff_messages.py app/api/staff_messages.py tests/test_staff_messages_api.py
git commit -m "feat(server): group rename, add/remove participants"
```

---

## Task 6: Domain + API — photo messages

**Files:**
- Modify: `server/app/domain/staff_messages.py` (extend `send_message` caller-side validation is already there; add photo sniffing at the API layer, matching `add_work_order_photo`)
- Modify: `server/app/api/staff_messages.py` (photo upload + serve routes)
- Test: `server/tests/test_staff_messages_api.py` (append)

**Interfaces:**
- Consumes: `app.domain.work_orders.{sniff_image_type, MAX_PHOTO_BYTES}` (reused, not duplicated).

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_staff_messages_api.py`:

```python
JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 100


def test_send_photo_only_message_and_fetch_it(app, fx, client, database, login):
    from io import BytesIO
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    res = agent.post(f"{base}/{conv['id']}/messages",
                     data={"photo": (BytesIO(JPEG_BYTES), "room.jpg")},
                     content_type="multipart/form-data")
    assert res.status_code == 201
    msg = res.get_json()
    assert msg["body"] is None and msg["photoUrl"]
    eng = login("engineer@hvh.test")
    fetched = eng.get(msg["photoUrl"])
    assert fetched.status_code == 200 and fetched.data == JPEG_BYTES
    outsider = login("supervisor@hvh.test")
    assert outsider.get(msg["photoUrl"]).status_code == 404


def test_photo_rejects_bad_type_and_oversize(app, fx, client, database, login):
    from io import BytesIO
    base = f"/api/p/{fx.property_a.id}/staff-conversations"
    agent = login("agent@hvh.test")
    conv = agent.post(base, json={"kind": "dm", "userId": fx.engineer_a.id}).get_json()
    bad_type = agent.post(f"{base}/{conv['id']}/messages",
                          data={"photo": (BytesIO(b"not an image"), "x.jpg")},
                          content_type="multipart/form-data")
    assert bad_type.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v -k photo`
Expected: FAIL (`send_message` route ignores the `photo` file part entirely — body-required validation trips the "bad_type" case wrongly, and there's no photo GET route)

- [ ] **Step 3: Rewrite the send-message route to accept a photo**

In `server/app/api/staff_messages.py`, update the top imports — `Response` and `request` join the flask import, and two new lines are added:

```python
from flask import Blueprint, Response, g, request

from app.domain.work_orders import MAX_PHOTO_BYTES, sniff_image_type
from app.errors import ValidationFailed
```

(`ValidationFailed` is new to this file's imports — Tasks 3-5 raised it only from inside `app.domain.staff_messages`, never from a route directly.) Then replace the `send_message` route with:

```python
MULTIPART_OVERHEAD_BYTES = 4096  # matches work_orders.py's rationale exactly


@bp.post("/<conversation_id>/messages")
@require_auth
@require_property
def send_message(property_id: str, conversation_id: str):
    if (request.content_length or 0) > MAX_PHOTO_BYTES + MULTIPART_OVERHEAD_BYTES:
        raise ValidationFailed(f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
                               details={"photo": "file_too_large"})
    data = parse_body(SendStaffMessageRequest)
    upload = request.files.get("photo")
    photo_bytes = None
    content_type = None
    if upload is not None:
        photo_bytes = upload.read(MAX_PHOTO_BYTES + 1)
        if len(photo_bytes) > MAX_PHOTO_BYTES:
            raise ValidationFailed(f"A photo must be {MAX_PHOTO_BYTES // (1024 * 1024)} MB or smaller",
                                   details={"photo": "file_too_large"})
        content_type = sniff_image_type(photo_bytes)
        if content_type is None:
            raise ValidationFailed("A photo must be a JPEG, PNG or WebP image",
                                   details={"photo": "unsupported_image_type"})
    with db_session() as db:
        msg = staff_messages.send_message(db, g.property_id, conversation_id, g.user.id,
                                          body=data.body, photo_content_type=content_type,
                                          photo_byte_size=len(photo_bytes) if photo_bytes else None,
                                          photo_data=photo_bytes)
        author = g.user
        return ok(StaffMessageOut(
            id=msg.id, conversation_id=msg.conversation_id, author_user_id=msg.author_user_id,
            author_name=f"{author.first_name} {author.last_name}", body=msg.body,
            photo_url=(staff_messages.photo_url(g.property_id, conversation_id, msg.id)
                      if content_type else None),
            created_at=msg.created_at), 201)


@bp.get("/<conversation_id>/messages/<message_id>/photo")
@require_auth
@require_property
def get_message_photo(property_id: str, conversation_id: str, message_id: str):
    with db_session() as db:
        staff_messages.get_for_participant(db, g.property_id, conversation_id, g.user.id)
        msg = staff_messages.get_message_photo(db, g.property_id, conversation_id, message_id)
    return Response(msg.photo_data, mimetype=msg.photo_content_type, headers={
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, max-age=86400",
    })
```

- [ ] **Step 4: Add `get_message_photo` to the domain module**

Append to `server/app/domain/staff_messages.py`:

```python
def get_message_photo(db: Session, property_id: str, conversation_id: str,
                      message_id: str) -> StaffMessage:
    msg = db.scalar(select(StaffMessage).where(
        StaffMessage.id == message_id, StaffMessage.property_id == property_id,
        StaffMessage.conversation_id == conversation_id))
    if msg is None or msg.photo_data is None:
        raise NotFound("Photo not found")
    return msg
```

- [ ] **Step 5: Run tests**

Run: `cd server && python -m pytest tests/test_staff_messages_api.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Run full backend suite**

Run: `cd server && python -m pytest -q`
Expected: PASS — this is the last backend task, so also confirm no lint regressions: `cd server && ruff check app tests`

- [ ] **Step 7: Commit**

```bash
cd server
git add app/domain/staff_messages.py app/api/staff_messages.py tests/test_staff_messages_api.py
git commit -m "feat(server): staff message photo attachments"
```

---

## Task 7: Seed data

**Files:**
- Modify: `server/seed/seed.py`

**Interfaces:**
- Consumes: `app.domain.staff_messages.{get_or_create_all_conversation, ensure_participant, send_message}`.

- [ ] **Step 1: Add the import**

In `server/seed/seed.py`, add to the existing `from app.domain...`-style imports (there isn't one yet — add a new line near the top import block): `from app.domain import staff_messages`.

- [ ] **Step 2: Add `#ALL` seeding**

`server/seed/seed.py` builds its HVH staff into a `staff` dict keyed by first name (`staff["alex"]` is the admin Alex Admin, `staff["morgan"]` the manager, `staff["sam"]` and `staff["hk_sup"]` the two supervisors, `staff["eli"]`/`staff["noah"]` engineering dept_staff, `staff["hana"]`/`staff["rosa"]` housekeeping dept_staff, `staff["ava"]`/`staff["marcus"]`/`staff["jordan"]` front-desk agents — all confirmed by reading the file). Right after the block that derives `stay_count`/`is_return_guest` (ends with the `db.flush()` immediately following the `for guest_stays in by_guest.values():` loop) and before the `# ---- content` comment, insert:

```python
        # ---- staff messaging: everyone joins #ALL, admin posts a welcome message so the
        # screen isn't empty on first login (design.md §11.2 — seed data should produce
        # realistic density, not an empty state).
        all_channel = staff_messages.get_or_create_all_conversation(db, hvh.id)
        for key in ("ava", "marcus", "jordan", "hana", "rosa", "eli", "noah", "hk_sup", "sam",
                   "morgan", "alex", "casey"):
            staff_messages.ensure_participant(db, all_channel.id, staff[key].id)
        staff_messages.send_message(db, hvh.id, all_channel.id, staff["alex"].id,
                                    body="Welcome to Relay Messages — this channel reaches "
                                        "every member of the team.")
```

- [ ] **Step 3: Run the seed script**

Run: `cd server && python -m seed.seed`
Expected: prints a summary; exits 0.

- [ ] **Step 4: Run the seed test**

Run: `cd server && python -m pytest tests/test_seed.py -v`
Expected: PASS (open the file first — if it asserts specific counts from `SeedSummary`, this step should not need new assertions since `SeedSummary` isn't changed; only add one if the existing test iterates over "everything seeded" in a way that would now miss staff conversations).

- [ ] **Step 5: Commit**

```bash
cd server
git add seed/seed.py
git commit -m "feat(server): seed the #ALL staff channel"
```

---

## Task 8: Frontend — generated types

**Files:**
- Modify: `web/src/api/types.ts` (export new type names)
- Verify only (no edits): `web/src/api/types.generated.ts`, `web/src/api/schema.json` (already regenerated in Task 2, Step 5)

**Interfaces:**
- Produces: `StaffConversationKind`, `CreateStaffConversationRequest`, `GroupPatch`, `AddParticipantsRequest`, `SendStaffMessageRequest`, `StaffParticipantOut`, `StaffConversationOut`, `StaffConversationDetail`, `StaffMessageOut`, `StaffDirectoryEntryOut` — importable from `web/src/api/types`, consumed by Task 9's hooks.

- [ ] **Step 1: Regenerate `types.generated.ts`**

Run: `cd web && npm run gen:types`
Expected: `web/src/api/types.generated.ts` is rewritten; `git diff --stat web/src/api/types.generated.ts` shows it changed.

- [ ] **Step 2: Confirm the new type names landed**

Run: `grep -c "StaffConversationOut\|StaffMessageOut\|StaffDirectoryEntryOut" web/src/api/types.generated.ts`
Expected: a nonzero count.

- [ ] **Step 3: Re-export from `types.ts`**

Open `web/src/api/types.ts` and add the new names into the existing single `export type { ... } from './types.generated'` block, keeping it alphabetically sorted the way the file already is. Insert:

```
  AddParticipantsRequest, CreateStaffConversationRequest,
```
near the top (after `AssetType, AuthorType,`), and:
```
  StaffConversationDetail, StaffConversationKind, StaffConversationOut,
  StaffDirectoryEntryOut, StaffMessageOut, StaffParticipantOut,
```
in the `S` section (alongside `SessionOut, SimEvent, ...`), and `GroupPatch,` and `SendStaffMessageRequest,` in their alphabetical spots (`G` and `S` sections respectively).

- [ ] **Step 4: Typecheck**

Run: `cd web && npm run build`
Expected: PASS — this compiles the whole app, so it will also catch any earlier task's naming mismatch. (Nothing imports the new types yet, so this step is really confirming `types.ts` itself is syntactically valid.)

- [ ] **Step 5: Commit**

```bash
cd web
git add src/api/types.generated.ts src/api/types.ts
git commit -m "feat(web): regenerate types for staff messaging API"
```

---

## Task 9: Frontend — API hooks and query keys

**Files:**
- Modify: `web/src/api/queryKeys.ts`
- Create: `web/src/api/hooks/staffMessages.ts`
- Modify: `web/src/api/ws.ts` (`invalidationsFor`)
- Test: `web/src/api/ws.test.tsx` (extend — open first to match its existing test shape)

**Interfaces:**
- Consumes: `api`, `propertyPath` from `../client`; `qk` from `../queryKeys`; types from Task 8.
- Produces: `useStaffConversations`, `useStaffConversation`, `useStaffDirectory`, `useCreateStaffConversation`, `useSendStaffMessage`, `useMarkStaffConversationRead`, `useUpdateStaffGroup`, `useAddStaffParticipants`, `useRemoveStaffParticipant` — consumed by Tasks 11-13.

- [ ] **Step 1: Add query keys**

In `web/src/api/queryKeys.ts`, add (near the `notifications` keys, matching that grouping style):

```typescript
  staffConversationsAll: (propertyId: string) => ['staffConversations', propertyId] as const,
  staffConversation: (propertyId: string, id: string) =>
    ['staffConversation', propertyId, id] as const,
  staffDirectory: (propertyId: string) => ['staffDirectory', propertyId] as const,
```

- [ ] **Step 2: Write the hooks**

Create `web/src/api/hooks/staffMessages.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  AddParticipantsRequest,
  CreateStaffConversationRequest,
  GroupPatch,
  StaffConversationDetail,
  StaffConversationOut,
  StaffDirectoryEntryOut,
  StaffMessageOut,
} from '../types'

export function useStaffConversations() {
  const { propertyId } = useSession()
  return useQuery<StaffConversationOut[], ApiError>({
    queryKey: qk.staffConversationsAll(propertyId),
    queryFn: () => api<StaffConversationOut[]>(propertyPath(propertyId, 'staff-conversations')),
  })
}

export function useStaffConversation(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<StaffConversationDetail, ApiError>({
    queryKey: qk.staffConversation(propertyId, id ?? ''),
    queryFn: () =>
      api<StaffConversationDetail>(propertyPath(propertyId, `staff-conversations/${id}`)),
    enabled: Boolean(id),
  })
}

export function useStaffDirectory() {
  const { propertyId } = useSession()
  return useQuery<StaffDirectoryEntryOut[], ApiError>({
    queryKey: qk.staffDirectory(propertyId),
    queryFn: () => api<StaffDirectoryEntryOut[]>(propertyPath(propertyId, 'staff-directory')),
  })
}

export function useCreateStaffConversation() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, CreateStaffConversationRequest>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(propertyPath(propertyId, 'staff-conversations'), {
        method: 'POST',
        json: body,
      }),
    onSuccess: (conv) => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
      client.setQueryData(qk.staffConversation(propertyId, conv.id), conv)
    },
  })
}

export function useSendStaffMessage(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffMessageOut, ApiError, { body?: string; photo?: File }>({
    mutationFn: ({ body, photo }) => {
      const form = new FormData()
      if (body) form.set('body', body)
      if (photo) form.set('photo', photo)
      return api<StaffMessageOut>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/messages`),
        { method: 'POST', body: form },
      )
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.staffConversation(propertyId, conversationId) })
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useMarkStaffConversationRead(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<void, ApiError, void>({
    mutationFn: () =>
      api<void>(propertyPath(propertyId, `staff-conversations/${conversationId}/read`), {
        method: 'POST',
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useUpdateStaffGroup(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, GroupPatch>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(
        propertyPath(propertyId, `staff-conversations/${conversationId}`),
        { method: 'PATCH', json: body },
      ),
    onSuccess: (conv) => {
      client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
    },
  })
}

export function useAddStaffParticipants(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail, ApiError, AddParticipantsRequest>({
    mutationFn: (body) =>
      api<StaffConversationDetail>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/participants`),
        { method: 'POST', json: body },
      ),
    onSuccess: (conv) => {
      client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
    },
  })
}

export function useRemoveStaffParticipant(conversationId: string) {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<StaffConversationDetail | void, ApiError, { userId: string }>({
    mutationFn: ({ userId }) =>
      api<StaffConversationDetail | void>(
        propertyPath(propertyId, `staff-conversations/${conversationId}/participants/${userId}`),
        { method: 'DELETE' },
      ),
    onSuccess: (conv) => {
      void client.invalidateQueries({ queryKey: qk.staffConversationsAll(propertyId) })
      if (conv) client.setQueryData(qk.staffConversation(propertyId, conversationId), conv)
    },
  })
}
```

- [ ] **Step 3: Wire realtime invalidation**

Open `web/src/api/ws.test.tsx` first to see how `invalidationsFor` is tested (it likely feeds a fake `ServerEvent` and asserts the returned key list). Add two cases matching that same style for `staff_conversation.created`/`staff_conversation.updated`/`staff_message.created`.

Then, in `web/src/api/ws.ts`, extend the `switch (event.type)` in `invalidationsFor` with:

```typescript
    case 'staff_conversation.created':
    case 'staff_conversation.updated':
      keys.push([...qk.staffConversationsAll(propertyId)])
      if (id) keys.push([...qk.staffConversation(propertyId, id)])
      break
    case 'staff_message.created':
      if (conversationId) keys.push([...qk.staffConversation(propertyId, conversationId)])
      keys.push([...qk.staffConversationsAll(propertyId)])
      break
```

- [ ] **Step 4: Run frontend tests**

Run: `cd web && npm run test`
Expected: PASS

- [ ] **Step 5: Typecheck/build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd web
git add src/api/queryKeys.ts src/api/hooks/staffMessages.ts src/api/ws.ts src/api/ws.test.tsx
git commit -m "feat(web): staff messaging API hooks and realtime invalidation"
```

---

## Task 10: Frontend — nav entry and routes

**Files:**
- Modify: `web/src/components/navModel.ts`
- Modify: `web/src/routes.tsx`
- Create: `web/src/features/messages/MessagesPage.tsx` (placeholder shell — filled out in Task 11)

**Interfaces:**
- Produces: route `/app/messages` and `/app/messages/:id`, both rendering `MessagesPage`; a "Messages" nav entry visible to every role.

- [ ] **Step 1: Add the nav entry**

In `web/src/components/navModel.ts`, add a new item to the `Overview` group, right after `Alerts` (matching its `needs: []` — visible to every role, same as Alerts):

```typescript
      { label: 'Messages', to: '/app/messages', icon: 'inbox', needs: [] },
```

(Reusing the `inbox` icon is deliberate — check `web/src/components/NavIcon.tsx` first; if a closer-fitting icon name already exists there — e.g. something chat-shaped — use that name instead of `inbox`.)

- [ ] **Step 2: Create a minimal page so routing compiles**

Create `web/src/features/messages/MessagesPage.tsx`:

```tsx
export function MessagesPage() {
  return <div className="p-4 text-sm text-text3">Loading…</div>
}
```

(Task 11 replaces this body with the real three-pane layout.)

- [ ] **Step 3: Wire the routes**

In `web/src/routes.tsx`, add the import `import { MessagesPage } from './features/messages/MessagesPage'` and, inside the `<Route element={<AppLayout />}>` block (right after the `notifications` route), add:

```tsx
          <Route path="messages" element={<MessagesPage />} />
          <Route path="messages/:id" element={<MessagesPage />} />
```

- [ ] **Step 4: Build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd web
git add src/components/navModel.ts src/routes.tsx src/features/messages/MessagesPage.tsx
git commit -m "feat(web): route and nav entry for staff messaging"
```

---

## Task 11: Frontend — conversation list and new-conversation list

**Files:**
- Create: `web/src/features/messages/ConversationList.tsx`
- Create: `web/src/features/messages/ConversationList.test.tsx`
- Create: `web/src/features/messages/NewConversationList.tsx`

**Interfaces:**
- Consumes: `useStaffConversations`, `useStaffDirectory` (Task 9); `Avatar`, `Badge`, `EmptyState`, `Spinner` from `../../components/ui`.
- Produces: `ConversationList` (props: `{ selectedId?: string; onSelect: (id: string) => void; onStartDm: (userId: string) => void }`), `NewConversationList` (props: `{ excludeUserIds: string[]; onStart: (userId: string) => void }`) — consumed by Task 13's `MessagesPage`.

- [ ] **Step 1: Write a failing component test**

Create `web/src/features/messages/ConversationList.test.tsx`. Open `web/src/features/board/TransitionButtons.test.tsx` or `web/src/features/inbox/FilterTabs.test.tsx` first to copy this project's exact render/query-client-wrapper test setup (which provider wrapper, which testing-library imports), then write:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ConversationList } from './ConversationList'
// (import whatever query-client + session-provider test wrapper the copied file uses)

vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversations: () => ({
    data: [
      { id: 'c1', kind: 'dm', displayName: 'Eli Engineer', avatarUrl: null, otherUserId: 'u2',
        lastMessagePreview: 'AC is out', unread: true, participants: [],
        lastMessageAt: '2026-09-19T12:00:00Z', createdAt: '2026-09-19T11:00:00Z',
        updatedAt: '2026-09-19T12:00:00Z', name: null },
    ],
    isPending: false,
    error: null,
  }),
}))

describe('ConversationList', () => {
  it('shows an unread indicator for an unread conversation', () => {
    render(<ConversationList onSelect={() => {}} onStartDm={() => {}} />)
    expect(screen.getByText('Eli Engineer')).toBeInTheDocument()
    expect(screen.getByText('AC is out')).toBeInTheDocument()
    expect(screen.getByTestId('unread-dot')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- ConversationList`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Write `ConversationList`**

Create `web/src/features/messages/ConversationList.tsx`:

```tsx
import { useStaffConversations } from '../../api/hooks/staffMessages'
import { Avatar, EmptyState, Spinner } from '../../components/ui'
import { cn } from '../../lib/cn'

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'a few seconds ago'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}

export function ConversationList({
  selectedId,
  onSelect,
}: {
  selectedId?: string
  onSelect: (id: string) => void
  onStartDm: (userId: string) => void
}) {
  const { data, isPending, error } = useStaffConversations()

  if (isPending) {
    return (
      <div className="grid place-items-center p-8">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load conversations" hint={error.message} />
  if (!data || data.length === 0) {
    return <EmptyState title="No conversations yet" hint="Start one from the list below." />
  }

  return (
    <ul className="flex flex-col">
      {data.map((conv) => (
        <li key={conv.id}>
          <button
            type="button"
            onClick={() => onSelect(conv.id)}
            aria-current={conv.id === selectedId ? 'true' : undefined}
            className={cn(
              'flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left',
              conv.id === selectedId ? 'bg-sel' : 'hover:bg-surface2',
            )}
          >
            <Avatar name={conv.displayName} tone={conv.kind === 'all' ? 'accent' : 'muted'} />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="truncate text-sm font-semibold">{conv.displayName}</span>
                {conv.lastMessageAt ? (
                  <span className="flex-none text-[11px] text-text3">
                    {relativeTime(conv.lastMessageAt)}
                  </span>
                ) : null}
              </span>
              <span className="block truncate text-[13px] text-text3">
                {conv.lastMessagePreview ?? 'No message sent'}
              </span>
            </span>
            {conv.unread ? (
              <span
                data-testid="unread-dot"
                aria-label="Unread"
                className="h-2 w-2 flex-none rounded-full bg-accent"
              />
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npm run test -- ConversationList`
Expected: PASS

- [ ] **Step 5: Write `NewConversationList`**

Create `web/src/features/messages/NewConversationList.tsx`:

```tsx
import { useStaffDirectory } from '../../api/hooks/staffMessages'
import { Avatar, EmptyState, Spinner } from '../../components/ui'

const ROLE_LABEL: Record<string, string> = {
  agent: 'Front Desk User',
  dept_staff: 'Staff',
  supervisor: 'Supervisor',
  manager: 'Manager',
  admin: 'Admin',
  corporate: 'Corporate',
}

export function NewConversationList({
  excludeUserIds,
  onStart,
}: {
  excludeUserIds: string[]
  onStart: (userId: string) => void
}) {
  const { data, isPending, error } = useStaffDirectory()

  if (isPending) {
    return (
      <div className="grid place-items-center p-6">
        <Spinner />
      </div>
    )
  }
  if (error) return <EmptyState title="Could not load staff" hint={error.message} />

  const exclude = new Set(excludeUserIds)
  const rows = (data ?? []).filter((entry) => !exclude.has(entry.userId))
  if (rows.length === 0) return null

  return (
    <ul className="flex flex-col">
      {rows.map((entry) => (
        <li key={entry.userId}>
          <button
            type="button"
            onClick={() => onStart(entry.userId)}
            title={`Click to start messaging ${entry.firstName} ${entry.lastName}`}
            className="flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left hover:bg-surface2"
          >
            <Avatar name={`${entry.firstName} ${entry.lastName}`} tone="muted" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold">
                {entry.firstName} {entry.lastName}
              </span>
              <span className="block truncate text-[12px] text-text3">
                {entry.departmentName ?? ROLE_LABEL[entry.role] ?? entry.role}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}
```

- [ ] **Step 6: Build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd web
git add src/features/messages/ConversationList.tsx src/features/messages/ConversationList.test.tsx src/features/messages/NewConversationList.tsx
git commit -m "feat(web): staff conversation list and directory picker"
```

---

## Task 12: Frontend — thread view (messages + composer)

**Files:**
- Create: `web/src/features/messages/ThreadView.tsx`
- Create: `web/src/features/messages/ThreadView.test.tsx`

**Interfaces:**
- Consumes: `useStaffConversation`, `useSendStaffMessage`, `useMarkStaffConversationRead` (Task 9); `Avatar`, `Button`, `EmptyState`, `Spinner` from `../../components/ui`; `formatClock` from `../../lib/time` (used by `PhotoPanel.tsx` — reuse it).
- Produces: `ThreadView` (props: `{ conversationId: string; onManageGroup?: () => void }`) — consumed by Task 13.

- [ ] **Step 1: Write a failing test**

Create `web/src/features/messages/ThreadView.test.tsx`, again copying the wrapper setup from an existing test (e.g. `web/src/features/inbox/MessageBubble.test.tsx`, opened first):

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ThreadView } from './ThreadView'

const mockSend = vi.fn()
vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversation: () => ({
    data: {
      id: 'c1', kind: 'dm', displayName: 'Eli Engineer', avatarUrl: null, otherUserId: 'u2',
      participants: [], lastMessageAt: null, lastMessagePreview: null, unread: false,
      createdAt: '2026-09-19T11:00:00Z', updatedAt: '2026-09-19T11:00:00Z', name: null,
      messages: [
        { id: 'm1', conversationId: 'c1', authorUserId: 'u2', authorName: 'Eli Engineer',
          body: 'On it', photoUrl: null, createdAt: '2026-09-19T12:00:00Z' },
      ],
    },
    isPending: false,
    error: null,
  }),
  useSendStaffMessage: () => ({ mutate: mockSend, isPending: false }),
  useMarkStaffConversationRead: () => ({ mutate: vi.fn() }),
}))

describe('ThreadView', () => {
  it('renders messages and sends on submit', () => {
    render(<ThreadView conversationId="c1" />)
    expect(screen.getByText('On it')).toBeInTheDocument()
    screen.getByPlaceholderText('Type your message').focus()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- ThreadView`
Expected: FAIL (module doesn't exist)

- [ ] **Step 3: Write `ThreadView`**

Create `web/src/features/messages/ThreadView.tsx`:

```tsx
import { useEffect, useRef, useState } from 'react'
import {
  useMarkStaffConversationRead,
  useSendStaffMessage,
  useStaffConversation,
} from '../../api/hooks/staffMessages'
import { Avatar, Button, EmptyState, Spinner } from '../../components/ui'
import { formatClock } from '../../lib/time'

const MAX_BYTES = 8 * 1024 * 1024 // server's staff_messages MAX_PHOTO_BYTES (work_orders.MAX_PHOTO_BYTES)
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']

export function ThreadView({
  conversationId,
  onManageGroup,
}: {
  conversationId: string
  onManageGroup?: () => void
}) {
  const { data, isPending, error } = useStaffConversation(conversationId)
  const send = useSendStaffMessage(conversationId)
  const markRead = useMarkStaffConversationRead(conversationId)
  const [draft, setDraft] = useState('')
  const [clientError, setClientError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    markRead.mutate()
    // Only when the conversation identity changes — marking read on every unrelated
    // re-render would spam the endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner />
      </div>
    )
  }
  if (error || !data) return <EmptyState title="Could not load this conversation" hint={error?.message} />

  function submitText(event: React.FormEvent) {
    event.preventDefault()
    const body = draft.trim()
    if (!body) return
    send.mutate({ body }, { onSuccess: () => setDraft('') })
  }

  function onFile(file: File | undefined) {
    if (!file) return
    if (!ACCEPTED.includes(file.type)) {
      setClientError('Only JPEG, PNG or WebP photos are accepted.')
      return
    }
    if (file.size > MAX_BYTES) {
      setClientError('That photo is over 8 MB. Choose a smaller one.')
      return
    }
    setClientError(null)
    send.mutate({ photo: file }, { onSuccess: () => {
      if (fileInput.current) fileInput.current.value = ''
    } })
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Avatar name={data.displayName} tone={data.kind === 'all' ? 'accent' : 'muted'} />
        <h2 className="text-sm font-bold">{data.displayName}</h2>
        {data.kind === 'group' && onManageGroup ? (
          <Button className="ml-auto" onClick={onManageGroup}>
            Group
          </Button>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4">
        {data.messages.length === 0 ? (
          <p className="m-auto text-xs text-text3">This is beginning of your conversation.</p>
        ) : (
          data.messages.map((message) => (
            <div key={message.id} className="max-w-[70%]">
              <p className="text-[11px] text-text3">
                {message.authorName} · {formatClock(message.createdAt)}
              </p>
              {message.body ? <p className="text-sm">{message.body}</p> : null}
              {message.photoUrl ? (
                <img src={message.photoUrl} alt="Attached" className="mt-1 max-h-60 rounded" />
              ) : null}
            </div>
          ))
        )}
      </div>

      {clientError ? (
        <p role="alert" className="mx-4 mb-2 rounded border border-danger bg-dangerBg px-3 py-2 text-xs text-dangerText">
          {clientError}
        </p>
      ) : null}

      <form onSubmit={submitText} className="flex items-center gap-2 border-t border-border p-3">
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED.join(',')}
          aria-label="Attach photo"
          onChange={(event) => onFile(event.target.files?.[0])}
          className="hidden"
          id="staff-message-photo"
        />
        <label htmlFor="staff-message-photo" className="cursor-pointer text-text3 hover:text-text">
          📷
        </label>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Type your message"
          disabled={send.isPending}
          className="h-10 flex-1 rounded border border-border3 bg-surface2 px-3 text-sm focus:border-accent focus:outline-none"
        />
        <Button type="submit" variant="primary" disabled={send.isPending || !draft.trim()}>
          Send
        </Button>
      </form>
    </div>
  )
}
```

- [ ] **Step 4: Run test**

Run: `cd web && npm run test -- ThreadView`
Expected: PASS

- [ ] **Step 5: Build**

Run: `cd web && npm run build`
Expected: PASS (fix any prop-type or import mismatch against the real `Button`/`Avatar`/`EmptyState` signatures — open `web/src/components/ui/index.ts` if a prop name doesn't match)

- [ ] **Step 6: Commit**

```bash
cd web
git add src/features/messages/ThreadView.tsx src/features/messages/ThreadView.test.tsx
git commit -m "feat(web): staff message thread view with photo attachments"
```

---

## Task 13: Frontend — group create/edit panel

**Files:**
- Create: `web/src/features/messages/GroupPanel.tsx`
- Create: `web/src/features/messages/GroupPanel.test.tsx`

**Interfaces:**
- Consumes: `useStaffDirectory`, `useCreateStaffConversation`, `useUpdateStaffGroup`, `useAddStaffParticipants`, `useRemoveStaffParticipant` (Task 9); `Dialog`, `Input`, `Button`, `Avatar` from `../../components/ui` (open `Dialog.tsx` first to match its exact prop API — likely `{ open, onClose, title, children }`, following `ArchiveDialog.tsx`'s usage as the closest existing example).
- Produces: `GroupPanel` (props: `{ open: boolean; onClose: () => void; existing?: StaffConversationOut }` — omitting `existing` means create-mode) — consumed by Task 14.

- [ ] **Step 1: Read the existing dialog pattern**

Open `web/src/features/inbox/ArchiveDialog.tsx` and `web/src/features/inbox/ArchiveDialog.test.tsx` in full — copy their exact `Dialog` usage, form-submission pattern, and test wrapper.

- [ ] **Step 2: Write a failing test**

Create `web/src/features/messages/GroupPanel.test.tsx` following the structure of `ArchiveDialog.test.tsx`, adapted to this component:

```tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GroupPanel } from './GroupPanel'

const mockCreate = vi.fn()
vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffDirectory: () => ({
    data: [
      { userId: 'u2', firstName: 'Alice', lastName: 'Smith', avatarUrl: null,
        role: 'dept_staff', departmentId: 'd1', departmentName: 'Housekeeping' },
    ],
    isPending: false,
    error: null,
  }),
  useCreateStaffConversation: () => ({ mutate: mockCreate, isPending: false }),
  useUpdateStaffGroup: () => ({ mutate: vi.fn(), isPending: false }),
  useAddStaffParticipants: () => ({ mutate: vi.fn(), isPending: false }),
  useRemoveStaffParticipant: () => ({ mutate: vi.fn(), isPending: false }),
}))

describe('GroupPanel', () => {
  it('creates a group with a name and selected members', () => {
    render(<GroupPanel open onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText('Group Name'), { target: { value: 'Team' } })
    fireEvent.click(screen.getByText('Alice Smith'))
    fireEvent.click(screen.getByText('Create'))
    expect(mockCreate).toHaveBeenCalledWith(
      { kind: 'group', name: 'Team', userIds: ['u2'] },
      expect.anything(),
    )
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npm run test -- GroupPanel`
Expected: FAIL (module doesn't exist)

- [ ] **Step 4: Write `GroupPanel`**

Create `web/src/features/messages/GroupPanel.tsx` (adapt `Dialog`'s exact prop names to whatever Step 1 found — the sketch below assumes `{ open, onClose, title, children }`, matching `ArchiveDialog.tsx`'s pattern):

```tsx
import { useState } from 'react'
import {
  useAddStaffParticipants,
  useCreateStaffConversation,
  useRemoveStaffParticipant,
  useStaffDirectory,
  useUpdateStaffGroup,
} from '../../api/hooks/staffMessages'
import type { StaffConversationOut } from '../../api/types'
import { Avatar, Button, Dialog, Input } from '../../components/ui'
import { cn } from '../../lib/cn'

export function GroupPanel({
  open,
  onClose,
  existing,
}: {
  open: boolean
  onClose: () => void
  existing?: StaffConversationOut
}) {
  const { data: directory } = useStaffDirectory()
  const create = useCreateStaffConversation()
  const update = useUpdateStaffGroup(existing?.id ?? '')
  const add = useAddStaffParticipants(existing?.id ?? '')
  const remove = useRemoveStaffParticipant(existing?.id ?? '')

  const existingIds = new Set((existing?.participants ?? []).map((p) => p.userId))
  const [name, setName] = useState(existing?.name ?? '')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  function toggle(userId: string) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(userId)) next.delete(userId)
      else next.add(userId)
      return next
    })
  }

  function submit() {
    if (existing) {
      if (name.trim() && name.trim() !== existing.name) update.mutate({ name: name.trim() })
      if (selected.size > 0) add.mutate({ userIds: [...selected] }, { onSuccess: onClose })
      else onClose()
      return
    }
    create.mutate(
      { kind: 'group', name: name.trim(), userIds: [...selected] },
      { onSuccess: onClose },
    )
  }

  const busy = create.isPending || update.isPending || add.isPending
  const canSubmit = existing ? true : name.trim().length > 0 && selected.size > 0

  return (
    <Dialog open={open} onClose={onClose} title={existing ? 'View Group' : 'Create Group'}>
      <div className="flex flex-col gap-3 p-4">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Group Name"
          disabled={Boolean(existing)}
        />

        {existing ? (
          <div>
            <p className="mb-1 text-xs font-bold uppercase tracking-wide text-text3">
              Selected Users ({existing.participants.length})
            </p>
            <div className="flex flex-wrap gap-1.5">
              {existing.participants.map((p) => (
                <span
                  key={p.userId}
                  className="flex items-center gap-1 rounded-full border border-border3 px-2 py-0.5 text-xs"
                >
                  {p.firstName} {p.lastName}
                  <button type="button" onClick={() => remove.mutate({ userId: p.userId })}>
                    ×
                  </button>
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-wide text-text3">
            All Users ({directory?.length ?? 0})
          </p>
          <ul className="max-h-64 overflow-y-auto">
            {(directory ?? [])
              .filter((entry) => !existingIds.has(entry.userId))
              .map((entry) => (
                <li key={entry.userId}>
                  <button
                    type="button"
                    onClick={() => toggle(entry.userId)}
                    className={cn(
                      'flex w-full items-center gap-2 px-2 py-2 text-left text-sm',
                      selected.has(entry.userId) ? 'bg-sel' : 'hover:bg-surface2',
                    )}
                  >
                    <Avatar name={`${entry.firstName} ${entry.lastName}`} size={22} tone="muted" />
                    {entry.firstName} {entry.lastName}
                  </button>
                </li>
              ))}
          </ul>
        </div>

        <Button variant="primary" disabled={!canSubmit || busy} onClick={submit}>
          {existing ? 'Save' : 'Create'}
        </Button>
      </div>
    </Dialog>
  )
}
```

- [ ] **Step 5: Run test**

Run: `cd web && npm run test -- GroupPanel`
Expected: PASS (adjust the `Dialog`/`Input`/`Button` prop names to match what Step 1 actually found, if they differ from the sketch above)

- [ ] **Step 6: Build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd web
git add src/features/messages/GroupPanel.tsx src/features/messages/GroupPanel.test.tsx
git commit -m "feat(web): create and manage staff message groups"
```

---

## Task 14: Frontend — assemble `MessagesPage`

**Files:**
- Modify: `web/src/features/messages/MessagesPage.tsx`
- Create: `web/src/features/messages/MessagesPage.test.tsx`

**Interfaces:**
- Consumes: `ConversationList`, `NewConversationList`, `ThreadView`, `GroupPanel` (Tasks 11-13); `useStaffConversations`, `useCreateStaffConversation` (Task 9); `useNavigate`/`useParams` from `react-router-dom`; `Button` from `../../components/ui`.

- [ ] **Step 1: Write a failing test**

Create `web/src/features/messages/MessagesPage.test.tsx`. Mock the four child components and the hooks it directly calls, asserting: with no `:id` param, no thread renders; selecting a conversation from the list navigates to `/app/messages/:id`.

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { MessagesPage } from './MessagesPage'

vi.mock('./ConversationList', () => ({
  ConversationList: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button onClick={() => onSelect('c1')}>pick c1</button>
  ),
}))
vi.mock('./NewConversationList', () => ({ NewConversationList: () => <div>new-list</div> }))
vi.mock('./ThreadView', () => ({
  ThreadView: ({ conversationId }: { conversationId: string }) => <div>thread-{conversationId}</div>,
}))
vi.mock('./GroupPanel', () => ({ GroupPanel: () => null }))
vi.mock('../../api/hooks/staffMessages', () => ({
  useStaffConversations: () => ({ data: [], isPending: false, error: null }),
  useCreateStaffConversation: () => ({ mutate: vi.fn(), isPending: false }),
}))

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/app/messages" element={<MessagesPage />} />
        <Route path="/app/messages/:id" element={<MessagesPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('MessagesPage', () => {
  it('shows no thread until one is selected', () => {
    renderAt('/app/messages')
    expect(screen.queryByText(/thread-/)).not.toBeInTheDocument()
  })

  it('shows the thread named by the route param', () => {
    renderAt('/app/messages/c1')
    expect(screen.getByText('thread-c1')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npm run test -- MessagesPage`
Expected: FAIL (current placeholder ignores the route param)

- [ ] **Step 3: Write the real `MessagesPage`**

Replace `web/src/features/messages/MessagesPage.tsx`:

```tsx
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useCreateStaffConversation, useStaffConversations } from '../../api/hooks/staffMessages'
import { Button, EmptyState } from '../../components/ui'
import { ConversationList } from './ConversationList'
import { GroupPanel } from './GroupPanel'
import { NewConversationList } from './NewConversationList'
import { ThreadView } from './ThreadView'

export function MessagesPage() {
  const { id } = useParams<{ id?: string }>()
  const navigate = useNavigate()
  const { data: conversations } = useStaffConversations()
  const createDm = useCreateStaffConversation()
  const [creatingGroup, setCreatingGroup] = useState(false)
  const [managingGroupId, setManagingGroupId] = useState<string | null>(null)

  const dmPartnerIds = (conversations ?? [])
    .filter((conv) => conv.kind === 'dm' && conv.otherUserId)
    .map((conv) => conv.otherUserId as string)

  function startDm(userId: string) {
    createDm.mutate({ kind: 'dm', userId }, {
      onSuccess: (conv) => navigate(`/app/messages/${conv.id}`),
    })
  }

  const managingGroup = conversations?.find((c) => c.id === managingGroupId)

  return (
    <div className="grid h-full min-h-0 grid-cols-[320px_1fr] divide-x divide-border">
      <div className="flex min-h-0 flex-col overflow-y-auto">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h1 className="text-base font-bold">Messaging</h1>
          <Button onClick={() => setCreatingGroup(true)}>+ Group</Button>
        </header>
        <div>
          <p className="px-4 pt-3 text-xs font-bold uppercase tracking-wide text-text3">
            Active Conversations
          </p>
          <ConversationList
            selectedId={id}
            onSelect={(conversationId) => navigate(`/app/messages/${conversationId}`)}
            onStartDm={startDm}
          />
          <p className="px-4 pt-4 text-xs font-bold uppercase tracking-wide text-text3">
            New Conversations
          </p>
          <NewConversationList excludeUserIds={dmPartnerIds} onStart={startDm} />
        </div>
      </div>

      <div className="min-h-0">
        {id ? (
          <ThreadView
            conversationId={id}
            onManageGroup={() => setManagingGroupId(id)}
          />
        ) : (
          <EmptyState title="Select a conversation" hint="Pick someone from the list, or start a new one." />
        )}
      </div>

      <GroupPanel open={creatingGroup} onClose={() => setCreatingGroup(false)} />
      {managingGroup ? (
        <GroupPanel
          open
          onClose={() => setManagingGroupId(null)}
          existing={managingGroup}
        />
      ) : null}
    </div>
  )
}
```

- [ ] **Step 4: Run test**

Run: `cd web && npm run test -- MessagesPage`
Expected: PASS

- [ ] **Step 5: Build**

Run: `cd web && npm run build`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd web
git add src/features/messages/MessagesPage.tsx src/features/messages/MessagesPage.test.tsx
git commit -m "feat(web): assemble the staff messaging page"
```

---

## Task 15: Full-stack verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full backend suite**

Run: `cd server && python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 2: Run the full frontend suite**

Run: `cd web && npm run test`
Expected: PASS, no regressions.

- [ ] **Step 3: Run the frontend build**

Run: `cd web && npm run build`
Expected: PASS.

- [ ] **Step 4: Manual smoke test with the `run` skill**

Invoke the `run` skill to start the app (backend + frontend + seed data), then in the browser: log in as two different seeded users in two browser profiles/tabs (e.g. `agent@hvh.test` / `engineer@hvh.test`, password `Password123!`), open **Messages** in both, confirm:
  - Both see `#ALL` with the seeded welcome message.
  - Starting a DM from "New Conversations" opens a thread; sending a message from one tab shows up in the other within ~2s without a manual refresh (realtime).
  - The conversation shows an unread dot for the recipient until they open it.
  - Creating a group with 2+ members works and is visible to all of them.
  - Sending a photo works and is visible to the other participant.
  - A third user with no relation to a DM/group cannot reach it via a guessed URL (`/app/messages/<that-conversation-id>` shows the "select a conversation" empty state or a load error, not the thread).

- [ ] **Step 5: Report findings**

If any manual check in Step 4 fails, fix it in the relevant task's files (not a new ad hoc patch) and re-run that task's tests before re-verifying. Once all checks pass, this plan is complete — no commit needed for this task (verification only).
