## Task 4: Pydantic schemas and generated types

**Files:**
- Create: `server/app/schemas/log.py`
- Modify: `server/app/schemas/export_json_schema.py`, `web/src/api/schema.json`, `web/src/api/types.generated.ts`
- Test: `server/tests/test_schema_export.py` (existing, must stay green)

**Interfaces:**
- Produces, all importable from `app.schemas.log`: `MentionRef`, `CreateLogEntryRequest`, `LogMentionOut`, `LogAckOut`, `LogEntryOut`, `LogFeedOut`, `LogMentionableOut`, `LogFeedQuery`

- [ ] **Step 1: Write the schemas**

Create `server/app/schemas/log.py`:

```python
from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.enums import MentionTargetType, Shift

MAX_BODY = 4000
MAX_MENTIONS = 100          # a hotel-sized bound on the per-id validation SELECTs
FEED_PAGE_SIZE = 50


class MentionRef(CamelModel):
    """One @mention or one member of an acknowledgement audience."""

    type: MentionTargetType
    id: str


class CreateLogEntryRequest(CamelModel):
    """The non-file half of the body; a `photo` file part may arrive alongside it, exactly
    like SendStaffMessageRequest."""

    body: str = Field(min_length=1, max_length=MAX_BODY)
    department_id: str | None = None
    mentions: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    requires_ack: bool = False
    ack_audience: list[MentionRef] = Field(default_factory=list, max_length=MAX_MENTIONS)
    linked_work_order_id: str | None = None
    linked_conversation_id: str | None = None


class LogFeedQuery(CamelModel):
    shift: Shift | None = None
    department_id: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    mentioning_me: bool = False
    cursor: str | None = None


class LogMentionOut(CamelModel):
    type: MentionTargetType
    id: str
    display_name: str


class LogAckOut(CamelModel):
    user_id: str
    name: str
    acknowledged_at: datetime


class LogPersonOut(CamelModel):
    user_id: str
    name: str


class LogEntryOut(CamelModel):
    id: str
    created_at: datetime
    author_user_id: str
    author_name: str
    author_avatar_url: str | None = None
    department_id: str | None = None
    department_name: str | None = None
    shift: Shift
    body: str
    mentions: list[LogMentionOut] = Field(default_factory=list)
    pinned: bool
    pinned_by_user_id: str | None = None
    pinned_at: datetime | None = None
    requires_ack: bool
    ack_expected_count: int
    acks: list[LogAckOut] = Field(default_factory=list)
    outstanding: list[LogPersonOut] = Field(default_factory=list)
    acked_by_me: bool
    can_ack: bool
    photo_url: str | None = None
    linked_work_order_id: str | None = None
    linked_conversation_id: str | None = None


class LogFeedOut(CamelModel):
    pinned: list[LogEntryOut] = Field(default_factory=list)
    entries: list[LogEntryOut] = Field(default_factory=list)
    next_cursor: str | None = None


class LogMentionableOut(CamelModel):
    """One row of the composer's picker — a person or a department, one flat list."""

    type: MentionTargetType
    id: str
    display_name: str
    subtitle: str | None = None
```

- [ ] **Step 2: Register the module with the schema exporter**

In `server/app/schemas/export_json_schema.py`, add `log` to both the import block and `MODULES`:

```python
from app.schemas import (
    analytics,
    auth,
    content,
    conversations,
    dev,
    log,
    notifications,
    properties,
    staff_messages,
    users,
    work_orders,
)

MODULES = (auth, users, conversations, work_orders, content, notifications, analytics,
           properties, staff_messages, log, dev)
```

- [ ] **Step 3: Run the schema test to verify it fails**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q`
Expected: FAIL with "web/src/api/schema.json is stale"

- [ ] **Step 4: Regenerate schema.json and the TypeScript types**

```bash
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd ../web && npm run gen:types
```

The module has a `__main__` block that writes `web/src/api/schema.json` and prints the path, so that command is exactly right — no alternative invocation needed.

- [ ] **Step 4b: Extend the public-models assertion**

`server/tests/test_schema_export.py::test_export_contains_the_public_models` lists the models that must appear in `$defs`. The staff-messaging slice added its two (`StaffConversationOut`, `StaffMessageOut`); this slice must do the same, or the test silently stops guarding the new models. Add to that tuple:

```python
                 "LogEntryOut", "LogFeedOut", "LogMentionableOut",
```

- [ ] **Step 5: Verify both sides are green**

Run: `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_schema_export.py -q`
Expected: PASS

Run: `cd web && npm run build`
Expected: PASS — confirms the generated types compile.

- [ ] **Step 6: Commit**

```bash
git add server/app/schemas/log.py server/app/schemas/export_json_schema.py web/src/api/schema.json web/src/api/types.generated.ts
git commit -m "feat(server): hotel log request and response schemas"
```

---

