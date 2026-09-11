# A2 — the quick-replies admin screen · implementation report

**Status: DONE_WITH_CONCERNS.** All five gaps closed and the panel reordered to the mockup. Two
disclosed divergences from the mockup (both pre-authorised by the brief), one test I had to
rewrite because the first version could not fail, and one pre-existing finding that contradicts
the brief's premise about client-side segment counting.

Commits on `main`, from `9ae2bac`:

| sha | subject |
| --- | --- |
| `778eeed` | feat(web): hooks for the quick-reply preview and variables endpoints |
| `a025359` | feat(web): finish the quick-replies panel against the mockup |

## Verification

```
$ cd web && npm test
 Test Files  44 passed (44)
      Tests  400 passed (400)

$ npx tsc -b            (exit 0, no .d.ts anywhere under web/tests — web/tests holds only e2e/)
$ npm run lint          (exit 0)
$ npm run build         (exit 0, tsc -b && vite build)
```

**386 → 400 passed, 0 failed.** Nothing removed, nothing broken. The 14 new tests are all in
`web/src/features/admin/QuickRepliesAdmin.test.tsx` (12 → 26 in that file).

Exercised against the real app (`dev_start.py` + `npm run dev`, API 5200 / web 5173) as **both**
`casey@group.test` (corporate) and `alex@hvh.test` (admin). Screenshots:
`a2-quick-replies-corporate.png`, `a2-quick-replies-admin.png` in this directory.

---

## 1 · Files changed

| file | what |
| --- | --- |
| `web/src/api/queryKeys.ts` | `quickReplyVariables`, `quickReplyPreview` keys |
| `web/src/api/hooks/content.ts` | `useQuickReplyVariables`, `useQuickReplyPreview` |
| `web/src/features/admin/QuickRepliesAdmin.tsx` | the screen |
| `web/src/features/admin/QuickRepliesAdmin.test.tsx` | +14 tests, and a de-flaked existing one |

Nothing else. No server file, no other admin screen, no UI primitive.

### The type pipeline — nothing needed regenerating

Checked rather than assumed, as instructed. A1's fix round (`9ae2bac`) already regenerated
`schema.json` and `types.generated.ts` and already added the new names to the hand-maintained
re-export list in `web/src/api/types.ts`. Both types this wave needs are there:

- `PreviewRequest` — the request body.
- **`RenderedQuickReply` — the preview *response*.** A1's report gives the response inline as
  `{ "body", "segments", "characters" }` without naming a model; `domain/quick_replies.preview()`
  returns `RenderedQuickReply`, the same model `/render` returns, and that name was already in the
  re-export list from before this wave. So there is no `PreviewOut`, and no type was hand-written.

`npm run gen:types` was not run and `schema.json` was not touched;
`src/api/types.generated.test.ts` still passes, which is the check that they are in step.

---

## 2 · The chips (mockup lines 111–115)

The static hint line is gone. Each chip is a `<button type="button">` whose click inserts
`{{name}}` at `selectionStart`, replacing `selectionStart..selectionEnd` if something is selected.
`onMouseDown` preventDefault keeps the textarea's selection alive across the click; the caret is
then re-placed in a `useEffect` keyed on the body, because a controlled `value` change is committed
by React after the handler returns and the browser would otherwise drop the caret at the end.

**The chip list comes from `GET /api/p/{propertyId}/quick-replies/variables`** — A1's endpoint, a
bare array — not a constant in the client. Confirmed live: the running server returned

```
["guest_first_name","room_number","property_name","agent_first_name","departure_date"]
```

**Five chips, not the mockup's four — ruling D68, disclosed divergence.** The mockup omits
`property_name`, which `server/app/domain/quick_replies.py:16` supports.

Verified in the browser as corporate: caret at index 10 of
`"Breakfast is 6:30–10:30 in the Harbour Room, level 2."`, clicked `guest_first_name`, got
`"Breakfast {{guest_first_name}}is 6:30–10:30 …"` with `selectionStart === 30` and the textarea
still focused.

## 3 · The counter (mockup line 121)

