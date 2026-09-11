# S1 — reskin + shell upgrade

Web only. This wave changes **chrome**, not screen content.

## Where this came from

The user supplied `score.png` at the repo root — a screenshot of SCORE, their own bid-estimator
app — as a reference for "a more professional look and feel". They were offered three tiers and
chose the middle one: **reskin + shell upgrade**. The tier they explicitly did NOT choose was
the one that would have reworked the data screens in SCORE's idiom and superseded
`docs/mockups/` as the design of record.

**So the hard boundary for this wave is:** everything inside the `<main>` content area still
belongs to `docs/mockups/`, which remains the binding fidelity reference. You are restyling the
frame and retuning the palette. You are not redesigning the Inbox, Board, Analytics, Admin or
Work Order screens, and you are not moving anything inside them.

**Open `score.png` and look at it before you write anything.** Sample its actual colours,
spacing and type sizes from the image rather than inventing values or trusting my prose
description of it.

---

## 1. The palette — token VALUES only

`web/src/index.css` holds 45 custom properties. **Dark is the default (`:root`); light is
`[data-theme='light']`.** Note that the reference screenshot is in light mode, so light is the
theme to match against it — but both themes must be retuned and both must be checked.

Two absolute rules, and they are the reason a previous full reskin on this project touched
**zero component files**:

- **Never rename a token.** Change values only. Every component and the Tailwind config map
  these by name.
- **Never hardcode a hex in a component.** The only sanctioned hardcoded colours in the entire
  client are in `web/src/components/PhoneFrame.tsx`, and they are covered by ruling D52.

### PhoneFrame is off limits

`PhoneFrame.tsx` deliberately hardcodes fixed iOS chrome and two bubble colour pairs, because
it depicts the guest's actual phone. Ruling D52 settled this after a full argument. **Do not
re-theme it, do not token-ify it, do not touch it.** A phone that restyles itself teaches an
operator something false about what the guest sees.

### The navy rail needs NEW tokens — this is the trap

In light mode `--nav` is currently `#ffffff`. The reference's rail is deep navy. Turning
`--nav` navy is the single highest-impact change in this wave — and the palette has **no
nav-specific foreground tokens**. `AppShell.tsx` currently paints rail text with `text-text3`
(`#667286` in light mode), which on navy is nearly invisible.

So **add** nav-scoped tokens. Adding is fine; renaming is not. Suggested set, name them as you
see fit but keep the convention:

- `--navText` — active/primary rail label
- `--navTextMuted` — inactive rail label
- `--navSection` — the small uppercase group heading
- `--navActiveBg` — the filled pill behind the active item
- `--navActiveText` — label on that pill
- `--navBorder` — the hairline between rail and content, and the group rules

Define them in BOTH theme blocks. In dark mode the rail is already dark, so these mostly
collapse to existing values — but define them explicitly anyway rather than leaving dark mode
inheriting by accident.

### Type

The body font is currently `'Space Grotesk'`. That is a geometric display face, and it is a
real part of why the current app reads as less serious than the reference, which uses a neutral
grotesque. **Switch the UI face to Inter with a system fallback stack**, keep a monospace stack
for the mono bits (property codes, room numbers, shortcuts, counts) which several screens rely
on. If Inter is not already a dependency, use the system UI stack rather than adding a webfont
download to the critical path — say which you chose and why in your report.

Also adopt from the reference: **tabular figures for all numerics** (`font-variant-numeric:
tabular-nums`), so columns of numbers align. Apply it at the mono/numeric level, not globally.

### Accessibility is not optional here

Every text/background pair you produce must clear **4.5:1** contrast (3:1 for large text and UI
borders). The navy rail is where this will bite. Check the pairs you actually ship, in both
themes, and put the measured ratios for the rail tokens in your report. The existing
`:focus-visible` outline uses `--accent` — verify it stays visible against the navy rail, and
give it a nav-scoped value if it does not.

---

## 2. The shell — `web/src/components/AppShell.tsx`

Read the current file first. It already has the bones: a 184px rail, a property lockup, an icon
nav, a theme toggle, a sign-out button and an avatar block.

### Grouped nav with uppercase section dividers

The `NAV` array is currently flat. Group it, with a small letter-spaced uppercase heading above
each group, as the reference does:

- **OVERVIEW** — Inbox, Board, Alerts
- **INSIGHTS** — Analytics
- **ADMIN** — Admin

**Ruling D62 — the ADMIN group holds the single `Admin` entry. Do not hoist the individual
admin screens into the global rail.** `docs/mockups/Admin.dc.html` has a 220px in-page sub-nav
that carries the three greyed Phase 2 items (Automations, Blocked numbers, Integrations) and
the caption "Greyed items arrive in Phase 2". Hoisting the admin screens would either duplicate
that navigation or force three permanently-disabled entries into the global rail. A single-item
group is on-idiom for the reference — `score.png`'s own rail has an `ACCOUNT` group containing
only `My Profile`. **Leave the admin sub-nav exactly as it is.**

