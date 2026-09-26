import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChecklistItemOut, ChecklistTemplateOut } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ChecklistTemplatesAdmin } from './ChecklistTemplatesAdmin'

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }))
}

const item = (id: string, label: string, categoryId: string | null, position: number): ChecklistItemOut => ({
  id, position, label, itemType: 'checkbox', unit: null, minValue: null, maxValue: null,
  required: true, active: true, categoryId,
})

const NIGHT: ChecklistTemplateOut = {
  id: 't-night', name: 'Night Audit', departmentId: 'dept-eng', departmentName: 'Engineering',
  schedule: 'unscheduled', shift: null, weekdays: null, active: true, kind: 'normal',
  categories: [{ id: 'c-audit', name: 'Audit', position: 0 }, { id: 'c-pay', name: 'Payments', position: 1 }],
  items: [item('i-run', 'Night audit run', 'c-audit', 0), item('i-batch', 'Card batch closed', 'c-pay', 1),
          item('i-notes', 'Notes checked', null, 2)],
}
const POOL: ChecklistTemplateOut = {
  ...NIGHT, id: 't-pool', name: 'Pool Readings', kind: 'readings', schedule: 'weekly', shift: 'am',
  weekdays: 127, categories: [], items: [item('i-ph', 'Pool pH', null, 0)],
}

let templates: ChecklistTemplateOut[] = []

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/departments')) return json([aDepartment()])
    if (init?.method === 'POST') return json({ id: 't-new' }, 201)
    if (init?.method === 'PATCH') return json(NIGHT)
    return json(templates)
  })
}

function sent(method: 'POST' | 'PATCH') {
  const call = vi.mocked(fetch).mock.calls.find(([, init]) => init?.method === method)
  return call ? JSON.parse(String(call[1]!.body)) : undefined
}
const posted = () => sent('POST')

function mount() {
  renderWithProviders(
    <SessionProvider>
      <ChecklistTemplatesAdmin />
    </SessionProvider>,
    { session: sessionFixture({ role: 'admin' }) },
  )
}

async function startNew(name: string) {
  mount()
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
    templates = []
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
      weekdays: 0b0011111, active: true, kind: 'normal', categories: [],
      items: [{ label: 'Skimmers', itemType: 'checkbox', unit: null, minValue: null,
                maxValue: null, required: true, categoryKey: null }],
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

  it('saves a readings template without a schedule yet', async () => {
    await startNew('Pool')
    await userEvent.click(screen.getByRole('radio', { name: 'Readings' }))
    await userEvent.click(screen.getByRole('radio', { name: 'Not scheduled yet' }))
    expect(screen.queryByLabelText('Shift')).not.toBeInTheDocument()
    await addCheckbox('Strip photo taken')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toMatchObject(
      { kind: 'readings', schedule: 'unscheduled', shift: null, weekdays: null }))
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

  it('creates categories and files items under them', async () => {
    await startNew('Night Audit')
    await userEvent.click(screen.getByRole('button', { name: 'Add category' }))
    await userEvent.type(screen.getByLabelText('Name for category 1'), 'Audit')
    await addCheckbox('Night audit run')
    await userEvent.selectOptions(screen.getByLabelText('Category for item 1'), 'Audit')
    expect(within(screen.getByRole('region', { name: 'Items in Audit' }))
      .getByDisplayValue('Night audit run')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(posted()).toBeDefined())
    const body = posted()
    expect(body.categories).toEqual([{ key: expect.any(String), name: 'Audit' }])
    expect(body.items[0].categoryKey).toBe(body.categories[0].key)
  })

  it('blocks saving a category with no name', async () => {
    await startNew('Night Audit')
    await userEvent.click(screen.getByRole('button', { name: 'Add category' }))
    await addCheckbox('Night audit run')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Name every category')).toBeInTheDocument()
    expect(posted()).toBeUndefined()
  })

  it('reorders, renames and removes saved categories, ungrouping the removed one\'s items', async () => {
    templates = [NIGHT]
    mount()
    await userEvent.click(await screen.findByText('Night Audit'))
    await userEvent.click(screen.getByRole('button', { name: 'Move category 2 up' }))
    await userEvent.clear(screen.getByLabelText('Name for category 1'))
    await userEvent.type(screen.getByLabelText('Name for category 1'), 'Payments & cards')
    await userEvent.click(screen.getByRole('button', { name: 'Remove category 2' })) // Audit
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(sent('PATCH')).toBeDefined())
    const body = sent('PATCH')
    expect(body.categories).toEqual([{ key: 'c-pay', id: 'c-pay', name: 'Payments & cards' }])
    expect(body.items.map((i: { id: string; categoryKey: string | null }) => [i.id, i.categoryKey]))
      .toEqual([['i-run', null], ['i-notes', null], ['i-batch', 'c-pay']])
  })

  it('lists kind, categories and "Set schedule", and filters by kind', async () => {
    templates = [NIGHT, POOL]
    mount()
    const night = (await screen.findByText('Night Audit')).closest('tr')!
    expect(within(night).getByText('Normal')).toBeInTheDocument()
    expect(within(night).getByText('Set schedule')).toBeInTheDocument()
    expect(within(night).getByText('2')).toBeInTheDocument() // categories (it has 3 items)
    const pool = screen.getByText('Pool Readings').closest('tr')!
    expect(within(pool).getByText('Readings')).toBeInTheDocument()
    expect(within(pool).getByText('AM · Every day')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Readings 1' }))
    expect(screen.queryByText('Night Audit')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Readings 1' })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Readings 1' }))
    expect(screen.getByText('Night Audit')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Normal 1' })).toBeInTheDocument()
  })

  it('shows the plain empty state when there are no templates at all', async () => {
    templates = []
    mount()
    expect(await screen.findByText('No checklist templates')).toBeInTheDocument()
  })

  it('names the active kind filter in the empty state when it hides every row', async () => {
    templates = [NIGHT] // kind normal
    mount()
    await screen.findByText('Night Audit')
    await userEvent.click(screen.getByRole('button', { name: 'Readings 0' }))
    expect(await screen.findByText('No readings checklists')).toBeInTheDocument()
  })

  it('says no checklists are created from an unscheduled template until it is scheduled', async () => {
    await startNew('Pool')
    await userEvent.click(screen.getByRole('radio', { name: 'Not scheduled yet' }))
    expect(screen.getByText('No checklists are created from it until you schedule it.', { exact: false }))
      .toBeInTheDocument()
    expect(screen.queryByText(/never appears on the Checklists page/)).not.toBeInTheDocument()
  })
})
