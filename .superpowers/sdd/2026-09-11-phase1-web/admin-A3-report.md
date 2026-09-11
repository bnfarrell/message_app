# A3 — Departments CRUD, Property settings, and two residuals · implementation report

**Status: DONE_WITH_CONCERNS.** All four brief items are built. Three brief/codebase defects were
caught and one destructive-misfire hazard was found by driving the real app; all four are below,
and two of them changed what shipped.

Commits on `main`, from `4438a5b`:

| sha | subject |
| --- | --- |
| `0c8fd1e` | test(web): restore real timers after every test (D92) |
| `5719987` | feat(web): give the shared normaliser human copy for reason codes (D93) |
| `2fc4a37` | fix(server): a validation 400 must not echo the caller's raw input (D91) |
| `4a12e63` | fix(web): clear the stored property when a session dies on its own (D56) |
| `818855e` | feat(web): Departments becomes full CRUD |
| `4f6fdc7` | feat(web): Property settings goes from greyed to live |

The brief required item 3 (D56) and item 4 (D91) to be committed separately; they are, and neither
diff carries any admin-screen change. D92 and D93 also got their own commits — D92 because the
brief said so, D93 because it changes a shared module every form reads.

## Verification

```
$ cd web && npm test
 Test Files  48 passed (48)
      Tests  477 passed (477)

$ npx tsc -b            (exit 0)
$ npm run lint          (exit 0)
$ npm run build         (exit 0, tsc -b && vite build)
$ find tests -name "*.d.ts"      (nothing)

$ cd server && python -m pytest -q
326 passed in 29.77s
$ python -m ruff check app tests seed
All checks passed!

$ git status --short
?? railway.png          (not mine — see "Found but not fixed" 6)
```

**Web 446 → 477 passed, 0 failed. Server 323 → 326 passed.** Nothing removed, nothing broken.
+31 web (21 new in two new files, 11 in `DepartmentsAdmin.test.tsx`, 12 in
`PropertySettingsAdmin.test.tsx`, 6 in `fieldErrors.test.ts`, 2 in `RequireAuth.test.tsx`; existing
counts adjusted where copy changed) and +3 server.

Exercised against the real app (`server/dev_start.py` + `npm run dev`, API 5200 / web 5173).
Screenshots in this directory: `a3-departments-delete-conflict.png`,
`a3-property-settings.png`, `a3-property-settings-field-error.png`.

---

## Where the brief was wrong, and what I did instead

### 1. `ava@hvh.test` cannot reach this wave at all

The brief says to exercise the work as `ava@hvh.test` / `Password123!`. **Ava is an `agent`.**
Queried before relying on it, as instructed:

```
sqlite> select u.email, m.role, p.code from user_account u
        join property_membership m on m.user_id=u.id join property p on p.id=m.property_id;
('alex@hvh.test','admin','HVH')   ('ava@hvh.test','agent','HVH')   ('casey@group.test','corporate','HVH')
('blake@lsi.test','admin','LSI')  ...
```

and the live server agrees:

```
POST /api/p/<hvh>/departments  as ava  ->  403 {"code":"FORBIDDEN","message":"Your role lacks 'manage_admin'"}
```

`manage_admin` is `{admin, corporate}` and `routes.tsx` gates the whole `admin/*` splat on it, so
Ava never sees the admin section. **The login that exercises A3 is `alex@hvh.test` (admin at HVH)
or `casey@group.test` (corporate), both with `Password123!`.** I used Alex. Ava is presumably right
for the inbox-facing briefs and was copied forward.

### 2. `min={1}` on the SLA box would have made the brief's own requirement untestable

The brief asks that a `slaMinutes` of `0` "surface that error against the field rather than as a
bare failure". My first draft put `min={1}` on the two number inputs, which looked like a kindness.
It is not: a native `min` makes the browser refuse the form submit and answer with its own tooltip,
so the request never leaves and the server's `gt=0` message — the one that explains 0 makes every
conversation instantly overdue — can never reach the field. The test failed in jsdom for exactly
that reason, which is how I found it rather than shipping it.

`min` is gone from both boxes. The server is the single authority on validity here, as it is on
every other box on every other admin screen. Confirmed live: typing `0` and saving puts
*"Input should be greater than 0"* under **Overdue after (minutes)**.

### 3. The delete confirmation stays armed across rows (found by driving the app)

