## Task 11: LogComposer

**Files:**
- Create: `web/src/features/log/LogComposer.tsx`, `web/src/features/log/LogComposer.test.tsx`

**Interfaces:**
- Consumes: `MentionInput`, `tokenFor` (Task 10); `useCreateLogEntry`, `useLogMentionables` (Task 9); `useDepartments` from `web/src/api/hooks/properties.ts` (check the exact export name before using it)
- Produces: `export function LogComposer(props: { onPosted?: (entry: LogEntryOut) => void }): JSX.Element`

- [ ] **Step 1: Write the failing test**

Create `web/src/features/log/LogComposer.test.tsx`. It must cover:

```tsx
it('submits body, department, mentions and the ack audience in one request', async () => {
  // Arrange: render inside the project's test harness (copy the wrapper from
  // web/src/features/messages/*.test.tsx — it provides QueryClient + SessionContext).
  // Act: type a body, pick a department tag, mention a department, toggle
  //      "Requires acknowledgement", pick Housekeeping as the audience, submit.
  // Assert: exactly one POST to /api/p/<id>/log-entries whose JSON body is
  //   {
  //     body: '<typed text with the token inline>',
  //     departmentId: 'd-housekeeping',
  //     mentions: [{ type: 'department', id: 'd-housekeeping' }],
  //     requiresAck: true,
  //     ackAudience: [{ type: 'department', id: 'd-housekeeping' }],
  //   }
})

it('sends multipart when a photo is attached', async () => {
  // Assert the request body is a FormData carrying both `body` and `photo`,
  // and that `mentions` rides along as a JSON string.
})

it('does not submit an empty body', async () => {
  // The submit button is disabled until the body has non-whitespace content.
})

it('shows the server error message when the post fails', async () => {
  // Mock a 422 with the project's error envelope; assert a role="alert" carries the message.
  // This matches the established precedent from GroupPanel (staff messaging Task 14).
})

it('resets every field after a successful post', async () => {
  // Body, mentions, department, photo and the ack toggle all return to empty/false.
  // Staff messaging Task 13 shipped a bug of exactly this shape; do not repeat it.
})
```

Write these out as real tests, not comments — the comments above are the specification for what each must assert.

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npm test -- LogComposer`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

Create `web/src/features/log/LogComposer.tsx`:

- Body via `MentionInput`, holding `{ value, mentions }` in one piece of state so they never drift apart.
- A department `<select>` populated from the departments hook, with an explicit "No department" option.
- A file input accepting `image/jpeg,image/png,image/webp`, with the chosen filename shown and a clear button.
- A "Requires acknowledgement" checkbox. When checked, a second `MentionInput`-style picker (reuse the same component with its own state) chooses the audience. When unchecked, the audience state is cleared so it cannot be submitted stale.
- Submit disabled while `body.trim()` is empty or the mutation is pending.
- On error, render the `ApiError.message` in a `role="alert"`.
- On success, reset all state and call `onPosted?.(entry)`.

- [ ] **Step 4: Run to verify they pass**

Run: `cd web && npm test -- LogComposer`
Expected: PASS, 5 tests.

- [ ] **Step 5: Lint and commit**

```bash
cd web && npm run lint
git add web/src/features/log/LogComposer.tsx web/src/features/log/LogComposer.test.tsx
git commit -m "feat(web): hotel log composer"
```

---

