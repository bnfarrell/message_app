# Task 11: LogComposer — Report

## What was implemented

`web/src/features/log/LogComposer.tsx` — `export function LogComposer(props: { onPosted?: (entry: LogEntryOut) => void })`.

- Body via `MentionInput`, with `body`/`mentions` held together in one `onChange` call so
  they never drift apart.
- A department `<select id="log-department">` populated from `useDepartments()` (found in
  `web/src/api/hooks/users.ts` — the brief's pointer to `properties.ts` was stale; confirmed
  by grepping every existing consumer, e.g. `CreateWorkOrderModal.tsx`), with an explicit
  "No department" option.
- A file input (`id="log-photo"`, `accept="image/jpeg,image/png,image/webp"`) showing the
  chosen filename and a "Clear" button that also resets the underlying DOM input value via a
  ref (React can't clear a file input's value through state alone).
- A "Requires acknowledgement" checkbox. Checking it mounts a second `MentionInput` (its own
  `audienceText`/`audienceMentions` state) for the ack audience. Unchecking it clears that
  state immediately, not just at submit — so a re-check later starts clean rather than
  resubmitting a stale pick.
- Submit disabled while `body.trim()` is empty or `create.isPending`.
- `create.error?.message` rendered in `role="alert"` (GroupPanel precedent).
- On success: `reset()` clears body, mentions, department, photo (state + DOM value),
  requiresAck, and audience state/text, then calls `onPosted?.(entry)`.

Modelled on `web/src/features/inbox/CreateWorkOrderModal.tsx` (select styling — the
`FIELD`/`SELECT` class constants and `<label htmlFor>` pattern — and the mount/serve/postCalls
test shape) and `web/src/features/inbox/ThreadView.tsx` / `Composer.tsx` (file-input-with-ref
reset, `role="alert"` placement).

### The carried-forward defect (Task 10 review)

`MentionInput` records a `MentionRef` on pick but never removes it if the token text is later
deleted. Fixed at submit time with:

```ts
function pruneMentions(text: string, mentions: MentionRef[]): MentionRef[] {
  const present = new Set<string>()
  for (const match of text.matchAll(TOKEN_RE)) {
    present.add(`${match[2]}:${match[3]}`)
  }
  return mentions.filter((m) => present.has(`${m.type}:${m.id}`))
}
```

Used via `text.matchAll(TOKEN_RE)`, not `.exec()`/`.test()` on the shared `g`-flagged
instance — `matchAll` requires (and internally clones) a global regex, so it doesn't leak
`lastIndex` across calls the way calling `.exec()`/`.test()` directly on `TOKEN_RE` would.
Applied to both the body mentions and the ack audience (same picker, same bug class).

## Tests written (`web/src/features/log/LogComposer.test.tsx`, 6 tests)

1. `submits body, department, mentions and the ack audience in one request` — types a body,
   mentions Housekeeping, selects Housekeeping as department, checks "Requires
   acknowledgement," mentions Housekeeping as audience, submits; asserts the exact JSON POST
   body via `toEqual`.
2. `sends multipart when a photo is attached` — mentions Housekeeping in the body, attaches a
   photo, submits; asserts `FormData` carrying `body`/`photo`, and `mentions` as a JSON
   string.
3. `does not submit an empty body` — submit button disabled with no text, still disabled with
   whitespace-only text, enabled once real content is typed.
4. `shows the server error message when the post fails` — mocks a 422 with the project's
   error envelope; asserts `role="alert"` carries the message.
5. `resets every field after a successful post` — fills body+mention, department, photo,
   ack toggle, posts, then asserts all of them are back to empty/false/unmounted (including
   the audience picker being gone once unchecked automatically reset).
6. `prunes a mention whose token text was deleted before submit` (the carried-forward defect
   fix) — mentions Ana, then clears the body and retypes text with no token, submits, asserts
   `mentions` is `[]`.

One notable fixture detail: `TOKEN_RE` only matches ids shaped like a real UUID
(`[0-9a-f-]{36}`), so test fixtures use UUID-shaped ids (`aaaaaaaa-aaaa-...`) rather than
friendly ids like `d-housekeeping` — with a friendly id, `pruneMentions` would silently strip
every mention regardless of whether the token was actually deleted, since the regex would
never match the token in the first place. Caught this via TDD (see RED/GREEN below).

## TDD evidence

**RED** — test file written against a component that didn't exist yet:
```
$ cd web && npm test -- LogComposer
Error: Failed to resolve import "./LogComposer" from ".../LogComposer.test.tsx"
Test Files  1 failed (1)
     Tests  no tests
```

**Intermediate RED** (implementation written, first run) — ambiguous `role="option"` matches
because native `<select><option>` also exposes `role="option"`, colliding with the
MentionInput dropdown's `<li role="option">`:
```
$ npm test -- LogComposer
Tests  3 failed | 3 passed (6)
"Found multiple elements with the role 'option' and name /Housekeeping/i"
```
Fixed by scoping to `within(screen.getByRole('listbox'))`.

