# S1 — reskin + shell upgrade — report

Status: **DONE_WITH_CONCERNS** (the concerns are two pre-existing defects found on the way, not
anything this wave broke — see "Found but not fixed").

Commits, oldest first:

| sha | what |
| --- | --- |
| `c68c13a` | D96 — the property-settings PATCH mock now refuses and normalises like the server |
| `be203ba` | D69 — `cn` resolves Tailwind conflicts through `tailwind-merge` |
| `309084c` | the reskin, the grouped shell, the top bar and the Ctrl+K palette |

Tests: web **516 passing, 0 failed** (51 files) against a 489/50 baseline; server **347 passing,
0 failed** — re-run, not assumed. `npx tsc -b` clean with no `.d.ts` under `tests/`; `npm run lint` exit 0; `npm run build`
clean. Stderr read on every run — no React warnings.

Screenshots in this directory: `s1-inbox-dark.png`, `s1-inbox-light.png`, `s1-thread-dark.png`,
`s1-analytics-light.png`, `s1-admin-light.png`, `s1-palette-light.png`,
`s1-switcher-corporate.png`.

---

## 1. `score.png` was not on disk

It never reappeared at the repo root while I worked. Everything below is chosen from the written
description in the brief, not sampled from the image — so every hue here is mine and the user
should expect to adjust some of them. What I did not leave to judgement is legibility: every pair
that ships is measured, and the measurements are asserted in `src/index.css.test.ts` so they
cannot silently rot.

## 2. The palette

**Token names are unchanged.** Seven were added; nothing was renamed. `index.css.test.ts` still
pins the exact set, so an eighth cannot sneak in unnoticed.

The honest finding first: **the light palette was already about 80% of the reference before I
touched it** — very light cool grey ground, white cards, 1px cool-grey hairlines, 10px radii, no
shadows, near-black text with two muted steps, a saturated non-neon blue accent. I left
`--accent` (`#2563eb` light / `#4f8fd4` dark) and `--danger` exactly where they were, because
`#2563eb` *is* the reference's accent character and moving it would have been change for its own
sake. Four values changed, seven were added.

### Changed values

| token | theme | before → after | why |
| --- | --- | --- | --- |
| `--nav` | light | `#ffffff` → `#111b2e` | the deep navy rail. The single highest-impact change in the wave. |
| `--nav` | dark | `#0b0f14` → `#0a101c` | same navy identity in dark, still darker than `--bg` so the rail reads as its own ground. |
| `--surface` | dark | `#171d26` → `#1c2430` | swapped with `surface2` — see F5 below. |
| `--surface2` | dark | `#1c2430` → `#171d26` | swapped with `surface`. |
| `--sel` | dark | `#172231` → `#1d2a40` | after the swap, the old `--sel` sat a hair off the new `--surface2`, so a *selected* row and a *hovered* row in `AdminTable` and `ConversationList` became near-indistinguishable. Bluer and lighter now. Verified on the Inbox list (`s1-thread-dark.png`). |
| `--sel` | light | `#eff4fb` → `#e9f0fd` | same reasoning in the other theme: `#eff4fb` was one step from `--surface2` `#eef2f7`. |

### New nav-scoped tokens, with measured contrast

`AppShell` painted rail text with `text-text3`, which on navy is ~2:1. These are rail-scoped and
defined explicitly in **both** theme blocks rather than left to inherit.

| token | light (`--nav` `#111b2e`) | ratio | dark (`--nav` `#0a101c`) | ratio |
| --- | --- | --- | --- | --- |
| `--navText` — property name, hovered label | `#f4f7fb` | **16.02:1** | `#e8edf5` | **16.18:1** |
| `--navTextMuted` — inactive row, property code | `#a7b6cd` | **8.37:1** | `#93a2b8` | **7.34:1** |
| `--navSection` — uppercase group heading | `#8296b4` | **5.71:1** | `#8797ae` | **6.40:1** |
| `--navActiveBg` — the filled pill | `#2563eb` | **3.33:1** vs rail | `#2f66c2` | **3.44:1** vs rail |
| `--navActiveText` — label on the pill | `#ffffff` | **5.17:1** on pill | `#ffffff` | **5.53:1** on pill |
| `--navBorder` — rail/content hairline, lockup hover | `#2b3a57` | 1.51:1 | `#1c2740` | 1.28:1 |
| `--navFocus` — focus ring inside the rail | `#9dc2ff` | **9.50:1** vs rail | `#9dc2ff` | **10.50:1** vs rail |

