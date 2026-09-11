# Task 20: Phone simulator (dev only) — Report

## What I implemented

1. **`web/src/api/client.ts`** — widened `ApiInit` per the brief:
   `export type ApiInit = Omit<RequestInit, 'body'> & { json?: unknown; body?: BodyInit }`
   and in `api()`, destructured `body` out of `rest` first, then
   `body: json === undefined ? body : JSON.stringify(json)`.

2. **`web/src/api/client.test.ts`** — added the test the brief asked for: "sends a raw body and
   does not set a JSON content type when `body` is used instead of `json`" (posts
   `new URLSearchParams({...})` and asserts the raw body string and a null `Content-Type`).

3. **`web/src/api/hooks/sim.ts`** (new) — `useSimGuests`, `useSimThread`, `useSimEvents`,
   `useSendInbound`, exactly as given in the brief's Step 1 (no `as never` needed once
   `ApiInit.body` existed).

4. **`web/src/features/sim/PhoneFrame.tsx`** (new) — as given in Step 3, with one deliberate
   deviation: the brief's sample hardcodes several extra hex colours on the phone chrome
   (`#d1d1d6`, `#f6f6f6`, `#111111` text, `#8e8e93`, `#0e1116`, and bare `bg-white`/`text-white`)
   that are **not** the four bubble colours the dispatch calls "the single sanctioned exception
   to the token rule." That sentence in the same code block's own comment says these bubble
   colours are "the only hard-coded colours in the app," which the surrounding JSX in the same
   snippet contradicts. I kept `RECEIVED`/`SENT` exactly as specified (the actual bubble fills)
   and replaced every other chrome colour with the existing design tokens (`border-border3`,
   `bg-surface`, `bg-surface2`, `border-border`, `bg-accent`/`text-accentText`, `text-text`,
   `text-text3`) — matching the pattern already used for the identical "HV" badge in
   `LoginPage.tsx` and in `SimulatorPage`'s own header. All logic, structure, data-testids,
   the direction inversion, and `formatClock` usage are unchanged from the brief.

5. **`web/src/features/sim/SimulatorPage.tsx`** (replaced the Task 8 stub) — exactly as given
   in Step 4, with the `import { PhoneFrame } from './PhoneFrame'` added per the brief's note.
   Default export preserved for the lazy route.

6. **`web/src/features/sim/SimulatorPage.test.tsx`** (new) — the 12-test file from Step 2,
   copied verbatim.

Did **not** create `GuestPicker.tsx` or `ServerLog.tsx` — both live inline in `SimulatorPage`
per the brief's explicit instruction.

## What I tested and the results

- `SimulatorPage.test.tsx` + `client.test.ts` in isolation: **23 passed** (12 sim + 11 client,
  including the new raw-body test).
- Full suite `npm test`: **358 passed**, 0 failed (345 pre-existing + 13 new: 12 sim tests + 1
  client test). No `act()` warnings, no unhandled rejections in the output.
- `npx tsc -b`: clean, no output, no warnings.

## TDD evidence

**RED** — ran the new test files against the pre-existing code (before `sim.ts`/`PhoneFrame.tsx`
existed and before `client.ts` was widened):
```
cd web && npx vitest run src/features/sim/SimulatorPage.test.tsx src/api/client.test.ts
```
Failing output (expected): `Cannot find module './PhoneFrame'` / `Cannot find module
'../../api/hooks/sim'` from `SimulatorPage.tsx`'s stub not yet replaced, and in `client.test.ts`
the new raw-body test failed because `ApiInit` didn't accept `body` (`Object literal may only
specify known properties`) and the client silently dropped it (`init.body` was `undefined`).
This failure was expected: the hooks module, `PhoneFrame`, and the widened `ApiInit` did not
exist yet.

**GREEN** — after all Step 1–4 files were written:
```
cd web && npx vitest run src/features/sim/SimulatorPage.test.tsx src/api/client.test.ts
```
```
✓ src/api/client.test.ts (11 tests) 13ms
✓ src/features/sim/SimulatorPage.test.tsx (12 tests) 1341ms
Test Files  2 passed (2)
     Tests  23 passed (23)
