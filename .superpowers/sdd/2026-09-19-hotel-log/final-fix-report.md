# Hotel Log — Final Fix Wave Report

Branch: `hotel-log`, base commit `aae1814`, fix commit `ca65e82`.

## Fix 1 — linked-conversation link goes to the wrong page

**File:** `web/src/features/log/LogEntryCard.tsx:70`

Changed:
```
- <Link to={`/app/messages/${entry.linkedConversationId}`} ...>
+ <Link to={`/app/inbox/${entry.linkedConversationId}`} ...>
```

**Evidence it's right:** Confirmed all three cited siblings link a guest
conversation id via `/app/inbox/`:
- `web/src/features/board/WorkOrderDetailPage.tsx:107` — `Link to={`/app/inbox/${data.sourceConversationId}`}`
- `web/src/features/inbox/ConversationList.tsx:32` — `Link to={`/app/inbox/${conversation.id}`}`
- `web/src/features/notifications/NotificationsPage.tsx:16` — `if (notification.entityType === 'conversation') return `/app/inbox/${notification.entityId}``

`LogEntry.linked_conversation_id` is a FK to `conversation.id` (guest
conversations), validated against the `Conversation` model in
`app/domain/log.py:130` — the same table these three siblings link to.
`/app/messages/:id` resolves to `MessagesPage`, which treats the param as a
`StaffConversation` id — a different table entirely. The old code would land
there with a guest conversation id and show nothing.

**Test added:** `web/src/features/log/LogEntryCard.test.tsx` — two new cases:
1. `renders the work order and conversation links with correct hrefs, and
   omits them when unset` — mounts with UUID-shaped `linkedWorkOrderId` /
   `linkedConversationId` fixtures and asserts hrefs
   `/app/work-orders/<id>` and `/app/inbox/<id>`.
2. `renders neither link when linkedWorkOrderId and linkedConversationId are
   null` — asserts neither link renders.

### Sabotage-verify cycle

1. Ran `LogEntryCard.test.tsx` with the fix in place: 11/11 passed.
2. Reverted the href back to `/app/messages/${entry.linkedConversationId}`
   (sed edit, no other changes).
3. Re-ran: the new hrefs test failed exactly as expected —
   `expected href="/app/inbox/eeee..." received href="/app/messages/eeee..."`.
   10/11 passed, 1 failed (the new test; all pre-existing tests still green).
4. Restored the fix (`/app/inbox/${entry.linkedConversationId}`).
5. Re-ran: 11/11 passed again.

This confirms the new test is the one guarding the regression, not a
tautology.

## Fix 2 — EXPECTED_TABLES missing the four log tables

**File:** `server/tests/test_models.py:14-21`

Added a new line following the existing convention of grouping tables by the
migration/feature that introduced them (mirrors the `staff_conversation`
trio's own line):
```python
"log_entry", "log_entry_mention", "log_entry_photo", "log_entry_ack",
```

**Evidence it's right:** `test_migration_creates_all_tables` runs
`run_migrations` against a fresh SQLite db and asserts `EXPECTED_TABLES <=
names`. Ran the full suite (below) — this test still passes, confirming
migration 0006 actually creates all four tables and the guard is now
meaningful (previously it silently proved nothing about them, since the
check is a subset comparison).

## Fix 3 — include_context=False hardening

**Files:** `server/app/api/_util.py` (`parse_query`), `server/app/errors.py`
(`_pydantic_error`)

Added `include_context=False` to both `.errors()` calls, with a one-line
comment pointing back at `parse_body`'s existing five-line explanation rather
than repeating it:

- `_util.py`: `# include_context=False: see parse_body's comment above.`
- `errors.py`: `# Same arguments as _util.parse_body: no pydantic.dev URL, no
  echo of the caller's raw input, and include_context=False per parse_body's
  comment above.` (extended the existing "Same two arguments" comment since
  it now covers three arguments).

**No test added**, as instructed — both sites are unreachable today (the
only custom validator in the schemas package goes through `parse_body`, per
the task description), and a regression test would require inventing a
validator that doesn't exist. Confirmed via `ruff` and the full pytest run
that nothing broke.

## Test / lint / build results

- `cd server && ../.venv/Scripts/python.exe -m pytest -q` → **429 passed**
  (matches baseline; no new server tests were requested/added).
- `cd server && ../.venv/Scripts/python.exe -m ruff check .` → **All checks
  passed.**
- `cd web && npm test` → **645 passed** (baseline 643 + 2 new
  `LogEntryCard` tests).
- `cd web && npm run lint` → clean, no output/errors.
- `cd web && npm run build` → `tsc -b && vite build` succeeded, produced
  `dist/` bundle (379.38 kB / 111.91 kB gzip).

## Diff scope

Committed files only:
- `server/app/api/_util.py`
- `server/app/errors.py`
- `server/tests/test_models.py`
- `web/src/features/log/LogEntryCard.tsx`
- `web/src/features/log/LogEntryCard.test.tsx`

Excluded per instructions: `server/data/app.db*` (untouched by these fixes,
not staged/committed), `server/app/domain/users.py` (CRLF artifact, left
alone), `two.png` deletion and `.claude/` (pre-existing working-tree state,
unrelated to this task, left untouched).

Commit: `ca65e82` — "fix(web,server): correct log-entry conversation link and
harden validation error paths"

## Things noticed but out of scope (not touched)

- `server/app/domain/users.py` shows as modified in `git status` with an
  apparently empty diff — consistent with the CRLF-artifact note in the task;
  left untouched as instructed.
- `server/data/app.db`, `app.db-shm`, `app.db-wal` are modified (presumably
  from running the test suite / dev server locally) — not committed, per
  instructions.
- The pre-existing `_util.py` comment on `parse_body` says "include_context=False:
  when a validator raises a plain exception ... pydantic's `ctx` carries that
  exception object itself" — worth knowing this hardening is generic (applies
  to any raised exception in a `mode="before"`/`mode="after"` validator, not
  just the one CreateLogEntryRequest case mentioned), so the same fix pattern
  should be applied by default anywhere `.errors()` is called on a
  `ValidationError` in future code.

## Concerns

None. All three fixes are small, isolated, and verified. The sabotage-verify
cycle for Fix 1 confirms the new test actually catches the bug it was written
for.
