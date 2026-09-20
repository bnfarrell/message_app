# CLAUDE.md

## Project

Unified hotel guest engagement & operations platform. Full spec: `docs/design.md`.
Phase 1 scope, stack decisions and acceptance criteria: `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md`.
Implementation plan: `docs/superpowers/plans/2026-09-10-phase1-server.md`. Approved screens: `docs/mockups/`.

Stack: Python 3.12 · Flask 3 · SQLAlchemy 2 · Alembic · Pydantic v2 · flask-sock · pytest;
frontend Vite + React + TypeScript.

**Remote:** https://github.com/bnfarrell/message_app — push the finished work here.

---

## Environment and database — read before writing any code

### Commands

Always invoke Python by explicit path. **Bare `python` is NOT on PATH** — it resolves to a 0-byte
Windows Store alias stub that exits silently with no output, which looks like a hung command.

```
cd server && ../.venv/Scripts/python.exe -m pytest -q      # backend tests
cd server && ../.venv/Scripts/python.exe -m ruff check .   # backend lint, line-length 100
cd web && npm test && npm run lint && npm run build        # frontend, all three must be clean
```

The venv is Python 3.12, matching `Dockerfile` (`python:3.12-slim`) and ruff's
`target-version = "py312"`. If the venv ever breaks, recreate it with
`python -m venv .venv` from a real 3.12 install, then `pip install -e ".[dev]"` from `server/`.

### PostgreSQL is the real target

**Production runs PostgreSQL 18** (`ghcr.io/railwayapp-templates/postgres-ssl:18` on Railway).
Dev and the test suite still run SQLite, so **SQLite passing is not evidence that code works.**

- Write engine-portable SQL only. No `json_each`, no SQLite-only pragmas or functions.
  If you need to filter inside a JSON array, model it as a table instead — that is exactly why
  `log_entry_mention` is a table rather than the `mentions uuid[]` column `docs/design.md` §5.4
  specifies.
- Enums go through `enum_type()` in `app/models/core.py` (`native_enum=False`), which produces a
  VARCHAR + CHECK constraint that behaves the same on both engines.
- `app/config.py:normalise_database_url` rewrites a provider-style `postgresql://` to
  `postgresql+psycopg://`, because a bare URL resolves to psycopg2, which is not installed.
- Datetimes: `UTCDateTime` stores **naive UTC** and returns **aware UTC**. It raises
  `ValueError` on a naive input — get the time from `app.clock.now()`, which tests freeze.
  Convert through the property's own timezone for anything user-facing; never compare a local
  wall-clock value straight against a column.

Verify a migration against real Postgres before merging — SQLite will not catch a portability bug:

```
docker run -d --name relay-pg18 -e POSTGRES_PASSWORD=relaydev -e POSTGRES_USER=relay \
  -e POSTGRES_DB=relay_test -p 55432:5432 postgres:18
cd server && DATABASE_URL="postgresql://relay:relaydev@localhost:55432/relay_test" \
  ../.venv/Scripts/python.exe -m alembic upgrade head
```

Also run `alembic downgrade <prev>` and re-upgrade. `docker-entrypoint.sh` runs
`alembic upgrade head` on every boot **before** gunicorn, so a migration that fails takes the
whole service down at startup, not just the new feature — and a `downgrade()` that does not
truly reverse leaves no way back.

### Generated files — never hand-edit

`web/src/api/schema.json` and `web/src/api/types.generated.ts` are generated from the Pydantic
models. Committed tests fail if they go stale. After changing any schema:

```
cd server && ../.venv/Scripts/python.exe -m app.schemas.export_json_schema
cd web && npm run gen:types
```

When adding API models, also add them to the tuple in
`test_schema_export.py::test_export_contains_the_public_models`, and add new tables to
`EXPECTED_TABLES` in `test_models.py` — each slice so far has had to, and forgetting leaves the
new things unguarded.

### Two invariants the test suite enforces

- **Property isolation.** `tests/test_isolation.py` enumerates every route under
  `/api/p/<property_id>` and asserts a non-member gets 403 **and that an admin of the property
  never does**. A capability that excludes `Role.admin` will break it as soon as a route uses it.
- **Capability tables must not drift.** `server/app/auth/permissions.py` is authoritative;
  `web/src/auth/capabilities.ts` mirrors it. Change both in the same commit.

### Other conventions

- `server/data/app.db` is tracked in git **deliberately** — it is fixture data (see `.gitignore`).
  Do not commit incidental dev churn to it; do commit it when seed data genuinely changes.
- API models subclass `CamelModel`: camelCase on the wire, snake_case in Python.

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