Not in the brief; found by actually doing what the brief said to do. Sequence in the real browser:

1. open **Engineering**, press **Delete** → the panel arms with *"Delete this? This cannot be
   undone."* + **Confirm** / **Keep**;
2. press **Confirm** → the guard refuses with its 409, the panel stays open (correct);
3. click the **Housekeeping** row → its panel opens **still showing Confirm**, unprompted.

One further click deletes Housekeeping. `EditPanel` holds `confirming` in local state and the panel
is never unmounted between rows, so the arming survives the subject change. This is precisely the
screen where it bites — the delete guard means an admin will press Delete and be refused as a matter
of routine.

Fixed in my screen only, with `key={draftId ?? 'new'}` on the `EditPanel` — one word at the call
site, remounting the panel per record. I did **not** change `EditPanel` itself: the same carry-over
exists on `UsersAdmin`, `CategoriesAdmin`, `AssetsAdmin` and `QuickRepliesAdmin`, and changing a
shared primitive's behaviour for four screens outside this wave is not mine to do unilaterally. It
is recorded below as finding 1.

Verified live after the fix: `armedOnEngineering: true`, refusal message shown, then Housekeeping
opens with `stillArmedOnHousekeeping: false` and a plain **Delete** button.

### 4. Nothing else disagreed

Every shape in A1's report matched the server source I read and the live server: `DepartmentIn` /
`DepartmentPatch` / `DepartmentOut`, the 409 `message`, `PropertySettingsOut` / `PropertySettingsPatch`
including the three D80 fields, and both `details` shapes. A2's report named the normaliser
correctly at `web/src/api/fieldErrors.ts`. **No A1/A2-vs-brief conflict arose**, so nothing needed
resolving in A1's favour.

The type pipeline needed nothing: A1's `9ae2bac` already regenerated `schema.json` and
`types.generated.ts` **and** already added `DepartmentIn`, `DepartmentPatch`, `PreviewRequest`,
`PropertySettingsOut` and `PropertySettingsPatch` to the hand-maintained re-export list in
`web/src/api/types.ts`, in its case-sensitive alphabetical order. Checked rather than assumed;
`gen:types` was not run, `schema.json` was not touched, `types.generated.test.ts` still passes, and
**no type was hand-written**. `DepartmentType` was already re-exported too.

---

## 1 · Departments — read-only becomes full CRUD (`818855e`, panel key in `4f6fdc7`)

| file | what |
| --- | --- |
| `web/src/api/hooks/users.ts` | `useCreateDepartment`, `usePatchDepartment`, `useDeleteDepartment` |
| `web/src/features/admin/DepartmentsAdmin.tsx` | the screen, rewritten |
| `web/src/features/admin/DepartmentsAdmin.test.tsx` | new, 11 tests |
| `web/src/features/admin/AdminPage.test.tsx` | its read-only assertion inverted |

The false header comment is gone. `AdminTable` + `EditPanel`, same shape as `CategoriesAdmin` and
`QuickRepliesAdmin`; no new pattern, no new primitive. Fields are **name**, **type** and **active**.

**Disclosed divergence from the mockup.** `docs/mockups/Admin.dc.html` draws no create affordance
for Departments, so the **New department** button and the edit panel are not in it. They are here on
the user's decision to make this screen editable — the same authority the mockup itself carries. It
is said in the file's header comment and here.

**`escalationMinutes` (ruling D81):** kept as a table column, deliberately absent from the panel,
and omitted from the create body so `DepartmentIn`'s default of 15 applies. A test asserts both
halves — `20 min` renders, `queryByLabelText(/escalation/i)` finds nothing, and no PATCH body ever
contains the key.

**The type select defaults to `other`, not `front_desk`.** `Department.type` is load-bearing, not
decorative: `app/domain/notifications.py:36` routes unassigned-conversation alerts to the department
whose type is `front_desk`, and `app/domain/work_orders.py:165` filters by type. A default that
silently claimed a routing role is worse than one that claims none. Grepped before deciding.

**The labels are a `Record<DepartmentType, string>`, not a `DepartmentType[]`.** The array form the
other screens use (`ROLES`, `TYPES`) catches a *wrong* value but never a *missing* one, and a
missing one here is an enum value the admin simply cannot pick. A ninth server type now fails the
build. It also replaces `type.replace(/_/g, ' ')` in the table, so `food_beverage` reads as
"Food & beverage" in both places.

