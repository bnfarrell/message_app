### Task 21: End-to-end tests, production build and README

**Files:**
- Create: `web/playwright.config.ts`, `web/tests/e2e/smoke.spec.ts`, `web/tests/e2e/presence.spec.ts`
- Modify: `web/src/routes.tsx` (delete the `Placeholder` component — every screen is real now), `README.md`
- Test: the two specs above are the test

**Interfaces:**
- Consumes: every screen.
- Produces: `npm run test:e2e`; a README section covering the web setup, the simulator and the two-surface dev loop.

**§7 requires exactly two specs.** `smoke.spec.ts` is the full loop; `presence.spec.ts` is §11.1 #3.

**The specs run against a real server with real seed data.** Playwright starts both processes through `webServer`. The seed is deterministic (`random.Random(42)`), but the specs must still not depend on *which* seeded conversation is which — they create their own guest traffic through the simulator and find it by the text they sent. A spec that asserts on "the third row" breaks the first time the seed shifts.

- [ ] **Step 1: Write `web/playwright.config.ts`**

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false, // one server, one database — parallel specs would fight over seed state
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
  },
  webServer: [
    {
      // dev_start.py migrates and seeds only if empty, and runs the worker (START_WORKER=1).
      command: 'python ../server/dev_start.py',
      url: 'http://127.0.0.1:5000/api/health',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
```

The health path is `/api/health` (`server/app/api/health.py:6`, on a blueprint with no prefix) — verified, so no lookup is needed. A wrong `url` here makes Playwright hang for two minutes and then fail with a timeout that looks like a server bug.

- [ ] **Step 2: Write `web/tests/e2e/smoke.spec.ts`**

The §7 loop, in one spec, with a unique marker so it never collides with seed data or a previous run.

```ts
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'Password123!'
const MARKER = `e2e-${Date.now()}`
const GUEST_TEXT = `The AC is broken ${MARKER}`

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/app\//)
}

test('a guest text becomes a reply, a work order, and a closed loop', async ({ browser }) => {
  const guest = await browser.newContext()
  const agent = await browser.newContext()
  const engineer = await browser.newContext()
  const simulator = await guest.newPage()
  const agentPage = await agent.newPage()
  const engineerPage = await engineer.newPage()

  // 1. The guest texts the hotel.
  await simulator.goto('/sim')
  await simulator.getByText('Sarah Chen').click()
  await expect(simulator.getByTestId('sms-in').first()).toBeVisible()
  await simulator.getByPlaceholder(/text as/i).fill(GUEST_TEXT)
  await simulator.getByRole('button', { name: /^send$/i }).click()
  await expect(simulator.getByTestId('sms-out').filter({ hasText: MARKER })).toBeVisible()

  // 2. The agent sees it and replies.
  await signIn(agentPage, 'ava@hvh.test')
  await agentPage.goto('/app/inbox')
  const row = agentPage.getByRole('link').filter({ hasText: MARKER })
  await expect(row).toBeVisible({ timeout: 20_000 })
  await row.click()
  await expect(agentPage.getByText(GUEST_TEXT)).toBeVisible()

  const replyText = `Engineering is on the way ${MARKER}`
  await agentPage.getByRole('textbox').fill(replyText)
  await agentPage.getByRole('button', { name: /^send$/i }).click()

  // 3. The reply reaches delivered — the worker and the socket, end to end.
  await expect(agentPage.getByText(replyText)).toBeVisible()
  await expect(agentPage.getByText('Delivered').first()).toBeVisible({ timeout: 30_000 })
  await expect(simulator.getByTestId('sms-in').filter({ hasText: replyText })).toBeVisible({
    timeout: 30_000,
  })

  // 4. The agent raises a work order, pre-filled from the conversation.
  await agentPage.getByRole('button', { name: /create work order/i }).click()
  await expect(agentPage.getByLabel('Title')).not.toHaveValue('')
  const woTitle = `AC repair ${MARKER}`
  await agentPage.getByLabel('Title').fill(woTitle)
  await agentPage.getByRole('button', { name: /^create$/i }).click()
  await expect(agentPage.getByRole('link', { name: new RegExp(woTitle) })).toBeVisible()

  // 5. The engineer completes it.
  await signIn(engineerPage, 'eli@hvh.test')
  await engineerPage.goto('/app/board')
  await engineerPage.getByRole('link').filter({ hasText: woTitle }).click()
  await engineerPage.getByRole('button', { name: 'In progress' }).click()
  await expect(engineerPage.getByRole('button', { name: 'Complete' })).toBeVisible()
  await engineerPage.getByRole('button', { name: 'Complete' }).click()

  // 6. The agent gets the draft prompt without reloading, and sends it.
  const banner = agentPage.getByTestId('draft-prompt')
  await expect(banner).toBeVisible({ timeout: 30_000 })
  await expect(banner).toContainText(/is complete/i)
  await banner.getByRole('button', { name: /use draft/i }).click()
  await expect(agentPage.getByRole('textbox')).not.toHaveValue('')
  const draftText = await agentPage.getByRole('textbox').inputValue()
  await agentPage.getByRole('button', { name: /^send$/i }).click()

  // 7. The guest receives it, and the prompt is gone.
  await expect(simulator.getByTestId('sms-in').filter({ hasText: draftText.slice(0, 30) })).toBeVisible({
    timeout: 30_000,
  })
  await expect(agentPage.getByTestId('draft-prompt')).toHaveCount(0)

  await guest.close()
  await agent.close()
  await engineer.close()
})
```

- [ ] **Step 3: Write `web/tests/e2e/presence.spec.ts`** (§11.1 #3)

```ts
import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'Password123!'

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/app\//)
}

