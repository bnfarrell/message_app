# A3 — Departments CRUD, Property settings, and one security residual

Web only. Three items, and item 3 is unrelated to the other two and gets **its own commit**.

## Read the A1 report first

Wave A1 added the server endpoints this wave consumes. **`admin-A1-report.md` in this directory
carries the exact request and response shapes — code against those, not against this brief's
description of them.** If A1's report and this brief disagree, A1's report wins and you should
say so in your report.

---

## 1. Departments: read-only becomes full CRUD

`web/src/features/admin/DepartmentsAdmin.tsx` exists and is read-only. Its header comment says:

```
// Read-only by design: Phase 1 exposes only GET /api/p/<id>/departments (spec §385), so there
// is no create/edit affordance here and no EditPanel — which is also how Admin.dc.html draws it.
```

**A1 added POST / PATCH / DELETE, so that comment is now false.** Rewrite it — do not leave a
comment asserting a constraint that no longer holds. (Its claim about the mockup also needs
care: the mockup genuinely does not draw a create affordance for Departments, so adding one is a
disclosed divergence, authorized by the user's decision to build this. Say so in the comment and
in your report.)

Bring it to the same shape as the other CRUD admin screens — `UsersAdmin`, `CategoriesAdmin` and
`AssetsAdmin` are your precedents; follow whichever is closest in shape. Reuse `AdminTable` and
`EditPanel`. Do not invent a new pattern.

Fields per A1: `name`, `type` (a fixed enum — render a `<select>`, not free text),
`escalationMinutes`, `active`.

You will need create / patch / delete hooks alongside the existing `useDepartments` in
`web/src/api/hooks/users.ts`. Follow the existing mutation hooks there for cache invalidation —
**many screens read the department list to populate pickers**, so a stale cache after a mutation
shows up as a wrong dropdown three screens away. Check what `useDepartments`'s query key is and
make sure every mutation invalidates it.

**The delete guard is the part users will actually hit.** A1's `DELETE` refuses with a `Conflict`
when the department is still referenced by a staff member, quick reply, digital asset,
conversation or work order. That is a normal outcome, not an exceptional one. Surface the
server's message in the UI — do not swallow it, and do not show a generic "something went
wrong". The server's message names what the admin must fix first, and deactivating
(`active: false`) is the intended escape hatch for a department in use.

There is a pre-existing minor here that this work resolves on its own: `AdminTable` rows are
unconditionally `tabIndex={0}` and `cursor-pointer`, which looked wrong on a read-only screen.
Once the screen is editable, selecting a row does something. No `AdminTable` change needed.

## 2. Property settings: greyed becomes live

`web/src/features/admin/AdminPage.tsx` holds the sub-nav. Today:

```
const PHASE_2 = ['Property settings', 'Automations', 'Blocked numbers', 'Integrations']
```

Move `Property settings` out of `PHASE_2` and into `LIVE` with a route. **The other three stay
greyed and the "Greyed items arrive in Phase 2" caption stays exactly as it is** — the mockup
captions them that way and they have no models, no endpoints and no spec behind them. Do not
touch them.

Note the comment above `LIVE` explaining why the targets are absolute (`/app/admin/...`) rather
than relative — this project's router future flags resolve a relative `to` against the full
splat path. Follow that convention for your new entry.

New screen `PropertySettingsAdmin.tsx`. This one is a **form, not a table** — it edits a single
record, so `AdminTable` does not apply. Spec line 417 says the non-quick-reply admin screens
"reuse the table + edit-panel pattern"; with one record there is no table, so reuse the
`EditPanel`'s field styling and the existing `Input` / `Button` primitives and lay it out as a
single settings form. Say in your report how you resolved that.

Fields per A1: `name`, `timezone`, `address`, `phone`, `smsNumber`, `brand`, `currency`,
`logoUrl`, `primaryColor`. **`code` is returned but is NOT patchable** — display it as read-only
context, do not put it in an editable field.

**Plus three operational settings added in A1's fix round (ruling D80)** — confirm their final
names in `admin-A1-report.md`:

- `slaMinutes` — how long before a conversation is overdue.
- `autoResolveHours` — how long before a conversation auto-resolves.
- `helpText` — **guest-visible outbound copy.** This is the automatic reply sent when a guest
  texts HELP (`server/app/channels/inbound.py:59`). Label it so an admin understands they are
  editing something guests will read, not an internal note.