Every *text* pair clears 4.5:1 (none of the rail labels are large text — 13px rows, 10px
headings — so none qualify for the 3:1 allowance). The active pill clears 3:1 as a UI component
against the rail and 4.5:1 for its own label.

`--navBorder` is deliberately below 3:1 and that is correct: it is a decorative rule between two
grounds that are themselves 16:1 apart, not a control boundary, so WCAG 1.4.11 does not apply to
it. Raising it to 3:1 would put a bright line down the rail that the reference does not have.

**`--navFocus` exists because the brief's check found a real problem.** The shared
`:focus-visible` rule uses `--accent`, which is only **3.33:1** on the light navy rail — it passes
1.4.11 by 0.33 and is visually weak on a dark blue ground. One extra rule scopes a brighter ring
to the rail:

```css
[data-nav-surface] button:focus-visible, [data-nav-surface] a:focus-visible {
  outline-color: var(--navFocus);
}
```

Verified with a **real keyboard Tab** in Chromium (a programmatic `.focus()` does not match
`:focus-visible` on a link, which is a trap worth recording): rail link outline computes to
`rgb(157, 194, 255) 2px solid` in both themes; the top bar, being outside the scope, keeps
`--accent`.

### F5 — the inverted selected-state metaphor (D74) — fixed in the tokens

The light theme forces the answer. `--surface` is the card colour and the reference's cards are
white, so `--surface` cannot go below `--surface2` in light. The invariant therefore had to be
**`--surface` sits above `--surface2` in lightness, in both themes**, and the fix in dark is a
straight swap of the two values.

Verified live with `getComputedStyle` on Composer's mode tabs:

| | track (`bg-surface2`) | active tab (`bg-surface`) |
| --- | --- | --- |
| light | `rgb(238,242,247)` | `rgb(255,255,255)` — raised |
| dark | `rgb(23,29,38)` | `rgb(28,36,48)` — raised |

The swap fixes two other places that had the same inversion without anyone filing them:
`BarList`'s bar track and `QuickReplyPalette`'s highlighted row were recessed in light and raised
in dark. No component file was changed for any of this. The invariant is now asserted per theme
in `index.css.test.ts` and the assertion goes red if the values are swapped back.

Knock-on checked and fixed: `--sel` in both themes (above). `--autoBg` in dark now equals the new
`--surface`, which is harmless — auto bubbles render on the thread ground, never on a card, and
carry their own `--autoBorder`.

### Type

**Inter, loaded from the same Google Fonts link that already carried Space Grotesk.** The brief
said to fall back to the system stack rather than "adding a webfont download to the critical
path" — but a webfont was *already* on the critical path, so swapping Space Grotesk for Inter
adds no request and removes a geometric display face that was a real part of why the app read as
less serious than the reference. That is strictly better than the system stack for matching a
neutral grotesque, so I took it. The stack still degrades to a neutral grotesque if the CDN is
blocked:

```
font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, system-ui, sans-serif;
```

Weights went from 500/600/700 to **400**/500/600/700 — body text at 400 was previously being
synthesised. JetBrains Mono is untouched.

Tabular figures are applied at the mono level, not globally:

```css
.font-mono { font-variant-numeric: tabular-nums; }
```

Every numeric that stacks into a column in this product already carries `font-mono` — room
numbers, SLA timers, property codes, badge counts, the analytics tables, the shortcut badge. The
UI face keeps proportional figures in prose, which is what the brief asked for.

## 3. What moved in the shell

- **Rail: 184px → 208px**, still `bg-nav`, now `border-navBorder`. It carries `data-nav-surface`,
  which is what the scoped focus rule keys on.
