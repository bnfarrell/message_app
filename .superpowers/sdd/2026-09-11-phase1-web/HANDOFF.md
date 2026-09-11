# Resume here — Phase 1 web build

Rewritten 2026-09-11 at commit `e6fbfb8`, branch `main`, working tree clean.
Supersedes the earlier version, which described the state before the final review.

## Read these, in this order

1. `progress.md` — **the recovery map.** The pre-flight conflict scan, rulings D1–D55, and a
   completion line per task naming its commits and review outcome. Trust it and `git log`
   over any recollection. Read its LAST 250 lines first: that is the final review, the
   mockup-fidelity sweep, and the restoration waves.
2. `docs/superpowers/plans/2026-09-11-phase1-web.md` — the 21-task plan. Each task's brief is
   already extracted to `task-N-brief.md` here.
3. `docs/superpowers/specs/2026-09-10-hotel-engagement-phase1-design.md` — the spec the plan
   argues from, and the binding authority when the plan contradicts itself.

Process is `superpowers:subagent-driven-development`: one implementer per wave, an independent
reviewer per diff, fix rounds, scoped re-reviews.

## State

- **Tasks 1–21: complete and reviewed clean.**
- **Whole-branch final review: done.** Verdict "ready to merge, with fixes". It found no
  cross-tenant or above-role leak — the thing it was sent to hunt is not there. It confirmed
  three defects (A presence, B a CRITICAL exponential job-row race, C untyped E2E specs) and,
  in an added mockup-fidelity sweep, nine undisclosed demotions from the approved mockups.
- **Correction fix wave: complete**, 8 commits `336d9ad..e6fbfb8`. Server 258 pass, web 366,
  `npx tsc -b` clean, `npm run lint` now exits 0 (that accepted gap is CLOSED), Playwright 2
  pass, `/sim` verified absent from `web/dist/`.
- **Fix-wave scoped re-review: RETURNED CLEAN.** All nine sections addressed. It independently
  confirmed the fixer's refusal of a prescribed test that could not fail, and verified the job
  -claim CAS on both SQLite and PostgreSQL. One residual it raised that was NOT a brief item:
  `activePropertyId` is cleared on explicit logout but NOT on silent session expiry, because
  `RequireAuth`'s 401 path never calls `useLogout`. Assigned to A3 (ruling D56).
- **Restoration R1 (inbox): COMPLETE**, 3 commits `e6fbfb8..28e8b97`, web 381 passing. Its
  review is dispatched.
- **R2 (board / work orders: I4, I5, I6): not started.** Brief at `restore-R2-brief.md`.
- **R3 as originally briefed is SUPERSEDED** — see below. `restore-R3-brief.md` still holds M8
  (analytics custom range) and M12 (simulator PMS buttons), which are NOT admin and survive as
  leftovers.

## Two NEW user directives arrived after the final review

**1. "Finish all the admin section."** The user was shown the precise gap table and chose the
middle scope: **through Property settings**. Quick-replies polish, Departments full CRUD, and a
live Property settings screen. Automations / Blocked numbers / Integrations STAY GREYED — no
models, no endpoints, no spec, and the mockup itself captions them Phase 2. This supersedes
ruling D51's second half and removes accepted gaps 5, 6 and 7 from the final report's gap list.
Split into three waves by ruling D59: `admin-A1-brief.md` (server), A2 (quick-replies screen),
A3 (Departments + Property settings screens + the D56 residual fix).

**2. "See score.png for a more professional look and feel."** `score.png` at the repo root is a
screenshot of SCORE, the user's own bid-estimator app. Offered three tiers, they chose the
middle: **reskin + shell upgrade**. Navy palette and type scale via token VALUES only, plus
grouped nav, brand lockup carrying the property switcher, a global top bar, and a `Ctrl+K`
navigation palette. **Screen content still belongs to `docs/mockups/`, which remains binding
inside the content area.** Brief at `shell-S1-brief.md`. Rulings D62–D64, D69.

## Where the waves actually stand

