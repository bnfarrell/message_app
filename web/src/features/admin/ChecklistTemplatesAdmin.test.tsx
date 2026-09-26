import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (init?.method === 'POST') return json({ id: 't-new' }, 201)
    return json([])
  })
}

function posted() {
  const post = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === 'POST')
  return post ? JSON.parse(String(post[1]!.body)) : undefined
}

async function startNew(name: string) {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
  await userEvent.click(await screen.findByRole('button', { name: 'New template' }))
  await userEvent.type(screen.getByLabelText('Name'), name)
  await userEvent.selectOptions(await screen.findByLabelText('Department'), 'dept-eng')
}

async function addCheckbox(label: string) {
  await userEvent.click(screen.getByRole('button', { name: 'Add item' }))
  await userEvent.type(screen.getByLabelText('Label for item 1'), label)
}

describe('ChecklistTemplatesAdmin', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('creates a weekly template with the chosen days as a bitmask', async () => {
    await startNew('AM Rounds')
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sat' }))
    await userEvent.click(screen.getByRole('checkbox', { name: 'Sun' }))
    await addCheckbox('Skimmers')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toEqual({
      name: 'AM Rounds', departmentId: 'dept-eng', schedule: 'weekly', shift: 'am',
      weekdays: 0b0011111, active: true,
      items: [{ label: 'Skimmers', itemType: 'checkbox', unit: null, minValue: null,
                maxValue: null, required: true }],
    }))
  })

  it('sends no shift or days for an on-demand template', async () => {
    await startNew('Outage')
    await userEvent.click(screen.getByRole('radio', { name: 'On demand' }))
    expect(screen.queryByLabelText('Shift')).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: 'Mon' })).not.toBeInTheDocument()
    await addCheckbox('Generator started')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toMatchObject(
      { schedule: 'on_demand', shift: null, weekdays: null }))
  })

  it('blocks saving a weekly template with no day ticked', async () => {
    await startNew('AM Rounds')
    for (const day of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      await userEvent.click(screen.getByRole('checkbox', { name: day }))
    }
    await addCheckbox('Skimmers')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Pick at least one day')).toBeInTheDocument()
    expect(posted()).toBeUndefined()
  })
})
