import { screen, waitFor } from '@testing-library/react'
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
  status: 'in_progress', assignedUserId: 'u-eli', assignedName: 'Eli Engineer',
  completedByName: null, done: 0, total: 2, outOfRangeCount: 0, startedByName: 'Eli Engineer',
  startedAt: '2026-09-10T11:30:00Z', completedAt: null, comment: null,
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

  it('shows a failed save inline', async () => {
    patchStatus = 409
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('checkbox', { name: /Skimmers/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('This checklist is not in progress')
  })
})
