# Parked findings and deferred minors — Phase 1 web build

Extracted from progress.md for the final whole-branch review to triage.
Each block below is verbatim ledger text with its line number in progress.md.

101:**M1 — Minor (deferred): Task 5's `SessionProvider` `useMemo` depends on `logoutMutation`,**
102-whose identity changes every render, so the memo never holds and every consumer re-renders. Not a
103-correctness problem and not worth a fix round; noted for the final review to triage.
104-
105-Scan complete: 4 defects ruled on and patched into the plan, 1 minor deferred.
106-
107----
108-
--
430:  Minors parked for final-review triage (both real, neither blocking):
431-  - **No test asserts focus is restored to the pre-open element on an ordinary close.** This is a
432-    pre-existing gap, not a regression — but it is the one behaviour I named as load-bearing when
433-    dispatching the review, and it is currently verified only by code inspection. `Dialog` is
434-    consumed by Tasks 15 and 16 (create-work-order, archive, transition-reason). I am parking
435-    rather than opening a round because Minors do not enter the fix loop, and flagging it here so
436-    the final review can triage it into its single fix wave.
437-    Ruling: park, do not extend Task 4's loop for a coverage gap.
--
440:    reasonable cost. Minor; parked with the above.
441-
442-Task 6: implementer returned DONE, commit e68a928. Server 256/256 (247 baseline + 9 new), web
443-        52/52 including the types staleness guard, so the schema/type regeneration round-tripped
444-        correctly. No defect found in the brief.
445-        Noted, no action: my brief predicted a 405 on the RED run for the PATCH tests; Flask
446-        actually returns 404 for a path with no registered rule. Plan text inaccuracy, harmless.
447-Task 6: review dispatched (sonnet) against e6e486f..e68a928.
--
470:  Minor parked, and **nominated for the final review's fix wave**:
471-  `test_patch_prefs_merges_rather_than_replacing` only ever writes the single `theme` key, so it
472-  would pass equally against a buggy `prefs = {}` implementation — it cannot currently distinguish
473-  merge from replace. The shipped code genuinely merges, so this is a coverage gap rather than a
474:  defect. Unlike most parked minors this one is cheaply closable: seed an unrelated key directly on
475-  the row, PATCH `theme`, and assert the unrelated key survived. I am parking rather than opening a
476-  round because Minors do not enter the fix loop, but this is a good catch and the final wave
477-  should take it.
478-
479-Task 5: fix round 1/5 applied, commit f18983f. The implementer probed **both** flag spellings —
480-        `--no-webstorage` (Node 25+, tried first) and `--no-experimental-webstorage` (older) — and
481-        demonstrated the probe discriminates: true for the real flags on Node 26.7, false with
--
543:  Minors parked, both plan-mandated and inherited verbatim from my brief:
544-  - `ThemeContext`'s provider value is a fresh object literal each render, so every `useTheme()`
545-    consumer re-renders whenever `ThemeProvider` does. Same class as the `SessionProvider` memo
546-    issue I fixed at dispatch in D13 — but that one was in code not yet written, whereas this is
547-    already shipped and `ThemeProvider`'s re-render triggers are infrequent (session change or a
548-    theme mutation). Ruling: park for final-review triage rather than open a round for a
549-    cosmetic re-render.
550-  - A redundant `as Record<string, unknown> | undefined` cast; the generated type is structurally
--
606:  Parked, latent, no action now: `/api` and `/ws` remain string-prefix proxy keys, the same bug
607-  *shape* as `/a`. Grep confirms no collision exists today (every server blueprint prefix is
608-  followed by a slash, `/ws` is an exact route, and no client route in §5.2 begins with those
609-  strings), so this is not a defect — but whoever adds the next top-level client route should
610-  convert them to `'^/api/'` and `'^/ws$'` rather than rediscovering this. Both the implementer and
611-  the re-reviewer reached this conclusion independently and chose not to churn working config,
612-  which matches the project's "surgical changes" rule.
613-
--
639:  Minors parked: no dedicated test for the already-authenticated redirect off /login (logic
640-  verified by reading it); the login screen's "HV" logo mark uses 8px rather than 6px — I rule this
641-  correct as-is, a decorative logo is not a tag/avatar/timer and the radius rule does not reach it;
642-  and `client.ts`'s doc comment says the 401 hook is "installed by SessionProvider" when it is
643-  actually installed by `RequireAuth` — a one-line doc inaccuracy for the final wave.
644-
645-  Fix round 1 for Task 8 is QUEUED: Task 9's implementer holds the writer slot.
646-
--
775:  Minors parked: no test asserts the chip's interval is cleared on unmount (the cleanup is visibly
776-  present, so coverage-breadth only); and at exactly `remaining === 0` the label is `00:00` rather
777-  than `−00:00`. The latter is genuinely unspecified in the plan and "00:00" at the precise due
778-  moment is arguably the better reading, so I am not treating it as a defect.
779-Task 9: fix round 2 re-review — all three findings ADDRESSED, no new breakage. The re-reviewer
780-        traced `secondRole: 'admin'` through `harness.tsx` to confirm it genuinely sets
781-        `memberships[1].role` distinct from `opts.role` rather than being a same-value no-op;
782-        confirmed the test asserts on the router location via a `useLocation()`-driven sibling
--
1073:**D35 — Ruling: the ordinal bug is real, user-visible, and nominated for the final fix wave.**
1074-`GuestPanel` renders `${stay.stayCount}th stay`, which produces **"1th stay", "2th stay",
1075-"3th stay", "21th stay"** — wrong for most real values, and confirmed live (room 412 rendered
1076-"2th stay"). Stay counts cluster at 1-5, so this is visible on the majority of conversations. It is
1077-my brief's literal template string.
1078-By the rubric this is Minor and Minors do not enter the fix loop, so I am not opening a round for
1079-it. But it is exactly the kind of sloppy copy a hotel operator notices immediately, and it needs an
1080-ordinal helper (`1st/2nd/3rd/nth` with the 11-13 exception), not a one-character edit. Parking it
1081:**nominated for the final review's single fix wave**, alongside Task 6's merge-test gap and Task 4's
1082-focus-restore coverage gap.
1083-*Cost if wrong:* none — it is presentation-only and the fix is self-contained.
1084-
1085-Task 13: complete (commit c3380f0, review clean, no fix round needed).
1086-
1087-Task 12: review returned **Needs fixes**, 0 Critical, 3 Important, 3 Minor. The **factory audit was
1088-        exhaustive** — all 14 factories checked field-by-field against `types.generated.ts` with
--
1232:**D39 — Ruling: park the hanging-test concern, nominated for the final wave.** The implementer flags
1233-that A3's regression test would *hang* rather than fail fast if the loop ever came back, and
1234-deliberately left it rather than papering over it. They are right that the guard is what ships, but
1235-a hanging test in CI blocks a pipeline until an outer timeout and then reports something unhelpful
1236-instead of "the auth loop is back". An explicit short timeout on that one test would make the
1237-failure legible. Minor, so it does not open a round; adding it to the final wave's list alongside
1238-the `${n}th stay` ordinal, Task 6's merge-test gap and Task 4's focus-restore coverage gap.
1239-
--
1261:**D40 — Ruling: park the missing responsive regression test, nominated for the final wave.**
1262-The re-reviewer notes neither A1 nor A2 has an automated test — both were verified live only, and a
1263-future refactor of the breakpoint classes would have no safety net. It is right, and §5.2 is a spec
1264-requirement rather than polish. But jsdom cannot verify real layout, so the only available test is a
1265-class-presence assertion, which is weak evidence of behaviour while still catching the realistic
1266-regression (someone deleting `lg:block` or `md:hidden`). That trade is worth making, but it belongs
1267:in the final wave with the other parked items rather than opening another round now.
1268-Final-wave list now: the `${n}th stay` ordinal, Task 6's merge-test gap, Task 4's focus-restore
1269-coverage gap, A3's hanging-test timeout, and this.
1270-
1271-Task 15: fix round 1 applied, commit ce25419. 252 tests, tsc -b clean. Finding 1 verified with
1272-        deliberate-failure evidence showing exact expected/received instants against the
1273-        mount-capture version, **plus five stable reruns** to confirm the click-time computation did
1274-        not simply trade a silent bug for a flaky test — which was the whole risk of that fix.
--
1429:  Minors parked for the final wave: `agents.error` is never checked, so a failed agents fetch is
1430-  indistinguishable from an empty range; the department `max` is recomputed inside the `.map`
1431-  (O(n²), harmless at real volumes); no test exercises a zero-activity agent row with null
1432-  p50/p90/share; `BarChart` still renders gridlines for an empty series (verbatim from my own
1433-  reference code); and the export CSV covers only the four KPI cards rather than everything on
1434-  screen (the brief never specified a schema).
1435-
1436-**USER DECISION — palette reskin requested and chosen: "Slate & Steel Blue", dark stays default.**
--
1502:        and its single fix wave, which triages the parked items.
1503-
1504-**USER-REPORTED GAP: there is no way to sign out.** Verified rather than assumed:
1505-  - `useLogout()` exists (`api/hooks/auth.ts:26`) and does the right thing — POSTs
1506-    `/api/auth/logout` and clears the query cache on settle.
1507-  - `SessionContext` exposes `logout` on the session object (`SessionContext.tsx:16,31,61`).
1508-  - **Nothing in the UI calls it.** `grep -in "sign out|logout" AppShell.tsx` → no match.
1509-  - **The approved mockups omit it too.** `grep -io "sign out|log out" docs/mockups/*.dc.html`
--
1557:Parked, with reasons: dark `text3`/`surface2` slipped 5.41 → 4.96 but still clears AA; light
1558-`okText`/`okBg` sits at 4.48:1, a pre-existing hair under 4.5 and untouched by this diff;
1559-`Button.test.tsx`'s title still reads "uses the amber accent" while its assertion
1560-(`toContain('bg-accent')`) remains correct — cosmetic, and correctly left alone as out of scope.
1561-
1562-**Doc drift to carry forward:** the plan still narrates "amber accent" in several later-task
1563-sections. The implementer correctly left those alone (only two edit sites were in scope) and
1564-flagged them rather than silently rewriting. **Consequence: Tasks 20 and 21's already-generated
--
1604:  Minors parked: a category can still be set as its own descendant's parent (no cycle check —
1605-  Phase 2 hardening, not brief-required); and `LoginPage.test.tsx` still has no test that pre-seeds
1606-  a successful session and asserts the redirect fires — a pre-existing gap that **just became
1607-  load-bearing** because the redirect fix landed on exactly that branch. Nominating that one
1608-  prominently for the final wave; it is auth-path coverage, not cosmetics.
1609-
1610-Sign-out + done-chip contrast: review returned **Approved**, 0 Critical, 0 Important, 2 Minor
1611-        (both "checked, not a defect"). All three contrast ratios recomputed independently in
--
1752:Task 20: minor (deferred): PhoneFrame.tsx:180-181 — the chrome token-ification diverges from
1753-      the brief's literal sample code. Upheld by the reviewer; recorded so the final review
1754-      sees both sides.
1755:Task 20: minor (deferred): SimulatorPage.tsx:496 — quick-reply buttons use `rounded-full`, a
1756-      fourth radius outside the mandated 6/8/10 px system. Brief-given verbatim code, not an
1757-      implementer choice; the reviewer could not confirm from the diff whether the mockup
1758-      sanctions a pill here. FOR THE FINAL REVIEW to triage against docs/mockups/.
1759-
1760-Task 20: complete (commits ad89f5d..da8ac92, review clean).
1761-
1762-Task 20 minor #2 RESOLVED by the controller against the mockup, before the final review.