- **The `NAV` array became `NAV_GROUPS`** in a new `web/src/components/navModel.ts`, with
  `OVERVIEW` (Inbox, Board, Alerts), `INSIGHTS` (Analytics) and `ADMIN` (Admin). Headings are
  10px uppercase, 0.12em tracked, in `--navSection`.
- **A group with no visible items renders nothing** — not an empty heading. `visibleNavGroups()`
  filters items first and then drops empty groups. Verified in a browser with three real logins:
  `eli@hvh.test` (dept_staff) sees only OVERVIEW with Inbox/Board/Alerts;
  `casey@group.test` (corporate) sees all three headings with Inbox, Alerts, Analytics, Admin and
  **no Board**; `alex@hvh.test` (admin) sees everything.
- **Ruling D62 honoured:** the ADMIN group holds the single `Admin` entry. `AdminPage`'s 220px
  in-page sub-nav, its three greyed Phase 2 items and its caption are untouched. It now imports
  `ADMIN_SECTIONS` from `navModel` instead of keeping a private copy, so the rail, the sub-nav and
  the palette cannot drift apart. That is the only edit to a screen file in this wave and it moves
  a constant; nothing renders differently.
- **The property switcher moved onto the brand lockup (D64).** Clicking the property opens it.
  `setPropertyId` → `navigate(landingPath(m.role), { replace: true })` carried over verbatim. A
  single-membership user gets **plain text, not a dead button** — the lockup is only a `<button>`
  when there is somewhere to switch to. The accessible name survives the move through a visually
  hidden "Switch property", so both the screen-reader intent and the visible tenant name are
  present. `Dropdown` gained one optional `triggerClassName` that **replaces** the default trigger
  classes rather than merging with them, because the rail sits on a different ground from every
  other Dropdown in the app.
- **A new 48px top bar** spans the content column: `bg-surface`, `border-b border-border`. Right
  to left it carries the Ctrl+K trigger (bordered pill with a `<kbd>` badge), the user block,
  the theme toggle and Sign out. **The left side is deliberately empty** — the screens carry their
  own headers and the brief said not to invent breadcrumbs.
- **The avatar block moved to the top bar rather than staying at the rail foot** — my call, as
  offered. The reference has both a rail ACCOUNT group and a top-bar name, but this product has no
  profile screen to put in an ACCOUNT group, so a rail block would have been identity stated twice
  with nowhere to click. One identity block, in the bar that also holds sign-out, is the coherent
  reading. The rail is now purely navigation.
- **`PhoneFrame.tsx` untouched.** Not read for editing, not re-themed, not token-ified.
- Nothing inside `<main>` moved. The only screen file touched is the `ADMIN_SECTIONS` import.

## 4. The Ctrl+K command palette

`web/src/components/CommandPalette.tsx` — its own file, owns its trigger, its state and its
shortcut, so `AppShell` stays readable.

**Ruling D63 honoured: it makes no server call at all.** It is navigation, not record search.

Entries, in order, for a user who can see everything:

| group | entries |
| --- | --- |
| GO TO | every nav destination `visibleNavGroups(can)` yields — Inbox, Board, Alerts, Analytics, Admin |
| ADMIN | Users & roles, Departments, Quick replies, Digital assets, Resolution categories, Property settings |
| PROPERTY | one "Switch to «name»" per membership — **omitted entirely for a single-membership user** |
| SESSION | "Switch to light/dark theme", "Sign out" |

**Capability filtering is the same code path as the rail**, not a parallel list: the GO TO group
is literally `visibleNavGroups(can)`, and the ADMIN group is gated on `can('manage_admin')` — the
capability that also gates the `admin/*` route. An agent's palette is exactly
`Inbox, Board, Alerts, Switch to light theme, Sign out` and that full list is asserted, so an
entry appearing where it should not makes the test red. Corporate gets the admin sections and no
Board.

Behaviour: opens on `Ctrl+K` **and** `Cmd+K`; closes on Escape and on selection; focus enters the
input on open and **returns to the trigger on close**; Tab is trapped; Up/Down move, Enter
activates, typing filters. `role="dialog"` with `aria-modal` and an accessible name; the input is
a `combobox` driving a `listbox` of `option`s through `aria-activedescendant`. Empty result says
so rather than showing a blank panel.

