# Task report — SLA-bucket colour fix + Slate & Steel Blue reskin

## Part 1 — analytics SLA-bucket colouring fix

**Root cause:** `AnalyticsPage.tsx` picked "danger" buckets by substring match
(`bucket.label.includes('15') || bucket.label.includes('30')`). The server's
`"5–15 min"` label contains the substring `"15"`, so it matched and rendered
red even though it is entirely within the 15-minute SLA.

**Deliberate-failure evidence.** I widened the test fixture to all five server
buckets and added an assertion that `"5–15 min"`'s row (rendered as `14%`)
must **not** carry `dangerText`, then ran the suite against the still-buggy
substring code:

```
❯ AnalyticsPage > marks only the past-SLA reply buckets in red
  AssertionError: expected 'w-12 flex-none text-right font-mono t…' not to contain 'dangerText'
  Expected: "dangerText"
  Received: "w-12 flex-none text-right font-mono text-xs text-dangerText"
Tests  1 failed | 11 passed (12)
```

This confirms the bug was real and the new test catches it.

**Fix:** replaced the substring check with an exact-label set drawn from the
server's stable bucket order (`app/domain/analytics.py:25-26`):

```ts
const PAST_SLA_LABELS = new Set(['15–30 min', '30+ min'])
...
danger: PAST_SLA_LABELS.has(bucket.label),
```

Re-ran the same test after the fix: all 12 tests in `AnalyticsPage.test.tsx`
pass, including the new assertion (`14%` not red, `9%` red).

**Widened fixture:** `firstResponseDistribution` in `AnalyticsPage.test.tsx`
now has all five server buckets (`< 2 min`, `2–5 min`, `5–15 min`, `15–30
min`, `30+ min`) with distinct shares (41/19/14/9/17%) so each renders a
unique percentage and can be asserted individually. Previously it only had
`'< 2 min'` and a malformed `'15–30'` (missing " min"), which is exactly why
the bug slipped past coverage — the buggy substring code happened to produce
the right answer for the two buckets that were tested.

Files changed: `web/src/features/analytics/AnalyticsPage.tsx`,
`web/src/features/analytics/AnalyticsPage.test.tsx`.

Live confirmation: signed in as `morgan@hvh.test` (manager) at
`/app/analytics` in both themes — the "Time to first reply" bar list shows
`5–15 min` at 0% in the default (non-red) style and `30+ min` at 5% in red,
matching the fixed logic.

## Part 2 — Slate & Steel Blue reskin

### Token count and name verification

Before touching anything I extracted the current 45-name `TOKENS` list from
`web/src/index.css.test.ts` and diffed it, name-for-name, against the
dispatch's supplied dark/light blocks. Both blocks in the dispatch contained
exactly 45 `--name: value;` pairs and the names matched the existing token
set with no additions, omissions, or misspellings. After writing the new
`index.css` I re-verified programmatically (parsed `:root` and
`[data-theme='light']` blocks, counted unique `--name:` matches):

```
dark count 45
light count 45
same set: true
```

Both blocks equal the pre-existing 45-token set, matching
`web/src/index.css.test.ts`'s "45 tokens and no more" test.

### Contrast ratios (accentText on accent)

Computed via the standard WCAG relative-luminance formula (sRGB → linearized
→ `0.2126R + 0.7152G + 0.0722B` → `(L1+0.05)/(L2+0.05)`):

- **Dark:** `#0b1016` on `#4f8fd4` → **5.65:1**
- **Light:** `#ffffff` on `#2563eb` → **5.17:1**

Both clear WCAG AA's 4.5:1 threshold for normal text (14px semibold is below
the "large text" bold threshold of ~18.7px, so 4.5:1 is the correct bar). No
adjustment needed.

### Visual check (Playwright, dev server)

Ran `.venv\Scripts\python.exe server\dev_start.py` and `npm run dev` (Vite
landed on port 5181 after several already-in-use ports), and drove the app
with the Playwright browser tool.

- **Inbox, dark, as `ava@hvh.test`:** room numbers and "All" tab render in the
  new blue accent (`#7ab3ea`/`#4f8fd4`); the selected row shows a blue inset
  bar with legible text on `sel` (`#172231`); SLA chips read red
  (`dangerBg`/`dangerText`) for overdue conversations; "Opted in" reads green;
  the outbound (agent) bubble is the unchanged navy `outBg` (#1e3a5f, deliberately
  distinct from the new accent); the presence avatar badge is violet, distinct
  from both.
- **Inbox, light, as `ava@hvh.test`:** same structure — blue "All" tab
  (white text), blue room numbers (`#1d4ed8`), light-blue `sel`
  (`#eff4fb`) with dark, legible text, red SLA chips, green consent badge, blue
  Send button with white text.
- **Board (work-order kanban), both themes, as `ava@hvh.test`/`morgan@hvh.test`:**
  blue room numbers/links, amber `warn`-styled priority tag ("high"), red
  `danger`-styled "urgent" tag, dark avatar-initial badges — all legible in
  both themes.
- **Analytics, both themes, as `morgan@hvh.test` (manager):** confirms the
  Part 1 fix live — "Time to first reply" shows `5–15 min` at 0% in the
  neutral/accent style (not red) and `30+ min` at 5% in red; the hourly bar
  chart and the "7 days" range-tab both use the new blue accent; KPI numbers
  legible in both themes.