Capability filtering must survive the regrouping: `needs` is an OR, an empty `needs` means
always visible, and **a group with no visible items renders nothing at all — not an empty
heading.** Corporate and dept_staff see very different rails; verify both.

### The brand lockup carries the property switcher (ruling D64)

The property switcher is currently a `Dropdown` at the foot of the rail. Move it onto the
lockup at the top: clicking the property opens the switcher. That is where the reference puts
tenant identity and it is the standard multi-tenant pattern.

Carry the existing behaviour over untouched — `setPropertyId(m.propertyId)` followed by
`navigate(landingPath(m.role), { replace: true })`, because the new property's role may differ.
Keep the single-membership case rendering no switcher affordance at all, exactly as today.

### A global top bar

New, thin (~44–48px), spanning the content column to the right of the rail. It takes over what
is currently crammed into the rail's foot:

- **Right side:** the `Ctrl+K` palette trigger, the user's name with role, the theme toggle, and
  Sign out. Match the reference's treatment — a bordered pill for the palette trigger with a
  keyboard-shortcut badge, quiet icon buttons for the rest.
- **Left side:** leave it for context text. Do not invent breadcrumbs.

The screens keep their own headers — the reference stacks a thin global bar above a content
header too, so two levels is on-idiom and not a mistake.

The rail's foot is emptied by this. The avatar block stays at the foot as the ACCOUNT analogue,
or moves to the top bar with the user menu — your call, but make it deliberate and say which in
your report.

### The Ctrl+K command palette

**Ruling D63 — this is a NAVIGATION palette, not a record search, and that is a verified
constraint, not a shortcut.** The only `q=` search parameter anywhere on the server is
`server/app/api/quick_replies.py:16`. There is no conversation, guest or work-order search
endpoint — inbox search was already disclosed to the user as unbuildable in Phase 1 for exactly
this reason. **Make no new server calls from the palette.**

What it offers: every nav destination the user can see, every admin sub-section, switch property
(one entry per membership), toggle theme, sign out.

- Opens on `Ctrl+K` and `Cmd+K`. Closes on `Escape` and on selection.
- Type to filter; Up/Down to move; Enter to activate.
- **Entries are filtered by the same capabilities the rail uses.** A palette that offers a
  destination the user cannot reach, or that lists admin sections to a non-admin, is the defect
  to avoid here.
- Focus moves into the input on open and **returns to the trigger on close**. Trap focus while
  open. Give it `role="dialog"` with an accessible name, and the listbox/option roles for the
  results.
- Do not register the shortcut so that it steals `Ctrl+K` while the user is typing in the
  message composer or any other text input — check that first.

Keep it in its own component file. Do not put a 200-line palette inside `AppShell.tsx`.

---

## 3. The `cn` / tailwind-merge hazard (ruling D69) — read this before you write a single class

A previous implementer on this project discovered, and confirmed in a real browser with
`getComputedStyle`, that **`cn` does not resolve Tailwind class conflicts and there is no
`tailwind-merge` dependency.** When a `className` override collides with a base class, the
class-string order is irrelevant — **CSS source order decides**, which here means the order of
the token array in `tailwind.config.js`. So a colour override you write can silently do nothing,
and `npx tsc -b`, `npm run lint` and the entire test suite will all pass over the dead override.
It worked around its own case with `!bg-noteBg`-style important overrides.

You are the wave most exposed to this, because restyling chrome means writing exactly these
overrides. So:

- **Evaluate adding `tailwind-merge` to `cn`.** It is the standard fix and it makes overrides
  behave the way every developer on this codebase already assumes they behave.
- **If you add it, the regression risk runs the other way:** overrides elsewhere in the client
  that have been silently dead may suddenly become live, changing screens this wave is not
  supposed to touch. Hunt for them deliberately — grep for `className=` colour utilities passed
  into components, check the screens they belong to, and report what changed.
- If you judge the risk too high to take inside this wave, say so and keep the `!important`
  workaround as the house pattern. Either answer is acceptable; an unexamined one is not.
- Either way, **verify in a browser that the rail and top-bar colours you ship are actually
  applied**, with `getComputedStyle` rather than by eye. That is how this was caught the first
  time.

**Two facts a later reviewer established, which sharpen this:**

- Tailwind here is **`^3.4.13`, where the `!` PREFIX is the correct important syntax**. Tailwind
  v4 uses the suffix form, so every `!`-prefixed class breaks *silently* on a v4 upgrade. Right
  now there is exactly **one** `!`-modifier use in the entire client, so the idiom has not spread
  — which is the argument for fixing `cn` properly now rather than letting it become the house
  pattern.
- The workaround has **already caused an accessibility defect once**. `!border-noteBorder` on the
  composer's textarea beat `focus:border-accent`, and since `Textarea` pairs `focus:outline-none`
  with `focus:border-accent` as its *only* focus affordance, a keyboard user tabbing into that
  field got no visible focus state at all. The implementer who wrote the workaround did not
  notice it had done this. **When you write any `!` override on an interactive element, check the
  focus state specifically.**

### One test guarding focus WILL LIE TO YOU (ruling D86)