- **R1 (inbox restorations): COMPLETE.** `e6fbfb8..8094d4f`, clean after one fix round.
- **A1 (admin server endpoints): COMPLETE.** `28e8b97..0992aa8`, clean after **two** fix rounds.
- **A2 (quick-replies screen): COMPLETE.** `9ae2bac..4438a5b`, clean after one fix round.
- **A3 (Departments CRUD + Property settings + three separate commits): built and reviewed
  (spec PASS, quality PASS high, no Critical/Important).** Fix round 1 in flight — the
  `EditPanel` destructive carry-over per ruling D94, plus four Minors.
- **S1, R2, M8/M12: not started.** All briefs written, and both restoration briefs now open by
  pointing at `_CURRENT-CONTRACTS.md`, which wins over them.

Suites after A3: **server 347**, **web 477 / 0 failed**.

## Deployment — added mid-build at the user's request, outside the plan

The repo now deploys to Railway as **one service behind a Dockerfile**: node builds `web/`,
Flask serves the client and the API from one origin (auth is a cookie and the inbox holds a
WebSocket open, so a second origin would mean `SameSite=None` and CORS for nothing).

`origin/main` is now **current** — the 26-commit backlog was pushed and every wave since has
been pushed as it landed.

Four things were found only by chasing the deploy, each of which would have failed in a way
that did not name itself:

1. **No Postgres driver shipped at all.** The README documented `pip install "psycopg[binary]"`
   as a manual step, which an image cannot rely on. `psycopg[binary]` is now a dependency.
2. **A provider's `postgresql://` resolves to psycopg2**, which is not installed — so a pasted
   Railway URL raised `ModuleNotFoundError` for a driver nobody chose. `Config.from_env` now
   points bare Postgres URLs at psycopg 3, leaving explicit `postgresql+driver://` alone.
3. **The seeded fixture could not log in under `FLASK_ENV=production`** — every account is on an
   RFC 2606 reserved domain and `LoginRequest.email` is an `EmailStr`. Behind
   `ALLOW_TEST_EMAIL_DOMAINS=1`, off by default.
4. **`python -m seed.seed` failed outright against Postgres** — its `__main__` passed
   `reset=True`, which `run()` rightly refuses for any non-SQLite URL.

**The image itself is unverified** — Docker is not installed on this machine, so the first
Railway build is the real test. `npm ci` was checked statically: the lockfile and manifest
agree, including the late ESLint additions.

## Do next, in order

1. **A1 fix re-review** returns → if it opens findings, that fix round WAITS until A2 commits
   (one writer in the tree).
2. **A2 report** → review package with BASE `9ae2bac` → scoped review → fix rounds.
3. **A3** (Departments CRUD screen, Property settings screen, un-grey the nav, plus the D56
   residual `activePropertyId` fix as its own commit) → review.
4. **S1** (reskin + shell) → review. Runs LAST of the admin work by ruling D65, so it restyles a
   complete admin section in one pass.
5. **R2** (board / work orders: I4, I5, I6), then the R3 leftovers M8 and M12.
6. **Push to `https://github.com/bnfarrell/message_app`** — standing authorization, origin set,
   currently behind at `6be8006`.
7. Final report to the user, carrying the accepted-gaps list below and the full `Ruling:` list
   from the ledger (`grep -n 'Ruling:' progress.md` — it runs to D86 and counting).

## Contracts later waves must code against

- A PATCH that receives an explicit `null` for a non-nullable field returns **400** with
  `details` naming the **camelCase** field, e.g. `{"escalationMinutes": "required"}`.
- `ValidationFailed` is **400** on this project, never 422. (422 is `ConsentError` alone.)
- `locale` is bounded 1–8 on both create and patch.
- Property settings exposes three typed keys out of the settings bag — `slaMinutes`,
  `autoResolveHours`, `helpText` — and `helpText` is **guest-visible** (the automatic HELP reply).
- Editing `slaMinutes` does NOT retro-update existing `slaDueAt`; it applies from the next
  inbound message. The UI must say so.

## Standing instructions from the user

- Run autonomously. Decide, do not ask. Record every call as a `Ruling:` in the ledger with
  what it costs if wrong.
- Write the ledger entry for a dispatch **in a separate tool call, after the dispatch returns
  an agent id.** "Review dispatched" has twice been written without a dispatch.
