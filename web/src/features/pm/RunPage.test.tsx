import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router-dom'
import type { Role, RunOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { RunPage } from './RunPage'

const RUN: RunOut = {
  id: 'run-1', templateId: 't-1', templateName: 'Guest Room Quarterly',
  unitId: 'u-204', unitCode: '204', unitName: 'Room 204', unitKind: 'guest_room',
  cycleId: 'cy-3', workOrderId: null, status: 'in_progress',
  startedByUserId: 'u-eli', startedByName: 'Eli Engineer', startedAt: '2026-09-10T12:00:00Z',
  completedAt: null, inspectedByUserId: null, inspectedByName: null, inspectedAt: null,
  inspectionNote: null, dueAt: null,
  items: [
    { id: 'i-hvac', position: 0, label: 'HVAC filter replaced', itemType: 'checkbox', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
    { id: 'i-temp', position: 1, label: 'Tap hot-water temperature', itemType: 'number', unit: '°F',
      minValue: 100, maxValue: 120, required: true, active: true },
    { id: 'i-caulk', position: 2, label: 'Caulk condition', itemType: 'text', unit: null,
      minValue: null, maxValue: null, required: false, active: true },
    { id: 'i-fan', position: 3, label: 'Bathroom fan photo', itemType: 'photo', unit: null,
      minValue: null, maxValue: null, required: true, active: true },
  ],
  answers: [
    { id: 'a-hvac', itemId: 'i-hvac', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-temp', itemId: 'i-temp', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-caulk', itemId: 'i-caulk', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
    { id: 'a-fan', itemId: 'i-fan', boolValue: null, textValue: null, numberValue: null, outOfRange: false, answeredAt: null },
  ],
  photos: [],
  missingRequired: ['i-hvac', 'i-temp', 'i-fan'],
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

/** GET returns `run`; any PATCH/POST returns `after` (or `run`). */
function serve(run: RunOut, after?: RunOut) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/pm/runs/') && init?.method && init.method !== 'GET') return json(after ?? run)
    if (url.includes('/pm/runs/')) return json(run)
    return json([])
  })
}

function mount(role: Role = 'dept_staff') {
  return renderWithProviders(
    <ToastProvider>
      <SessionProvider>
        <Routes>
          <Route path="/app/pm/runs/:id" element={<RunPage />} />
        </Routes>
      </SessionProvider>
    </ToastProvider>,
    { session: sessionFixture({ role }), route: '/app/pm/runs/run-1' },
  )
}

function patchCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'PATCH')
}

describe('RunPage', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders every item by type and lists what still blocks Complete', async () => {
    serve(RUN)
    mount()
    expect(await screen.findByText('Room 204')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /HVAC filter replaced/ })).toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: /Tap hot-water temperature/ })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Caulk condition/ })).toBeInTheDocument()
    expect(screen.getByLabelText(/Bathroom fan photo/)).toHaveAttribute('type', 'file')
    expect(screen.getByRole('button', { name: 'Complete' })).toBeDisabled()
    expect(screen.getByText(/3 required items still need an answer/)).toBeInTheDocument()
  })

  it('saves a number on blur and shows the out-of-range warning the server returns', async () => {
    const flagged: RunOut = {
      ...RUN,
      answers: (RUN.answers ?? []).map((a) =>
        a.id === 'a-temp' ? { ...a, numberValue: 122, outOfRange: true, answeredAt: '2026-09-10T12:05:00Z' } : a),
      missingRequired: ['i-hvac', 'i-fan'],
    }
    serve(RUN, flagged)
    mount()
    const field = await screen.findByRole('spinbutton', { name: /Tap hot-water temperature/ })
    await userEvent.type(field, '122')
    await userEvent.tab()
    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(String(patchCalls()[0]![0])).toContain('/pm/runs/run-1/answers/a-temp')
    expect(JSON.parse(String(patchCalls()[0]![1]!.body))).toEqual({ numberValue: 122 })
    expect(await screen.findByText(/Outside 100–120/)).toBeInTheDocument()
    expect(screen.getByText(/2 required items still need an answer/)).toBeInTheDocument()
  })

  it('does not let a slow PATCH response clobber a fresh edit made after the blur that triggered it', async () => {
    let resolvePatch: ((response: Response) => void) | undefined
    vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/pm/runs/') && init?.method === 'PATCH') {
        return new Promise<Response>((resolve) => {
          resolvePatch = resolve
        })
      }
      if (url.includes('/pm/runs/')) return json(RUN)
      return json([])
    })
    mount()
    const field = await screen.findByRole('spinbutton', { name: /Tap hot-water temperature/ })

    // Blur field A with "122" — the PATCH fires but never resolves yet.
    await userEvent.type(field, '122')
    await userEvent.tab()
    await waitFor(() => expect(patchCalls()).toHaveLength(1))

    // Before the response comes back, the user refocuses the same field and types "150",
    // without blurring again — nothing has saved this value yet.
    await userEvent.click(field)
    await userEvent.clear(field)
    await userEvent.type(field, '150')
    expect(field).toHaveValue(150)

    // The stale "122" PATCH now resolves and lands in the cache.
    const flagged: RunOut = {
      ...RUN,
      answers: (RUN.answers ?? []).map((a) =>
        a.id === 'a-temp' ? { ...a, numberValue: 122, outOfRange: true, answeredAt: '2026-09-10T12:05:00Z' } : a),
      missingRequired: ['i-hvac', 'i-fan'],
    }
    resolvePatch!(new Response(JSON.stringify(flagged), { status: 200 }))

    // Wait for the cache update to actually land (the warning only renders off `answer`,
    // not off the field's local state), then confirm the focused field kept "150".
    expect(await screen.findByText(/Outside 100–120/)).toBeInTheDocument()
    expect(field).toHaveValue(150)
  })

  it('enables Complete once nothing is missing and posts it', async () => {
    const ready = { ...RUN, missingRequired: [] }
    serve(ready, { ...ready, status: 'completed' })
    mount()
    const button = await screen.findByRole('button', { name: 'Complete' })
    expect(button).toBeEnabled()
    await userEvent.click(button)
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([input, init]) =>
        String(input).endsWith('/pm/runs/run-1/complete') && init?.method === 'POST')).toBe(true))
    expect(await screen.findByText('Awaiting inspection')).toBeInTheDocument()
  })

  it('is read-only with a Pass/Fail footer for an inspector on a completed run', async () => {
    const completed: RunOut = { ...RUN, status: 'completed', completedAt: '2026-09-10T12:40:00Z', missingRequired: [] }
    serve(completed, { ...completed, status: 'failed' })
    mount('supervisor')
    expect(await screen.findByRole('button', { name: 'Pass' })).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /HVAC filter replaced/ })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Fail' }))
    const submit = screen.getByRole('button', { name: 'Record failure' })
    expect(submit).toBeDisabled()
    await userEvent.type(screen.getByLabelText('What must be redone'), 'Grille still dusty')
    await userEvent.click(submit)
    await waitFor(() => {
      const call = vi.mocked(fetch).mock.calls.find(([input]) => String(input).endsWith('/inspect'))!
      expect(JSON.parse(String(call[1]!.body))).toEqual({ result: 'fail', note: 'Grille still dusty' })
    })
  })

  it('offers only Start PM for a pending scheduled run', async () => {
    serve({ ...RUN, status: 'pending', workOrderId: 'w-9', startedByName: null, answers: [], missingRequired: [] })
    mount()
    expect(await screen.findByRole('button', { name: 'Start PM' })).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /work order/i })).toHaveAttribute('href', '/app/work-orders/w-9')
  })
})