`Composer.test.tsx`'s "keeps a focus indicator in Note mode" asserts only that the `className`
**string** contains `focus:!border-accent`. jsdom computes no cascade and no specificity, so that
test passes whether or not the rule actually wins.

That class exists because an earlier `!important` override silently removed the note composer's
only focus indicator. The rule currently wins by **specificity** — `focus:!border-accent` is
(0,2,0) against `!border-noteBorder`'s (0,1,0), and CSS resolves ties among `!important`
declarations by specificity before falling back to source order.

You are the wave most likely to rewrite that className or reorder the token array. **If you touch
it, verify the focus border in a real browser in both themes with `getComputedStyle`** — the test
will stay green either way, so it is not your safety net here.

### F5 — an inverted selected-state metaphor that is yours to fix (ruling D74)

R1's reviewer found this and it is a **token relationship** problem, not a component one, so it
belongs to you rather than to a component patch:

`Composer.tsx:281` renders the active tab as `bg-surface` inside a `bg-surface2` track. In light
mode `--surface` (`#ffffff`) is **lighter** than `--surface2` (`#eef2f7`), so the active tab
reads as a raised pill. In dark mode `--surface` (`#171d26`) is **darker** than `--surface2`
(`#1c2430`), so the identical markup reads as an inset well. Both are legible; the *metaphor
inverts* between the two supported themes.

You are retuning all 45 values, so fix the relationship rather than patching the component:
decide deliberately whether `surface` sits above or below `surface2` in lightness, keep that
consistent in both themes, and check the other selected/raised surfaces in the product against
whatever you decide. If you conclude a component change is genuinely required instead, say so —
but do not leave the inversion in place.

## 3b. One unrelated item, SEPARATE COMMIT (ruling D96)

The admin screens' shared test helper answers a PATCH by echoing back whatever the test sent
(`{...SETTINGS, ...sent}`). That models a server which accepts anything — including values the
real one refuses, and values the real one would rewrite.

It has already produced one defect: a test sent `{"name": null}`, the mock returned 200, the
component received `value={null}`, and React emitted two warnings **that no test failed on**. It
was found by grepping stderr, not by a red suite.

A reviewer then established the hazard is broader than the one case. The default handler models
**two** impossible behaviours:

- **refusal** — any `null` on `name`, `currency` or `timezone` is rejected by the real server;
- **normalisation** — the real server upper-cases `currency` and reformats `smsNumber` to E.164,
  and the screen's own hint copy tells the admin to expect that. The mock does neither.

So a future test that asserts what the screen displays *after* a save would assert a lie and
pass.

Harden the default handler so it refuses what the server refuses and normalises what the server
normalises, rather than leaving each test to remember an override. That is the same argument
that chose a required `subjectId` prop over a per-call-site `key`: a safe default beats a
remembered convention. Keep it in its own commit — it is nothing to do with the reskin.

## 4. What you must NOT do

- Do not change anything inside the `<main>` content area — no screen layouts, no tables, no
  cards, no per-screen headers. That content belongs to `docs/mockups/`.
- Do not build the dark section-header bars, the inline chips, or the right summary rails from
  the reference. That was the tier the user declined.
- Do not touch `PhoneFrame.tsx`.
- Do not rename a single token.
- Do not add a server call.
- Do not commit the stray `r1-*.png` verification screenshots or `score.png` from the repo root.
  `score.png` is the user's own file — leave it exactly where it is.

## 5. Verify before you commit

- **The web suite.** It is at **489 passing, 0 failed** (50 files) and the server at **347**;
  beat the web number and break neither.
  `AppShell.test.tsx` WILL break when you restructure the rail, and updating it is part of the
  work, not a regression. Add coverage for: the grouped rendering, a group with no visible
  items rendering nothing, the palette opening/filtering/navigating, and the palette's
  capability filtering.
- `npx tsc -b` — clean, and no `.d.ts` emitted under `tests/`.
- `npm run lint` — exits 0.
- The Playwright e2e specs under `web/tests/e2e/`. **Read them first**: sign-out and the
  property switcher have MOVED, so any spec that selects them by position in the rail will
  break. Update the selectors; do not weaken an assertion to make it pass.
- **Look at it.** Run the app and check both themes — the rail, the top bar, the palette, and at
  least one dense screen. Attach or reference screenshots in your report. Put verification
  screenshots in this workspace directory, not in the repo root.

## 6. Report

Full report to `shell-S1-report.md`: the colour values you sampled and where from, the new nav
tokens and their measured contrast ratios in both themes, the font decision, what moved in the
shell, the palette's entry list and how capability filtering is applied, and a "Found but not
fixed" section.

Return in your final message ONLY: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT /
BLOCKED), commit shas, a one-line test summary, and your concerns. Keep it short — that text
lands in the controller's context.

If any instruction above is wrong — a token that does not exist, a contrast pair that cannot be
made to work, a test that cannot fail — **say so and do the correct thing instead.** Three
implementers on this project have caught defects in brief text and it has been the single
highest-value thing they did. Never make production code less correct in order to make a test
deterministic. Do not dispatch subagents.