**It does not steal Ctrl+K from a text box.** The document-level handler returns early when
`event.target` is an `input`, `textarea`, `select` or anything `contenteditable`. The test for it
mounts a real `<textarea>` alongside the palette and fails when the guard is removed.

All thirteen palette tests were mutation-tested: removing the text-box guard, removing the
`manage_admin` gate, swapping `visibleNavGroups(can)` for the unfiltered `NAV_GROUPS`, and
removing the focus-return each turn the suite red.

## 5. Verdict on `tailwind-merge`: **added**

I audited first rather than assuming — but **the audit matched colour utilities only, and that
turned out to matter**; see the correction at the end of this section. A script over every
`<Capitalised …>` JSX element in `src/` found **exactly two** colour `className` overrides passed
into components in the whole client:

- `EditPanel.tsx:91` — `<Button variant="ghost" className="ml-auto text-dangerText">`. `ghost`'s
  base is `text-text3`; `dangerText` is declared *after* `text3` in `tailwind.config.js`, so the
  override already won under source order.
- `ConversationList.tsx:52` — `<Badge tone="danger" className="text-dangerText">`, which is the
  same class the tone already applies. Redundant, not dead.

So **there were no silently-dead overrides to revive**, which is the regression the brief warned
about, and the measured risk of adding `tailwind-merge` was near zero. Against that: the hazard
had already produced one accessibility defect, and the `!`-prefix workaround breaks *silently* on
a Tailwind v4 upgrade. With only one `!` site in the client, fixing `cn` now is cheaper than it
will ever be again.

Pinned at **`^2.6.1`** — v3 targets Tailwind v4 and this project is on `^3.4.13`.

The important discovery, verified by probing the library directly: **tailwind-merge keys its
conflict groups on the important modifier**, so `!border-noteBorder` does *not* displace
`border-border3`; both survive in the attribute and `!important` still decides. Composer's note
mode is therefore byte-for-byte unaffected. Four tests in `cn.test.ts` pin all of this, including
that an unrecognised class (`shadow-[inset_3px_0_0_var(--accent)]`, `rounded-card`) is never
touched.

Full suite after the change: 498/498 with no warnings.

**Correction (fix round 1, F6 in the review).** The sentence that stood here originally —
"no visual change anywhere" — was wrong, and a controller relying on it would have been relying
on something untrue. The audit above matched `bg-`/`text-`/`border-` against the 45 token names,
so by construction it could not find a size conflict. Two **non-colour** overrides did revive,
both in `Button` and both reaching screen content: base `px-4` versus the ghost variant's
`px-2.5` (ghost buttons went 16px → 10px side padding), and `<Spinner className="h-4 w-4" />`
versus Spinner's own `h-5 w-5` (20px → 16px). The corrected claim is: **no colour override changed
anywhere, and two size overrides in `Button` began to take effect — which is the author's evident
intent finally being honoured, the pre-merge behaviour having been the bug.** Each affected
control was then measured and looked at in both themes; see "F2" in the fix round below.

### D86 — the focus test that cannot fail, verified in a browser instead

`Composer.test.tsx`'s "keeps a focus indicator in Note mode" asserts a `className` **string**, so
it stays green either way. I checked the real cascade in Chromium with `getComputedStyle`, in
both themes, after adding `tailwind-merge`:

| | light | dark |
| --- | --- | --- |
| Note mode, blurred | border `rgb(230,201,106)` = `--noteBorder` | `rgb(90,74,18)` = `--noteBorder` |
| Note mode, **focused** | border `rgb(37,99,235)` = `--accent` | `rgb(79,143,212)` = `--accent` |

The focus indicator is intact in both themes. (`outline-style` computes to `solid` there, which
looks alarming and is not: Tailwind's `outline-none` is `outline: 2px solid transparent`, not
`outline-style: none`. Pre-existing and correct.)

### The rail and top-bar colours, verified the same way

Not by eye. `getComputedStyle` on the live page, both themes:

| | light | dark |
| --- | --- | --- |
| rail ground | `rgb(17,27,46)` = `#111b2e` | `rgb(10,16,28)` = `#0a101c` |
| active row | `#ffffff` on `rgb(37,99,235)` | `#ffffff` on `rgb(47,102,194)` |
| inactive row | `rgb(167,182,205)` | `rgb(147,162,184)` |
| group heading | `rgb(130,150,180)` | `rgb(135,151,174)` |
| top bar | `#0f141a` on `#ffffff` | `#e6eaf0` on `rgb(28,36,48)` |

Every one matches the intended token exactly.

**One trap worth recording for the next implementer:** the Vite dev server does **not** pick up a
change to `tailwind.config.js` on HMR. Every new `nav*` utility was missing from the dev
stylesheet and the rail rendered with inherited colours, while `npm run build` emitted all of them
correctly. Restart the dev server after editing that file, and never trust the dev page to prove a
new token works.

## 6. Tests

489 → **516** (51 files), 0 failed, no React warnings in stderr.

- `AppShell.test.tsx` — 13 → 18. Added: grouped rendering with uppercase headings; an agent
  rendering *no* INSIGHTS or ADMIN heading at all; the zero-capability case asserted on
  `visibleNavGroups` directly (no role in the product holds zero capabilities, so miming it
  through a fake role would have been a lie); the lockup as plain text for one membership; the
  switcher on the lockup with its accessible name intact.
- `CommandPalette.test.tsx` — new, 13 tests, all mutation-tested.
- `index.css.test.ts` — 4 → 8. Added the per-theme rail contrast assertions and the per-theme
  `surface` > `surface2` invariant, both mutation-tested by putting the old values back.
- `cn.test.ts` — 3 → 6.
- `PropertySettingsAdmin.test.tsx` — 14 → 16 (D96 commit), all four affected tests mutation-tested
  against an echoing handler.

