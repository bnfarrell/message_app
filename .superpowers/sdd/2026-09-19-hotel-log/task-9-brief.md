## Task 9: Web data layer

**Files:**
- Create: `web/src/api/hooks/log.ts`
- Modify: `web/src/api/queryKeys.ts`, `web/src/api/ws.ts`
- Test: `web/src/api/ws.test.tsx`

**Interfaces:**
- Produces: `useLogFeed(params)`, `useLogEntry(id)`, `useLogMentionables()`, `useCreateLogEntry()`, `useAckLogEntry()`, `useSetLogPinned()`; `qk.logFeed`, `qk.logFeedAll`, `qk.logEntry`, `qk.logMentionables`

- [ ] **Step 1: Write the failing test**

Append to `web/src/api/ws.test.tsx`, inside the `invalidationsFor` describe block:

```tsx
it('invalidates the log feed on log.entry.created', () => {
  const keys = invalidationsFor(
    { type: 'log.entry.created', propertyId: 'p1', payload: { id: 'e1' }, at: '' },
    'p1',
  )
  expect(keys).toContainEqual(['logFeed', 'p1'])
})

it('invalidates both feed and entry on log.entry.updated', () => {
  const keys = invalidationsFor(
    { type: 'log.entry.updated', propertyId: 'p1', payload: { id: 'e1' }, at: '' },
    'p1',
  )
  expect(keys).toContainEqual(['logFeed', 'p1'])
  expect(keys).toContainEqual(['logEntry', 'p1', 'e1'])
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npm test -- ws`
Expected: FAIL — the returned array is empty for an unhandled event type.

- [ ] **Step 3: Add the query keys**

In `web/src/api/queryKeys.ts`, after the `staffDirectory` entry:

```ts
  logFeed: (propertyId: string, params: Record<string, string | boolean | null>) =>
    ['logFeed', propertyId, params] as const,
  logFeedAll: (propertyId: string) => ['logFeed', propertyId] as const,
  logEntry: (propertyId: string, id: string) => ['logEntry', propertyId, id] as const,
  logMentionables: (propertyId: string) => ['logMentionables', propertyId] as const,
```

- [ ] **Step 4: Add the switch cases**

In `web/src/api/ws.ts`, before `default:`:

```ts
    case 'log.entry.created':
      keys.push([...qk.logFeedAll(propertyId)])
      break
    case 'log.entry.updated':
      keys.push([...qk.logFeedAll(propertyId)])
      if (id) keys.push([...qk.logEntry(propertyId, id)])
      break
```

- [ ] **Step 5: Write the hooks**

Create `web/src/api/hooks/log.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from '../../auth/SessionContext'
import { ApiError, api, propertyPath } from '../client'
import { qk } from '../queryKeys'
import type {
  CreateLogEntryRequest,
  LogEntryOut,
  LogFeedOut,
  LogMentionableOut,
} from '../types'

export type LogFeedParams = {
  shift?: string | null
  departmentId?: string | null
  mentioningMe?: boolean
}

function toQuery(params: LogFeedParams): string {
  const search = new URLSearchParams()
  if (params.shift) search.set('shift', params.shift)
  if (params.departmentId) search.set('departmentId', params.departmentId)
  if (params.mentioningMe) search.set('mentioningMe', 'true')
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

export function useLogFeed(params: LogFeedParams = {}) {
  const { propertyId } = useSession()
  return useQuery<LogFeedOut, ApiError>({
    queryKey: qk.logFeed(propertyId, {
      shift: params.shift ?? null,
      departmentId: params.departmentId ?? null,
      mentioningMe: params.mentioningMe ?? false,
    }),
    queryFn: () => api<LogFeedOut>(propertyPath(propertyId, `log-entries${toQuery(params)}`)),
  })
}

export function useLogEntry(id: string | undefined) {
  const { propertyId } = useSession()
  return useQuery<LogEntryOut, ApiError>({
    queryKey: qk.logEntry(propertyId, id ?? ''),
    queryFn: () => api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}`)),
    enabled: Boolean(id),
  })
}

export function useLogMentionables() {
  const { propertyId } = useSession()
  return useQuery<LogMentionableOut[], ApiError>({
    queryKey: qk.logMentionables(propertyId),
    queryFn: () => api<LogMentionableOut[]>(propertyPath(propertyId, 'log-entries/mentionables')),
  })
}

export function useCreateLogEntry() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, CreateLogEntryRequest & { photo?: File }>({
    mutationFn: ({ photo, ...rest }) => {
      if (!photo) {
        return api<LogEntryOut>(propertyPath(propertyId, 'log-entries'), {
          method: 'POST',
          json: rest,
        })
      }
      // Multipart: the server reads scalars from request.form and the file from request.files,
      // so arrays go over as JSON strings. Matches SendStaffMessageRequest's handling.
      const form = new FormData()
      form.set('body', rest.body)
      if (rest.departmentId) form.set('departmentId', rest.departmentId)
      if (rest.mentions?.length) form.set('mentions', JSON.stringify(rest.mentions))
      if (rest.requiresAck) form.set('requiresAck', 'true')
      if (rest.ackAudience?.length) form.set('ackAudience', JSON.stringify(rest.ackAudience))
      form.set('photo', photo)
      return api<LogEntryOut>(propertyPath(propertyId, 'log-entries'), {
        method: 'POST',
        body: form,
      })
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}

export function useAckLogEntry() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, string>({
    mutationFn: (id) =>
      api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}/ack`), { method: 'POST' }),
    onSuccess: (entry) => {
      client.setQueryData(qk.logEntry(propertyId, entry.id), entry)
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}

export function useSetLogPinned() {
  const { propertyId } = useSession()
  const client = useQueryClient()
  return useMutation<LogEntryOut, ApiError, { id: string; pinned: boolean }>({
    mutationFn: ({ id, pinned }) =>
      api<LogEntryOut>(propertyPath(propertyId, `log-entries/${id}/pin`), {
        method: pinned ? 'POST' : 'DELETE',
      }),
    onSuccess: (entry) => {
      client.setQueryData(qk.logEntry(propertyId, entry.id), entry)
      void client.invalidateQueries({ queryKey: qk.logFeedAll(propertyId) })
    },
  })
}
```

**Server-side counterpart:** `parse_body` falls back to `request.form.to_dict()` for multipart, which yields strings. The `mentions` and `ackAudience` fields arrive as JSON strings in that path. Add a `model_validator(mode="before")` to `CreateLogEntryRequest` in `server/app/schemas/log.py` that `json.loads` those two fields when they are `str`, and a test in `test_log_api.py` posting a multipart body with mentions to prove it works. Do this in this task, and regenerate `schema.json` + types if the model's shape changes (it should not — only its parsing).

- [ ] **Step 6: Run to verify everything passes**

Run: `cd web && npm test && npm run lint && npm run build`
Expected: PASS, clean

Run: `cd server && ../.venv/Scripts/python.exe -m pytest -q`
Expected: PASS, including the new multipart-mentions test.

- [ ] **Step 7: Commit**

```bash
git add web/src/api/hooks/log.ts web/src/api/queryKeys.ts web/src/api/ws.ts web/src/api/ws.test.tsx server/app/schemas/log.py server/tests/test_log_api.py
git commit -m "feat(web): hotel log query hooks and realtime invalidation"
```

---