Renders `preview.data.characters` and `preview.data.segments` verbatim, in the composer's existing
format (`138 chars · 1 segment`), pluralised. **No segment arithmetic was written in this screen.**

The test pins this: the mocked server answers `{characters: 4242, segments: 3}` for an
11-character, one-segment body, and the assertion is on `4242 chars · 3 segments` — a local
recomputation cannot produce that.

## 4 · The preview (mockup lines 118–120)

`POST /quick-replies/preview` with `{ body }` and **no `conversationId`**, so the server renders
through `FALLBACKS`. Debounced 300 ms, `enabled` only for a non-empty body (the server 400s on an
empty one). No conversation picker, no conversation list fetch — asserted in the test.

**Label is `Preview · sample values`, not the mockup's `Preview as Sarah Chen · 412` — disclosed
divergence.** With sample values the mockup's label is a false statement about whose data is on
screen.

Loading and error states: on a preview failure the pane is replaced by
`Preview unavailable: <message>` and the counter is hidden — a stale count is the actively
misleading part. While the debounce has not caught up or the request is in flight the pane carries
`aria-busy` and is dimmed, and the counter reads `Updating…` rather than a number belonging to an
older draft.

Live debounce check, real browser, typing 24 characters with `pressSequentially`: **2 preview POSTs
total** (one on open, one after the pause). Undebounced that is 25.

## 5 · Category — the vocabulary I found

**There is none.** Queried the actual install before deciding, as instructed:

```
sqlite> select distinct category from quick_reply;   ->  [(None,)]     -- 16 rows, all NULL
sqlite> select distinct locale   from quick_reply;   ->  [('en',)]
```

`grep` also shows `category` on quick replies is read by nothing in `server/app/` beyond the schema
and the model, and by nothing in the client except `AssetsAdmin` (a different resource's field of
the same name). So: no fixed vocabulary exists, none was invented, and a free-text `Input` is what
shipped. Emptying it sends `null`, which is correct — the column is nullable, so clearing is a real
edit, not a 400. Verified against the live server both ways.

## 6 · Locale — and the comment that was wrong

Confirmed in `server/app/schemas/content.py` before relying on it:
`QuickReplyPatch.locale: str | None = Field(default=None, min_length=1, max_length=8)`. The
comment claiming `extra="forbid"` rejects `locale` on patch is deleted, `locale` is in the patch
payload, and there is an input for it with `maxLength={8}` mirroring the column and A1's bound.

Round-tripped against the live server as a corporate user: `{"locale": "fr-CA", "category":
"dining"}` on `/breakfast` persisted to the database and reverted cleanly afterwards, so the seed
is back to `category NULL, locale 'en'` and the body is untouched.

## 7 · Field-level errors (the cross-cutting contract from A1's fix round)

`fieldErrors()` maps an `ApiError.details` onto the input that caused it, and a `<FieldError>` sits
under each of Shortcut, Department, Title, Body, Category and Locale. It handles **both** shapes
this server produces, because the form can trigger either:

- `patch_changes` (ruling D82): `details` is an object, `{"escalationMinutes": "required"}`, keyed
  by the **camelCase** alias.
- `parse_body`: `details` is Pydantic's error **list**, each entry's `loc` ending in the field name.

Handling only the first would have left the more likely case on this screen bare: clearing the
Locale box sends `""`, not `null`, so it fails `min_length=1` in Pydantic rather than reaching
`patch_changes`. Verified live — emptying Locale and saving put
*"String should have at least 1 character"* directly under the Locale input in `--dangerText`, with
the banner still showing `Invalid request body`.

## 8 · Layout

Mockup order (lines 104–122): Shortcut and Department in a two-column grid, Title, Body with the
chips, the preview with its counter, then Active and the Save/Cancel/Delete row. Category and
Locale are appended as a second two-column grid between the preview and Active — the mockup draws
neither, so they go where they disturb the drawn flow least. Existing `EditPanel`, `AdminTable`,
`Input`, `Textarea`, `Button` and `Badge` throughout; no new primitive.