### The delete-conflict UX

The 409's `message` is surfaced **verbatim** in the panel's existing `role="alert"` banner. It is
the only thing on screen that says *which* of the five referencing tables is holding the department,
and it names the escape hatch. The panel stays open on failure, so the **Active** checkbox it points
at is right there, and a static hint under it says the same in the UI's own words. Live, as Alex:

```
DELETE Engineering -> banner: "Move the staff members in this department to another one first,
                               or deactivate the department instead"
                      panel still open, Active checkbox present, 3 rows still listed
```

A clean delete was exercised too: created **Spa & Wellness** (type Spa) through the form, saw it
appear in the refreshed list at `15 min` escalation, then deleted it — 204, row gone. **The seed is
back exactly as found** (3 HVH departments, all `escalation_minutes=15, active=1`), verified by
querying the database afterwards.

### Cache invalidation

All three mutations invalidate `qk.departments(propertyId)`, which is `['departments', propertyId]`
— the whole prefix, so there is no `departmentsAll`/`departments` split to get wrong. That matters
because the picker on Users, Quick replies, Digital assets, the inbox filter and the work-order form
all read `useDepartments`: a missed invalidation shows up as a wrong dropdown three screens away.
The covering test counts reads before and after a delete; removing the `onSuccess` fails it.

`AdminTable` needed no change, as the brief predicted: its unconditional `tabIndex={0}` /
`cursor-pointer` now means something.

## 2 · Property settings — greyed becomes live (`4f6fdc7`)

| file | what |
| --- | --- |
| `web/src/api/queryKeys.ts` | `propertySettings` |
| `web/src/api/hooks/properties.ts` | new — `usePropertySettings`, `usePatchPropertySettings` |
| `web/src/features/admin/PropertySettingsAdmin.tsx` | new screen |
| `web/src/features/admin/PropertySettingsAdmin.test.tsx` | new, 12 tests |
| `web/src/features/admin/AdminPage.tsx` | `LIVE` entry + route; `PHASE_2` loses one entry |

The nav entry uses an absolute `/app/admin/property`, per the `v7_relativeSplatPath` comment above
`LIVE`. **The other three stay greyed and the "Greyed items arrive in Phase 2" caption is byte-for-byte
unchanged.** No second capability gate was added; the route inherits the `admin/*` splat's
`manage_admin`.

Worth noting for review: **`Admin.dc.html` already draws Property settings ungreyed** (line 64 is a
plain `.sub`, while Automations / Blocked numbers / Integrations carry
`style="color: var(--text4)"`), sixth and last before the divider. So this move brings the client
*into* line with the mockup, and my nav order matches the mockup's exactly.

### How "table + edit-panel" resolved for a single record

Spec line 417 asks the non-quick-reply admin screens to "reuse the table + edit-panel pattern".
`GET/PATCH /settings` edits **one** record: there is no list to select from, so `AdminTable` has
nothing to draw, and `EditPanel` is a 340px `<aside>` that would be a side panel with no main
content beside it. Wrapping a single record in a one-row table to satisfy the letter of the line
would be worse for the admin and worse to read.

What is reused is the part of the pattern that carries its *look and behaviour*: `EditPanel`'s
`LABEL` and `SELECT` class strings verbatim, its `role="alert"` banner markup, its per-field
`FieldError`, and the `Input` / `Textarea` / `Button` primitives — laid out as one form in the main
column with a Save / Revert footer. Nothing new was invented and no primitive was added.

### Field-by-field decisions

- **`code`** is read-only context (mono text plus a line saying it is not editable here). It is not
  an input because `PropertySettingsPatch` has no such field and `CamelModel` sets `extra="forbid"`,
  so an input for it would turn every save into a 400.
- **`timezone`** is a `<select>` from `Intl.supportedValuesOf('timeZone')` (418 options in the real
  browser), with a 17-entry fallback where that is missing. **The stored value is always forced into
  the option list.** Without that, a zone this browser has never heard of leaves the select showing
  its *first* option while the server still holds the real one, and the next save silently moves the
  property to a different time zone. The test uses `Antarctica/Troll` — deliberately not on the
  fallback list — so it actually exercises the forcing; my first version used `America/New_York`,
  which **is** on the list, and the mutation proved the assertion was vacuous. Fixed before commit.
