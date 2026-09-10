# Resume here — Phase 1 server build

**Written:** 2026-09-10, end of session 1. Read this file first, then `.superpowers/sdd/2026-09-10-phase1-server/progress.md` (the ledger).

## What this project is

Unified hotel guest engagement & operations platform — guests text the hotel, staff answer from a shared
inbox, problems become work orders, and when a work order closes the agent is prompted to tell the guest.

| Document | What it is |
|---|---|
| `docs/design.md` | The original full product spec (v1.0, all 4 phases) |
| `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md` | **Binding authority.** Phase 1 scope, stack decisions, acceptance criteria |
| `docs/superpowers/plans/2026-09-10-phase1-server.md` | **The plan being executed.** 24 tasks, each with complete code and tests |
| `docs/mockups/*.dc.html` | Approved screen designs ("Night Shift" direction). Published: https://claude.ai/code/artifact/cc54191d-cdf8-4474-b5a2-eda523b54ad8 |

Stack: Python 3.14 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · flask-sock · pytest, on SQLite
(PostgreSQL later by changing `DATABASE_URL`). Frontend (not started): Vite + React + TypeScript.

Remote to push to when done: **https://github.com/bnfarrell/message_app** (configured as `origin`; nothing pushed yet).

## Where the build stands

**Tasks 1–8 of 24 committed and green.** Suite: **64 passing, 0 warnings**
(`cd server && ../.venv/Scripts/python.exe -m pytest -q`). Working tree clean.

Reviews for Tasks 6 and 7 were run at the top of session 2 and both came back **clean**
(spec ✅, quality Approved, 0 Critical/Important). No reviews are owed.

| # | Task | State |
|---|---|---|
| 1 | Scaffold: app factory, config, clock, error shape, health route | ✅ `859b27a`, `b40401c` |
| 2 | 20 SQLAlchemy models, 17 enums, initial Alembic migration | ✅ `22aff26`, `71a9445` |
| 3 | Test fixtures, conftest, template-DB copy, login helper | ✅ `b07acd5`, `aa1e88e` |
| 4 | Auth: bcrypt, server-side sessions, decorators, capabilities, rate limiting | ✅ `4c89683` |
| 5 | Departments/users routes + **property-isolation suite** (acceptance #9) | ✅ `5fdf2b6` |
| 6 | SMS segments, card redaction, quick-reply interpolation | ✅ `0f130aa`, `21fec0c` — review clean |
| 7 | Realtime event outbox, connection registry, notifications | ✅ `9471872`, `e69ff49` — review clean |
| 8 | Job queue and worker (retry/backoff/dead-letter, in-process thread) | ✅ `9d45faf` — review in flight |
| **9** | **Channels/mock SMS, outbound + delivery-status handlers — in progress** | Dispatched |
| 10–24 | Guests+consent, conversations, work orders, content, analytics, WS/presence, PMS, dev endpoints, seed, schema export, README | Not started |

## How to resume the process

The build is running under the `superpowers:subagent-driven-development` skill:

1. Read the ledger: `.superpowers/sdd/2026-09-10-phase1-server/progress.md`. Tasks with a
   `Task N: complete` line are done — never re-dispatch them.
2. Task briefs are already extracted for all 24 tasks at
   `.superpowers/sdd/2026-09-10-phase1-server/task-N-brief.md`. Regenerate one with:
   `bash "<superpowers>/skills/subagent-driven-development/scripts/task-brief" docs/superpowers/plans/2026-09-10-phase1-server.md N`
3. Per task: record BASE (`git rev-parse HEAD`) → dispatch an implementer with the brief path →
   package the diff (`scripts/review-package PLAN BASE HEAD`) → dispatch a reviewer → fix loop if needed →
   append `Task N: complete (commits …)` to the ledger.
4. Working **in place on `main`** — the user chose this over a worktree.

### Environment notes that cost time to discover

- Run Python as `../.venv/Scripts/python.exe` from `server/`. Activating the venv inside a subagent's
  shell is unreliable; the explicit path always works.
- npm ≥ 11.19 blocks package install scripts by default (irrelevant to the Python side, matters for the web build).
- `email_validator.TEST_ENVIRONMENT = True` is set in `tests/conftest.py` because the fixtures use
  RFC 2606 `.test` emails, which the library otherwise rejects. Test-only; leave it.
- Commit trailers so far are inconsistent (Fable 5.1 / Sonnet 5 / Opus 5) — cosmetic, not worth rewriting.

## Open items to carry forward

- **Deferred to Task 24:** one ruff cleanup pass (`ruff check --fix` plus manual E501 wraps) across
  `server/`. Ruff findings in plan-verbatim code were deliberately NOT fixed per-task.
- **Deferred minors from reviews** (all in the ledger): `require_role`/`require_capability` dereference
  `g.membership` without a guard, so a route that forgets `@require_property` 500s instead of 403ing
  (the isolation suite catches such routes anyway); `_pydantic_error` may hit non-serializable values in
  a validation `ctx`; no catch-all 500 handler producing the `{"error":…}` shape.
- **The web plan does not exist yet.** `docs/superpowers/plans/` has the server plan only. After the
  server ships, write the React plan (spec §5 describes every screen, and `docs/mockups/` shows them).
- **Three acceptance criteria are not yet reachable:** #3 (presence, needs Task 19), #4's UI half and
  #7's UI half (need the web build).

## The one thing not to lose

The plan's value is that every task carries its own tests, and reviews plus implementers have caught **six
real defects in the plan text itself** so far: an `AppError` ordering bug, a deprecated Alembic key, a test
that asserted nothing, a vacuous enum test, an SMS segment boundary off by one, and a notification-ordering
test that couldn't pass under a frozen clock. Keep the review step — it is doing real work — and keep
telling implementers to report brief defects rather than paper over them. Every one of those was found
that way.
