## Task 13: LogPage, route and nav

**Files:**
- Create: `web/src/features/log/LogPage.tsx`, `web/src/features/log/LogPage.test.tsx`
- Modify: `web/src/routes.tsx`, `web/src/components/navModel.ts`
- Test: `web/src/components/navModel.test.ts`

**Interfaces:**
- Consumes: `LogComposer` (Task 11), `LogEntryCard` (Task 12), `useLogFeed` (Task 9)
- Produces: the `/app/log` route and the "Log" rail entry

- [ ] **Step 1: Write the failing tests**

`LogPage.test.tsx` must assert:

- Renders a tab strip whose only tab is "Posts" and which is selected.
- Groups entries under day headings, with today's reading `Today · 2 posts` for two entries created today.
- Renders the pinned block above the day groups, labelled "Pinned", when `feed.pinned` is non-empty, and omits the block entirely when it is empty.
- The shift filter changes the query — selecting "Overnight" issues a request with `shift=overnight`.
- The "Mentioning me" toggle issues a request with `mentioningMe=true`.
- An empty feed renders an empty state, not a bare page.

Append to `navModel.test.ts`:

```ts
it('shows the Log entry to every staff role', () => {
  const groups = visibleNavGroups(() => false) // no capabilities at all
  const items = groups.flatMap((g) => g.items)
  expect(items.find((i) => i.to === '/app/log')).toBeTruthy()
})
```

That test passes only if the entry's `needs` is `[]`, which is correct — `view_log` is granted to every role, so gating the rail entry on it would be a lie that the `can()` mock would expose.

- [ ] **Step 2: Run to verify they fail**

Run: `cd web && npm test -- "LogPage|navModel"`
Expected: FAIL

- [ ] **Step 3: Implement the page**

Create `web/src/features/log/LogPage.tsx`:

- Header, then `<LogComposer>`, then filters (shift `<select>`, department `<select>`, "Mentioning me" toggle), then the pinned block, then the day-grouped feed.
- **Day grouping uses the BROWSER's local day, not the property timezone.** The spec's §7 wording says property timezone; this is a deliberate departure, ruled during execution — see the reasoning below. Add a small `dayKey(iso)` helper to `web/src/lib/time.ts` beside the existing `relativeTime`/`formatClock` (there is no day-grouping helper yet, and `formatClock` already renders in browser-local time). Do not add a date library.

  Why browser-local: every existing timestamp in this app already renders in the viewer's local zone — `formatClock` calls `toLocaleTimeString([])` with no zone argument — and the property timezone is not currently plumbed into any display component. Grouping this one screen by property time would make the log disagree with every other timestamp in the product, and would require new plumbing to fetch property settings into the feed. Hotel staff are physically at the property, so the two coincide in the overwhelming majority of cases.

  What stays authoritative: the **shift badge** is computed server-side from the property's timezone and stored on the row (spec §3.3), so shift labelling is unaffected by this choice. Only the visual day heading follows the viewer.
- The tab strip is a real `role="tablist"` with one `role="tab"`, so Wakeups and Followups slot in later without restructuring (spec §7).
- Loading and error states consistent with the other pages — copy the pattern from `MessagesPage`.

- [ ] **Step 4: Wire the route**

In `web/src/routes.tsx`, add the import and the route inside the `AppLayout` block, after `messages`:

```tsx
import { LogPage } from './features/log/LogPage'
```

```tsx
          <Route path="log" element={<LogPage />} />
```

No `RequireCapability` wrapper — `view_log` is granted to every role.

- [ ] **Step 5: Add the nav entry**

In `web/src/components/navModel.ts`, in the `Overview` group after `Messages`:

```ts
      { label: 'Log', to: '/app/log', icon: 'log', needs: [] },
```

**Add a `log` icon** to `web/src/components/NavIcon.tsx` — both the `IconName` union and the `PATHS` record. The existing set is `inbox | board | analytics | alerts | admin | theme | signout | search`, and `Messages` already reuses `inbox`, so reusing it again would give the rail three visually identical entries out of five. A ruled-notebook glyph, matching the existing 24×24 stroke style (`fill="none"`, `strokeWidth={1.75}`):

```ts
  log: 'M6 3h11a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Zm3 0v18M12 8h4M12 12h4',
```

`PATHS` is typed `Record<IconName, string>`, so TypeScript fails the build if the union and the record disagree — adding to only one is caught at compile time, not review.

- [ ] **Step 6: Run everything**

Run: `cd web && npm test && npm run lint && npm run build`
Expected: PASS, clean

- [ ] **Step 7: Commit**

```bash
git add web/src/features/log/LogPage.tsx web/src/features/log/LogPage.test.tsx web/src/routes.tsx web/src/components/navModel.ts web/src/components/navModel.test.ts
git commit -m "feat(web): assemble the hotel log page"
```

---