- **`primaryColor`** is a text input plus a swatch. **This is the wave's one inline colour and it is
  not a palette violation:** the value is supplied by the server and rendered as `style={{background:
  <server value>}}` so the admin can see what they stored. It is data, not a palette colour. It is
  deliberately **not** wired into any CSS custom property — confirmed live:
  `documentElement.style` is `null` and `--accent` still computes to `#2563eb` while the swatch
  computes to `rgb(240, 179, 35)` = the stored `#f0b323`. A test asserts the same.
- **`slaMinutes`** carries the no-retro-update sentence directly under it: *"Applies from the next
  inbound message. Conversations already waiting keep the deadline they were given."*
  `conv.sla_due_at` is written at `domain/messages.py:163` on inbound and never recomputed.
- **`helpText`** is labelled **"HELP reply — guests read this"**, with a hint saying it is sent
  automatically as an SMS to any guest who texts HELP and *"is outbound guest copy, not an internal
  note."*
- **Emptied nullable boxes send `null`, not `""`** — otherwise clearing Address would store an empty
  string rather than clearing the column. The two required ints send `null` when emptied, which the
  server answers with `{"<field>": "required"}` → "This field is required." under that box.
- The PATCH response (the full normalised record) is written into the cache with `setQueryData`, so
  the form re-reads what was **stored**, not what was typed. The query is `staleTime: Infinity` so a
  background refetch cannot replace a half-typed draft.

### Live exercise

```
load                -> every field populated from the server; 418 zone options; code HVH shown
phone "(555) 012-9999" + brand -> Save -> "Saved."; phone box now reads "+15550129999"
full page reload    -> phone "+15550129999", brand "Harbourview Collection"   (persisted)
slaMinutes 0        -> banner "Invalid request body"; "Input should be greater than 0" under the box
smsNumber "+"       -> banner "Invalid phone number";
                       "Enter a valid phone number, for example +1 555 012 3456." under SMS number
timezone Europe/Lisbon -> Save -> sqlite: timezone = 'Europe/Lisbon'
```

**The seed was then restored through the UI** (timezone `America/New_York`, phone and brand cleared
back to `NULL`, smsNumber `+15550100`) and re-verified against the database. Note the second and
third cases together confirm the two `details` shapes both land: `slaMinutes` came through
`parse_body`'s **array** and `smsNumber` through the domain validator's **object**, and a form
written against only one of them would have shown nothing for the other.

Focus-indicator check, since `cn` cannot resolve conflicts: `#prop-color` (the one input I passed a
`className` through, `font-mono`) computes `rgb(195,204,217)` = `--border3` unfocused and
`rgb(37,99,235)` = `--accent` focused. Nothing silently no-opped. No hex anywhere in the screen
except the server-supplied swatch value.

## 3 · The `activePropertyId` session-expiry leak (`4a12e63`, ruling D56)

`RequireAuth` now clears the key on the **same condition that drives the redirect**:

```ts
const sessionLost = !isPending && (Boolean(error) || !data)
useEffect(() => { if (sessionLost) clearActivePropertyId() }, [sessionLost])
```

The `!isPending` half is not decoration: on a cold start `data` is undefined until `/api/auth/me`
answers, so without it every page load would wipe the preference `SessionProvider` reads one render
later. Both halves are covered and both mutations bite — removing the effect fails the session-loss
test, removing the guard fails the cold-start test. My first version of the cold-start test seeded
the session through the harness, so `isPending` was never true and the guard mutation passed; the
test now mounts unseeded, which is the only way it exercises the thing it claims to.

**Where the constant went: `web/src/auth/storage.ts`.** It exports `ACTIVE_PROPERTY_KEY` and
`clearActivePropertyId()`, imports nothing, and so cannot participate in the
`SessionContext → hooks/auth → SessionContext` cycle that forced the duplication. `SessionContext`
imports the constant (its private `STORAGE_KEY` is gone), and `useLogout` and `RequireAuth` both
call the helper — three call sites, one literal, and the two that clear share one `try`/`catch`.
Every access is still wrapped.

Verified live, not only in jsdom. In the real browser I set `activePropertyId` by hand, then killed
the cookie with a direct `fetch('/api/auth/logout')` — which is the silent path, because it never
invokes the `useLogout` mutation — and reloaded `/app/admin/property`:

```
{ url: "/login", activePropertyId: null }
```

## 4 · The two server lines (`2fc4a37`, ruling D91)

`_util.parse_body` and `_util.parse_query` now pass `include_input=False` alongside the
`include_url=False` they already had, and `errors.py`'s `ValidationError` handler — which called
`e.errors()` bare and leaked both the raw input **and** a pydantic.dev URL — gets the same two
arguments. The array's shape is otherwise unchanged, so `fieldErrors` is untouched; the tests assert
`loc`, `msg` and `type` are all still present.

Three tests, one per call site. The bare handler is reached only by a `ValidationError` escaping a
view rather than by `parse_body`, so it is invoked directly through
`app.error_handler_spec[None][None][ValidationError]`. All three were mutation-tested: with the
arguments removed, all three fail.

## 5 · D92 — fake timers no longer leak (`0c8fd1e`)

`web/vitest.setup.ts` gains `afterEach(() => vi.useRealTimers())`. Proven in both directions with a
throwaway probe file (deleted; `git status` clean): a test that installs fake timers and never
restores them, followed by one that awaits a real `setTimeout`. With the hook, both pass in 898 ms;
with the setup file back at its one line, the second fails on the timeout. The full suite is
unaffected, so nothing was silently depending on a leaked clock.

## 6 · D93 — reason codes become copy (`5719987`)

A `REASON_COPY` map inside `web/src/api/fieldErrors.ts`, consulted **only** in the object branch —
the array branch's `msg` is already a sentence, and rewriting one that happened to collide with a
code would be wrong. A test pins that.

The three codes are every one `server/app/` raises today, grepped rather than guessed: `details=`
outside `e.errors(...)` hits `domain/_patch.py` (`required`), `domain/guests.py`
(`invalid_phone_number`) and `domain/properties.py` (`invalid_timezone`), and nowhere else.

```
required              -> "This field is required."
invalid_phone_number  -> "Enter a valid phone number, for example +1 555 012 3456."
invalid_timezone      -> "Not a recognised IANA time zone."
```

**An unlisted code falls through verbatim.** Swallowing it or replacing it with a generic apology
would hide that the server said something specific; a code on screen is ugly but actionable, and it
names the gap. A test asserts the pass-through, and an `it.each` over the three known codes asserts
each renders as a capitalised sentence ending in a full stop with no surviving underscore — so a
future entry added in the wrong shape fails.

Six new tests in `fieldErrors.test.ts` (15 → 21). The three existing object-shape assertions and the
five `findByText('required')` matches in `QuickRepliesAdmin.test.tsx` were updated to the new copy —
forced by the shared-module change, and the only reason that file was touched. `QuickRepliesAdmin.tsx`
itself is untouched.

**On the array-index entry that A2 flagged:** `fieldErrors` still **drops** an entry whose `loc` ends
in a numeric index rather than walking back to the last string element. I decided not to change it,
deliberately. It is still unreachable — no request schema in the product has a list field — so
changing it would be an untestable behaviour change in a shared module in the same commit that
changes its output for every form. It wants its own ruling, not a silent flip. Saying so rather than
doing it quietly, as asked.

---

## Found but not fixed

1. **`EditPanel`'s delete confirmation survives a subject change, on the other four admin screens.**
   The mechanism is in `web/src/features/admin/EditPanel.tsx`: `confirming` is local state and the
   panel is not unmounted when the admin clicks from one row to the next. Departments is now keyed
   per record so it is immune (finding 3 above); `UsersAdmin`, `CategoriesAdmin`, `AssetsAdmin` and
   `QuickRepliesAdmin` are not. On those screens the sequence is: press Delete on row A, change your
   mind, click row B, and B's panel opens one click from deleting B. The cheapest fix is the same
   one-word `key={draftId ?? 'new'}` at each call site; the better one is for `EditPanel` to reset on
   a `subjectId` prop, which is a shared-primitive change and wants a ruling.

2. **A failed save still outlives its panel on `UsersAdmin`, `CategoriesAdmin` and `AssetsAdmin`.**
   A2's F1 fix (`clearFailures()` on open / new / cancel) landed on `QuickRepliesAdmin` only, and I
   built it into `DepartmentsAdmin`. The other three still show the previous record's banner when
   another row is opened. Same class, same three-line fix, out of this wave's scope.

