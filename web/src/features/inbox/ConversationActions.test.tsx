import { fireEvent, screen, waitFor } from '@testing-library/react'
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
    // shouldAdvanceTime: true keeps findByRole/waitFor's own internal polling (and
    // userEvent's internal event-delay handling) working off real elapsed time — turning
    // it off hangs every async query in this file, since nothing else would ever tick the
    // clock forward. That auto-advance is exactly what made an EXACT `.getTime()` assertion
    // flaky against `new Date()` read inside a render-prop (real drift accrues across the
    // whole interaction). The fix isn't disabling auto-advance everywhere; it's routing the
    // two timing-sensitive tests below through synchronous `fireEvent.click` (no internal
    // await, so no timer-driven drift can accrue between `vi.setSystemTime` and the instant
    // the click handler actually runs) while everything else keeps using real `userEvent`.
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
    expect(screen.queryByRole('button', { name: /snooze/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /work order/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument()
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

  // These two use fireEvent, not userEvent: fireEvent.click is fully synchronous (no
  // internal await, no simulated pointer/keyboard delay), so nothing can advance the fake
  // clock between `vi.setSystemTime` and the instant the click handler reads `Date.now()`.
  // That is what makes the exact `.getTime()` assertions below reliable rather than
  // approximate — see the beforeEach comment for why the file otherwise keeps real
  // userEvent (and shouldAdvanceTime: true) for every other test.

  it('snoozes an hour out', async () => {
    mount('agent')
    fireEvent.click(screen.getByRole('button', { name: /snooze/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /1 hour/i }))
    // The click computes and hands off `snoozedUntil` synchronously; this only waits for
    // the mutation's own fetch call to actually land (React Query defers that by a
    // microtask), not for anything that could change what instant was computed.
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'PATCH')).toBe(true))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    const body = JSON.parse(String(patch![1]!.body)) as { snoozedUntil: string }
    expect(new Date(body.snoozedUntil).getTime()).toBe(
      new Date('2026-09-10T20:00:00Z').getTime(),
    )
  })

  // Regression for a bug introduced by an earlier fix: the preset must be computed from
  // the moment of the click, not from whenever the conversation view happened to mount.
  // An agent can sit on a conversation for a while before deciding to snooze it — if "1
  // hour" were still measured from mount time, that snooze could already be in the past
  // by the time they click it, and the conversation would pop straight back out of snooze.
  it('computes the snooze target from the click, not from when the view mounted', async () => {
    mount('agent')
    fireEvent.click(screen.getByRole('button', { name: /snooze/i }))
    // The agent works the conversation for two and a half hours before snoozing it.
    vi.setSystemTime(new Date('2026-09-10T21:30:00Z'))
    fireEvent.click(screen.getByRole('menuitem', { name: /1 hour/i }))
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([, i]) => i?.method === 'PATCH')).toBe(true))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    const body = JSON.parse(String(patch![1]!.body)) as { snoozedUntil: string }
    // 1 hour from the click (21:30), not 1 hour from mount (19:00 -> 20:00, which would
    // already be in the past relative to the click).
    expect(new Date(body.snoozedUntil).getTime()).toBe(
      new Date('2026-09-10T22:30:00Z').getTime(),
    )
  })
})
