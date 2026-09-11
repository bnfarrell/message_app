import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aDepartment, aStaffUser, aWorkOrder } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { CreateWorkOrderModal } from './CreateWorkOrderModal'

const PREFILL = {
  title: 'AC not cooling',
  description: "Guest reports the AC in 412 isn't working at all and the room is warm.",
  type: 'maintenance',
  priority: 'urgent',
  locationType: 'room',
  locationRef: '412',
  departmentId: 'dept-eng',
  guestName: 'Sarah Chen',
  sourceConversationId: 'c-1',
  sourceMessageId: 'm-1',
}

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/work-orders') && init?.method === 'POST') {
      return Promise.resolve(
        new Response(JSON.stringify(aWorkOrder({ id: 'w-500' })), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = url.includes('prefill')
      ? PREFILL
      : url.includes('/departments')
        ? [aDepartment(), aDepartment({ id: 'dept-hk', name: 'Housekeeping', type: 'housekeeping' })]
        : url.includes('/users')
          ? [aStaffUser({ id: 'u-eli', firstName: 'Eli', lastName: 'Engineer', role: 'dept_staff' })]
          : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(onClose = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <CreateWorkOrderModal conversationId="c-1" open onClose={onClose} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onClose
}

describe('CreateWorkOrderModal', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('pre-fills from the server suggestion (§5.3)', async () => {
    mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    expect(screen.getByLabelText('Description')).toHaveValue(PREFILL.description)
    expect(screen.getByLabelText('Location')).toHaveValue('412')
    expect(screen.getByLabelText('Priority')).toHaveValue('urgent')
    expect(screen.getByLabelText('Department')).toHaveValue('dept-eng')
  })

  it('lets the agent edit before saving', async () => {
    mount()
    const title = await screen.findByLabelText('Title')
    await waitFor(() => expect(title).toHaveValue('AC not cooling'))
    await userEvent.clear(title)
    await userEvent.type(title, 'AC dead in 412')
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({ title: 'AC dead in 412' })
  })

  it('carries the conversation and message link through unchanged (§11.1 #6)', async () => {
    mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    expect(JSON.parse(String(post![1]!.body))).toMatchObject({
      sourceConversationId: 'c-1',
      sourceMessageId: 'm-1',
    })
  })

  it('will not save an empty title', async () => {
    mount()
    const title = await screen.findByLabelText('Title')
    await waitFor(() => expect(title).toHaveValue('AC not cooling'))
    await userEvent.clear(title)
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('closes on success', async () => {
    const onClose = mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('shows the server error and stays open on failure', async () => {
    const onClose = mount()
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'FORBIDDEN', message: 'Not allowed' } }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Not allowed')
    expect(onClose).not.toHaveBeenCalled()
  })
})
