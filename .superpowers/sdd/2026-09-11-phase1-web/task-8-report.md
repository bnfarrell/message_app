# Task 8 report — Login, routing and the provider stack

## Fix report — the `/a` proxy bug (Defect 5, resolved as its own change)

The coordinator confirmed Defect 5 as Critical and asked for it fixed as its own commit
before any later task relies on manual verification. Fixed in `acc7ebf`.

**The fix** — `web/vite.config.ts`'s proxy key changed from the string `'/a'` to the RegExp
`'^/a/'` (Vite treats any proxy key starting with `^` as a regex):

```diff
-      '/a': { target: API, changeOrigin: true },
+      // A string key is matched by prefix, and '/app/inbox'.startsWith('/a') is true --
+      // every hard navigation to an /app/* route was being proxied to Flask instead of
+      // served by Vite. A key starting with '^' is a RegExp instead: '^/a/' requires the
+      // slash right after '/a', so it still matches the asset short-link route
+      // (GET /a/<short_code>) without also matching /app/*.
+      '^/a/': { target: API, changeOrigin: true },
```

**`/api` and `/ws` — conclusion: no change needed, no collision now or under the planned
route table.** Both are matched by the same string-prefix rule as `/a` was, so in principle
they have the same *shape* of risk. But the actual collision on `/a` happened because `/a`
is a narrow prefix (2 characters) that happens to also be a proper prefix of an unrelated,
real, approved route (`/app`). Checked both for the same thing:

- Every server route under `/api` is registered with a Flask `url_prefix` that always has a
  slash immediately after `/api` (`/api/auth`, `/api/dev`, `/api/hooks`, `/api/p/<property_id>/...`,
  confirmed via `grep -rn "url_prefix" server/app`) — there is no `/api<something>` route without
  the slash for a client path to collide with.
- The one WebSocket route is registered as an exact match, `@sock.route("/ws")`
  (`server/app/realtime/ws.py:22`) — no sub-path variants exist.
- The client's route table is the fixed, approved one in the brief's §5.2 (`/login`, `/app/*`,
  `/sim`, `/`). None of those begin with `api` or `ws`, and any new client route would be added
  under `/app/*` per the established pattern — not as a new top-level prefix — so there's no
  foreseeable future route shaped like `/apiFoo` or `/wsFoo` either.

Left both as plain string keys; changing them would be an unrequested, unjustified edit to a
config that isn't broken.

**Verification 1 — a hard request to `/app/*` is now served by Vite, not proxied to Flask.**
With both the Flask dev server and `npm run dev` running again, a real GET (PowerShell
`Invoke-WebRequest`, `-UseBasicParsing`, no browser JS involved) to `http://localhost:5173/app/inbox`
(the `127.0.0.1` form still refuses to connect — see the pre-existing Vite IPv6-bind note in the
original report; `localhost` is the reachable equivalent used throughout this verification):

```
STATUS: 200
CONTENT-TYPE: text/html
<!doctype html>
<html lang="en" data-theme="dark">
  <head>
    <script type="module">import { injectIntoGlobalHook } from "/@react-refresh";
...
    <title>Harbourview — Guest Engagement</title>
```

