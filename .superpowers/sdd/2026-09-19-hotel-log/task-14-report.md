# Task 14 report: Seed data and full-stack verification

## Part 1 — Seed data

### Entries added (`server/seed/seed.py`), property A (Harbourview Hotel / HVH), all dated "yesterday" so shift classification never lands in the future regardless of when the seed happens to run:

1. **am** — author Ava Agent (front desk agent), `department_id` = Front Desk (tag), body modelled on the AM CHECKLIST reference image (`images/image (2).png`): arrivals/departures/occupancy/notes, ending with an `@[Housekeeping](department:…)` mention token. Posted at 07:30 local (America/New_York) → shift `am`.
2. **pm, pinned** — author Sam Super (supervisor), `pinned=True`, `pinned_by_user_id`/`pinned_at` set. A short corporate-visit announcement. Posted at 15:30 local → shift `pm`.
3. **overnight, requires_ack** — author Marcus Reyes (front desk agent), `department_id` = Housekeeping, `requires_ack=True`, `ack_expected` = the three active Housekeeping members (Hana Keeper, Rosa Lima, Grace Osei) — nobody has acknowledged. Posted at 02:00 local → shift `overnight`.

### `SeedSummary` / test changes

- Added `log_entries: int` to `SeedSummary` (`server/seed/seed.py`), populated in `run()` from `select(func.count()).select_from(LogEntry)` after all mutations (same real-row-query convention as every other field, per the existing comment about the showcase-conversation rewire desync).
- `server/tests/test_seed.py`: added `LogEntry` to imports, and asserted:
  - `count(LogEntry, LogEntry.property_id == hvh.id) == 3`
  - `count(LogEntry, ..., LogEntry.pinned.is_(True)) == 1`
  - `count(LogEntry, ..., LogEntry.requires_ack.is_(True)) == 1`
  - `summary.log_entries == count(LogEntry)` alongside the other summary-vs-reality assertions.

### Server suite / lint

- `../.venv/Scripts/python.exe -m pytest -q` → **427 passed** (matches baseline; no new test functions, only new assertions inside the existing seed test).
- `../.venv/Scripts/python.exe -m ruff check .` → **all checks passed**.
- Also ran `npm test -- --run` in `web/` for completeness (no web files touched): **643 passed**, matching baseline.

## Part 2 — Full-stack verification

Reset `server/data/app.db*` (they held stale pre-Task-14 seed data) and cold-started both halves exactly as `start.bat` does:
- API: `.venv\Scripts\python.exe server\dev_start.py` → migrated, seeded fresh (log confirms "Seeded 2 properties, 14 users, 110 guests, 113 stays, 35 conversations, 59 messages, 21 work orders"), served on `127.0.0.1:5200`.
- Web: `cd web && npm run dev` → Vite on `127.0.0.1:5173`.

Drove a real Chromium browser via Playwright MCP tools against this stack. Multiple logins were exercised sequentially (marcus, jordan, hk.supervisor, hana, alex, ava) since the harness's browser tabs share one cookie jar (no incognito-context tool available) — realtime (AC2) was instead verified with two tabs under the *same* logged-in user, which is still two independent WebSocket-connected sessions and is a valid test of property-scoped broadcast.

### Acceptance criteria (spec §10)

1. **PASS** — Logged in as Ava (agent), composed a note in the `/app/log` composer: typed `@Marc` → picked Marcus Reyes, `@Jordan` → picked Jordan Tate, `@Housekeeping` → picked the Housekeeping department, set the Department tag to Housekeeping, and attached a photo (`images/image (2).png`) via the Photo file picker. Posted successfully; the card rendered the photo (`img "Attached"`) and the mention text as plain bold names. Checked notifications: Marcus's Alerts count went 2→3 with a new "Ava mentioned you in the hotel log" entry; Jordan's went 2→3 with the same; Ava's own Alerts count stayed at 2 (no self-notification). **Minor defect found** (not one of the 8 criteria, noted below): the notification body shows the raw unrendered mention token `@[Marcus Reyes](user:95786ed2-…)` instead of the friendly display name — `renderBody`'s `TOKEN_RE` parsing is only applied in `LogEntryCard`, not in the notifications list.

