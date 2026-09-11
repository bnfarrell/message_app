### Task 2: Generated types and the staleness guard

**Files:**
- Create: `web/src/api/types.generated.ts` (generated output, committed)
- Create: `web/src/api/types.ts` (hand-written re-export surface)
- Test: `web/src/api/types.generated.test.ts`
- Already present: `web/src/api/schema.json` (67 models, committed by the server phase)

**Interfaces:**
- Consumes: Task 1's `package.json` `gen:types` script.
- Produces: every model name as a TypeScript interface, re-exported from `src/api/types.ts`. Later tasks import **only** from `./api/types` — never from `types.generated.ts` directly, so the generated file can be regenerated without touching import sites. The names later tasks rely on, verbatim from `$defs`:
  `SessionOut`, `UserOut`, `MembershipOut`, `LoginRequest`, `Role`,
  `ConversationSummary`, `ConversationDetail`, `ConversationPatch`, `ConversationStatus`,
  `MessageOut`, `NoteOut`, `DraftPromptOut`, `SendMessageRequest`, `CreateNoteRequest`,
  `GuestOut`, `GuestDetail`, `StayOut`, `GuestThread`, `GuestThreadMessage`,
  `WorkOrderOut`, `WorkOrderBrief`, `WorkOrderDetail`, `WorkOrderEventOut`, `WorkOrderPrefill`,
  `CreateWorkOrder`, `WorkOrderPatch`, `WorkOrderStatus`, `WorkOrderType`, `Priority`,
  `QuickReplyOut`, `QuickReplyIn`, `QuickReplyPatch`, `RenderRequest`, `RenderedQuickReply`,
  `AssetOut`, `AssetIn`, `AssetPatch`, `CategoryOut`, `CategoryIn`, `CategoryPatch`,
  `DepartmentOut`, `StaffUserOut`, `CreateStaffRequest`, `StaffPatch`,
  `NotificationOut`, `UnreadCount`,
  `Overview`, `AgentStats`, `HourBucket`, `DayBucket`, `ResponseBucket`, `DepartmentBucket`,
  `SimGuest`, `SimEvent`,
  `Channel`, `DeliveryStatus`, `Direction`, `AuthorType`, `SmsConsentStatus`,
  `DraftPromptStatus`, `WorkOrderEventType`, `StayStatus`, `AssetType`, `LocationType`,
  `DepartmentType`, `ListQuery`, `WorkOrderListQuery`.

**Why a re-export file:** `types.generated.ts` carries a "do not edit" banner and one junk interface (`ConciergeAPI`, the empty document root). `types.ts` is where we name that boundary and where a future hand-written helper type would live.

- [ ] **Step 1: Write the failing staleness test**

This is the §4.8 guard on the web side: the committed generated file must be exactly what the generator produces from the committed schema. It shells out to the same script `npm run gen:types` runs, writes to a temp file, and compares — so drift cannot be committed even if someone hand-edits the output.

`web/src/api/types.generated.test.ts`:

```ts
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const here = new URL('.', import.meta.url).pathname
const schema = join(here, 'schema.json')
const committed = join(here, 'types.generated.ts')

describe('generated API types', () => {
  it('are exactly what the generator produces from the committed schema', () => {
    const out = join(mkdtempSync(join(tmpdir(), 'json2ts-')), 'types.ts')
    execFileSync(
      'npx',
      ['json2ts', '--input', schema, '--output', out,
       '--style.singleQuote', '--no-additionalProperties', '--unreachableDefinitions'],
      { stdio: 'pipe', shell: process.platform === 'win32' },
    )
    expect(readFileSync(committed, 'utf8')).toBe(readFileSync(out, 'utf8'))
  }, 60_000)

  it('exports the models the client depends on', () => {
    const src = readFileSync(committed, 'utf8')
    for (const name of [
      'SessionOut', 'ConversationSummary', 'ConversationDetail', 'MessageOut',
      'WorkOrderDetail', 'WorkOrderPrefill', 'QuickReplyOut', 'AssetOut',
      'NotificationOut', 'Overview', 'AgentStats', 'SimGuest', 'GuestThread',
    ]) {
      expect(src, `${name} was not generated`).toContain(`export interface ${name} `)
    }
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web && npx vitest run src/api/types.generated.test.ts
```

Expected: FAIL — `ENOENT` reading `types.generated.ts`, because nothing has generated it yet.

- [ ] **Step 3: Generate the types**

```bash
cd web && npm run gen:types
```

`--unreachableDefinitions` is load-bearing. The exported document is `{"$schema": …, "title": "Concierge API", "$defs": {…67 models…}}` — the root has **no `properties`**, so without that flag json2ts emits only the empty `ConciergeAPI` interface and every model is silently missing.

- [ ] **Step 4: Write `web/src/api/types.ts`**

```ts
/**
 * The client's type surface. Import from here, never from `types.generated.ts`:
 * that file is overwritten by `npm run gen:types` and carries the document root
 * (`ConciergeAPI`), which is an artefact of the export, not a model.
 */
export type {
  AgentStats, AssetIn, AssetOut, AssetPatch, AssetType, AuthorType,
  CategoryIn, CategoryOut, CategoryPatch, Channel, ConversationDetail,
  ConversationPatch, ConversationStatus, ConversationSummary, CreateNoteRequest,
  CreateStaffRequest, CreateWorkOrder, DayBucket, DeliveryStatus, DepartmentBucket,
  DepartmentOut, DepartmentType, Direction, DraftPromptOut, DraftPromptStatus,
  GuestDetail, GuestOut, GuestThread, GuestThreadMessage, HourBucket, ListQuery,
  LocationType, LoginRequest, MembershipOut, MessageOut, NoteOut, NotificationOut,
  Overview, Priority, QuickReplyIn, QuickReplyOut, QuickReplyPatch, RenderRequest,
  RenderedQuickReply, ResponseBucket, Role, SendMessageRequest, SessionOut, SimEvent,
  SimGuest, SmsConsentStatus, StaffPatch, StaffUserOut, StayOut, StayStatus,
  UnreadCount, UserOut, WorkOrderBrief, WorkOrderDetail, WorkOrderEventOut,
  WorkOrderEventType, WorkOrderListQuery, WorkOrderOut, WorkOrderPatch,
  WorkOrderPrefill, WorkOrderStatus, WorkOrderType,
} from './types.generated'
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd web && npm test && npx tsc -b
```

Expected: both type tests PASS and `tsc -b` is clean. A `tsc` error naming a type in the `export type` list means the generated name differs from the `$defs` key — fix the re-export to match the generated file, never the other way round.

- [ ] **Step 6: Confirm the loop is closed end to end**

```bash
cd .. && npm run schema && cd web && npm run gen:types && git status --short
```

Expected: **no changes** to `schema.json` or `types.generated.ts`. If either moves, the server's export and the committed copies had already drifted — report that as a defect rather than committing the churn silently, because it means the server's own `test_schema_export.py` guard is not covering something.

- [ ] **Step 7: Commit**

```bash
git add web/src/api/types.generated.ts web/src/api/types.ts web/src/api/types.generated.test.ts
git commit -m "feat(web): generate API types from the committed schema, with a staleness guard"
```

---