That's Vite's SPA shell (React-refresh preamble, the app's own `<title>`), not Flask's
`{"error":{"code":"NOT_FOUND",...}}` envelope from before the fix.

Re-ran the two Step 9 checks this bug had blocked, with a real Playwright browser:

- **Direct navigation to a protected route:** hard-navigated to `http://localhost:5173/app/inbox`
  with no session. Final URL: `http://localhost:5173/login`; the login form rendered
  (Email/Password fields, "Sign in" button) — confirmed via a page snapshot. This is the
  `RequireAuth` → `Navigate to="/login"` path now actually reachable by a real page load.
- **Admin URL typed by hand as a non-admin:** signed in as `ava@hvh.test` (agent role, lands on
  `/app/inbox`), then hard-navigated to `http://localhost:5173/app/admin/users`. Final URL:
  `http://localhost:5173/app/inbox`; the page snapshot showed the `Inbox` / `Not built yet.`
  placeholder — the `RequireCapability` guard bounced her back, exactly as §5.2 specifies, and
  this time via an actual full page load rather than only the unit test.

**Verification 2 — the asset short-link route still proxies.** Found a real seeded short code
by signing in as Ava and calling the assets API in-browser (`GET /api/p/<propertyId>/assets`,
200, first row `"name":"Breakfast menu","shortCode":"k2pzyc"`). Requested
`http://localhost:5173/a/k2pzyc` (PowerShell `Invoke-WebRequest -MaximumRedirection 0`, so the
redirect itself is inspected rather than followed):

```
STATUS: 302
LOCATION: https://example.test/harbourview/breakfast.pdf
```

That 302 only comes from Flask's asset-redirect route — confirms `^/a/` still matches and still
reaches the server, while `/app/*` no longer does.

**Regression check:**

```
$ cd web && npm test
 Test Files  13 passed (13)
      Tests  73 passed (73)

$ npx tsc -b
(no output)
```

No change to any `.test.ts(x)` file was needed for this fix — it's a `vite.config.ts`-only change,
and the full suite (73 tests) plus a clean `tsc -b` both hold.

**Commit:** `acc7ebf` — "fix(web): stop the dev proxy from swallowing /app/* on hard navigation"
(separate from Task 8's own commit, `f76a15a`, per the coordinator's request).


## What I implemented

Exactly the brief's file list, TDD-ordered:

- `web/src/features/login/LoginPage.test.tsx` — the brief's 6 literal tests (2 defect fixes, see below)
- `web/src/features/login/LoginPage.tsx` — brief's literal component
- `web/src/components/ErrorBoundary.tsx` — brief's literal component
- `web/src/components/AppShell.tsx` — **deliberate one-line stub**, as the brief's task-context section instructs, so `AppLayout` compiles. Task 9 replaces it with the real 184px left nav. Not a nav, no feature work.
- `web/src/AppLayout.tsx` — brief's literal component (`ThemeProvider` + `AppShell` + `Outlet`)
- `web/src/routes.tsx` — brief's literal route table (`AppRoutes`, `Placeholder`, `LandingRedirect`, `RequireCapability`)
- `web/src/routes.test.tsx` — brief's literal 8 tests (1 defect fix, see below)
- `web/src/App.tsx` — replaced Task 1 placeholder with the brief's literal provider stack; `BrowserRouter` carries the same v7 future flags (`v7_startTransition`, `v7_relativeSplatPath`) as `renderWithProviders`'s `MemoryRouter` in `src/test/harness.tsx`
- `web/src/main.tsx` — added `QueryClient`/`QueryClientProvider` per the brief's literal config
- `web/src/vite-env.d.ts` — **new, not in the brief's file list** — required fix, see Defects Found
- `web/src/features/sim/SimulatorPage.tsx` — **new, not in the brief's file list** — deliberate placeholder stub, see Defects Found

## Defects found in the brief (fixed, not worked around)

### 1. `LoginPage.test.tsx`'s `respond()` helper answers every fetch call identically, but `LoginPage` makes two

`LoginPage` calls `useSessionQuery()` unconditionally on mount (to redirect an already-authenticated visitor), which fires `/api/auth/me` before any login POST. The brief's `respond(status, body)` used `vi.mocked(fetch).mockResolvedValue(...)` with **one shared `Response` instance** for every call. Two independent bugs fell out of that:

- **Premature redirect.** `respond(200, sessionFixture())` in "posts the credentials to /api/auth/login" also answered the mount-time `/api/auth/me` check with a valid session, so `LoginPage` rendered `<Navigate>` and unmounted the form before the test finished typing the password. Failure: `Unable to find a label with the text of: Password`.
- **Body-already-read.** A `Response` body can only be read once (verified directly: a second `.json()` call throws `"Body is unusable: Body has already been read"`). For the 401/429 tests, the mount-time `/api/auth/me` call consumed the shared `Response`'s body first; the login POST's `.json()` then failed, was swallowed by `api()`'s `.catch(() => null)`, and fell back to the generic `Request failed (401)` message instead of the server's actual text. Failures: `Expected "Email or password is incorrect", Received "Request failed (401)"` (and the 429 equivalent).
- **Wrong call assumed to be the login request.** "does not submit an empty form" asserted `expect(fetch).not.toHaveBeenCalled()`, not accounting for the mount-time `/api/auth/me` call that happens regardless of form validity. Failure: `expected "spy" to not be called at all, but actually been called 1 times` (the `/api/auth/me` call).

Fix (test-only, no change to `LoginPage.tsx`): `respond()` now uses `mockImplementation` returning a **fresh** `Response` per call, and answers only `/api/auth/login` with the given status/body — any other URL (the mount-time check) gets a 401 "not signed in". The "posts the credentials" test now finds the call by URL (`.find(([input]) => String(input) === '/api/auth/login')`) instead of assuming `mock.calls[0]`, and "does not submit an empty form" asserts no call was made *to `/api/auth/login`* rather than no call at all. This mirrors the `.find(([url]) => ...)` pattern `ThemeContext.test.tsx` (Task 7) already established for the identical class of problem.

### 2. `routes.test.tsx`'s default fetch mock (204) makes React Query log a spurious error

The brief's `beforeEach` stubs `fetch` to resolve `new Response(null, { status: 204 })` for everything. The 7 role-seeded tests never actually hit this (their session is pre-seeded into the query cache with `staleTime: Infinity`, so `/api/auth/me` is never fetched), but the 8th test ("sends an unauthenticated visitor to /login") does fetch it live. A 204 makes `api()` return `undefined` per its own logic (`if (response.status === 204) return undefined as T`), and TanStack Query logs `console.error("Query data cannot be undefined...")` even though the resulting redirect is correct. Fix (test-only): changed the default mock to a realistic 401 JSON body, which is what `/api/auth/me` actually returns when signed out. All 8 tests still pass; the console is now clean.

### 3. `import.meta.env.DEV` doesn't type-check — no `vite-env.d.ts` in the project

`routes.tsx`'s literal `const SimulatorPage = import.meta.env.DEV ? ... : null` fails `tsc -b` with `TS2339: Property 'env' does not exist on type 'ImportMeta'`, because nothing in the project references Vite's client types (`web/src/vite-env.d.ts` — the standard Vite scaffold file — was never created in Task 1, and `tsconfig.json`'s `types` array doesn't include `vite/client`). This is the first task to actually use `import.meta.env`. Fix: added `web/src/vite-env.d.ts` containing the one standard line, `/// <reference types="vite/client" />`. `npx tsc -b` (and `--force`) is clean afterward.

### 4. `routes.tsx`'s dynamic import to `./features/sim/SimulatorPage` has no module to resolve yet — breaks dev server and Vitest, not just the prod build

The brief explains the `/sim` exclusion in terms of a **production build**: `import.meta.env.DEV` folds to `false`, so Rollup drops the dynamic import entirely. That's correct for `vite build`. But `SimulatorPage.tsx` is created only in **Task 20**, and Vite's import-analysis plugin resolves every `import()` specifier it finds in a module's AST during **any** transform — dev server request or Vitest collection — regardless of whether the surrounding `DEV` ternary would execute that branch (the fold-and-drop only happens at production-build time). Without the target file, both `npm run dev` and `npx vitest run src/routes.test.tsx` fail outright with `Failed to resolve import "./features/sim/SimulatorPage"`.

This is the same category of gap as `AppShell` (a later task's module referenced before that task exists), just not called out in the brief's text the way `AppShell` explicitly was. I applied the identical treatment: created `web/src/features/sim/SimulatorPage.tsx` as a minimal, deliberate default-export stub (`export default function SimulatorPage() { return null }`) with a comment explaining why it exists and that Task 20 replaces it. This is not feature work — it renders nothing — and only exists to let `routes.tsx`'s literal, approved import shape resolve.

### 5. Pre-existing bug in `web/vite.config.ts` (Task 1, already committed) — blocks part of the brief's own live-verification step

Discovered during Step 9. `vite.config.ts`'s dev proxy (`'/a': { target: API, changeOrigin: true }`, intended for asset short-links) matches by string prefix. `/app/inbox` and `/app/admin/users` both start with `/a`, so **any hard navigation (full page load) to `/app/*` is proxied to the Flask server** instead of being served by Vite's SPA history fallback. Flask has no such route and returns its own JSON 404 (`{"error":{"code":"NOT_FOUND",...}}`), confirmed via direct Playwright navigation and cross-checked against `netstat`/`curl`/`Invoke-WebRequest`.

Client-side navigation (React Router's `history.pushState`, used for every redirect inside the running SPA) is unaffected — only a real address-bar navigation or page refresh to `/app/*` hits it. I did **not** fix this: `vite.config.ts` is not in Task 8's file list, it was written and committed in Task 1, and "Surgical Changes" means I shouldn't touch a file outside my brief to fix an unrelated task's bug. I'm reporting it because it measurably blocked two of the brief's own Step 9 bullets (see below) and will keep blocking `/app/*` hard-loads (including, e.g., a developer refreshing the inbox) until someone narrows the proxy rule — e.g. to `'/a/'` or a regex that doesn't match `/app`.

## What I tested and the results

**Full suite**, after both fixes:

```
$ cd web && npm test
 ✓ src/index.css.test.ts (4 tests)
 ✓ src/api/types.generated.test.ts (2 tests)
 ✓ src/api/client.test.ts (10 tests)
 ✓ src/lib/cn.test.ts (3 tests)
 ✓ src/auth/capabilities.test.ts (7 tests)
 ✓ src/components/ui/Avatar.test.tsx (4 tests)
 ✓ src/auth/SessionContext.test.tsx (6 tests)
 ✓ src/components/ui/Button.test.tsx (4 tests)
 ✓ src/components/ui/Dialog.test.tsx (7 tests)
 ✓ src/routes.test.tsx (8 tests)
 ✓ src/theme/ThemeContext.test.tsx (7 tests)
 ✓ src/components/ui/Dropdown.test.tsx (5 tests)
 ✓ src/features/login/LoginPage.test.tsx (6 tests)

 Test Files  13 passed (13)
      Tests  73 passed (73)
```

No `act()` warnings, no unhandled rejections, no React Router future-flag warnings, no stray `console.error` output.

## TDD evidence

**RED** — `cd web && npx vitest run src/features/login` (before `LoginPage.tsx` existed):
```
FAIL src/features/login/LoginPage.test.tsx [ src/features/login/LoginPage.test.tsx ]
Error: Failed to resolve import "./LoginPage" from "src/features/login/LoginPage.test.tsx". Does the file exist?
 Test Files  1 failed (1)
      Tests  no tests
```
Expected — `LoginPage.tsx` did not exist yet.

**GREEN** — same command, after `LoginPage.tsx` + the two test defect fixes:
```
✓ src/features/login/LoginPage.test.tsx (6 tests) 1394ms
 Test Files  1 passed (1)
      Tests  6 passed (6)
```

**RED** — `cd web && npx vitest run src/routes.test.tsx` (before `AppShell.tsx`/`SimulatorPage.tsx` stubs existed, `routes.tsx` present):
```
FAIL src/routes.test.tsx [ src/routes.test.tsx ]
Error: Failed to resolve import "./features/sim/SimulatorPage" from "src/routes.tsx". Does the file exist?
 Test Files  1 failed (1)
      Tests  no tests
```
(An earlier run, before I'd created `routes.tsx`/`AppLayout.tsx` at all, failed the same way on `AppShell` — exactly as the brief predicts in Step 8's note.)

**GREEN** — same command, after both stubs + the default-mock fix:
```
✓ src/routes.test.tsx (8 tests) 165ms
 Test Files  1 passed (1)
      Tests  8 passed (8)
```

## Live-server verification (Step 9)

Started both processes:
- `.venv\Scripts\python.exe server\dev_start.py` (background) — seeded and started Flask at `http://127.0.0.1:5000`.
- `npm run dev` in `web/` (background) — Vite ready at `http://localhost:5173/` (bound to `::1`, not `127.0.0.1` — `curl http://127.0.0.1:5173/` and PowerShell's `Invoke-WebRequest -Uri http://127.0.0.1:5173/` both got `Connection refused`; `http://localhost:5173/` worked, confirmed with `Get-NetTCPConnection`).

**Checks I ran, with a real browser (Playwright MCP tools were available, so I used them — not a claim, verifiable via the tool calls in this session):**

1. `curl`-equivalent GET on `http://localhost:5173/` → 200, returned the app shell HTML (`<title>Harbourview — Guest Engagement</title>`, Vite's dev script tags).
2. `POST http://localhost:5173/api/auth/login` through the Vite proxy with `ava@hvh.test` / `Password123!` (via PowerShell `Invoke-WebRequest`) → 200, body is the session JSON, and the response carries `Set-Cookie: sid=...; HttpOnly; Path=/; SameSite=Lax`.
3. Browser: navigated to `http://localhost:5173/` unauthenticated → client-side redirect chain `/` → `/app` → `/login` landed correctly, login form rendered with labeled Email/Password fields and a "Sign in" button. (Two expected 401 console entries from the unauthenticated `/api/auth/me` check — not errors in the app.)
4. Browser: typed `ava@hvh.test` / `Password123!`, clicked Sign in → landed on `/app/inbox`, rendered the `Inbox` / `Not built yet.` placeholder.
5. Logged out via `fetch('/api/auth/logout')`, signed in as `eli@hvh.test` / `Password123!` → landed on `/app/board?mine=1`, rendered the `Board` placeholder.
6. Logged out, signed in as `morgan@hvh.test` / `Password123!` → landed on `/app/analytics`, rendered the `Analytics` placeholder.

**Checks I could not perform, and why:**

- `http://localhost:5173/app/inbox` (direct/hard navigation) → redirected to `/login`, and "as Ava, visit `/app/admin/users` by hand → bounced back to `/app/inbox`" — both require a **hard** navigation to a path under `/app/*`. Confirmed via Playwright that this currently 404s: Vite's dev proxy (`web/vite.config.ts`, Task 1, not in my file list) forwards any path starting with `/a` — including `/app/*` — to the Flask server, which has no such route and returns its own JSON 404. This is a pre-existing bug unrelated to my changes (see Defect 5 above). I verified the equivalent behavior instead via client-side navigation (checks 3 and 5/6 above, which exercise the same `RequireAuth`/`AppRoutes`/`landingPath` code paths without a hard page load), and the admin-guard logic specifically is covered by the passing `routes.test.tsx` tests ("keeps a manager out of admin", "lets an admin into admin").

I did drive a real browser for this verification (Playwright MCP), not just static analysis — flagging this explicitly per the task's instruction not to claim more than was done.

## `npx tsc -b`

Clean, no output, both a normal run and `npx tsc -b --force` (to rule out stale `.tsbuildinfo` masking an error).

## Files changed

- `web/src/App.tsx` (modified)
- `web/src/main.tsx` (modified)
- `web/src/routes.tsx` (new)
- `web/src/routes.test.tsx` (new)
- `web/src/AppLayout.tsx` (new)
- `web/src/components/ErrorBoundary.tsx` (new)
- `web/src/components/AppShell.tsx` (new — **deliberate stub**, Task 9 replaces it; a plain pass-through, no nav)
- `web/src/features/login/LoginPage.tsx` (new)
- `web/src/features/login/LoginPage.test.tsx` (new, with the 2 documented defect fixes)
- `web/src/vite-env.d.ts` (new — required for `import.meta.env` to type-check; standard one-line Vite boilerplate, not scope creep)
- `web/src/features/sim/SimulatorPage.tsx` (new — **deliberate stub**, Task 20 replaces it; renders `null`, no feature work)

Commit: `f76a15a` — "feat(web): login, route table with role landings and capability guards"

## Self-review

- **Completeness:** every route in the brief's §5.2 table is present in `routes.tsx`. All six roles' `landingPath` values match the brief and the passing `capabilities.test.ts` (unchanged, from Task 5). `RequireCapability` bounces `agent` out of `/app/analytics` and `manager` out of `/app/admin/*`, both covered by passing tests and (for the non-admin cases) live-verified.
- **Quality:** `LoginPage` does not submit on an empty form (guarded in the `onSubmit` handler and covered by a passing test); shows the server's own message for both 401 and 429 (`login.error.message`, tested); the password field is `type="password"` (tested, and literally typed into in the browser).
- **Discipline:** nothing beyond the brief's literal code except the two stubs (both explicitly scoped and documented) and `vite-env.d.ts` (a required, non-feature fix). No nav was built in `AppShell`. No feature screens were built — `Placeholder` stands for all of them.
- **Testing:** all tests exercise real behavior — real `fetch` mock call shape (URL, method, body), real DOM state, real role-based routing — not implementation internals. Output is pristine: no `act()` warnings, no unhandled rejections, no React Router future-flag warnings, no stray console errors.

## Issues / concerns

- **Five real defects found in the brief**, all fixed at the test-scaffolding or project-config level, none by bending `LoginPage.tsx`/`routes.tsx`/`AppLayout.tsx`/`App.tsx`/`main.tsx` logic away from their literal, approved text. Full detail above.
- **Pre-existing bug in `web/vite.config.ts` (Task 1, already committed)**: the `/a` proxy rule intercepts hard navigations to `/app/*`, misrouting them to Flask's 404. This blocked two of the brief's own Step 9 checks (direct-navigation redirect-to-login, and the admin-bounce-by-hand check). I did not fix it — out of scope for Task 8's file list — but it should be looked at soon: it will affect real developers refreshing any `/app/*` page in dev, and every later feature task that verifies against the live dev server will hit the same wall for hard navigations. A minimal fix would be narrowing the proxy match, e.g. `'/a/'` (with a trailing slash) or a regex anchored to the asset-route shape.
- `web/src/features/sim/SimulatorPage.tsx` and `web/src/vite-env.d.ts` are additions beyond the brief's literal file list. Both are minimal, non-feature, and necessary for the brief's own literal code to build/run/test — flagged prominently here for the reviewer.
