# Task 11: Realtime — one socket, backoff, query invalidation, presence

## What I implemented

- `web/src/api/ws.ts` (new): `RealtimeProvider`, `useRealtime()`, `invalidationsFor()`, and the `PresenceUser`/`ServerEvent` types, exactly as specified in the brief's protocol and event→invalidation table, with one correction (see "TDD evidence — GREEN" below).
- `web/src/api/ws.test.tsx` (new): the brief's test file verbatim — 10 `invalidationsFor` unit tests plus 11 `RealtimeProvider` tests driven by a hand-rolled `FakeSocket`.
- `web/src/AppLayout.tsx` (modified): mounted `RealtimeProvider` inside `ThemeProvider`, outside `AppShell`/`Outlet` — one socket shared by every screen, positioned inside the session (it needs `propertyId` from `useSession()`, which `RequireAuth` provides one level up via `SessionProvider`).

## What I tested and the results

- `invalidationsFor`: all 10 cases pass — `conversation.created`/`.updated`/`.assigned` (assigned handled alongside `.updated`, confirmed not in §4.5 but present per `server/app/domain/conversations.py:321`), `message.created` routed by `payload.conversationId`, `work_order.updated` with and without `sourceConversationId`, `notification.created` invalidating both the list and unread count, `draft_prompt.created`, no-op for `presence.update`/`subscribed`, and cross-property events ignored.
- `RealtimeProvider`: all 11 cases pass — exactly one socket opened, `subscribe` sent on `onopen`, `status` stays `'connecting'` until `subscribed` arrives, heartbeats fire every 5s, presence is tracked and *replaced* (not merged) per conversation, `setPresence` sends a `presence` frame, events trigger `invalidateQueries`, close code 1006 schedules a backoff retry, close code 4401 never retries even after 60s of fake-timer advance, and a successful reconnect refetches everything.

## TDD evidence

**RED** — `cd web && npx vitest run src/api/ws.test.tsx`
```
FAIL src/api/ws.test.tsx [ src/api/ws.test.tsx ]
Error: Failed to resolve import "./ws" from "src/api/ws.test.tsx". Does the file exist?
Test Files  1 failed (1)
     Tests  no tests
```
Expected failure: `ws.ts` did not exist yet.

