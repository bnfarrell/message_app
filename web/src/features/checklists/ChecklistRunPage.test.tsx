import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { ChecklistInstanceOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistRunPage } from './ChecklistRunPage'

const BASE: ChecklistInstanceOut = {
  id: 'i-1', templateId: 't-1', templateName: 'Engineering AM Rounds', departmentId: 'dept-eng',
  departmentName: 'Engineering', dueDate: '2026-09-10', shift: 'am', onDemand: false,
  status: 'in_progress', kind: 'normal', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
  completedByName: null, done: 0, total: 2, outOfRangeCount: 0, startedByName: 'Eli Engineer',
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null, categories: [],
  items: [
    { id: 'it-chk', position: 0, label: 'Skimmers', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
    { id: 'it-ph', position: 1, label: 'Pool pH', itemType: 'number', unit: '', minValue: 7.2,
      maxValue: 7.8, required: true, active: true },
  ],
  answers: [
    { id: 'a-chk', itemId: 'it-chk', boolValue: null, textValue: null, numberValue: null,
      outOfRange: false, answeredAt: null },
    { id: 'a-ph', itemId: 'it-ph', boolValue: null, textValue: null, numberValue: 7.4,
      outOfRange: false, answeredAt: '2026-09-10T11:40:00Z' },
  ],
  photos: [],
  missingRequired: ['it-chk'],
}

// Checklist structure spec §2.2: Skimmers ungrouped, Pool pH under "Pool" (answered, so 1 / 1).
const GROUPED: ChecklistInstanceOut = {
  ...BASE, kind: 'readings',
  categories: [{ id: 'c-pool', name: 'Pool', position: 0, done: 1, total: 1 }],
  items: [{ ...BASE.items[0]!, categoryId: null }, { ...BASE.items[1]!, categoryId: 'c-pool' }],
}

let instance: ChecklistInstanceOut = BASE
let patchStatus = 200
const writes: { url: string; method: string; body: unknown }[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (method !== 'GET') {
      writes.push({ url: String(input), method,
                    body: init?.body ? JSON.parse(String(init.body)) : null })
      if (patchStatus !== 200) {
        return Promise.resolve(new Response(JSON.stringify({ error: {
          code: 'INVALID_TRANSITION', message: 'This checklist is not in progress' } }),
          { status: patchStatus }))
      }
    }
    return Promise.resolve(new Response(JSON.stringify(instance), { status: 200 }))
  })
}

function mount() {
  return renderWithProviders(
    <SessionProvider>
      <Routes>
        <Route path="/app/checklists/:id" element={<ChecklistRunPage />} />
      </Routes>
    </SessionProvider>,
    { session: sessionFixture({ role: 'dept_staff', departmentId: 'dept-eng' }),
      route: '/app/checklists/i-1' },
  )
}

describe('ChecklistRunPage', () => {
  beforeEach(() => {
    instance = BASE
    patchStatus = 200
    writes.length = 0
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('saves an answer as it is entered', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('checkbox', { name: /Skimmers/ }))
    await waitFor(() => expect(writes).toContainEqual({
      url: '/api/p/prop-a/checklists/instances/i-1/answers/a-chk', method: 'PATCH',
      body: { boolValue: true } }))
  })

  it('keeps Complete disabled and lists what is missing', async () => {
    mount()
    expect(await screen.findByRole('button', { name: 'Complete' })).toBeDisabled()
    expect(screen.getByText(/Still to do: Skimmers/)).toBeInTheDocument()
  })

  it('saves the handover comment', async () => {
    const user = userEvent.setup()
    mount()
    await user.type(await screen.findByLabelText('Handover note'), 'Boiler 2 noisy')
    await user.click(screen.getByRole('button', { name: 'Save note' }))
    await waitFor(() => expect(writes).toContainEqual({
      url: '/api/p/prop-a/checklists/instances/i-1', method: 'PATCH',
      body: { comment: 'Boiler 2 noisy' } }))
  })

  it('is read-only once missed', async () => {
    instance = { ...BASE, status: 'missed', missingRequired: [] }
    mount()
    expect(await screen.findByText('Missed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Skimmers/ })).toBeDisabled()
  })

  it('lets the note grow to the server\'s 4000-character limit', async () => {
    mount()
    expect(await screen.findByLabelText('Handover note')).toHaveAttribute('maxlength', '4000')
  })

  it('shows a checklist without categories as one list with no headings', async () => {
    mount()
    await screen.findByRole('checkbox', { name: /Skimmers/ })
    expect(screen.queryByRole('button', { name: /done$/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Readings')).not.toBeInTheDocument()
  })

  it('groups items under collapsible category headings with progress, ungrouped first', async () => {
    instance = GROUPED
    const user = userEvent.setup()
    mount()
    const heading = await screen.findByRole('button', { name: 'Pool, 1 of 1 done' })
    expect(heading).toHaveAttribute('aria-expanded', 'true')
    expect(within(heading).getByText('1 / 1')).toBeInTheDocument()
    const pool = screen.getByRole('region', { name: 'Pool' })
    expect(within(pool).getByText(/Pool pH/)).toBeInTheDocument()
    expect(within(pool).queryByText(/Skimmers/)).not.toBeInTheDocument()
    // the ungrouped item is above the first heading
    const skimmers = screen.getByRole('checkbox', { name: /Skimmers/ })
    expect(skimmers.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    await user.click(heading)
    expect(heading).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/Pool pH/)).not.toBeInTheDocument()
    await user.click(heading)
    expect(screen.getByText(/Pool pH/)).toBeInTheDocument()
  })

  it('tags a readings checklist in the header', async () => {
    instance = GROUPED
    mount()
    expect(await screen.findByText('Readings')).toBeInTheDocument()
  })

  it('shows a failed save inline', async () => {
    patchStatus = 409
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('checkbox', { name: /Skimmers/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This checklist is not in progress')
  })
})