- **Never state a seed or data fact in a dispatch without querying that exact thing first.**
  Implementers have caught three fabricated seed facts.
- Never make production code less correct to make a test deterministic.
- Tell every implementer to report a defect in its brief rather than paper over it. That
  instruction has now caught a bad brief three times, most recently a prescribed regression
  test that passed against the unfixed code.

## Accepted gaps — surface these in the final report, they are deliberate

1. Seed does not match spec §8: opted-out guest Lena Park has **0 conversations**, there is no
   no-stay conversation, and **Property B has 0 conversations**, so the property switcher lands
   on an empty inbox.
2. `server/app/domain/analytics.py:57` buckets hours by raw UTC, not the property's
   `America/New_York` — the manager's chart is shifted 4 hours.
3. No work-order photo upload (no Phase 1 endpoint) — a visible difference from
   `WorkOrder.dc.html`.
4. ~~No ESLint config~~ — **CLOSED** in the fix wave, `npm run lint` exits 0.
5. ~~Quick-reply `category` has no UI input; `locale` not patchable~~ — **being built in A1/A2.**
6. ~~`Admin.dc.html`'s "Insert:" token helper chips~~ — **being built in A2**, and with FIVE
   chips, not the mockup's four: `domain/quick_replies.py:15-16` defines `VARIABLES` as five and
   the mockup omits `property_name` (ruling D68, a disclosed divergence).
7. ~~Property settings stays greyed~~ — **being built in A1/A3.** The user authorized the server
   endpoint that ruling D51 had declined to add.
9. **`StayOut` carries no rating and no conversation count**, so `Main.dc.html`'s "1 conv" and
   "5★" on the Previous stays rows cannot be rendered (found by R1).
10. **Seed cannot demonstrate "Previous stays" at all**: 106 guests against 106 stay rows, with
   no guest having more than one — so the section renders empty for every guest, including
   guests whose denormalised `stayCount` claims "4th stay". A seed self-inconsistency that
   sharpens gap 1.
11. **`cn` does not resolve Tailwind class conflicts and there is no `tailwind-merge`** — a
   `className` colour override can silently no-op, and tsc, lint and the whole suite pass over
   it. Assigned to S1 to evaluate (ruling D69).
8. **M11** guest-panel "Work orders + New", **M13** inbox search (no server support in Phase 1),
   and the live-preview half of **M9** were offered to the user and NOT selected — disclosed
   rather than built.

## Running it

`start.bat` at the repo root cold-starts both halves and opens a browser.
API on **http://127.0.0.1:5200**, web client on **http://127.0.0.1:5173**.
Login `ava@hvh.test` / `Password123!` — but she is an **`agent`** and CANNOT reach Admin.
Use **`alex@hvh.test`** for the admin screens. I stated ava as the admin login in several
briefs; an implementer queried the DB and the live server (403) and corrected it.

The API alone serves no pages — `GET /` is a 404 by design. The web client is the surface.

**Port note (ruling D47, commit `7d912e2`):** 5000 collided with another app on this machine;
the user also ruled out 5050, 5100 and 8000. 6000 is unusable in any case — browsers return
ERR_UNSAFE_PORT. 5200 was chosen by test-binding candidates on this host. `PORT` in the
environment still overrides everything.

## Two disciplines that are load-bearing here

- The palette is 45 CSS custom properties in `web/src/index.css`, mapped into Tailwind by name.
  A full reskin touched **zero component files**. Change token values, never token names, and
  never hardcode a hex in a component. The only sanctioned hardcoded colours in the client are
  the iOS chrome and two bubble pairs in `PhoneFrame.tsx` (ruling D52) — dev-only, and not a
  precedent.
- `web/src/auth/capabilities.ts` — **note the path, it is `auth/`, not `lib/`; a dispatch of
  mine sent an implementer to the wrong one** — is byte-for-byte `server/app/auth/permissions.py`.
  The client is never the enforcement point, but the UI must gate on the same capability the
  server checks or a role gets a button that 403s. Two live traps found this way: `corporate`
  has `manage_admin` but NOT `reply`, and `dept_staff` lacks `view_all_conversations`, which
  `GET /guests/<id>` requires.