### The `cn` / colour hazard — checked in a browser, not assumed

No hex anywhere; every colour is a palette token (`bg-tagBg`, `text-roomNum`, `bg-outBg`,
`text-outText`, `text-dangerText`). `getComputedStyle` on the running app, dark theme:

| element | computed | token |
| --- | --- | --- |
| chip text | `rgb(122, 179, 234)` | `--roomNum: #7ab3ea` |
| chip background | `rgb(35, 43, 54)` | `--tagBg: #232b36` |
| preview text | `rgb(230, 234, 240)` | `--outText: #e6eaf0` |
| preview background | `rgb(30, 58, 95)` | `--outBg: #1e3a5f` |

Also re-checked the accessibility defect class named in the brief: the Body textarea's focus border
is `rgb(79, 143, 212)` = `--accent` when focused and `--border3` when not, and the Shortcut input —
the one place I passed a `className` through `cn` (`font-mono`) — still goes `--border3` →
`--accent` on focus. Nothing silently no-opped.

---

## Divergences from the mockup (both disclosed, both pre-authorised)

1. **Five chips, not four.** `property_name` is added. Ruling D68; the mockup is stale, as A1's
   finding 4 already flagged.
2. **`Preview · sample values`, not `Preview as Sarah Chen · 412`.** The preview deliberately
   carries no conversation, so a guest-named label would misdescribe what is on screen.

## Where the brief and A1's report disagreed

**They did not, on any shape.** The preview request, the preview response, the variables endpoint
and `QuickReplyPatch.locale` all match A1's report exactly, and A1's report matches the server
source I read. Two small things worth recording rather than calling disagreements:

- The brief quotes `FALLBACKS` as four values (`"there"`, `"your room"`, `"the front desk"`,
  `"soon"`). The map has **five**; `property_name → "the hotel"` is missing from the brief's list,
  the same omission as the mockup's fourth chip. No behavioural consequence.
- A1's report describes the preview response inline and never names `RenderedQuickReply`. That cost
  a minute of grep; recording it so A3 knows the response models are worth naming.

---

## A test that could not fail, and what replaced it

My first debounce test typed the body with `userEvent.setup({ delay: null })` and asserted exactly
one preview request. **It passed with the debounce set to 0 ms** — a null-delay burst lands inside
one task, so even a zero-length timer coalesces it, and the assertion was about React's batching
rather than about debouncing. I verified this by editing the component, not by reasoning about it.

Replaced with real keystroke spacing (`delay: 20`, 31 characters) and an assertion of fewer than 5
requests. Proved it fails in the direction that matters: with `useDebounced` removed entirely the
test reports **`expected 31 to be less than 5`**. The component was restored to 300 ms and the
suite re-run; nothing about production code was weakened to make the test behave.

I also rewrote the pre-existing *"shows the server error in the panel"* test. It used
`mockResolvedValueOnce`, which claims the **next** fetch — and this screen now fires a debounced
preview on its own schedule, so that one-shot could land on the preview instead of the PATCH it was
written for. `serve()` now takes an optional per-route override and the test asks for a failing
PATCH specifically. That is a latent flake removed, not a behaviour change.

---

## Found but not fixed

1. **`web/src/lib/segments.ts` is exactly the duplicate SMS counter the brief argues against, and
   it already shipped.** It is a line-for-line TypeScript port of `server/app/domain/sms.py`
   (same GSM-7 tables, same 160/153 and 70/67 boundaries) used by `Composer.tsx:67-68` for the
   inbox counter. Its own header says "Keep the two in step". I compared the two and **they agree
   today**, and I did not use it on this screen — the admin counter comes from the server. But the
   brief's reasoning ("a second copy in the client would be free to drift from the one that
   actually bills the customer") describes a file that exists, and the inbox composer is the
   higher-traffic of the two counters. Someone should decide whether the composer should also go
   through `/preview` (it has a conversation id, so it could) or whether the duplicate is accepted
   with a test that pins the two implementations together. Out of scope here; changing the composer
   was not asked for and is not this wave's screen.