- I did **not** find a seeded conversation with a rendered internal note in
  the visible inbox (checked several conversations; all showed "Notes: None"
  in the guest panel and no `Internal`-labelled bubble in the thread). I
  confirmed via source instead: `ConversationView.tsx`, `GuestPanel.tsx`, and
  `Badge.tsx` all reference notes purely through
  `noteBg`/`noteBorder`/`noteText`/`noteIcon` classes (`bg-noteBg`,
  `border-noteBorder`, `text-noteText`, `text-noteIcon`), which are unchanged
  amber values in the new palette, and `ConversationView.test.tsx` already
  asserts `toContain('bg-noteBg')` for a note bubble — so the note treatment
  is still fully token-driven and still amber; it just wasn't exercised by
  eyeball in this pass.
- Nothing went invisible: text on `sel` legible in both themes; `accentText`
  on buttons legible in both themes (see contrast ratios above); ok/warn/danger
  still read as green/amber/red in both themes and both screens checked.

Screenshots were taken to a scratch location and deleted after review (not
committed) — see the git-status note below.

### Component hardcoding audit

Searched `web/src` for hex literals and Tailwind colour utility classes
outside the token system (`grep -rniE "#[0-9a-f]{3,6}" ... `, plus
`amber|yellow-|blue-|indigo-`). No component file hardcodes a colour value.
The only two hits were both false positives, not colour bugs:

- `SlaChip.tsx:5` — `const AMBER_AT = 2 / 3` is a **fraction name**, not a
  colour; it gates when the chip's tone becomes `'warn'`, which still maps to
  `bg-warnBg text-warnText` tokens. No change needed.
- `Button.test.tsx:12` — the test title *`'uses the amber accent only for the
  primary variant'`* is now stale wording (accent is blue, not amber), but
  the test itself only asserts the `bg-accent` class is present/absent, which
  is unaffected by the value change and still correct. I did **not** touch
  this file — `Button.test.tsx` is not one of the three files the dispatch
  named as holding values, and the assertion itself isn't wrong, only its
  English description. Flagging it here as requested rather than editing it.

**No component `.tsx` file was edited for colour reasons.** The re-skin went
through `index.css` alone, confirming the token system is doing its job.

### Files changed

- `web/src/index.css` — dark (`:root`) and light (`[data-theme='light']`)
  blocks replaced with the Slate & Steel Blue values given in the dispatch,
  token-for-token, no renames.
- `web/src/index.css.test.ts` — pinned-value test updated: `--accent:
  #4f8fd4` (dark) / `#2563eb` (light), `--danger: #f26d6d` (dark) / `#dc2626`
  (light, unchanged).
- `docs/superpowers/plans/2026-09-11-phase1-web.md` — two spots updated to
  match what shipped:
  - Global Constraints line: `"green = ok, amber = warn/accent, red =
    danger"` → `"green = ok, amber = warn, blue = accent/primary action, red
    = danger"`.
  - Task 1's `index.css` code block (Step 4) replaced with the new palette
    values, and Step 5's quoted `index.css.test.ts` pinned-value test block
    updated to match (same task, same quoted file — left inconsistent
    otherwise). No other plan text was touched; several other prose mentions
    of "amber" describe the *warn* state (SLA chip thresholds, unread-row
    tint) and remain correct, or are downstream narrative describing "amber
    accent"/"amber Accent pill" in dev-verification and later-task sections
    (e.g. lines ~554, ~1012, ~3412, ~8183) that the dispatch did not name and
    that are out of this task's stated scope — flagging them here rather than
    silently rewriting unrelated plan text, per the dispatch's own
    instruction.

### Test results

- `npm test`: 39 files, **323 tests passed** (same total as before — Part 1's
  changes only widened an existing fixture/assertion, no new test cases; Part
  2 touched no test file's test *count*, only pinned values).
- `npx tsc -b`: clean, no output.

### Self-review findings / concerns

1. `web/src/components/ui/Button.test.tsx:12`'s test description says "amber
   accent" — now inaccurate wording, not a functional bug. Left untouched per
   scope (see above); worth a follow-up rename if anyone's picking at
   test-description hygiene.
2. Several other spots in the plan doc narrate "amber accent"/"amber Accent
   pill" as if it were still the primary-action colour (dev-server smoke-test
   text, later task walkthroughs). The dispatch named exactly two edit sites
   (Task 1's CSS block and the Global Constraints line) and said not to
   rewrite unrelated plan text, so I left these. They are stale relative to
   the shipped palette but are narrative/walkthrough text in later tasks, not
   the specification the CSS is built from.
3. `start.bat` and `web/vite.config.ts` showed up as modified in `git status`
   at the time I ran it, but I did not touch either file — these appear to be
   pre-existing uncommitted changes from other work (the diff is a
   dev-experience improvement to `start.bat`'s cold-start flow and an IPv4
   binding fix in `vite.config.ts`, unrelated to colours or analytics). I did
   not stage, commit, or discard them; both commits below contain only the
   files listed for each part.
4. I could not find a seeded conversation with a rendered internal note to
   eyeball directly; verified the note-colour path is still fully
   token-driven by reading the three components that reference
   `noteBg`/`noteBorder`/`noteText`/`noteIcon` and the existing
   `ConversationView.test.tsx` assertion instead.
5. Screenshots taken during the Playwright check were saved to the repo root
   by the tool's relative-path default; they were deleted before committing
   and never staged.

## Commits

1. `fix(web): stop the 5-15min SLA bucket rendering as a breach` —
   `web/src/features/analytics/AnalyticsPage.tsx`,
   `web/src/features/analytics/AnalyticsPage.test.tsx`.
2. `style(web): reskin palette to Slate & Steel Blue` —
   `web/src/index.css`, `web/src/index.css.test.ts`,
   `docs/superpowers/plans/2026-09-11-phase1-web.md`.