**Second RED** — `mentions`/`ackAudience` came back `[]` even though the token was present in
body text:
```
Tests  2 failed | 4 passed (6)
- "mentions": [{ "id": "d-housekeeping", "type": "department" }]
+ "mentions": []
```
Root cause: `d-housekeeping` isn't a 36-char UUID, so `TOKEN_RE` never matched it — this was
the fixture bug described above, not a component bug. Fixed by switching to UUID-shaped ids.

**Third RED** — `sends multipart when a photo is attached` couldn't find the listbox:
```
Unable to find role="listbox"
```
Cause: typing `'Photo of @Housekeeping cart'` in one call includes the trailing space+text
after the mention, which closes the query (and the listbox) before the click could land.
Fixed by splitting the type call around the pick.

**GREEN**:
```
$ cd web && npm test -- LogComposer
✓ src/features/log/LogComposer.test.tsx (6 tests) 4121ms
  ✓ submits body, department, mentions and the ack audience in one request
  ✓ sends multipart when a photo is attached
  ✓ does not submit an empty body
  ✓ shows the server error message when the post fails
  ✓ resets every field after a successful post
  ✓ prunes a mention whose token text was deleted before submit
Test Files  1 passed (1)
     Tests  6 passed (6)
```

**Full suite / lint / build**:
```
$ npm test         → Test Files 62 passed (62); Tests 617 passed (617)   [baseline 611 + 6 new]
$ npm run lint      → clean (no output)
$ npm run build     → tsc -b && vite build succeeded, 165 modules, no errors
```

## Sabotage verification (break → fail → revert), one at a time

1. **Test 1** (full JSON body): changed `departmentId: departmentId || undefined` to a hardcoded
   `undefined`. Ran `-t "submits body, department, mentions and the ack audience"` → failed
   (`departmentId` key missing from the diff). Reverted.
2. **Test 2** (multipart): changed `photo: photo ?? undefined` to a hardcoded `undefined`. Ran
   `-t "sends multipart when a photo is attached"` → failed (`expected '{"body":...}' to be an
   instance of FormData` — fell back to the JSON branch since no photo was passed). Reverted.
3. **Test 3** (disabled submit): changed `disabled={create.isPending || !body.trim()}` to
   `disabled={create.isPending}`. Ran `-t "does not submit an empty body"` → failed (`Received
   element is not disabled`). Reverted.
4. **Test 4** (error alert): deleted the `role="alert"` block entirely. Ran `-t "shows the
   server error message when the post fails"` → failed (`findByRole('alert')` timed out).
   Reverted.
5. **Test 5** (reset after post): changed `onSuccess: (entry) => { reset(); onPosted?.(entry) }`
   to drop the `reset()` call. Ran `-t "resets every field after a successful post"` → failed
   (body still held the typed token text after the mocked post resolved). Reverted.
6. **Test 6** (pruning — the carried-forward defect): changed
   `mentions: pruneMentions(body, mentions)` to plain `mentions`. Ran `-t "prunes a mention
   whose token text was deleted before submit"` → failed (`expected [{ type: 'user', ... }]
   to deeply equal []` — exactly the wrong-notification bug this task exists to close).
   Reverted.

After each sabotage/revert cycle the file was diffed back to the pre-sabotage state (confirmed
by reading the file back before the final commit). Full suite, lint, and build were re-run
clean after all reverts, immediately before committing.

## Files changed

- `web/src/features/log/LogComposer.tsx` (new)
- `web/src/features/log/LogComposer.test.tsx` (new)

No other files touched. `server/data/app.db*` and `server/app/domain/users.py` were left
untouched and unstaged, per instructions.

## Self-review findings

- `useDepartments` genuinely lives in `web/src/api/hooks/users.ts`, not `properties.ts` as the
  brief suggested — verified via every existing import site before using it.
- `ackAudience` is sent as `undefined` (omitted from the JSON) rather than `[]` when
  `requiresAck` is false, consistent with `CreateLogEntryRequest`'s optional-field shape and
  what the multipart branch in `useCreateLogEntry` already does (`if (rest.ackAudience?.length)
  form.set(...)`).
- Pruning is applied to both the body mentions and the ack-audience mentions, even though the
  brief's defect description only names "the mentions in the body." Same picker, same bug
  shape, and the ack audience also drives notifications per spec §6 — leaving it unpruned would
  reintroduce the identical defect one field over for a few extra lines of shared logic.
- Field IDs (`log-department`, `log-photo`) and `role="alert"` line up with the project's
  established conventions (`CreateWorkOrderModal`, `GroupPanel`).

## Concerns

- None outstanding. The one thing worth flagging to whoever writes Task 12 (the entry
  renderer): mentionable ids from the real API are presumably true UUIDs, so `TOKEN_RE`'s
  36-char-hex assumption should hold in production — this only bit as a *test fixture* issue
  here, not a component defect, but it's worth knowing the regex is that strict if other test
  fixtures reuse short friendly ids like `dept-eng`.
