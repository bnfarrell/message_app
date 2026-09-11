import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
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

function mountStandalone(onClose = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <CreateWorkOrderModal open onClose={onClose} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role: 'dept_staff' }) },
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

  it('opens blank with no conversation and asks the server for no prefill', async () => {
    // CreateWorkOrder.sourceConversationId is optional server-side, and the mockups are full of
    // work orders with no guest behind them — POOL PUMP, 3F ICE, ELEV B.
    mountStandalone()
    const title = await screen.findByLabelText('Title')
    expect(title).toHaveValue('')
    expect(screen.getByLabelText('Description')).toHaveValue('')
    expect(screen.getByLabelText('Location')).toHaveValue('')
    expect(screen.getByLabelText('Priority')).toHaveValue('normal')
    expect(screen.getByLabelText('Department')).toHaveValue('')
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).includes('prefill'))).toBe(false)
  })

  it('posts a standalone work order without a sourceConversationId key', async () => {
    const onClose = mountStandalone()
    await userEvent.type(await screen.findByLabelText('Title'), 'Pool pump seized')
    await userEvent.selectOptions(screen.getByLabelText('Location type'), 'equipment')
    await userEvent.type(screen.getByLabelText('Location'), 'POOL')
    await userEvent.selectOptions(screen.getByLabelText('Department'), 'dept-eng')
    await userEvent.click(screen.getByRole('button', { name: /create/i }))

    const post = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'POST')
    const body = JSON.parse(String(post![1]!.body))
    expect(body).toMatchObject({
      title: 'Pool pump seized',
      locationType: 'equipment',
      locationRef: 'POOL',
      departmentId: 'dept-eng',
    })
    // Omitted, not null: the route branches on `if data.source_conversation_id`.
    expect('sourceConversationId' in body).toBe(false)
    expect('sourceMessageId' in body).toBe(false)
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('will not save an empty title with no conversation either', async () => {
    mountStandalone()
    await screen.findByLabelText('Title')
    await userEvent.click(screen.getByRole('button', { name: /create/i }))
    expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'POST')).toBe(false)
  })

  it('resets the edited draft on Cancel, so a reopen re-seeds from a fresh prefill', async () => {
    // The real ConversationActions keeps this modal mounted permanently and only toggles
    // `open`, so a wrapper that does the same is the only way to exercise a genuine reopen.
    function Wrapper() {
      const [open, setOpen] = useState(true)
      return (
        <>
          <button onClick={() => setOpen(true)}>Reopen</button>
          <CreateWorkOrderModal conversationId="c-1" open={open} onClose={() => setOpen(false)} />
        </>
      )
    }
    renderWithProviders(
      <SessionProvider>
        <ToastProvider>
          <Wrapper />
        </ToastProvider>
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    const title = await screen.findByLabelText('Title')
    await waitFor(() => expect(title).toHaveValue('AC not cooling'))
    await userEvent.clear(title)
    await userEvent.type(title, 'Something the agent typed and abandoned')
    await userEvent.click(screen.getByRole('button', { name: /cancel/i }))
    await userEvent.click(screen.getByRole('button', { name: /reopen/i }))
    await waitFor(() => expect(screen.getByLabelText('Title')).toHaveValue('AC not cooling'))
  })
})
