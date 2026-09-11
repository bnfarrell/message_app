import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { ToastProvider } from '../../components/ui'
import { aConversationDetail, aDepartment, aStaffUser } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { ConversationActions } from './ConversationActions'

function serve() {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (init?.method === 'PATCH') {
      return Promise.resolve(
        new Response(JSON.stringify(aConversationDetail()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = url.includes('/departments')
      ? [aDepartment()]
      : url.includes('/users')
        ? [aStaffUser({ id: 'u-marcus', firstName: 'Marcus', lastName: 'Reyes' })]
        : []
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
  })
}

function mount(role: Role = 'agent') {
  renderWithProviders(
    <SessionProvider>
      <ToastProvider>
        <ConversationActions conversation={aConversationDetail()} />
      </ToastProvider>
    </SessionProvider>,
    { session: sessionFixture({ role }), route: '/app/inbox/c-1' },
  )
}

describe('ConversationActions', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-09-10T19:00:00Z'))
    serve()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('offers Assign, Snooze, Archive and Create work order to an agent', async () => {
    mount('agent')
    expect(await screen.findByRole('button', { name: /assign/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /snooze/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /archive/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /work order/i })).toBeInTheDocument()
  })

  it('hides Archive from dept_staff, who lack the capability', async () => {
    mount('dept_staff')
    expect(await screen.findByRole('button', { name: /assign/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument()
  })

  it('hides every write action from corporate', async () => {
    mount('corporate')
    await waitFor(() => expect(screen.queryByRole('button', { name: /assign/i })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /work order/i })).not.toBeInTheDocument()
  })

  it('assigns to a person', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Marcus Reyes/ }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ assignedUserId: 'u-marcus' })
  })

  it('assigns to a department', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /Engineering/ }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ assignedDepartmentId: 'dept-eng' })
  })

  it('unassigns with the explicit clear flag', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /assign/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /unassign/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ clearAssignment: true })
  })

  it('snoozes an hour out', async () => {
    mount('agent')
    await userEvent.click(await screen.findByRole('button', { name: /snooze/i }))
    await userEvent.click(screen.getByRole('menuitem', { name: /1 hour/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    const body = JSON.parse(String(patch![1]!.body)) as { snoozedUntil: string }
    expect(new Date(body.snoozedUntil).getTime()).toBe(
      new Date('2026-09-10T20:00:00Z').getTime(),
    )
  })
})