Two behaviours you must surface in the UI, because they will otherwise generate bug reports:

- **Changing `slaMinutes` does not retro-update conversations that already have an `sla_due_at`.**
  Only the next inbound message picks the new value up. Say so next to the field.
- `slaMinutes` of `0` would make every conversation instantly overdue; the server validates
  `gt=0`, so surface that error against the field rather than as a bare failure.

### `escalationMinutes` is read-only (ruling D81)

`Department.escalation_minutes` is stored, returned and displayed — and **nothing in the codebase
computes with it.** The SLA that is actually enforced is the property-level `slaMinutes` above.

So: **keep it as a column in the Departments table** (it is displayed there today and removing it
would regress shipped behaviour) and **do NOT put it in the Departments edit form.** Shipping an
editable control that changes a number nothing reads is worse than showing a stored value plainly.
Per-department SLA is a Phase 2 concept — `conv.sla_due_at` is set on *inbound message*, when
`conv.assigned_department_id` is typically still null, so there is no department to read at the
only moment it would be needed.

Two that need care:

- **`timezone`** is validated server-side against IANA zones and a bad value 422s. Do not ship a
  free-text box that lets an admin type `EST` and get a 422 they cannot interpret. Use a
  `<select>` built from `Intl.supportedValuesOf('timeZone')` where available, with a sensible
  fallback list. This field is load-bearing — it is the intended basis for analytics bucketing.
- **`primaryColor`** is a per-property brand colour stored on the server. It has **nothing to do
  with this client's palette** and must not be wired into the theme. Render it as a value with a
  swatch. Do not let it set a CSS custom property.

Surface server validation errors against the field that caused them where the response makes
that possible; a form that reports "422" and nothing else is not done.

## 3. The `activePropertyId` session-expiry leak — SEPARATE COMMIT (ruling D56)

Unrelated to the admin work. It rides in this wave to avoid a dispatch seat for a small fix, so
**give it its own commit** and keep it out of the other two commits' diffs.

The fix wave cleared `activePropertyId` from `localStorage` in `useLogout`'s `onSettled`. The
re-review then found that this only closes the **explicit** sign-out path. `RequireAuth`
(`web/src/auth/RequireAuth.tsx`, around lines 18–27) installs an `onUnauthorized` handler that
refetches and, on failure, renders `<Navigate to="/login">` — **without ever invoking the
`useLogout` mutation.** So a silent session loss (cookie expiry, server restart, TTL) leaves the
key in place. On a shared front-desk machine that is the original cross-user bleed by a different
door.

Clear the key on the session-loss path too.

While you are there, there is a related wart worth fixing in the same commit: `useLogout`
duplicates the `'activePropertyId'` string literal that `SessionContext.tsx` holds privately as
`STORAGE_KEY`. The previous fixer left it duplicated on purpose, because importing it would make
`SessionContext → hooks/auth → SessionContext` circular. **Break that by moving the constant into
its own tiny module** (e.g. `web/src/auth/storage.ts`) that both import — no cycle, one literal,
three call sites agreeing. If you find a reason that does not work, leave the duplication and say
why.

Keep every `localStorage` access wrapped in `try`/`catch`, as the existing code does — private
browsing and blocked site data both throw.

Test it: assert the key is gone after a 401-driven redirect, not just after an explicit logout.

---

## 4. Two server lines — SEPARATE COMMIT, and the only server change you may make (ruling D91)

Yes, this contradicts "do not change the server" below. That constraint is overridden for these
two lines and nothing else.

A validation 400 built from Pydantic returns `details` as an array of
`{loc, msg, type, ctx, input}`, and **`input` echoes the admin's raw typing back verbatim** — a
reviewer confirmed a 99-character `smsNumber` comes back in full at `details[0].input`. Nothing
reads that key; the shared normaliser you are about to import says so in its own comment.

- `server/app/api/_util.py` (two call sites, around lines 28 and 35): add `include_input=False`
  to the `e.errors(...)` calls, which already pass `include_url=False`.
- `server/app/errors.py:87` calls `e.errors()` bare, so it leaks both the raw input **and** a
  documentation URL. Give it the same two arguments.

This does not change the array's shape, so it does not affect the normaliser. Add a test
asserting the raw input no longer appears in a 400 body. Run the server suite — it is at **323
passing**.

## The error contract you must code against — use the shared normaliser, do not write your own

`details` arrives in **two shapes** and your forms must handle both:

