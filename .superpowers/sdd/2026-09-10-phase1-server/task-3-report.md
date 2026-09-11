# Task 3 Report: Test infrastructure — app fixture, template DB, fixture data, login helper

## What I implemented

Created exactly the three files the brief specifies, using its code verbatim:

- `server/tests/test_fixtures.py` — three tests: fixture-loads-counts, clock-is-frozen, fresh-database-per-test.
- `server/tests/fixtures.py` — `Fixture` dataclass, `_hash` (bcrypt, cost 12→rounds=4 for test speed, per the brief/task note since `app.auth.passwords.hash_password` doesn't exist until Task 4), `_user`/`_member` helpers, `load_fixture(db)` building 2 properties, 4 departments, 11 user accounts, 11 property memberships, 3 guests, 2 stays.
- `server/tests/conftest.py` — session-scoped `template_db_path` (migrated once via `run_migrations`), function-scoped `app` (copies the template DB file per test via `shutil.copy`, freezes the clock at `2026-09-10T12:00:00Z`, builds a `Config` with a fresh sqlite path, disposes the engine and resets the clock on teardown), plus `database`, `client`, `fx`, and `login` fixtures.

I verified every model field name/signature used in `fixtures.py` (`Property`, `UserAccount`, `Department`, `PropertyMembership`, `Guest`, `Stay`) against `server/app/models/core.py` and `server/app/models/guests.py` before running anything — all match.

## TDD evidence

**RED** — before `fixtures.py`/`conftest.py` existed:

```
cd server && python -m pytest tests/test_fixtures.py -q
```
```
EEE                                                                      [100%]
=================================== ERRORS ====================================
________ ERROR at setup of test_fixture_loads_two_properties_and_users ________
E       fixture 'app' not found
...
3 errors in 0.37s
```
Expected: since neither `fixtures.py` nor `conftest.py` existed yet, no fixtures at all were registered, so pytest reports the fixture closest to the test signature (`app`) as missing rather than `fx` (which the brief's Step 2 describes for the case where `conftest.py` already exists but `fixtures.py` doesn't). This is the correct RED for this task's actual step ordering (test file written first, before either support file) — it confirms the test can't pass without the infrastructure.

**GREEN** — after writing `fixtures.py` and `conftest.py`:

```
cd server && python -m pytest tests/test_fixtures.py -q
```
```
...                                                                      [100%]
3 passed in 0.38s
```

**Full suite:**

```
cd server && python -m pytest -q
```
```
............                                                             [100%]
12 passed in 1.22s
```
Ran twice more back-to-back for stability: 1.18s and 1.25s. 9 pre-existing + 3 new = 12 passed, 0 warnings, 0 errors. The template-DB-copy strategy (migrate once per session, `shutil.copy` per test) keeps per-test setup to a few ms — the whole 12-test suite runs in ~1.2s total.

## Files changed

- Created: `server/tests/test_fixtures.py`
- Created: `server/tests/fixtures.py`
- Created: `server/tests/conftest.py`

## Self-review

- **Completeness:** All three files match the brief's code verbatim, byte-for-byte (confirmed via `git show` after commit). `Fixture` has all 19 required fields; `load_fixture` produces exactly 11 user accounts (10 named + 1 `shared` regional manager not exposed as a Fixture field, matching the brief), 11 memberships, 3 guests, 2 stays, 2 properties, 4 departments.
- **Quality:** No deviations from the brief. Field names for `Property`, `UserAccount`, `Department`, `PropertyMembership`, `Guest`, `Stay` all verified against the actual model definitions in `app/models/core.py` and `app/models/guests.py` before running — no mismatches found.
- **Discipline (YAGNI):** Implemented only what the brief specifies; no auth route was stubbed (the `login` fixture is defined but unused by any test in this task, as instructed). No extra fixtures, no refactoring of adjacent files.
- **Testing:** `test_each_test_gets_a_fresh_database` inserts a scratch `Property` row with no matching assertion in that test — its only job is to prove that if per-test DB isolation were broken, the row would leak into `test_fixture_loads_two_properties_and_users`'s count assertions in a subsequent run. Ran the full suite twice in a row (fresh `tmp_path` each time) and got 12 passed both times with stable counts, confirming isolation actually holds (function-scoped `tmp_path`/`app` fixtures copy a fresh DB file per test, so no leakage is structurally possible, not just accidentally absent).
- **Output pristine:** 0 warnings, 0 errors across three consecutive full-suite runs.

## Concerns

- `ruff check` flags 5 pre-existing-style issues in the new files (one `UP017` datetime.UTC-alias suggestion in `conftest.py`, four `E501` line-length overruns in `fixtures.py`, all from the brief's verbatim code, e.g. the `Property`/`Stay` construction lines running to 101–102 chars against the 100-char limit in `pyproject.toml`). I did not touch these, since the brief instructs using this code verbatim and Task 3's job is TDD to green, not lint conformance. For context: running `ruff check` against the already-committed Task 1/2 code (`app/models/guests.py`, `tests/test_models.py`, etc.) turns up the same class of violations (E501, UP017) that were accepted in prior commits, so this is consistent with existing project precedent, not a new regression. Flagging for awareness only — not a functional issue, and pytest itself is clean.

## Commit

```
b07acd5 test(server): app/database fixtures, deterministic fixture data, frozen clock
```
`git status` confirmed only `server/tests/{conftest.py,fixtures.py,test_fixtures.py}` were added; nothing else in the working tree was touched.

## Fix round 1 (review finding: `test_each_test_gets_a_fresh_database` asserted nothing)

**Finding:** the test only inserted a scratch `Property` row and relied on a comment claiming a later test's count assertion would catch a leak. That was false in this suite — it's the last test in its file, and `test_health.py`/`test_models.py` don't use the `app`/`database` fixtures at all — so a broken per-test DB copy would go completely unnoticed.

**What changed:** `server/tests/test_fixtures.py`, `test_each_test_gets_a_fresh_database` — added an entry assertion that no `Property` with code `"SCR"` exists before inserting it, then an exit assertion that it does exist afterward. The entry assertion is what actually proves isolation: if the previous test run's scratch row had survived (broken template-copy or shared engine), the entry assertion would fail regardless of run order. Replaced the misleading comment with a one-line docstring stating what the assertions prove. Test name unchanged. `select` was already imported at module level (from Step 1's `from sqlalchemy import func, select`), so the local `Property` import matches the file's existing per-test local-import style and no extra top-level import was added.

```python
def test_each_test_gets_a_fresh_database(app, database):
    """The entry assertion is the real check: a leaked row from a prior run would fail it."""
    from app.models import Property

    with database.session() as db:
        assert db.scalar(select(Property).where(Property.code == "SCR")) is None
        db.add(Property(name="Scratch", code="SCR", timezone="UTC"))
    with database.session() as db:
        assert db.scalar(select(Property).where(Property.code == "SCR")) is not None
```

**Covering tests:** `tests/test_fixtures.py::test_each_test_gets_a_fresh_database` (direct), plus the other two tests in the same file (`test_fixture_loads_two_properties_and_users`, `test_clock_is_frozen`) as regression coverage for the same file/fixtures.

**Commands and output:**

```
cd server && python -m pytest tests/test_fixtures.py -q
```
```
...                                                                      [100%]
3 passed in 0.37s
```

```
cd server && python -m pytest -q
```
```
.....................                                                    [100%]
21 passed in 1.54s
```

Note: the full-suite count went from 12 to 21 between the original submission and this fix round because Task 4 (`server/tests/test_auth.py`, 9 tests) was committed to `main` (`4c89683`) by a separate concurrent process while this fix was in progress — unrelated to this change. Confirmed via `git log --oneline -5` and `git status`; only `server/tests/test_fixtures.py` was staged and committed for this fix. A second unrelated unstaged change to `CLAUDE.md` (adding a Project/stack/remote section) was also observed in the working tree from the same concurrent activity; left untouched and not committed, as it is out of scope for this task.

**Commit:**

```
aa1e88e test(server): make the per-test database isolation test actually assert isolation
```
