# Restoration R3 — analytics custom range, simulator PMS buttons

> **Read `_CURRENT-CONTRACTS.md` in this directory first.** This brief predates waves
> R1, A1 and A2; that file carries the hazards, the error contract and the test-quality
> standard established since, and it wins wherever it disagrees with this brief.


TWO smaller affordances the approved mockups promise that the shipped screens do not have.
(The third, R3.1, was built by wave A2 — see below.) Both are buildable today. Line numbers below were read from the current tree; a fix wave
and two restoration waves landed before you, so **verify each anchor before editing** and report
any that moved.

---

## R3.1 — SUPERSEDED. DO NOT BUILD THIS.

The quick-reply segment counter was built by **wave A2** (commits `9ae2bac..4438a5b`), along with
the Insert chips, the category and locale inputs, and **the live preview that this section
explicitly put out of scope.** The user later widened the admin scope, which authorised it.

It was also built *differently* from what this section prescribed, and the reasons matter if you
are tempted to "fix" it back:

- The counter is **server-computed**, via a new non-mutating `POST .../quick-replies/preview`
  endpoint — not via `web/src/lib/segments.ts` as this section instructed.
- The old `/render` endpoint could not serve it, for three independent reasons: it increments
  `usage_count`, which the same screen displays in a "Uses" column; it is gated on `reply`, which
  **excludes `corporate`**, a role that reaches the admin screen; and it renders a *saved* row
  against a *real* conversation, when the panel must preview unsaved text on a property that may
  have no conversations at all.
- The preview renders the server's fallback values and is labelled `Preview · sample values`
  rather than the mockup's `Preview as Sarah Chen · 412`, because naming a real guest beside
  placeholder data would be a lie.
- `web/src/lib/segments.ts` still exists and still backs the **inbox composer's** counter, which
  needs per-keystroke feedback and whose users are agents who would get a 403 from the
  `manage_admin`-gated preview endpoint. The two implementations are now pinned against each
  other by a hand-computed golden-vector fixture at `fixtures/sms-segments.json`, asserted from
  both the Python and TypeScript suites.

**So this wave is R3.2 and R3.3 only.**

## R3.2 — Analytics has no "Custom" date range

**The gap.** `docs/mockups/Analytics.dc.html:44` offers **Today / 7 days / 30 days / Custom**.
`web/src/features/analytics/dateRange.ts` defines `RangeKey = 'today' | '7d' | '30d'` — no
custom option.

The server already accepts arbitrary `from`/`to`, so this is two date inputs and a fourth
range key.

Requirements:
- Add `'custom'` to `RangeKey` and a **Custom** option to the range control, ordered last as the
  mockup orders it.
- When Custom is selected, reveal two date inputs (from / to). Everything on the page —
  every KPI card, both charts, the agents table, and the CSV export — must respect the custom
  range, not just some of them. **Check the export specifically**; it is easy to miss.
- Validate: `from` must not be after `to`. Handle it the way the codebase already handles
  invalid input on other screens — do not invent a new error pattern.
- Do not fire a query until both dates are present; a half-filled custom range must not blank
  the page or spam the API.
- Preserve whatever URL/state persistence the existing range control has, so a custom range
  behaves like the presets do.
- Respect the project's date handling as it already exists in `dateRange.ts`. **Note a known,
  deliberate gap you must not "fix" here:** `server/app/domain/analytics.py:57` buckets hours in
  raw UTC rather than the property's `America/New_York`, so the by-hour chart is shifted four
  hours. That is disclosed and out of scope — do not touch it, and do not compensate for it in
  the client.

## R3.3 — Simulator has no PMS check-in / check-out buttons

**The gap.** `docs/mockups/Simulator.dc.html:91-93` shows **Fire PMS check-in** and
**Fire PMS check-out** buttons. `SimulatorPage.tsx` has neither, and the endpoints
`POST /api/dev/pms/check-in/<stay_id>` and `POST /api/dev/pms/check-out/<stay_id>`
(`server/app/api/dev.py:106-113`) are otherwise unreachable from the product.

Requirements:
- Add both buttons to the simulator, placed as the mockup places them.
- They act on the currently selected guest's stay. **Read `server/app/api/dev.py` for the exact
  route shape and what it expects**, and read how the simulator's existing hooks in
  `web/src/api/hooks/sim.ts` are written — follow that pattern.
- You need a stay id. Work out where it actually comes from for the selected guest; if the
  simulator's current data does not carry one, say so in your report rather than inventing a
  lookup or hardcoding an id.
- Surface the result in the simulator's existing event log, the way its other actions are
  surfaced. Handle and display errors — `ApiError` carries `error.message`.
- Disable both when no guest is selected.

**Two things about the simulator specifically.** It is dev-only (`/sim` is excluded from the
production build via `import.meta.env.DEV` in `routes.tsx`) — keep it that way; nothing you add
may make it reachable in a production build. And its `PhoneFrame` chrome uses **deliberately
hardcoded iOS colours** with a comment explaining why: that is a sanctioned exception you must
not "correct", and it does not license any new hardcoded colour elsewhere.

---

## Constraints

- TypeScript `strict`. No `any`; no `@ts-ignore` without a comment naming the reason.
- **No hardcoded hex anywhere**, with the single documented `PhoneFrame` exception noted above.
  All colour comes from the tokens in `web/src/index.css`, mapped into Tailwind by name.
- **Status colours are reserved and never decorative:** green = ok, amber = warn, blue =
  accent/primary action, red = danger.
- Radii are three values: **6 px** `rounded-md` (tags, badges, avatars, SLA chip), **8 px**
  `rounded` (buttons, inputs, nav rows), **10 px** `rounded-card` (cards, message bubbles).
- Server state lives **only** in TanStack Query. No server data in React state or context.
- Fonts: **do not assume Space Grotesk.** The shell/reskin wave (S1) runs BEFORE this one and
  changes the UI face. Read `web/src/index.css` for the current stack rather than hardcoding a
  family; mono is still used for room numbers, timers, ids and counts.
- Follow the existing component and test patterns in each feature directory you touch.
- Verify both themes — light is a real, supported mode.

## Tests (required)

- Selecting Custom and entering a range changes what analytics fetches, including the export;
  an invalid range (`from` after `to`) is rejected.
- The PMS buttons call the right endpoint for the selected guest and are disabled with none
  selected.

Each test must fail if the behavior it names breaks. An assertion that passes for an incidental
reason is a defect even when green — one such test was already caught on this branch.

## Verification before you commit

```
cd web && npm test && npx tsc -b && npm run build
```

All existing tests must still pass, plus yours. Confirm the production build still excludes the
simulator. Output must be pristine — stray warnings are findings against you. Do not run the
Playwright E2E suite; it boots two servers and is slow.

Commit in two logical commits, one per item.