- Pydantic failures → an **array** of `{loc, msg, type, ctx, input}`; the field is `loc[last]`.
- Domain failures → an **object** `{field: code}`; the field is the key.

Both name the camelCase field. A form written against only the object shape would silently
highlight **nothing** for the common cases — a bad `currency` pattern, an over-length `name`,
`slaMinutes: 0`, or an extra `code` field.

Wave A2 extracted the one correct handler of both shapes into a shared module under
`web/src/api/` with its own tests. **Import it. Do not write a second one**, and never render
`details` verbatim. Find its exact path and name in `admin-A2-report.md`.

## The type pipeline — do not hand-write a type A1 already defined

Client types are **generated from the server's Pydantic models**, not written by hand:

```
server/app/schemas/export_json_schema.py  →  web/src/api/schema.json
npm run gen:types                          →  web/src/api/types.generated.ts
```

and `web/src/api/types.ts` then **re-exports the names by hand** — its own header says to import
from `types.ts`, never from `types.generated.ts`.

You need this for `DepartmentIn`, `DepartmentPatch`, `PropertySettingsOut`,
`PropertySettingsPatch` and whatever else A1's report names. So:

1. Check whether A1 already regenerated `schema.json`. If it did not, run the export and
   `npm run gen:types` yourself.
2. **Add the new type names to the re-export list in `web/src/api/types.ts`.** This is a manual
   step and it is the easy one to miss — without it the generated type exists but cannot be
   imported, and the temptation is to hand-write a duplicate interface in the component. Do not
   do that. A hand-written copy of a generated type is free to drift from the server.
3. Keep the list's existing alphabetical grouping.

Note `export_json_schema.py`'s `MODULES` tuple already lists a `properties` module — confirm
what A1 actually put there rather than assuming the property-settings schemas landed in it.

## Constraints

- **No hardcoded hex colours.** 45 CSS custom properties in `web/src/index.css`, mapped into
  Tailwind by name. Only sanctioned exception in the client is `PhoneFrame.tsx`. Note that
  `primaryColor`'s swatch renders a **server-supplied** value as inline style — that is data,
  not a palette colour, and is not a violation. Say so in your report so a reviewer does not
  flag it.
- **Capabilities live in `web/src/auth/capabilities.ts`** — the path is `auth/`, not `lib/`.
  `manage_admin` is `{admin, corporate}`; `routes.tsx` already gates the whole `admin/*` splat on
  it, so your new route inherits that. Do not add a second gate.
- **Beware `cn`.** It does not resolve Tailwind class conflicts and there is no `tailwind-merge`:
  a `className` colour override can silently no-op while tsc, lint and the suite all pass. If you
  override a colour class, verify in a browser with `getComputedStyle`.
- Do not touch `QuickRepliesAdmin.tsx` — A2 owns it and you may be working alongside its diff.
- Do not change the server. A1 owns it.
- Do not build Automations, Blocked numbers or Integrations.

## Verify before you commit

- The web suite; check `git log` and the A1/A2 reports for the current count and beat it. Cover:
  department create/patch/delete, the delete-conflict message reaching the UI, property settings
  save, an invalid timezone surfacing as a field error, and the 401-path key clearing.
- `npx tsc -b` clean, no `.d.ts` under `tests/`. `npm run lint` exit 0. `npm run build` clean.
- **Exercise it against the real server.** `start.bat`; API http://127.0.0.1:5200, web
  http://127.0.0.1:5173, login `ava@hvh.test` / `Password123!`. Actually create a department,
  actually try to delete one that is in use and read the message you get, and actually save a
  property setting and reload to confirm it persisted. Screenshots into this workspace
  directory, never the repo root.

Commit in logical commits on `main` — and again, item 3 gets its own. End every commit message
with:
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>

## Report

Full report to `admin-A3-report.md`: what you built, how you resolved the "table + edit-panel"
pattern for a single-record form, the delete-conflict UX, where you put the storage-key constant,
and a "Found but not fixed" section.

Return in your final message ONLY: status (DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT /
BLOCKED), commit shas, a one-line test summary, and your concerns. Keep it short — that text
lands in the controller's context.

If any instruction above is wrong — a shape A1 built differently, a comment that is already
fixed, a test that cannot fail — **say so and do the correct thing instead.** Implementers on
this project have caught defects in brief text four times now and it has been the single
highest-value thing they did. Never make production code less correct to make a test
deterministic. Do not dispatch subagents.