test('two agents on one conversation each see the other within 2 seconds', async ({ browser }) => {
  const first = await browser.newContext()
  const second = await browser.newContext()
  const ava = await first.newPage()
  const marcus = await second.newPage()

  await signIn(ava, 'ava@hvh.test')
  await ava.goto('/app/inbox')
  await ava.getByRole('link').first().click()
  await expect(ava).toHaveURL(/\/app\/inbox\/.+/)
  const url = ava.url()

  await signIn(marcus, 'marcus@hvh.test')
  await marcus.goto(url)

  // §11.1 #3: each sees the other. The expect timeout is 15s, so assert the 2s
  // requirement explicitly rather than leaning on the default.
  await expect(ava.getByText(/Marcus is (viewing|replying)/)).toBeVisible({ timeout: 2000 })
  await expect(marcus.getByText(/Ava is (viewing|replying)/)).toBeVisible({ timeout: 2000 })

  // Composing flips the verb for the other viewer.
  await marcus.getByRole('textbox').click()
  await expect(ava.getByText('Marcus is replying')).toBeVisible({ timeout: 3000 })

  // Leaving clears it — the sweeper drops entries older than 10s.
  await marcus.goto('/app/board')
  await expect(ava.getByText(/Marcus is/)).toHaveCount(0, { timeout: 20_000 })

  await first.close()
  await second.close()
})
```

- [ ] **Step 4: Run the E2E suite**

```bash
cd web && npx playwright install chromium && npm run test:e2e
```

Expected: both specs PASS. If the smoke spec fails at step 3 (`Delivered`), the job worker is not running — check that `START_WORKER=1` is in `server/.env`. If it fails at step 6, the draft prompt is not arriving: check the socket in the browser trace (`trace: 'retain-on-failure'` leaves one under `test-results/`).

- [ ] **Step 5: Remove the scaffolding and verify the production build**

Delete the `Placeholder` component from `routes.tsx` — every route now has a real screen — and confirm nothing references it.

```bash
cd web && npm run build && node -e "const fs=require('fs');const files=fs.readdirSync('dist/assets');const hit=files.filter(f=>f.endsWith('.js')).find(f=>fs.readFileSync('dist/assets/'+f,'utf8').includes('Phone simulator'));if(hit)throw new Error('Simulator leaked into the production bundle: '+hit);console.log('simulator excluded from '+files.length+' asset files')"
```

Expected: `tsc -b` clean, and the node check prints the exclusion confirmation. If it throws, `import.meta.env.DEV` is not gating the lazy import and §5.2's "excluded from the production build" is violated.

Also confirm the full suite one more time, both sides:

```bash
cd server && python -m pytest -q && cd ../web && npm test && npx tsc -b && npm run lint
```

- [ ] **Step 6: Update the README**

Add a **Web client** section after the existing server setup, and extend the seeded-logins table note. Write exactly this into `README.md`, adjusting only if a command differs:

````markdown
## Web client

Requires Node 20+.

```bash
cd web
npm install
npm run dev        # http://localhost:5173
```

Run the server in a second terminal (`.\start.bat` on Windows, or `npm run server`). Vite proxies
`/api`, `/ws` and `/a` to `127.0.0.1:5000`, so there is no CORS to configure in development.

| Command | What it does |
|---|---|
| `npm run dev` | Vite dev server on 5173 |
| `npm run build` | Type-check and build to `web/dist` |
| `npm test` | Vitest unit and component tests |
| `npm run test:e2e` | Playwright; starts both servers itself |
| `npm run gen:types` | Regenerate `src/api/types.generated.ts` from `src/api/schema.json` |

### Regenerating the API types

`web/src/api/schema.json` is written by the server, so after any change to a Pydantic
request/response model:

```bash
npm run schema      # from the repo root — writes web/src/api/schema.json
cd web && npm run gen:types
```

Both files are committed. `server/tests/test_schema_export.py` fails if the schema is stale, and a
Vitest fails if the generated types are.

### The phone simulator

`http://localhost:5173/sim` — dev builds only. Pick a seeded guest, text the hotel, and watch the
staff inbox react. Quick buttons cover `STOP`, `HELP`, a maintenance complaint and a card number
(to demonstrate redaction). Numbers ending `0000` fail delivery on purpose with mock error `30007`
so the retry path can be exercised.

