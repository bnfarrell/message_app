## Task 12: LogEntryCard and AckBar

**Files:**
- Create: `web/src/features/log/AckBar.tsx`, `web/src/features/log/AckBar.test.tsx`, `web/src/features/log/LogEntryCard.tsx`, `web/src/features/log/LogEntryCard.test.tsx`

**Interfaces:**
- Consumes: `TOKEN_RE` (Task 10); `useAckLogEntry`, `useSetLogPinned` (Task 9); `useSession` for `can()`
- Produces:
  - `export function AckBar(props: { entry: LogEntryOut }): JSX.Element | null`
  - `export function LogEntryCard(props: { entry: LogEntryOut }): JSX.Element`

- [ ] **Step 1: Write the failing tests**

`AckBar.test.tsx` must assert:

- Renders `null` when `entry.requiresAck` is false.
- Shows `2 of 5 acknowledged` when `acks.length === 2` and `ackExpectedCount === 5`.
- Shows an enabled "Acknowledge" button when `canAck` is true, and clicking it fires one POST to `/ack`.
- Shows "You acknowledged this" and no button when `ackedByMe` is true.
- Lists the outstanding people's names when `outstanding` is non-empty.
- Renders no Acknowledge button when `canAck` is false and `ackedByMe` is false (the viewer was never asked).

`LogEntryCard.test.tsx` must assert:

- Renders author name, the shift badge text (`am` → "AM"), and the department tag when present.
- Renders a mention token as the display name only — the raw `@[Ana Marquez](user:...)` string must never appear in the DOM. Assert on `queryByText(/\]\(user:/)` being null.
- Renders an `<img>` when `photoUrl` is set and none when it is null.
- Shows a Pin button only when `can('pin_log_entry')`, and clicking it fires POST `/pin`; when `entry.pinned` is true the button reads "Unpin" and fires DELETE.
- A mention whose `displayName` contains HTML (`<b>x</b>`) renders as literal text, not markup.

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npm test -- "AckBar|LogEntryCard"`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement**

`AckBar.tsx`: a small progress row. Prefer plain text plus a `<progress>` or a Tailwind bar consistent with existing components; do not invent a new visual language — read `web/src/features/board/` for the existing badge and progress idiom first.

`LogEntryCard.tsx`: renders the body by splitting on `TOKEN_RE` and mapping each match to a styled `<span>` carrying the display name captured in group 1. **Never use `dangerouslySetInnerHTML`.** Header row: author name, relative time, shift badge, department tag, pin control. Footer: photo, links to a work order or conversation when present, then `<AckBar>`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd web && npm test -- "AckBar|LogEntryCard"`
Expected: PASS

- [ ] **Step 5: Lint and commit**

```bash
cd web && npm run lint
git add web/src/features/log/AckBar.tsx web/src/features/log/AckBar.test.tsx web/src/features/log/LogEntryCard.tsx web/src/features/log/LogEntryCard.test.tsx
git commit -m "feat(web): hotel log entry card and acknowledgement bar"
```

---