2. **`Property.settings["sla_minutes"]` / `Department.escalation_minutes` — A1's finding 5 still
   needs a ruling before A3 ships the department SLA control.** Not mine to settle; repeating it
   because A3 is next and the control is on its screen.

3. **The panel has no client-side validation at all, pre-existing.** `save()` refuses only on an
   empty shortcut/title/body, and does so silently — no message, the button just does nothing. A
   shortcut not matching `^/[a-z0-9_-]+$` makes a round trip to be refused. That is now less bad
   than it was, because the 400 lands against the offending input rather than only in the banner,
   but the silent no-op on an empty required field is still there. I did not change it: it is
   pre-existing behaviour shared with the other admin screens, and fixing it here alone would make
   this panel inconsistent with `AssetsAdmin` and `CategoriesAdmin`.

4. **`qk.assets` and `qk.assetsAll` (and `categories`/`categoriesAll`) are identical functions** in
   `web/src/api/queryKeys.ts` — both return `['assets', propertyId]`. Harmless today (the pairs are
   only meaningfully different for quick replies, which take a search term), but the naming implies
   a distinction that does not exist and invites someone to add a parameter to one of them without
   noticing the invalidation prefix collapses. Pre-existing, untouched.

5. **`usageCount` is labelled "Uses" in the table and "N uses" in the panel, while the mockup says
   "Uses · 30d" and "212 uses · 30d".** The server field is a lifetime counter with no window —
   `quick_replies.py:146` is a bare `r.usage_count += 1` — so the shipped label is the correct one
   and the mockup's "· 30d" is the stale side. Flagging it so review does not read the client as the
   defect. Not changed.

---
---

# A2 · Fix round 1

**Status: DONE_WITH_CONCERNS.** All six items addressed; none declined. One (F5) turned out to need
a different technique than the one suggested, for a reason I reduced to a minimal repro rather than
assumed — the details are below because they will bite A3 too. Two observations are recorded at the
end.

Commits on `main`, from `0992aa8`:

| sha | subject |
| --- | --- |
| `09cdd3d` | refactor(web): extract fieldErrors into a shared, tested normaliser (D90) |
| `4438a5b` | fix(web): a failed save must not accuse the next record's inputs |

## Verification

```
$ cd web && npm test
 Test Files  46 passed (46)
      Tests  446 passed (446)

$ npx tsc -b
(exit 0)

$ npm run lint
> eslint src --ext .ts,.tsx
(exit 0)

$ npm run build
> tsc -b && vite build
dist/index.html                   0.75 kB | gzip:  0.42 kB
dist/assets/index-BgTMxg8U.css   18.45 kB | gzip:  4.95 kB
dist/assets/index-DUUSkDVQ.js   307.42 kB | gzip: 92.44 kB
✓ built in 1.31s
(exit 0)

$ find tests -name "*.d.ts"
(nothing)

$ git status --short
(clean)
```

**426 → 446 passed, 0 failed.** +20: 15 in `src/api/fieldErrors.test.ts` (new file) and 5 in
`QuickRepliesAdmin.test.tsx` (26 → 31). Nothing removed, nothing broken.

### Every fix was mutation-tested

Each change was reverted in turn and the suite re-run, to prove the covering assertion actually
bites rather than merely passing:

```
--- F5 debounce removed          exit=1 :: Failed Tests 2
--- F1 no reset on open/close    exit=1 :: Failed Tests 2
--- F2 stale render kept         exit=1 :: Failed Tests 1
--- F3 bare Insert label         exit=1 :: Failed Tests 1
--- F4 no maxLength              exit=1 :: Failed Tests 1

FAILS-AS-EXPECTED   F5 debounce removed
FAILS-AS-EXPECTED   F1 no reset on open/close
FAILS-AS-EXPECTED   F2 stale render kept
FAILS-AS-EXPECTED   F3 bare Insert label
FAILS-AS-EXPECTED   F4 no maxLength
```

and the same for the new module (`src/api/fieldErrors.test.ts`):

```
array branch dropped           exit=1
object branch dropped          exit=1
input echoed instead of msg    exit=1
```