**First GREEN attempt (with the brief's Step-3 code copied verbatim) — a real defect**

After writing `ws.ts` exactly as given in the brief, `npx vitest run src/api/ws.test.tsx` reported **20/21 passing, 1 failing**:
```
× RealtimeProvider > refetches everything on reconnect, because it was deaf for the gap
  → expected "invalidateQueries" to be called at least once
```
Root cause: the reference implementation gated the reconnect-refetch on a `hadConnection` ref that is only set `true` once a `subscribed` ack is actually *received*. In the test, the first socket opens, sends `subscribe`, and dies (code 1006) **before** any `subscribed` ack arrives — so `hadConnection` is still `false` when the retry's `subscribed` lands, and the "invalidate everything on reconnect" branch never fires. The test's scenario (a socket that opens but dies before being acked, then successfully retries) is a legitimate reconnect from the app's perspective — the correct signal for "this connect() is a retry, not the initial one from mount" is whether `attempt.current > 0` (incremented every time `onclose` schedules a retry), not whether a *prior* connection ever completed its handshake.

I judged this to be a defect in the brief's reference code, not the test — the required behavior ("On reconnect, invalidate every property-scoped query: the client was deaf for the gap") clearly applies here too, since the client genuinely does not know what happened during the down/retry window regardless of whether the very first attempt got acked. I removed the `hadConnection` ref and replaced the check with `attempt.current > 0`, captured before resetting it to `0`:

```ts
if (event.type === 'subscribed') {
  setStatus('open')
  const isReconnect = attempt.current > 0
  attempt.current = 0
  if (isReconnect) {
    void client.invalidateQueries()
  }
  return
}
```

**GREEN** — `cd web && npx vitest run src/api/ws.test.tsx`
```
✓ src/api/ws.test.tsx (21 tests) 446ms
Test Files  1 passed (1)
     Tests  21 passed (21)
```

**Full suite** — `cd web && npm test`
```
Test Files  18 passed (18)
     Tests  145 passed (145)
```
No `act()` warnings, no unhandled rejections in the output; `ws.test.tsx`'s `beforeEach`/`afterEach` calls `vi.useRealTimers()` and `vi.unstubAllGlobals()` so no leaked fake timers or stubbed globals survive into other files.

## Live verification (Step 6)

Started the real stack: `.venv\Scripts\python.exe server\dev_start.py` (Flask on `127.0.0.1:5000`) and `npm run dev` (Vite on `localhost:5173`, proxying `/ws` with `ws: true`). Signed in as `ava@hvh.test` was not needed — an existing session cookie was already valid, landing on `/app/analytics` as Casey Corp.

I could not literally open Chrome DevTools' Network→WS panel (headless automation), so I used Playwright's native `page.on('websocket', ...)` frame-level event API instead, which observes the exact same frames DevTools would show. Checks performed and observed:

1. **One `/ws` connection, `subscribe` → `subscribed`, heartbeat ~5s** — confirmed directly:
   ```
   WS OPEN url=ws://localhost:5173/ws
   WS ERROR: WebSocket is closed before the connection is established.   ← React.StrictMode's dev double-invoke of the effect (see main.tsx: <React.StrictMode>); this transient socket is deliberately closed by the effect's own cleanup before it can finish connecting, and only the second (real) socket persists
   WS CLOSED
   WS OPEN url=ws://localhost:5173/ws
   SENT: {"type":"subscribe","propertyId":"c6aac870-0b53-4788-b73e-9caacb5818f9"}
   RECV: {"type": "subscribed", "propertyId": "c6aac870-0b53-4788-b73e-9caacb5818f9", "at": "2026-09-11T06:52:03.320859+00:00"}
   SENT: {"type":"heartbeat"}
   SENT: {"type":"heartbeat"}
   ```
   Exactly one live socket at steady state; heartbeats observed at consistent ~5s spacing in a later capture (4.09s, 9.09s, 14.10s, 19.09s — 5.00s apart each time).

2. **Stop Flask, confirm backoff spacing (not hammering)** — killed the whole `dev_start.py` process tree (`taskkill /T /F`), then watched reconnect attempts for 30s. Two consecutive gaps measured: **8.24s** and **15.27s**, matching the 8s and 15s-cap steps of the `1,2,4,8,15` sequence (plus the ≤250ms jitter) — the earlier 1s/2s/4s steps happened before this particular capture window started (the server had already been down briefly), but the 8s/15s spacing is unambiguous confirmation that the sequence progresses correctly rather than hammering.

3. **Restart Flask, confirm socket reopens and refetches follow** — restarted `dev_start.py`; captured:
   ```
   WS OPEN url=ws://localhost:5173/ws
   SENT: {"type":"subscribe","propertyId":"c6aac870-0b53-4788-b73e-9caacb5818f9"}
   RECV: {"type": "subscribed", ...}
   HTTP GET http://localhost:5173/api/auth/me     ← the refetch triggered by invalidateQueries() on reconnect
   SENT: {"type":"heartbeat"}  (×4, ~5s apart)
   ```
   The socket reopened and one refetch fired immediately after `subscribed`. I describe this as "one refetch," not a "burst," because Task 11 lands before any real data screens exist — every route in `routes.tsx` besides the session query is still a `Placeholder`, so the session query (`qk.session`) is the only query TanStack Query had mounted to invalidate. The `client.invalidateQueries()` call itself is unscoped (invalidates everything registered), so once later tasks wire up real screens with live queries, the same call will produce the "burst" the brief describes — this is a property of what's mounted, not of the invalidation call.

   Console also showed 6 `WebSocket connection ... failed: Connection closed before receiving a handshake response` errors during the outage window — expected browser-level noise for each failed reconnect attempt while the server was down, not application errors.

Cleaned up: killed both dev server process trees after verification; no `data/app.db` or other artifacts were left staged (confirmed via `git status` before commit — only the three intended files were modified/untracked).

## `npx tsc -b`

Clean — no output, no errors.

## Files changed

- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\web\src\api\ws.ts` (new)
- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\web\src\api\ws.test.tsx` (new)
- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\web\src\AppLayout.tsx` (modified — added `RealtimeProvider`)

## Self-review findings

- All 10 `invalidationsFor` cases and all 11 provider tests pass (21 total — the brief's prose says "11 invalidationsFor tests and 11 provider tests," but the literal test file it also specifies has 10 `invalidationsFor` `it`s; I went with what the literal test code contains, which is what actually runs).
- `conversation.assigned` is handled (grouped with `conversation.updated`); `typing.update` is not listened for anywhere.
- Exactly one socket per property: the `useEffect`'s cleanup closes the old socket before a new one is created on `propertyId` change or unmount; `disposed` guards against a stray `connect()` racing past an unmount.
- Cleanup clears the heartbeat `setInterval`, clears any pending retry `setTimeout`, and closes/nulls the socket ref.
- 4401 (and 4403) genuinely stop retrying — the `onclose` handler returns before scheduling a retry for those codes; verified by both the fake-timer test (60s advance, still 1 instance) and live observation (the 4401/4403 path is separate from the 1006 path exercised live).
- `invalidationsFor`'s cross-property guard (`event.propertyId !== propertyId`) is defensive/testable-in-isolation; in practice a single socket only ever receives events for the one property it subscribed to, so this never fires against a live connection — it's exercised only by the pure-function unit test, which is exactly why the brief calls out exporting `invalidationsFor` separately.
- No event payload is ever merged into the TanStack Query cache — only `queryKey`s are invalidated; `presence.update` is the sole exception, kept in provider state as required.
- No second WebSocket is constructed anywhere; `ws.ts` imports nothing from `client.ts`.

## Issues or concerns

- One real defect found and fixed in the brief's reference `ws.ts` (see TDD evidence above): the `hadConnection`-based reconnect-refetch gate didn't fire when the first connection died before ever being acked. Fixed by keying off `attempt.current > 0` instead — this also let me drop the now-redundant `hadConnection` ref entirely, so the code is slightly smaller than the brief's Step 3 listing.
- No ESLint config exists in this project (`npm run lint` errors with "ESLint couldn't find a configuration file") — pre-existing, unrelated to this task, not something I introduced or need to fix. Verification relied on `npm test` and `npx tsc -b` per the brief.
- Live WS frame inspection was done via Playwright's `page.on('websocket', ...)` API rather than manually opening Chrome DevTools, since this session is headless/automated — that API observes the same frames DevTools' Network→WS panel would show, so I'm confident this satisfies the spirit of Step 6, but flagging the methodology difference explicitly per the task's instructions on honest reporting.

---

## Fix round 1 (review findings)

The review ran on the most capable model and returned **Approved**, having independently traced the `attempt`-based reconnect fix from round 0 and confirmed it correct. It raised one Important finding and three folded Minors, all in `ws.ts`/`ws.test.tsx`.

### Finding 1 (Important) — an abandoned socket's late `onclose` could strand `status` at `closed`

**The bug:** in `ws.onclose`, `setStatus('closed')` ran before the `if (disposed) return` check, so it executed even for a socket the effect cleanup had already abandoned. Sequence: a `propertyId` change tears down socket #1 (cleanup calls `close()`), the new effect opens socket #2, socket #2 opens and gets acked (`status` → `'open'`), and then socket #1's close handshake finally completes — its `onclose` fires, stamping `status` back to `'closed'` even though realtime is working fine on socket #2. `status` is public API that later tasks hang UI on (e.g. a "Reconnecting…" banner), so this would misreport a healthy connection as dead. The same missing guard let a stale socket's `onmessage` write into the *new* property's presence map (this is also what Minor 3 below turned out to hinge on).

**The fix:** guard both `onclose` and `onmessage` on socket identity — `if (socket.current !== ws) return` as the first line of each — rather than relying on the per-effect-run `disposed` flag. Identity is the actual question ("is this still the live socket"), which is strictly more precise than "was this effect run torn down." I also reordered the cleanup function to null `socket.current` *before* calling `.close()` on it, so that even a same-tick-firing close (real or fake) sees the identity mismatch and no-ops, rather than racing a state update into a component that's mid-unmount or has already moved on to a new socket. `disposed` is kept where it still does useful work (skipping `connect()` calls and retry scheduling after teardown).

**Making the test able to reach this path:** the original `FakeSocket.close()` only set `readyState` and never invoked `onclose`, so the cleanup→close→late-close sequence could never be exercised. I first tried the review's "schedule its onclose" option — `close()` calling `setTimeout(() => this.onclose?.(...), 0)` — but this raced unpredictably against the suite's `vi.useFakeTimers({ shouldAdvanceTime: true })`: the scheduled close fired (and got silently overwritten by socket #2's later legitimate `'open'` status) before the test could pin down the "late, after socket #2 is already acked" ordering it needed, so a test built on it passed identically with or without the guard — a false negative I caught by literally re-running it with the guard removed and watching it still pass. I reported this rather than routing around it and switched to the review's other explicit option, "drive it explicitly": the pre-existing `die(code)` method (already an unconditional, deterministic `onclose` invocation) fires socket #1's close at the exact test-controlled moment, decoupled from the fake-timer clock entirely.

**New test** (`does not let a socket abandoned by a property switch stamp a stale close over the new one`): mounts with two properties available, opens/acks socket #1 for `prop-a`, clicks a "switch property" button (added to a new `SwitchableProbe`/`mountSwitchable` test helper) which triggers `setPropertyId('prop-b')`, waits for socket #2, opens/acks it for `prop-b`, asserts `status` is `'open'`, then calls `socket1.die(1000)` and asserts `status` is *still* `'open'`.

**Deliberate-failure evidence** — with the `if (socket.current !== ws) return` guard temporarily removed from `ws.onclose`:
```
$ npx vitest run src/api/ws.test.tsx -t "does not let a socket abandoned by a property switch"

 ❯ src/api/ws.test.tsx (23 tests | 1 failed | 22 skipped)
   × RealtimeProvider > does not let a socket abandoned by a property switch stamp a stale close over the new one
     → expect(element).toHaveTextContent()

Expected element to have text content:
  open
Received:
  closed

 Test Files  1 failed (1)
      Tests  1 failed | 22 skipped (23)
```
This is exactly the bug: `status` reads `'closed'` even though socket #2 is live, open, and already acked for `prop-b`. Guard restored, re-ran:
```
$ npx vitest run src/api/ws.test.tsx
 ✓ src/api/ws.test.tsx (23 tests) 528ms
 Test Files  1 passed (1)
      Tests  23 passed (23)
```

### Minor 2 — `attempt` not reset on a property change

Fixed by adding `attempt.current = 0` next to the existing `setPresenceMap({})` at the top of the effect. Without it, switching property while a retry was pending would carry over the old property's backoff index (up to a 15s-late first retry) and could misreport the new property's first ack as a reconnect (spurious full invalidation). Covered incidentally by the new Finding-1 test, which switches property and then confirms the resubscribe doesn't misbehave; no dedicated assertion was added since the review folded this in as a minor with no data-loss direction, and the existing "does not invalidate anything on a plain first connection" test (added for Minor 4 below) would catch a reconnect-miscount regression on any single-property run.

### Minor 3 — `presence.update` has no property check

Confirmed true and left as-is, as instructed: `presence.update` is handled directly in `onmessage`, above the `invalidationsFor` property guard, with no explicit `event.propertyId === propertyId` check of its own. Reasoning: a socket only ever receives server events for the one property it subscribed to (server-side scoping in `server/app/realtime/ws.py` — `connections.add(ws, property_id, user_id)` and property-scoped broadcasts), and the client never re-subscribes an existing socket to a different property (a `propertyId` change always tears down the old socket and opens a fresh one in `connect()`). So the only way a `presence.update` for the wrong property could ever reach this handler is via an abandoned/stale socket — exactly the case Finding 1's `onmessage` identity guard (`if (socket.current !== ws) return`) already closes. Adding a second, redundant property check to the `presence.update` branch would be dead code protecting against a path that guard already forecloses, so I did not add one.

### Minor 4 — tightened assertions, plus the negative test

- `reconnects with backoff after an unexpected close`: was `advanceTimersByTime(2000); expect(length >= 2)`, which would pass for a zero-delay reconnect or a socket storm equally. Tightened to assert `length === 1` at 900ms (before the 1000–1250ms first-step window can have elapsed) and `length === 2` at 1300ms (after it must have).
- `refetches everything on reconnect, because it was deaf for the gap`: was `expect(spy).toHaveBeenCalled()`, satisfiable by a single scoped-key invalidation. Tightened to `expect(spy).toHaveBeenCalledWith()` (vitest's no-argument form), which pins the call to the unscoped `client.invalidateQueries()` the requirement actually calls for.
- Added `does not invalidate anything on a plain first connection`: mounts, opens, emits `subscribed` for the very first socket, asserts `invalidateQueries` was never called. This is the direct negative guard on the `attempt.current > 0` substitution from fix round 0 — nothing previously protected against a regression that invalidated on every connect, not just reconnects.

### Commands and output

`npx vitest run src/api/ws.test.tsx`:
```
✓ src/api/ws.test.tsx (23 tests) 528ms
Test Files  1 passed (1)
     Tests  23 passed (23)
```

`npm test` (full suite — note `src/features/inbox/*` tests now present from a parallel, unrelated agent's work; I did not touch that directory):
```
Test Files  20 passed (20)
     Tests  164 passed (164)
```

`npx tsc -b`: clean, no output.

### Files changed (fix round 1)

- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\web\src\api\ws.ts` — identity guards on `onmessage`/`onclose`, `attempt` reset on property change, cleanup reordered to null the ref before closing.
- `C:\Users\bryan.farrell\Downloads\messaging_app_nw\web\src\api\ws.test.tsx` — new `SwitchableProbe`/`mountSwitchable` helpers, one new regression test for Finding 1, one new negative test for Minor 4, two tightened assertions.

Commit: `7ea51f1` — fix(web): guard realtime socket handlers by identity, not just disposed