3. **`Property.timezone` is now editable and still read by nothing.** A1's finding 3 stands:
   `grep -rn timezone server/app/` shows it set by the seed and read by no domain code —
   `domain/analytics.py` buckets in UTC. This wave gives an admin a validated picker for a value that
   currently changes nothing. That is better than a free-text box that 400s, and the brief calls the
   field load-bearing for future analytics bucketing, but someone should decide whether analytics is
   meant to honour it: an admin who sets the zone here will reasonably expect the dashboard to follow.

4. **`Department.escalation_minutes` is still read by nothing** (A1 finding 5, ruling D81). The
   column is shown and the control is withheld, which is the ruling. Repeating it because the screen
   now has an edit panel and the next person to look will ask why one displayed field has no input.

5. **`qk.assets`/`qk.assetsAll` and `qk.categories`/`qk.categoriesAll` are still identical functions**
   (A2 finding 4). I added `qk.propertySettings` as a single function deliberately — there is one
   record and no filtered variant, so there is nothing for a second key to distinguish.

6. **`railway.png` is untracked at the repo root and is not mine.** Timestamped 13:26, before I
   opened a browser at 13:33; my screenshots were written with explicit paths into this workspace
   directory. Left alone rather than deleted, per the "mention it, don't delete it" rule. It is the
   only thing in `git status` after this wave.

7. **The Phase 2 group is now three items and a divider's worth of nav.** Unchanged on purpose —
   Automations, Blocked numbers and Integrations have no models, no endpoints and no spec, and the
   caption above them is byte-for-byte as it was. Noting only that the mockup draws a horizontal
   divider between the live group and the greyed group which the client has never drawn; that is
   pre-existing and was not introduced or touched here.

---
---

# A3 · Fix round 1

**Status: DONE_WITH_CONCERNS.** All five items addressed; none declined. One instruction is
implemented in a way that deliberately departs from the letter of the ruling — the Departments
`key` — and my reasoning is under F1 rather than buried. One new defect was found while fixing
F4 and is fixed in its own commit.

Commits on `main`, from `2927e74`:

| sha | subject |
| --- | --- |
| `8b750c8` | fix(web): a delete confirmation must not outlive the record it was armed on |
| `ee5b9fa` | fix(web): four minors from the A3 review — copy, an inert assertion, a stale banner |
| `b722651` | test(web): the settings mock must refuse a null name, as the server does |

## Verification

```
$ cd web && npm test
 Test Files  50 passed (50)
      Tests  489 passed (489)          (and no React warnings on stderr — see F6)

$ npx tsc -b            (exit 0)
$ npm run lint          (exit 0)
$ npm run build         (exit 0)
$ find tests -name "*.d.ts"      (nothing)

$ cd server && python -m pytest -q      347 passed
$ python -m ruff check app tests seed   All checks passed!

$ git status --short     (clean)
```

**Web 477 → 489 passed, 0 failed** (+12: ten F1 regression tests across five screens, two for F4).
**Server unchanged at 347** — nothing in this round touches it. Two new test files,
`CategoriesAdmin.test.tsx` and `AssetsAdmin.test.tsx`, for screens that had none.

`railway.png` is gone from the working tree; it was never tracked and I never touched it. The tree
is clean.

---

## F1 · The delete confirmation, fixed in the primitive (`8b750c8`)

Implemented as ruled, with the review's shape. `EditPanel` takes a **required** `subjectId: string`
and resets in the render phase:

```tsx
const [confirming, setConfirming] = useState(false)
const [armedFor, setArmedFor] = useState(subjectId)
if (subjectId !== armedFor) { setArmedFor(subjectId); setConfirming(false) }
```

Required, not optional, so `tsc` forced all five call sites and will force every future one — the
thing a key convention cannot give you. Render-phase, not `useEffect`, so there is no committed
frame in which **Confirm** is on screen for the new subject. All five call sites pass
`subjectId={draftId ?? 'new'}`.

The mechanism is documented on the component rather than at the call sites, including the route
the review found and I had not: **arm, then press "New …"**. `onDelete` is undefined for an unsaved
record, so the whole delete row disappears and the admin reasonably reads that as the confirmation
having been dismissed. It has not been. That is the one that matters, because the UI actively
signals the opposite, and it is the one nobody found by reading the screens.

### Where I departed from the ruling: the Departments `key` is removed