2. **PASS** — With a second browser tab open on `/app/log` (same account, independent socket connection), posting from tab 1 caused tab 2's feed to show "Today · 4 posts" including the new entry immediately, with zero manual refresh or navigation performed on tab 2.

3. **PASS** — Logged in as Grace Osei (hk.supervisor@hvh.test, Housekeeping supervisor), posted an entry with "Requires acknowledgement" checked and audience `@Housekeeping`. Card showed "0 of 2 acknowledged" with "Outstanding: Hana Keeper, Rosa Lima" — correctly N=2 (3 active Housekeeping members minus the author herself, who was excluded from her own audience). Logged in as Hana Keeper and clicked Acknowledge: card updated to "1 of 2 acknowledged", "You acknowledged this", "Outstanding: Rosa Lima" (Hana's name removed).

4. **PASS** — Logged in as Alex Admin, went to Admin → Users & roles, edited Eli Engineer (previously Engineering, `dept_staff`) and changed his department to Housekeeping, saved (table confirmed the change). Reloaded `/app/log`: Grace's entry from step 3 still read "1 of 2 acknowledged" / "Outstanding: Rosa Lima" — Eli was not added to the denominator or outstanding list, confirming the `ack_expected` snapshot is frozen at creation time.

5. **PASS** — As Hana Keeper (`dept_staff`) and earlier as Ava (`agent`), no Pin/Unpin control appeared on any entry card. As Grace Osei (`supervisor`) and Alex Admin (`admin`), every card showed a Pin/Unpin button; Sam Super's pm entry was pinned in the seed and appeared throughout in the "Pinned" block above the daily feed on every login observed.

6. **PASS** — The seeded overnight entry (created at 02:00 local) displayed badge `OVERNIGHT`; the seeded am entry (created at 07:30 local) displayed badge `AM`. Confirmed via the feed UI across every snapshot taken in this session.

7. **PASS** — No edit affordance was observed on any log entry card in any of the ~12 UI snapshots taken (only Pin/Unpin for authorized roles and Acknowledge/"You acknowledged this" for ack-eligible viewers). Cross-checked against `web/src/features/log/LogEntryCard.tsx`: the component renders no edit control and there is no PATCH/PUT route on the body in `server/app/api/log.py` (immutability is asserted at the route-map level per Task 8's self-review note).

8. **PASS** — While logged in as Alex Admin (HVH-only membership), issued a direct GET to `/api/p/<Lakeside-Inn-property-id>/log-entries` two ways: (a) `fetch()` from the page context, and (b) direct browser navigation to the URL. Both returned **403** with body `{"error":{"code":"FORBIDDEN","message":"No access to this property"}}` — no property-B data was present in the response.

### Tally: **8 PASS**

## Defects found

1. **Minor / cosmetic** — Notification bodies for `log.mention` and `log.ack_requested` show the raw mention-token markup (`@[Name](user:uuid)` / `@[Name](department:uuid)`) instead of a rendered display name, because `entry.body[:140]` is passed straight into the notification body in `app/domain/log.py`'s `create()` without running it through the same token-stripping renderer `LogEntryCard.tsx` uses. Cosmetic only — does not affect notification delivery, targeting, or the 8 acceptance criteria — but worth a follow-up ticket since a body with more than one token can look confusing (e.g. `Overnight leak in 219 is cleared. @[Marcus Reyes](user:95786ed2-8e87-4b03-9351-24a850fc7fc5) and @[Jordan Tate](user:bfd8a366-…`).

No other defects found. All 8 spec §10 criteria observed passing against a real running server + browser, not inferred from unit tests.

## Fix: mention-token leak in notification bodies (post-report follow-up)

Per coordinator request, fixed the defect above before merge.

**Change (`server/app/domain/log.py`):**
- Added `_MENTION_TOKEN` (a module-level compiled regex mirroring the frontend's `TOKEN_RE` in `web/src/features/log/MentionInput.tsx`, including the 36-char UUID id group, with a comment noting the two must be kept in sync) and `_plain_text(body)`, which substitutes each `@[Name](user|department:uuid)` token with `@Name`.
- Both notification call sites in `create()` (`log.mention` and `log.ack_requested`) now build the body as `_plain_text(entry.body)[:140]` — substitution happens **before** truncation, so a token straddling the 140-char cutoff is never sliced in half. The persisted `LogEntry.body` is untouched; only the notification's copy is transformed.

**Tests added (`server/tests/test_log_api.py`):**
1. `test_mention_notification_body_shows_a_name_not_raw_token_markup` — posts a body containing `@[Eli Engineer](user:…)`, asserts the resulting `log.mention` notification body contains `@Eli Engineer` and does not contain `](user:`.
2. `test_mention_token_is_never_split_by_truncation` — builds a body where the raw token straddles position 140 (`"A" * 120 + token + …`, with an inline assertion `120 < 140 < 120 + len(token)` documenting why), and asserts the notification body contains the intact `@Hana Keeper` name with no `[` or `](user:` fragment left over — this is the test that would catch a future refactor reordering substitute/truncate.

**Sabotage verification:** reverted both call sites to raw `entry.body[:140]`, re-ran the two new tests — both failed as expected (test 1: `AssertionError: assert '@Eli Engineer' in 'Please check 327 @[Eli Engineer](user:d13f13d5-…) today.'`; test 2: `AssertionError: assert '@Hana Keeper' in 'AAA…AAA@[Hana Keeper](user:'`, showing the exact mid-token slice the fix prevents). Restored the fix; both pass again.

**Verification:**
- `../.venv/Scripts/python.exe -m pytest -q` → **429 passed** (427 baseline + 2 new).
- `../.venv/Scripts/python.exe -m ruff check .` → all checks passed.

**Commit:** `aae1814` — fix(server): render mention tokens to display names in log notifications (`server/app/domain/log.py`, `server/tests/test_log_api.py`).

Coordinator's other three notes required no action: the two-tab realtime check is accepted as a legitimate two-socket property-scoped-broadcast test; `server/app/domain/users.py`'s modification is a pre-existing CRLF artifact unrelated to this task and was left untouched/uncommitted; leaving the reseeded `server/data/app.db*` uncommitted was confirmed correct.

## Files changed

- `server/seed/seed.py` — three log entries + `SeedSummary.log_entries` + imports (`LogEntry`, `LogEntryMention`, `MentionTargetType`, `shift_for`, `time`, `ZoneInfo`).
- `server/tests/test_seed.py` — `LogEntry` import + 4 new assertions (3 exact counts + summary-vs-reality).
- `server/data/app.db*` — regenerated locally by re-seeding for browser verification; **not committed** (brief's own commit instructions list only `server/seed` and `server/tests/test_seed.py`).

## Concerns

- `server/app/domain/users.py` was already modified (uncommitted) in the working tree before this task started (visible in the initial git status snapshot) and is unrelated to Task 14 — left untouched, not committed, flagging for whoever owns that change.
- Two browser tabs in this harness share one cookie jar, so the realtime check (AC2) used two tabs under the same account rather than two different staff accounts. This is still a valid, real test of the property-scoped WebSocket broadcast (each tab is an independent socket connection) but is a slightly weaker proof than "two different people" would be. If a true multi-account realtime check matters, it would need a second isolated browser context/profile.
- The pinned-pm seed entry's author (Sam Super, engineering supervisor) and the "requires-ack" manual-test author (Grace Osei, Housekeeping supervisor) were chosen because the brief said only "the supervisor" without specifying which of the two seeded supervisors; both are valid supervisors capability-wise. Flagging the choice in case a specific one was intended.