**Playwright.** Read both specs first. Neither selects sign-out or the property switcher, and
neither needed a selector change: `presence.spec.ts` picks a queue row by `a[href^="/app/inbox/"]`
(the rail's own link is `/app/inbox`, no trailing slash, so it still does not match) and clicks
`getByRole('link', { name: 'Board' })`, which the regrouped rail still exposes with that exact
name; `smoke.spec.ts` uses `getByRole('textbox')`, and the palette trigger is deliberately a
`<button>` with a `<kbd>`, not an input, so the composer stays the only textbox. `presence.spec.ts`
**passes**. `smoke.spec.ts` fails — see below; it fails identically on the pre-wave tree.

## 7. Found but not fixed

1. **`smoke.spec.ts` fails at the delivery-status step, and it is pre-existing.** The reply
   reaches the guest and the database records `delivery_status = 'delivered'` within two seconds,
   but the open thread keeps showing "Sending…" until the page is reloaded — so the delivered
   event is not reaching the mounted thread, or is not being applied to it. `presence.spec.ts`
   passes over the same socket, so the connection itself is fine. **Confirmed pre-existing:** I
   checked `web/` out at `8beea25` (the commit before this wave) and ran the same spec, and it
   fails at the same line with the same symptom. Nothing in this wave touches `api/ws`,
   `MessageBubble` or the thread. Worth its own investigation.
2. **`block()` in `index.css.test.ts` finds its selector by `indexOf` over the raw file**, so any
   comment mentioning `[data-theme='light']` silently redirects the light-theme assertions at the
   comment. I hit this within a minute of adding a comment and worked around it by rewording the
   comment; the helper itself is still fragile and should parse rather than string-search. I left
   it alone because hardening it is not this wave's job.
3. **The brief says "the admin screens' *shared* test helper".** There is no shared helper — each
   of the six admin test files defines its own `serve()`, and only `PropertySettingsAdmin`'s
   echoes the patch (`{...SETTINGS, ...sent}`). The other five answer a non-GET with a canned
   record, which does not have the D96 hazard. D96 is therefore correctly scoped to one file, and
   I fixed that one.
4. **The Admin sub-nav's active row is nearly invisible in light mode.** `bg-surface2` (`#eef2f7`)
   sits on the page ground `--bg` (`#f5f7fa`) — a 1.02:1 difference, carried almost entirely by
   the inset accent bar. Pre-existing, inside `<main>`, and fixing it would change a screen this
   wave is not allowed to touch. Visible in `s1-admin-light.png`.
5. **The seed property has been renamed** to "Holiday Inn Houston NW - Beltway 8 by IHG" (code
   still HVH) by an earlier session's use of the Property settings screen, which is why it appears
   that way in the screenshots rather than as "Harbourview Hotel". Not a defect; noted so a
   reviewer does not chase it.
6. **`server/data/app.db` and `app.db-wal` are tracked and are dirty** after running the app and
   the e2e suite. Not staged in any commit here. A dev database probably should not be tracked,
   but removing it is not this wave's call.
7. **The brief file itself (`shell-S1-brief.md`) is modified in the working tree** — the
   controller's own edit replacing the "open score.png" instruction with the written description.
   Left uncommitted and untouched; it is not mine to commit.

---

# Fix round 1

Six items from the review. Web **520 passing / 0 failed** (51 files), server **347**; `tsc -b`
clean with no `.d.ts` under `tests/`, lint 0, build clean, stderr read — no React warnings.

Screenshots added: `s1-fix1-departments-light.png`, `s1-fix1-dialog-light.png`,
`s1-fix1-dialog-dark.png`, `s1-fix1-loading-dark.png`, `s1-fix1-thread-dark.png`.

## F1 — the rail focus ring bled onto the property-switcher menu. Fixed.

The finding is correct and it was a regression in the control this wave moved.
`[data-nav-surface] button:focus-visible` matched every button *inside* the `<nav>`, and the
`Dropdown` menu panel renders inside the rail while sitting on `--surface`.

```css
[data-nav-surface] [role='menu'] button:focus-visible { outline-color: var(--accent); }
```

More specific than the rule above it (0,3,1 against 0,2,1), so it wins without reordering
anything. Verified in Chromium with a real keyboard Tab as `casey@group.test`, who has two
memberships, in both themes:

| | menu item ring | menu panel | ratio |
| --- | --- | --- | --- |
| light, before | `rgb(157,194,255)` | `rgb(255,255,255)` | **1.81:1** — fails 1.4.11 |
| light, after | `rgb(37,99,235)` = `--accent` | `rgb(255,255,255)` | **5.17:1** |
| dark, after | `rgb(79,143,212)` = `--accent` | `rgb(28,36,48)` | **4.62:1** |

And the rail's own links still get `--navFocus` (`rgb(157,194,255)`) in both themes, so the scope
narrowed exactly as intended and nothing else moved.

## F2 — the "no visual change anywhere" claim was wrong. Corrected, and the sizes verified.

**The claim in §5 of the original report is false as written, and the correction matters more
than the fix.** My audit script matched colour utilities only (`bg-|text-|border-` against the
45 token names), so it could not have found a `px-`/`h-`/`w-` conflict. Two non-colour overrides
did revive when `tailwind-merge` landed, and both are inside screen content:

- `Button.tsx:25` — base `px-4` versus the `ghost` variant's `px-2.5`. Now 10px.
- `Button.tsx:31` — `<Spinner className="h-4 w-4" />` versus Spinner's own `h-5 w-5`. Now 16px.

**The corrected claim: no *colour* override changed anywhere; two non-colour overrides in
`Button` began to take effect, and in both cases that is the author's evident intent finally
being honoured — the pre-merge behaviour was the bug.** §5 has been amended in place.

I am not pinning the old sizes back. Measured and looked at, in both themes:

| control | measured | reads correctly? |
| --- | --- | --- |
| Departments EditPanel **Delete** (ghost) | padding 10px/10px, **63 × 44px** | Yes. A borderless red text action beside two filled buttons; 10px side padding is what it wants, and the 44px height rule is untouched. `s1-fix1-departments-light.png`, `s1-fix1-loading-dark.png`. |
| Dialog **close ✕** (ghost) | padding 10px/10px, **31 × 44px** | Yes. Down from ~45px wide, still well clear of WCAG 2.5.8's 24 × 24 minimum, and the focus ring around it is unmistakable. `s1-fix1-dialog-light.png` / `-dark.png`. |
| **Spinner** in a loading Button | **16 × 16px**, track `rgb(102,116,138)` = `--border3`, head `rgb(79,143,212)` = `--accent` | Yes. Proportionate inside a 44px button next to 14px text; at 20px it crowded the label. `s1-fix1-loading-dark.png`. |

`MessageBubble`'s Retry is the same `ghost` variant with no `className` of its own, so it is the
same code path as the two ghost buttons above rather than a third case — I inspected the variant
in both themes rather than opening a failed message to see that specific instance. Saying so
because that is the limit of what I actually looked at.

## F3 — listbox ownership. Fixed.

`role="presentation"` on the `<li>` wrappers, the empty-state `<li>` and the `<p>` group
headings, so the options are the listbox's own children. A test asserts the listbox contains
**zero** `listitem`s and exactly as many `option`s as there are entries; it goes red when the
attribute is removed.

## F4 — D63 was unpinned. Fixed.

`makes no server call when it opens or filters (D63)` clears the fetch mock after mount, then
opens, types and arrows, and asserts `fetch` was never called. Mutation-tested by adding a
`fetch('/api/quick-replies?q=x')` to the open effect — red.

## F5 — `block()` hardened.

It now anchors to the start of a line and requires the selector to open **exactly one** block:

```ts
const escaped = selector.replace(/[.*+?^${}()|[\]\]/g, '\$&')
const found = [...css.matchAll(new RegExp(`^${escaped}\s*\{`, 'gm'))]
expect(found, `${selector} must open exactly one block at the start of a line`).toHaveLength(1)
```

Mutation-proved rather than asserted: I put the `indexOf` version back **and** restored the
comment wording that mentions `[data-theme='light']`, and the accent/danger test went red because
the light-theme assertions were reading the comment. With the hardened helper the same comment is
ignored. It also now fails loudly if a selector is ever declared twice.

## F6 — `--border3` raised to clear 3:1. Done, and it did not go boxy.

The finding is right, and the tension resolves cleanly because **`--border3` is the *control*
boundary token and nothing else**. Every use of it is a Button, Input, Textarea, `select`,
Dropdown trigger, the Composer's mode-tab track or one of the new top-bar pills. Card hairlines
and table rules are `--border` / `--border2`, which are left exactly as soft as they were. So the
controls gain definition and the page does not gain lines.

This is required, not optional, because the fills do not carry the identification either: in
light a default Button is `#ffffff` on `#f5f7fa` (1.03:1) and an Input is `#eef2f7` on `#ffffff`
(1.11:1). The 1px border is the only thing that says "control".

| | before | surface | surface2 | bg | bg2 |
| --- | --- | --- | --- | --- | --- |
| light | `#c3ccd9` | 1.62 | 1.44 | 1.51 | 1.56 |
| light | **`#7e8a9e`** | **3.49** | **3.10** | **3.25** | **3.37** |
| dark | `#35414f` | 1.50 | 1.63 | 1.78 | 1.69 |
| dark | **`#66748a`** | **3.30** | **3.57** | **3.90** | **3.70** |

3:1 is cleared against **every** ground a control can sit on, on both sides of the 1px line, not
just against the page background. Asserted per theme in `index.css.test.ts` and mutation-tested by
restoring the old values — both assertions go red.

Looked at in both themes on the densest screens: the admin EditPanel (`s1-fix1-departments-light.png`,
`s1-fix1-loading-dark.png`), the Create work order dialog (`s1-fix1-dialog-light.png` / `-dark.png`)
and the inbox thread with its composer (`s1-fix1-thread-dark.png`). The form fields and the
Quick/Attach/Work order row now read as controls instead of floating; the cards, the table and
the message bubbles are unchanged. It reads more defined, not heavier.

## Not touched, as instructed

The `smoke.spec.ts` delivery-status failure. Noted in the original report as pre-existing and
left to its own diagnosis.
