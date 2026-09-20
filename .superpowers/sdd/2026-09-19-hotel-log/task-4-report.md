# Task 4 Report: Pydantic schemas and generated types

## What I implemented

Created `server/app/schemas/log.py` with the exact contents from the brief:
`MentionRef`, `CreateLogEntryRequest`, `LogFeedQuery`, `LogMentionOut`, `LogAckOut`,
`LogPersonOut`, `LogEntryOut`, `LogFeedOut`, `LogMentionableOut`, plus module constants
`MAX_BODY`, `MAX_MENTIONS`, `FEED_PAGE_SIZE`. No deviation from the brief's code.

Registered the module with the exporter in `server/app/schemas/export_json_schema.py`:
added `log` to the import block (alphabetical) and to `MODULES` (after `staff_messages`,
before `dev`), exactly as specified.

Extended `server/tests/test_schema_export.py::test_export_contains_the_public_models`'s
tuple with `"LogEntryOut", "LogFeedOut", "LogMentionableOut"`.

Regenerated `web/src/api/schema.json` (via `python -m app.schemas.export_json_schema`)
and `web/src/api/types.generated.ts` (via `npm run gen:types`).

## What I tested and results

- `cd server && ../.venv/Scripts/python.exe -m pytest -q` → **399 passed**, matching the
  stated baseline exactly.
- `cd server && ../.venv/Scripts/python.exe -m ruff check .` → **All checks passed!**
- `cd web && npm run build` (`tsc -b && vite build`) → **passed**, confirming the
  regenerated types compile.
- `cd web && npm test -- --run` → **601 passed** (59 files), matching the stated
  baseline, including `src/api/types.generated.test.ts`'s check that the committed
  generated file matches what the generator produces from the committed schema.

## TDD evidence (brief step 3)

**RED** — ran `pytest tests/test_schema_export.py -q` after writing `log.py` and
registering the module, but before regenerating the JSON/TS artifacts:

```
.F                                                                       [100%]
================================== FAILURES ===================================
______________________ test_committed_schema_is_current _______________________
    ...
E       AssertionError: web/src/api/schema.json is stale — re-run python -m app.schemas.export_json_schema
1 failed, 1 passed in 0.50s
```//
(`test_export_contains_the_public_models` still passed at this point because step 4b
hadn't been applied yet — the new assertions weren't added until after RED was captured.)

**GREEN** — after running the two regeneration commands and applying step 4b:

```
..                                                                       [100%]
2 passed in 0.31s
```

## Finding on `LogFeedQuery` and `from_`/alias

Verified directly with a standalone script simulating query-string parsing:

```python
from app.schemas.log import LogFeedQuery
from urllib.parse import parse_qs
data = {k: v[0] for k, v in parse_qs('from=2026-09-01').items()}   # {'from': '2026-09-01'}
m = LogFeedQuery.model_validate(data)
# m.from_ == '2026-09-01'
# m.model_dump(by_alias=True) == {'shift': None, 'departmentId': None, 'from': '2026-09-01',
#                                  'to': None, 'mentioningMe': False, 'cursor': None}
```

**It works as designed.** In Pydantic v2, an explicit `Field(alias=...)` on a field takes
precedence over the model's `alias_generator` (`to_camel`) for that field — the
alias_generator only fills in aliases for fields that don't already have one. So `from_`
keeps its literal `"from"` alias (not camelCased, which would be a no-op here anyway since
`from` has no underscores) while every other field is still camelCased normally. Combined
with `populate_by_name=True` on `CamelModel`, the model accepts input keyed by either
`from` (the wire alias) or `from_` (the Python name). Parsing `from=2026-09-01` succeeds
and round-trips correctly. No design change was needed.

## Files changed

- `server/app/schemas/log.py` (new, 96 lines, matches brief verbatim)
- `server/app/schemas/export_json_schema.py` (added `log` import + `MODULES` entry)
- `server/tests/test_schema_export.py` (added 3 model names to public-models tuple)
- `web/src/api/schema.json` (regenerated — +499/-0 net, i.e. new Log* defs added, no
  hand edits)
- `web/src/api/types.generated.ts` (regenerated via `npm run gen:types` — no hand edits)

Commit: `28da793` — "feat(server): hotel log request and response schemas"

Note: `server/data/app.db`, `app.db-shm`, `app.db-wal` were modified in the working tree
(pre-existing, from earlier task work / test runs) but were deliberately NOT staged or
committed, per the global constraint. `docs/superpowers/plans/2026-09-19-hotel-log.md`,
deleted `two.png`, and untracked `.claude/`/`images/` are pre-existing working-tree state
unrelated to this task and were left untouched.

## Self-review findings

- `log.py` byte-for-byte matches the brief's code block (diffed against the brief text).
- `export_json_schema.py` change is exactly the two-line addition specified — no other
  edits to that file.
- `test_schema_export.py` change is exactly the tuple extension specified.
- The two generated files were produced only by running the documented regeneration
  commands (`python -m app.schemas.export_json_schema` then `npm run gen:types`) — I did
  not hand-edit either. Confirmed via `git diff --stat` scoping and by re-running the
  frontend's own `types.generated.test.ts`, which independently re-derives the file from
  the committed schema and asserts equality (it passed, 601/601 total).
- No speculative additions: no extra fields, no extra models, no changes to unrelated
  schema modules. `git status --short` before commit showed only the five intended paths
  staged; everything else in the working tree was left alone.
- Backend and frontend baselines (399 passed / 601 passed, ruff clean, build clean) all
  hold exactly, with no regressions and no new failures.

## Concerns

None. The `from_`/alias interaction works as the brief anticipated; no design change was
required.