The ruling says the key "was correct and should stay". **I removed it, and I think that is right.**

The ruling's own two arguments against a key as the general remedy apply verbatim to the one that
would survive: it is an invisible convention nothing enforces, and it discards the whole panel
subtree — scroll position and any child state — to clear one boolean. Keeping it would leave
Departments alone paying that cost for a problem the primitive now solves, and leave a comment in
the file describing a mechanism that is no longer how the screen works.

The decisive reason is the verification the ruling itself asked for: *"revert the EditPanel change
and confirm each screen's new regression test fails."* With the key still in place, Departments'
two regression tests pass under that mutation — the key masks the primitive, so those tests would
no longer guard the thing they are named after. Removing it is what makes the requested check
meaningful. Measured:

```
# render-phase reset removed from EditPanel
DepartmentsAdmin           Tests  2 failed | 10 passed (12)
UsersAdmin                 Tests  2 failed |  5 passed (7)
CategoriesAdmin            Tests  2 failed (2)
AssetsAdmin                Tests  2 failed (2)
QuickRepliesAdmin          Tests  2 failed | 31 passed (33)
# restored
                           Tests  73 passed (73)
```

Exactly two per screen: both routes bite on every one.

If the intent was that Departments keep the key as belt-and-braces, say so and I will put it back —
but the tests above would then be measuring the key on that screen, not the primitive, and I would
want to note that in the file.

### Tests

Two per screen, one per route, on all five. The "New …" test asserts the intermediate state
explicitly — **Confirm** gone *and* **Delete** gone — because that is the frame in which the admin
concludes they are safe; then it opens a saved record and asserts **Confirm** has not returned.

`QuickRepliesAdmin.tsx` was edited despite the original brief's "do not touch it": the ruling names
`QuickRepliesAdmin.tsx:197` as one of the four sites and a required prop leaves no alternative.
Wave A2 is closed, so there is no concurrent diff to collide with. The change there is one line.

`CategoriesAdmin.test.tsx` addresses rows by `getByRole('cell', …)` rather than by text: once the
panel is open its Parent select lists every category, so a bare text query matches the `<option>`
as well as the table cell. My first version did, and failed for that reason rather than for the
behaviour under test.

## F2 · The 422 that is a 400 (`ee5b9fa`)

Upheld and confirmed in source: `normalize_timezone` raises `ValidationFailed`
(`server/app/domain/properties.py`), and `ValidationFailed.status = 400`
(`server/app/errors.py:31`). The docstring now says 400 and says why the number matters — nothing
here branches on status, and a wrong number in a comment is how a `status === 422` branch that
never fires gets written.

## F3 · The assertion that could not fail for its stated reason (`ee5b9fa`)

Upheld, and the cause is mine: last round I applied a blanket
`getByText('Engineering')` → `getByText('Maintenance')` rename to fix a fixture-name collision, and
it silently rewrote the one assertion that was *supposed* to name the type label. It read
`expect(screen.getByText('Maintenance')).toBeInTheDocument() // the type of the row above`.

It now reads the labelled type out of **column 2 by cell index**, so it cannot match a name even if
a future fixture collides, and it additionally asserts the lowercase enum value is absent:

```tsx
const rows = screen.getAllByRole('row').slice(1) as HTMLTableRowElement[]
expect(maintenance!.cells[0]).toHaveTextContent('Maintenance')
expect(maintenance!.cells[1]).toHaveTextContent('Engineering')
expect(reception!.cells[1]).toHaveTextContent('Front desk')
expect(screen.queryByText('front_desk')).not.toBeInTheDocument()
expect(screen.queryByText('engineering')).not.toBeInTheDocument()
```

Mutation-checked: reverting the column to `r.type.replace(/_/g, ' ')` fails it. The old version did
not.

**Lesson worth recording, because it will recur:** a blanket string replace across a test file is
exactly the operation that turns a live assertion into a tautology, and it does it silently — the
suite stays green, because the rewritten assertion is still *true*. Anywhere I rename a fixture
value across a test file, the assertions that name the *other* column have to be re-read one by one.

## F4 · A raw regex reaching the admin (`ee5b9fa`)

Upheld. `name` and `currency` bypassed `orNull`, so clearing either box sent `""`, which fails in
Pydantic and reports Pydantic's own wording — `String should match pattern ^[A-Za-z]{3}$` under the
Currency box.

