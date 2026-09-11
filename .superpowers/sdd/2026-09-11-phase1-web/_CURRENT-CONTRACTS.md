# Current contracts and hazards — read this alongside any brief in this directory

Written after waves R1, A1 and A2 landed. **Every brief in this directory predates some of
this.** Where a brief disagrees with this file, this file wins, and say so in your report.

## Hazards that have already caused real defects here

**`cn` does not resolve Tailwind class conflicts, and there is no `tailwind-merge`.**
A `className` colour override can silently no-op — class-string order is irrelevant, CSS source
order decides — and `tsc`, `npm run lint` and the entire test suite will all pass over the dead
override. Tailwind is `^3.4.13`, where `!` is the correct **prefix** form (v4 uses a suffix, so
these break silently on upgrade). If you override a colour class, verify in a browser with
`getComputedStyle`.

This has already produced one accessibility defect: an `!important` border override beat
`focus:border-accent`, and since `Textarea` uses that as its **only** focus affordance, a keyboard
user got no visible focus state at all. The author of the workaround did not notice.

**`userEvent.type` hangs under vitest fake timers.** Reduced to a bare `<textarea>` with no app
code: it hangs with `delay: null`, with `advanceTimers`, and with `toFake`, because React's async
`act` waits on a `setTimeout` that is itself faked. RTL's `waitFor` recognises jest's fake timers,
not vitest's. The working shape is `fireEvent.change` plus synchronous
`act(() => vi.advanceTimersByTime(n))`, faking timers only after the component under test is
mounted.

**No hardcoded hex colours in components.** 45 CSS custom properties in `web/src/index.css`,
mapped into Tailwind by name. The only sanctioned exception in the client is `PhoneFrame.tsx`
(the dev-only simulator, which deliberately depicts fixed iOS chrome — ruling D52; do not
re-theme it). A server-supplied colour rendered as inline style is **data**, not a palette
colour, and is not a violation — but say so in your report so a reviewer does not flag it.

**Capabilities live in `web/src/auth/capabilities.ts`** — the path is `auth/`, not `lib/`. A
dispatch of mine sent an implementer to the wrong one. It mirrors
`server/app/auth/permissions.py` byte-for-byte. Two live traps found this way:
`corporate` has `manage_admin` but **not** `reply`, and `dept_staff` lacks
`view_all_conversations`, which `GET /guests/<id>` requires.

**Seed data is counter-intuitive and briefs have stated false things about it.** Never state a
seed or data fact without querying that exact thing first; implementers have caught fabricated
seed facts three times. Known: 106 guests against 106 stay rows with no guest having more than
one; Property B has zero conversations; opted-out guest Lena Park has zero conversations.

## A test harness that models impossible servers

The shared `serve()` helper in the admin test files answers a PATCH with
`{...SETTINGS, ...sent}` — it echoes back whatever the test sent. That models a server which
accepts anything, including values the real one refuses.

It has already bitten once: a test sent `{"name": null}`, the mock echoed a 200, the component
got `value={null}`, and React emitted two warnings **that no test failed on**. It was found by
grepping stderr, not by a red suite.

So when you write a mock response for a field the server would reject, make the mock reject it
too. And **read stderr** — a green suite with React warnings in it is not a green suite.

## The error contract

A validation failure returns **400** — never 422 on this project; 422 is `ConsentError` alone.
`details` arrives in **two shapes**:

- Pydantic failures → an **array** of `{loc, msg, type, ctx, input}`; the field is `loc[last]`.
- Domain failures → an **object** `{field: code}`; the field is the key.

Both name the **camelCase** field. **Import the shared normaliser at `web/src/api/fieldErrors.ts`
— do not write a second one.** A form written against only the object shape silently highlights
nothing for the common cases.

Never render `details` verbatim: the array shape's `input` key echoes the user's raw typing back.

An explicit `null` sent for a non-nullable field is a 400 naming that field, not a 500.

## Test-quality standard

Implementers on this project have caught **six** defects in brief text — tests that could not
fail, assertions contradicting the seed, a prescribed regression test that passed against the
unfixed code. **Report a defect in your brief rather than papering over it.** It has consistently
been the highest-value thing implementers here do.

The bar set by the most recent wave: every production fix was **mutation-tested** — reverted in
turn to confirm the suite actually fails without it. Match that. A test that cannot fail is worse
than no test, because it reports safety that is not there.

Never make production code less correct in order to make a test deterministic.
