import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChecklistInstanceOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { sessionFixture, testQueryClient } from '../../test/harness'
import { ChecklistRunPage } from './ChecklistRunPage'

/**
 * Isolates the note-seeding effect's dependency bug (minor finding 7) from an unrelated
 * TanStack Query quirk: switching `useChecklistInstance`'s query key on navigation briefly
 * flips `isPending` even with the new id's data already cached, which unmounts and remounts
 * the whole page (Spinner branch) and would reset the note regardless of the effect's own
 * dependency array. Mocking the hook removes that noise and exercises the effect directly:
 * given the SAME rendered `<ChecklistRunPage>`, only the `instance` prop-equivalent (the
 * hook's return value) changes between renders, exactly as it would if navigation truly did
 * not remount the component.
 */
const BASE: ChecklistInstanceOut = {
  id: 'i-1', templateId: 't-1', templateName: 'Engineering AM Rounds', departmentId: 'dept-eng',
  departmentName: 'Engineering', dueDate: '2026-09-10', shift: 'am', onDemand: false,
  status: 'in_progress', kind: 'normal', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
  completedByName: null, done: 0, total: 0, outOfRangeCount: 0, startedByName: 'Eli Engineer',
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null, categories: [],
  items: [], answers: [], photos: [], missingRequired: [],
}
// Same comment (null) as BASE on purpose: the bug is that a same-valued dependency array
// entry hides the id change and leaves the previous instance's draft on screen.
const OTHER: ChecklistInstanceOut = { ...BASE, id: 'i-2' }

let current = BASE
let currentId = 'i-1'

vi.mock('../../api/hooks/checklists', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/hooks/checklists')>()
  return {
    ...actual,
    useChecklistInstance: () => ({ data: current, isPending: false, error: null }),
  }
})

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return { ...actual, useParams: () => ({ id: currentId }) }
})

function Harness() {
  return (
    <MemoryRouter>
      <ChecklistRunPage />
    </MemoryRouter>
  )
}

describe('ChecklistRunPage note draft (isolated from routing/query transitions)', () => {
  beforeEach(() => {
    current = BASE
    vi.stubGlobal('fetch', vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify([]), { status: 200 }))))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('resets the draft when the instance id changes, even if the new comment is the same '
     + 'string', async () => {
    const user = userEvent.setup()
    const client = testQueryClient()
    client.setQueryData(['session'], sessionFixture({ role: 'dept_staff', departmentId: 'dept-eng' }))
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <Harness />
        </SessionProvider>
      </QueryClientProvider>,
    )
    const note = await screen.findByLabelText('Handover note')
    await user.type(note, 'Unsaved draft')
    expect(note).toHaveValue('Unsaved draft')

    current = OTHER
    currentId = 'i-2'
    rerender(
      <QueryClientProvider client={client}>
        <SessionProvider>
          <Harness />
        </SessionProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByLabelText('Handover note')).toHaveValue('')
  })
})