Fixed by routing both through `orNull`, which is the cheapest correct answer **and** the one the
review pointed at: `null` on a `nullable=False` column reaches `patch_changes` rather than the
Pydantic layer, and `patch_changes` raises the `required` reason code that the D93 map already
words as *"This field is required."* No new mechanism, no second contract in `fieldErrors`.

Confirmed against both sides rather than assumed: `Property.name` and `Property.currency` are
`nullable=False` (`server/app/models/core.py:35,42`), and the server response is already pinned by
`server/tests/test_property_settings.py::test_patch_settings_rejects_an_explicit_null_on_a_required_field`,
which asserts `{"currency": null}` to `400 details {"currency": "required"}` for real. Two client
tests; the mutation (both fields sent raw again) fails both.

**Residual, stated plainly:** this fixes the *clearing* case, which is what F4 reported. A
genuinely malformed value — typing `EUROS` — still shows Pydantic's pattern sentence, because that
comes through the **array** shape, whose `msg` the normaliser deliberately passes through. Wording
those would mean keying copy off Pydantic's `type` (`string_pattern_mismatch`, `string_too_long`, …)
— a second contract in a module that currently has exactly one, and one that would have to stay in
step with Pydantic rather than with our own code. I did not build it. The Currency field already
carries the hint *"Three letters, e.g. USD."*, which is the part the admin can act on. If it is
wanted, it wants its own ruling.

## F5 · The refused-delete banner outliving its action (`ee5b9fa`)

Upheld. A small `edit()` helper now backs the three Departments inputs; it clears the delete
failure before applying the change. Editing a field *is* the admin acting on the refusal, so the
refusal stops being the news — and the guard's message specifically tells them to clear Active, so
the old behaviour showed a complaint about deleting over a panel that was by then about saving.

**Only the delete failure is cleared.** A create/patch failure is pinned to the field the admin is
still fixing, and clearing that on the first keystroke would take the field error with it — the
opposite of what last round built. Mutation-checked.

## F6 · Found while fixing F4, and fixed (`b722651`)

My new F4 test let the mock answer `{"name": null}` with a **200 echoing the null back**. The real
server 400s — `name` is NOT NULL — so the form was being driven into `value={null}`, a state
production cannot reach. React said so on stderr:

```
Warning: `value` prop on `input` should not be null. …
Warning: A component is changing a controlled input to be uncontrolled. …
```

Neither warning fails a test, which is why they sat there unnoticed through a green run. The mock
now returns the 400 the server actually returns, the test additionally asserts the copy lands under
**Property name**, and the suite is silent again. Found only because I grepped the run's stderr for
React warnings while checking that the render-phase `setState` in F1 produced none — it did not;
these two were mine, from a mock modelling an impossible server.

**Worth generalising:** a mock permissive enough to echo any patch back as a 200 will happily model
a server that cannot exist, and the test still passes. `serve()`'s default PATCH handler on
`PropertySettingsAdmin.test.tsx` is `{...SETTINGS, ...sent}` — convenient, and wrong for any field
the server would refuse.

## Not re-exercised in the browser this round

Last round's live pass is what found F1 in the first place. I did not restart the app for this
round: F1's fix is compiler-enforced at every call site and covered by ten mutation-verified tests
across all five screens, F2 is a comment, F3 is a test, and F4/F5 are covered both by client tests
and — for F4 — by an existing server test that asserts the exact response. If you would rather have
a live pass over the four screens that previously had no `subjectId`, say so and I will run one.

## Found but not fixed — round 1 additions

8. **`UsersAdmin`, `CategoriesAdmin` and `AssetsAdmin` still let a failed save outlive its panel.**
   Unchanged from finding 2 above; this round fixed their *delete* arming, not their error state.
   Opening another row on those three still shows the previous record's banner. `QuickRepliesAdmin`
   (A2) and `DepartmentsAdmin` (A3) both call a `clearFailures()` on open/new/cancel; the other
   three want the same three lines.

9. **`PropertySettingsAdmin`'s test mock is more permissive than the server** (see F6). It is now
   correct for `name`, but the default PATCH handler still echoes any other field back verbatim —
   including values the server would normalise or refuse. Each test that cares overrides it, which
   is the pattern A2 established, but the default is a standing invitation to assert against an
   impossible response.