```

## The seven-step compliance walkthrough

Drove this live against the real server and the real Vite dev server with Playwright (two
browser tabs: `/sim` and the staff inbox logged in as `ava@hvh.test` / `Password123!`).

One environment hiccup mid-walkthrough: the machine is shared with other concurrent sessions,
and partway through, port 5000 was transiently taken over by an unrelated app ("ARIA") from
another project on this box, which made `/sim`'s polling 500/404 briefly. I did not touch that
foreign process; I started our own `server/dev_start.py` in the background, which re-bound
`127.0.0.1:5000` successfully (confirmed via `curl`), and continued testing once it was stable.
Steps 1–3 below were completed before this happened; steps 4–7 after the server was back.

1. **Text appears in queue** — Picked Sarah Chen, sent `"AC is broken"` via the quick button.
   Her conversation appeared at the top of Ava's inbox queue within a second, SLA timer running
   (`14:08` mm:ss chip), body `"The AC in our room isn't working at all, it's really warm"`.
   Verified live.
2. **Reply reaches the phone, ticks to Delivered** — Replied from the inbox
   ("Engineering is on the way to fix your AC."). It appeared as the grey received bubble on
   the phone at `08:50 · queued`, then ticked to `08:50 · delivered` after ~6s (worker tick).
   Verified live.
3. **`…0000` guest fails, Retry re-queues** — Sent as Tom Becker (`+15552000000`, flagged
   `FAILS` in the guest list), replied from the inbox. The message showed `Failed · 30007` with
   a `Retry` button in the inbox thread. Clicking Retry re-sent it and it failed again with the
   same `30007` (expected — the mock always fails that number). Verified live.
4. **STOP → one confirmation → Opted out chip → 422 → START re-subscribes** — As Sarah, pressed
   STOP. Exactly **one** confirmation bubble came back: "You're unsubscribed from Harbourview
   Hotel messages. Reply START to resume." The staff inbox queue row and the guest panel both
   showed the **Opted out** chip, and the composer showed the banner "This guest has opted out
   of SMS. A send will be rejected unless they text START." Attempting to send anyway produced
   the alert "Guest has opted out of SMS" (the 422 rejection surfaced in the UI). Typed `START`
   in the phone input and sent it; the phone showed "You're resubscribed to Harbourview Hotel
   messages." and the guest panel's Consent field changed back to **Opted in**. Verified live.
5. **HELP** — Pressed HELP; the phone showed "Harbourview Hotel: text us anytime, or call
   +1 555 0100." Verified live.
6. **card number → redaction chip** — Pressed the `card number` quick button
   (`my card is 4242 4242 4242 4242`, Luhn-valid). The staff inbox showed
   `my card is **** **** **** 4242` with a **Card number redacted** chip in the thread and in
   the queue preview. (Also noticed the seed's one pre-existing redacted message, "you can
   charge it to **** **** **** 4242" from Dmitri Costa, matching the dispatch's note.)
   Verified live.
7. **Right-hand log narrates each step** — Watched `message.created`, `notification.created`,
   `conversation.updated`, and `presence.update` events append to the "What the server did
   live" panel in real time, newest last, `HH:MM:SS` mono timestamps, throughout all of the
   above. Verified live.

All seven steps were driven and observed live; none were skipped or assumed.

## `npx tsc -b`

Clean — no output, no errors, no warnings.

## Files changed

- `web/src/api/client.ts` — widened `ApiInit`, passthrough of raw `body`.
- `web/src/api/client.test.ts` — added the raw-body test.
- `web/src/api/hooks/sim.ts` — new: the four sim hooks.
- `web/src/features/sim/PhoneFrame.tsx` — new.
- `web/src/features/sim/SimulatorPage.tsx` — replaced the Task 8 stub.
- `web/src/features/sim/SimulatorPage.test.tsx` — new: the 12-test suite.

## Self-review findings

- All 12 simulator tests pass, plus the client raw-body test — 13/13 new tests green.
- Bubble direction verified both in the test (`sms-in`/`sms-out` testids) and live: hotel
  replies render grey/left (received), guest's own texts render green/right (sent) — matches
  "we are the guest in the phone" rule.
- `useSimThread` sends both `phone` and `propertyId` — verified by the R5 test and live (the
  network tab and the working thread confirm it; the server would 400 otherwise).
- The inbound POST is genuinely form-encoded: `Content-Type: application/x-www-form-urlencoded`,
  `X-Mock-Secret: dev`, and a `URLSearchParams` body with Twilio's exact field names
  (`From`/`To`/`Body`/`MessageSid`) — verified by the dedicated test and live network behavior
  (STOP/HELP/card-number all round-tripped correctly against the real server).
- Card number is Luhn-valid (`4242 4242 4242 4242` — the well-known test PAN) and the server's
  redaction fired live, producing the "Card number redacted" chip in the real inbox.
- No `GuestPicker.tsx`/`ServerLog.tsx` created — both panels are inline in `SimulatorPage.tsx`.
- No `useSession()` anywhere in the sim feature; the test mounts `SimulatorPage` with no
  `SessionProvider`, and it renders and functions correctly with no server-side auth.
- Did not touch the `import.meta.env.DEV` gating in `routes.tsx`.
- Colour-token discipline: `PhoneFrame.tsx`'s only hardcoded hex values are the two bubble
  colour pairs (`#e9e9eb`/`#111111` for received, `#34c759`/`#ffffff` for sent); everything else
  on the page (including the phone's own header/background chrome) uses design tokens. This is
  a deliberate, documented deviation from the brief's literal sample code — see item 4 above.
- Test output is pristine: no `act()` warnings, no unhandled promise rejections, across the
  full 358-test suite.

## Issues or concerns

- **Defect in the brief's own text, not in the server or my implementation**: the dispatch
  message (Context section, point 5) states the bubble colours are "the single sanctioned
  exception to the token rule" and "everything else on the page uses the 45 design tokens," but
  the brief's literal `PhoneFrame.tsx` sample code hardcodes several additional hex values on
  the phone's header chrome that are not part of that exception. I followed the *token
  constraint* (the more specific, more binding instruction) over the literal sample bytes,
  and used existing design tokens for the chrome instead — this is the one place my
  implementation differs from the brief's given code. Flagging per "if a test/spec in the
  brief asserts something wrong, do not bend the code to make it pass — report the defect."
- Environment: this machine runs multiple concurrent Claude Code sessions across unrelated
  projects sharing the same port ranges. Port 5000 was transiently grabbed by an unrelated
  app mid-walkthrough; I did not kill that foreign process, and instead started our own
  server fresh, which re-bound successfully. No code or config change was made to work around
  this; it was a live-environment hiccup, not a defect in the simulator.
- No other concerns. All 12 brief tests plus the required client test pass, `tsc -b` is clean,
  and the full 7-step compliance walkthrough was driven and observed live end to end.