The file was restored from the in-memory original after each case and the suite re-run green.

---

## F1 · A failed save outliving its panel — upheld, fixed as suggested

Reproduced exactly as described. `create.reset()` / `patch.reset()` / `remove.reset()` are now a
single `clearFailures()` called wherever the panel's subject changes: `open()`, the New button, and
cancel. `remove` is included — its error feeds the same `failed` expression, so leaving it out
would have left one third of the bug.

While there I collapsed three copies of `setDraft(null); setSelected(null)` into `close()`, which
is also the `onSuccess` for save and delete. That is a consequence of the fix (every one of those
sites now needs the reset too), not an unrelated tidy.

Two tests, because the two routes in are different: open another row directly, and cancel then open
a new draft. Both assert **no banner and no field error**, and the second record's Locale is the
valid `"en"`.

**Confirmed against the live server** as well, not only in jsdom. Cleared Locale on `/breakfast`,
saved, got `banner: "Invalid request body"` and `fieldError: "String should have at least 1
character"` under Locale; opened `/gym` and both were `null` with its Locale reading `en`.

## F2 · The previous record's render during the debounce window — upheld, fixed

`preview.data?.body ?? draft.body` becomes `previewStale ? body : preview.data?.body ?? body`.

Worth stating precisely why the old fallback misfired, because it is not the obvious "key changed,
data is undefined" case: `preview` is keyed on `debouncedBody`, which still holds the *previous
row's* body for 300 ms after the click. So `preview.data` was not stale-undefined, it was a
complete, successful render of a different record.

The test freezes the clock before the second click, so the window is not a race. **Confirmed live**
too — clicking `/wifi` then `/towels` and sampling 30 ms in:

```
settled  pane: "Hi there — the network is Harbourview-Guest, …"   busy:false
during   pane: "Fresh towels are on their way to {{room_number}} — about 15 minutes."
         busy:true  counter:"Updating…"   (the towels draft, not the WiFi render)
after    pane: "Fresh towels are on their way to your room — about 15 minutes."  busy:false
```

## F3 · A bare "Insert:" when /variables fails — upheld, fixed

The row renders only when there are chips. When the fetch has failed, a hint takes its place:

> `{{variable_name}}` placeholders are filled in when the reply is sent. The list of names could
> not be loaded.

It deliberately does **not** name the variables. Naming them is the hardcoded copy the fetched chip
list exists to avoid, and a hint that lists four of five would be the mockup's stale list back
again by another route. It says the mechanism exists and that the list is missing, which is what
the admin needs to know.

The test asserts the hint appears, no chip buttons exist, and — the regression that matters — that
**no element's text is exactly `"Insert:"`**.

## F4 · No maxLength on the body — upheld, fixed

`maxLength={1600}`, matching `QuickReplyIn.body` and `PreviewRequest.body` (both
`Field(min_length=1, max_length=1600)`), so it is right for save as well as preview. Tested by
pasting 1700 characters and asserting the value is 1600. Confirmed live: the rendered textarea
reports `maxLength: 1600`.

## F5 · The debounce test's margin — upheld; fake timers work, but not with `userEvent`

The finding is right and the measurement is right. The test is now exact:

```
fireEvent.change(body, …'The pool')      -> previewed is []      (undebounced: 1 request already)
advanceTimersByTime(299)                 -> previewed is []      (inside the window)
fireEvent.change(body, …' is open')      -> restarts the window
advanceTimersByTime(299)                 -> previewed is []
advanceTimersByTime(1)                   -> previewed is ['The pool is open']   (exactly one)
```

No bound was loosened and no production code was touched for it.

**Two things had to change beyond "use fake timers", and I want them on the record because A3 will
hit both.** I reduced each to a minimal repro rather than working around a guess:

1. **`userEvent.type` hangs under vitest fake timers.** Not something about this screen — a bare
   `<textarea>` with no debounce, no query client and no app code hangs identically, and it hangs
   with `delay: null`, with `advanceTimers: vi.advanceTimersByTime`, and with
   `toFake: ['setTimeout','clearTimeout']`. React's async `act` waits on a `setTimeout` that is
   itself faked, and `userEvent`'s `advanceTimers` hook only covers `userEvent`'s own waits, not
   React's. Input is therefore driven by `fireEvent.change` plus **synchronous** `act(() =>
   vi.advanceTimersByTime(n))`, which needs no timer to flush. One `change` is one `onChange`,
   which is all a debounce keyed on the value can observe — so this tests the same contract.
2. **Timers are faked only after the panel is open.** `@testing-library`'s `waitFor` detects
   *jest's* fake timers (`typeof jest !== 'undefined'`) and vitest's are invisible to it, so any
   `findBy*`/`waitFor` inside a faked section sits forever on a clock nobody advances. This is also
   why the first attempt failed loudly: the timeout killed the test *inside* its `try`, so the
   `finally { vi.useRealTimers() }` never ran and fake timers leaked into every subsequent test in
   the file — 13 failures from one bad test. The current version keeps everything that waits
   outside the faked window.

The same applies to the F2 test, which clicks a row with `fireEvent.click` for the same reason.

## F6 · Ruling D90 — fieldErrors extracted — implemented

Now `web/src/api/fieldErrors.ts`, beside `client.ts` whose `ApiError` it reads. **Behaviour is
byte-identical**; the function body moved unchanged and only the doc comment grew.

15 unit tests in `web/src/api/fieldErrors.test.ts`, covering everything the ruling named:

- the object shape, including several fields in one failure and a non-string value;
- the array shape: `loc` to field, `msg` to message, first error per field wins, a nested `loc`
  (`["settings","slaMinutes"]`) landing on `slaMinutes`;
- **`input` never reaching the output** — asserted both by value and over the serialised map;
- absent `details`, `null`, a string, an empty array, a non-`ApiError`, and no error at all;
- a `loc` ending in an array index, alone and alongside a placeable field;
- a field no form has (`code`) not disturbing the field that is on screen (`currency`).

### One thing A3 should know before it writes its forms

The two shapes do not just differ in structure, they differ in **what the value means**, and the
normaliser cannot hide that without inventing wording:

- array shape: `msg` is an English sentence, renderable as-is (`"String should match pattern"`);
- object shape: the value is a **reason code** (`"required"`, and since `ec4ebc1` also
  `"invalid_phone_number"`, `"invalid_timezone"`), meant to be mapped.

On this screen the only reachable code is `"required"`, which reads acceptably raw. On the settings
form it will not: `invalid_phone_number` under the Phone box is not a sentence. That mapping is the
form's job by A1's design ("a form maps a code to a message"), so I kept the pass-through and
documented it rather than inventing a codes-to-copy table this wave has no use for. **A3 should add
one**, and the module is the natural home.

I also left the array-index case *dropping* the entry rather than walking back to the last string
element in `loc`, because the ruling says keep the behaviour identical. Walking back would pin such
an error to the list field's own input, which is arguably better; no request schema in the product
has a list field today, so it is currently unreachable either way. Flagging the choice rather than
making it silently.

---

## Found but not fixed — round 1 additions

9. **`vitest.setup.ts` should reset fake timers.** It is one line
   (`afterEach(() => vi.useRealTimers())`). Without it, any test that times out while timers are
   faked takes the rest of its file down with it — which is exactly what happened to me, 13
   failures from one hang, and the cause is invisible in the output because every victim just says
   "Test timed out". My tests restore in a `finally`, so this is belt-and-braces, but it is a
   global footgun and A3 is about to write more timer-sensitive form tests. I did not add it
   because `vitest.setup.ts` is shared by all 46 files and changing global test setup mid-wave is
   not mine to do unilaterally.

10. **`useDebounced` is now used by one screen and wanted by the next.** A3's settings form has the
    same shape of problem if it previews or validates as you type. It is six lines and lives in
    `QuickRepliesAdmin.tsx`; if A3 needs it, move it to `web/src/lib/` then rather than copying it.
    Not moved pre-emptively — a single-use hook does not need a module yet.