### Themes

Dark is the default. The **Theme** control in the left nav toggles light, and the choice is saved
per user (`PATCH /api/auth/prefs`), so it follows them to another machine. With no saved choice the
device's `prefers-color-scheme` decides.
````

- [ ] **Step 7: Check the §10 acceptance list**

Walk it explicitly and record the result of each in the task report:
- [ ] `python -m venv`, `pip install -e "server[dev]"`, `npm install`, `npm run seed`, then both dev servers — brings up both surfaces on a clean machine
- [ ] all server tests pass, including the §11.1 suite
- [ ] the Playwright smoke passes
- [ ] every screen in §5.2 is reachable by the roles that should see it and hidden from the ones that should not — check all six seeded roles
- [ ] the README documents setup, seeded credentials, the simulator and the Postgres switch

- [ ] **Step 8: Commit**

```bash
git add web/playwright.config.ts web/tests/e2e web/src/routes.tsx README.md
git commit -m "test(web): Playwright smoke and presence specs, and document the web client"
```

---

## Self-review

Run through this before declaring the plan done; it is a checklist for the plan's author, not a task.

**Spec coverage, §5.2's screen table:** Login (Task 8) · landing redirect (8) · Inbox list and detail (12, 13) · composer (14) · draft prompts and work-order creation (15) · Board and WO detail (16) · Analytics (17) · Notification centre (18) · Admin CRUD (19) · Simulator (20). §5.3's inbox behaviours: queue order (12), row anatomy (12), presence header (13), quick replies (14), asset picker (14), segment counter (14), optimistic send and retry (14), create WO (15), draft prompt banner (15), notes in-thread (13), archive with category (15), opted-out chip and enabled composer (13, 14). §5.0: both palettes (1), fonts (1), 184 px nav and 44 px controls (1, 9), SLA chip (10), CSS bars (17), theme toggle persisted (6, 7). §7's four required web tests: segment counter (14), quick-reply palette filtering (14), SLA chip thresholds (10), transition button enablement (16). §7's E2E: smoke and presence (21). §4.8 type generation with a staleness guard (2). §6's compliance surfaces: redaction chip (13), consent chip and warning (13, 14), STOP/START/HELP through the simulator (20).

**Known gaps, stated rather than hidden:**
- §4.7 lists `GET analytics/overview` with an `Export` affordance but no export endpoint exists. Task 17 exports client-side CSV from what is already on screen and says so.
- `NotificationBell` appears in the spec's file sketch; Task 18 drops it because the nav badge is the only mount point, and an unused component is a liability.
- `GuestPicker.tsx` / `ServerLog.tsx` likewise dropped in Task 20.
- The mockups show work-order **photos**; there is no upload endpoint in Phase 1, so no task builds it. Task 16 omits the photo block rather than rendering a dead affordance. **This is a visible difference from `WorkOrder.dc.html` and should be raised with the user rather than quietly shipped.**
- The `Mobile.dc.html` department-staff task list is a responsive presentation of the Board, not a separate screen; Task 16's list view plus the shell's responsive nav covers it. No dedicated mobile route.
