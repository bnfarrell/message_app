# Task 6 report: The feed query

## What I implemented

Appended the read side of the hotel log to `server/app/domain/log.py`, exactly as specified in
the brief:

- `photo_url(property_id, entry_id) -> str`
- `_encode_cursor` / `_decode_cursor` — `"<isoformat created_at>|<id>"` cursor encoding
- `_viewer_department_ids(db, property_id, user_id)`
- `_to_out(db, entries, viewer_user_id)` — batches name/department/mention/ack/photo lookups
  for a page of entries, all lookups property-scoped (joined through `PropertyMembership` /
  filtered on `Department.property_id`, per the task's design point 2)
- `feed(db, property_id, viewer_user_id, query: LogFeedQuery) -> LogFeedOut` — property filter,
  optional shift/department/from/to/`mentioning_me`/cursor filters, `mentioning_me` implemented
  as an `EXISTS` subquery against `log_entry_mention` (design point 1 — filtered in SQL, not
  Python), `tuple_()` keyset pagination ordered `created_at desc, id desc`, plus an always-fetched
  `pinned` block
- `get(db, property_id, entry_id) -> LogEntry` (raises `NotFound`)
- `get_out(db, property_id, viewer_user_id, entry_id) -> LogEntryOut`
- `_day_bound(db, property_id, iso_date, exclusive_end)` — converts a property-local calendar
  date to a UTC instant; `to` is inclusive of the named day via `exclusive_end=True` (following
  midnight)

Extended the existing import block (did not add a second one): added `UTC, date, timedelta` to
the `datetime` import, `and_, or_, tuple_` to the `sqlalchemy` import, `NotFound` to
`app.errors`, `LogEntryAck` to `app.models`, and `FEED_PAGE_SIZE, LogAckOut, LogEntryOut,
LogFeedOut, LogFeedQuery, LogMentionOut, LogPersonOut` to `app.schemas.log`. Ruff's import
sort (`I`) settled the order — no manual reordering needed.

Appended the 5 tests from the brief verbatim to `server/tests/test_log_api.py`, plus one new
top-level import (`from app import clock`) needed for `clock.advance(...)`.

## What I tested and the results

- `pytest tests/test_log_api.py -q` — 13 passed (8 pre-existing + 5 new)
- Full suite `pytest -q` — 412 passed, 0 failed (baseline 407 + 5 new, exactly as predicted)
- `ruff check .` — All checks passed

## TDD evidence

**RED** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q -k "feed or entry_out or mentioning"`

```
FAILED tests/test_log_api.py::test_feed_is_newest_first_and_paginates_on_the_cursor
FAILED tests/test_log_api.py::test_mentioning_me_matches_direct_and_department_mentions
FAILED tests/test_log_api.py::test_the_feed_never_leaks_another_property - At...
FAILED tests/test_log_api.py::test_entry_out_reports_ack_progress_for_the_viewer
4 failed, 9 deselected in 1.78s
```
(`test_shift_and_department_filters` didn't match the `-k` filter text, so it wasn't run here —
that's an artifact of the brief's chosen `-k` expression, not a bug. It failed the same way when
run un-filtered, before the implementation existed.)

Failure reason matched the brief's prediction: `AttributeError: module 'app.domain.log' has no
attribute 'feed'` (and `'get_out'`) — i.e. genuinely failing because the functions didn't exist
yet, not because of a typo or fixture problem.

**GREEN** — `cd server && ../.venv/Scripts/python.exe -m pytest tests/test_log_api.py -q`

```
.............
13 passed in 2.47s
```

Then full suite + lint:

```
cd server && ../.venv/Scripts/python.exe -m pytest -q && ../.venv/Scripts/python.exe -m ruff check .
...
412 passed in 46.33s
All checks passed!
```

## `tuple_()` cursor comparison on SQLite

None of the 5 brief tests actually exercise the cursor path (`FEED_PAGE_SIZE` is 50 and the
tests create at most 3 entries), so I wrote an ad hoc probe (not committed, deleted after
running) to check this explicitly: 5 entries created a minute apart, `FEED_PAGE_SIZE`
monkeypatched to 2 (patched in both `app.schemas.log` and `app.domain.log`, since the domain
module imports the name by value at import time — patching only the schema module's copy has no
effect on `log.py`), then walked the feed via `next_cursor` until exhausted.

Result: all 5 entries came back in the correct order (`note 4, note 3, note 2, note 1, note 0`)
across 3 pages, confirming `tuple_(LogEntry.created_at, LogEntry.id) < (created, entry_id)`
performs correct row-value (lexicographic) comparison on SQLite — it treats the pair the same way
the `ORDER BY created_at desc, id desc` does, so keyset pagination doesn't skip or repeat rows
even when multiple entries share a `created_at` (which the tie-break on `id` covers). SQLite has
supported row-value comparisons since 3.15 (2016), well within this project's floor.

## Files changed

- `server/app/domain/log.py` — read side appended (feed, get, get_out, _to_out, _day_bound,
  cursor helpers, _viewer_department_ids); imports extended
- `server/tests/test_log_api.py` — 5 new tests + `from app import clock` import

## Self-review

- Each of the 5 tests would fail against a broken implementation for a distinct reason: missing
  property filter, missing shift/department filter, wrong/missing `mentioning_me` EXISTS logic,
  wrong ordering, or wrong ack/can_ack/outstanding computation. None is vacuous.
- Cursor comparison for descending order verified correct (see above) via an ad hoc probe test
  that was not committed.
- I did not add anything beyond the brief's Step 3 code and Step 1 tests. No refactors, no
  unrelated cleanup.

## Concerns

**Concurrent modification of the shared working directory during this task.** While I was
running my verification probe, I observed (via the harness's file-change notifications) that
`server/tests/test_log_api.py` and `server/app/domain/users.py` were being edited on disk by
something other than me — changes I did not make and that are unrelated to Task 6 (a new test
`test_a_mentioned_user_who_must_also_ack_is_notified_once`, an extra assertion using
`fx.supervisor_a` in `test_disabled_users_are_excluded_from_the_snapshot`, an added self-mention
in `test_department_mention_notifies_each_member_once_and_never_the_author`, and one line in
`app/domain/users.py`). At one point `server/app/domain/log.py` on disk also transiently showed a
different `notify_users(...)` call in `create()` (unfiltered `expected` instead of
`[uid for uid in expected if uid not in set(mentioned)]`) before settling back to match what I
had committed. This looks like another agent/task working on Task 5 follow-up or a different
task in this same non-worktree-isolated checkout, concurrently with my Task 6 work.

I did not touch, stash, or commit any of that — it's out of scope for Task 6 and still appears to
be in progress. I confirmed my own commit (`server/app/domain/log.py`,
`server/tests/test_log_api.py`'s 5 new tests) is self-consistent: `git diff HEAD --
server/app/domain/log.py` is empty (disk matches my commit), and a full-suite run taken after the
concurrent edits still shows 413 passed / 0 failed (412 from my commit + 1 more from whatever the
other process added), so nothing of mine was clobbered and nothing I did broke the other work.
Flagging this so the controller is aware two agents may have been writing to the same working
tree at once — worth checking whether Task 5's or another task's own commit still contains
everything it intended.

No other concerns. Nothing beyond the brief was added.

---

## Fix report: coverage gaps from review (2e4c5b5 → 068aed0)

Review verdict: spec ✅, quality Approved, no production code changed. Three test-coverage gaps
in `server/tests/test_log_api.py`, addressed below. Pulled branch first — HEAD was already
`2e4c5b5` (Task 5 follow-up test coverage commit) locally.

### 1. Cursor pagination past page 1

Added `test_cursor_pagination_walks_every_entry_exactly_once_newest_first`: monkeypatches
`log_domain.FEED_PAGE_SIZE` to 2 (patching the name `feed()` actually reads at call time, in
`app.domain.log`'s namespace — patching `app.schemas.log.FEED_PAGE_SIZE` alone would have no
effect since the domain module imported the value at import time), creates 5 entries a minute
apart via `clock.advance(minutes=1)`, then walks `next_cursor` until it comes back `None`
(bounded at 10 iterations, with `pytest.fail` if it doesn't terminate). Asserts the concatenated
order is `["note 4", "note 3", "note 2", "note 1", "note 0"]` (each entry exactly once, strictly
newest-first) and that the final page's `next_cursor is None`.

**Sabotage run:** changed `next_cursor = _encode_cursor(rows[FEED_PAGE_SIZE - 1])` to
`rows[FEED_PAGE_SIZE]` (off-by-one into the lookahead row) in `app/domain/log.py`, reran
`pytest tests/test_log_api.py -q -k cursor_pagination`. Result: FAILED —
`AssertionError: ... At index 2 diff: 'note 1' != 'note 2' / Right contains one more item:
'note 0'` — the bad cursor caused `note 2` to be skipped entirely. Reverted via `cp` from a
pre-sabotage backup and confirmed with `diff` that the file was byte-identical to the original
afterward.

### 2. `mentioning_me` department scoping

Added a third `create()` call to `test_mentioning_me_matches_direct_and_department_mentions`
mentioning `fx.dept_housekeeping` (viewer `engineer_a` is not a member — only `housekeeper_a`
is), with a comment explaining why it must not appear. The existing assertion
`{e.body for e in mine.entries} == {"direct", "via dept"}` is already an exact set comparison, so
the new "other dept" entry appearing would fail it (not a subset check).

**Sabotage run:** changed the department arm of the `EXISTS` from
`LogEntryMention.target_id.in_(dept_ids or [""])` to `LogEntryMention.target_id.isnot(None)`
(matches any department mention, ignoring `_viewer_department_ids` entirely), reran
`pytest tests/test_log_api.py -q -k mentioning_me`. Result: FAILED —
`AssertionError: ... Extra items in the left set: 'other dept'`. Reverted via `cp` +`diff` check
as above.

### 3. Pinned-block property isolation

`test_the_feed_never_leaks_another_property` now creates the property-B entry, sets
`entry.pinned = True` directly on the model (Task 7's `pin_log_entry`/`set_pinned` doesn't exist
on this branch yet — grepped `app/domain/log.py` for `set_pinned`/`pin_log_entry`/`pin(` and
found nothing), flushes, then asserts both `page.entries == []` and `page.pinned == []`.

**Sabotage run:** removed `LogEntry.property_id == property_id` from the `pinned_rows` query in
`feed()`, reran `pytest tests/test_log_api.py -q -k never_leaks`. Result: FAILED —
`AssertionError: ... Left contains one more item: LogEntryOut(id=... )` — property B's pinned
entry leaked into property A's pinned block. Reverted via `cp` + `diff` check as above.

### Full suite, lint, commit

```
cd server && ../.venv/Scripts/python.exe -m pytest -q
414 passed in 46.53s

../.venv/Scripts/python.exe -m ruff check .
All checks passed!
```

414 = the 413 already on `2e4c5b5` (407 baseline + Task 6's 5 + Task 5-followup's 1) + 1 new
cursor-pagination test. The other two gaps were closed by strengthening existing tests, not
adding new test functions, so they don't change the count — confirmed by rereading the diff
before commit (`git diff --cached --stat`: 1 file changed, 35 insertions(+), 1 deletion(-)).

Committed as `068aed0` "test(server): cover cursor pagination, department scoping and pinned
isolation". Confirmed `git diff HEAD -- server/app/domain/log.py` is empty both before and after
this fix pass — no production code was touched, per the review's instruction.

### Files changed

- `server/tests/test_log_api.py` only — one new test, two existing tests strengthened with an
  additional entry/assertion each.

### Note on the shared working directory

`server/app/domain/users.py` and `docs/superpowers/plans/2026-09-19-hotel-log.md` are still
showing as uncommitted-modified in `git status` throughout this fix pass, unrelated to Task 6 and
not touched by me — consistent with another task's in-progress work in this same non-isolated
checkout, as noted in the original report.
