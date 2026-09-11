import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Role, WorkOrderStatus } from '../../api/types'
import { SessionProvider } from '../../auth/SessionContext'
import { aWorkOrderDetail } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { TransitionButtons } from './TransitionButtons'

function mount(status: WorkOrderStatus, role: Role = 'dept_staff') {
  return renderWithProviders(
    <SessionProvider>
      <TransitionButtons workOrder={aWorkOrderDetail({ status })} />
    </SessionProvider>,
    { session: sessionFixture({ role }) },
  )
}

describe('TransitionButtons', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(aWorkOrderDetail()), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('offers exactly the reachable statuses for an open order', async () => {
    mount('open')
    expect(await screen.findByRole('button', { name: 'Assigned' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In progress' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelled' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Verified' })).not.toBeInTheDocument()
  })

  it('offers Blocked and Complete only once in progress', async () => {
    mount('in_progress')
    expect(await screen.findByRole('button', { name: 'Blocked' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Complete' })).toBeInTheDocument()
  })

  it('offers Verified and a reopen once complete', async () => {
    mount('complete')
    expect(await screen.findByRole('button', { name: 'Verified' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In progress' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelled' })).not.toBeInTheDocument()
  })

  it('offers nothing on a verified order', async () => {
    const { container } = mount('verified')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })

  it('offers nothing on a cancelled order', async () => {
    const { container } = mount('cancelled')
    expect(container.querySelectorAll('button')).toHaveLength(0)
  })

  it('hides the closing transitions from an agent, who lacks close_work_order', async () => {
    mount('in_progress', 'agent')
    expect(await screen.findByRole('button', { name: 'Blocked' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Complete' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Cancelled' })).not.toBeInTheDocument()
  })

  it('marks Complete as the primary action', async () => {
    mount('in_progress')
    expect((await screen.findByRole('button', { name: 'Complete' })).className).toContain(
      'bg-accent',
    )
  })

  it('patches the status straight through for a plain transition', async () => {
    mount('open')
    await userEvent.click(await screen.findByRole('button', { name: 'In progress' }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({ status: 'in_progress' })
  })

  it('asks why before blocking, and sends the comment', async () => {
    mount('in_progress')
    await userEvent.click(await screen.findByRole('button', { name: 'Blocked' }))
    const box = await screen.findByRole('textbox')
    await userEvent.type(box, 'Waiting on a part')
    await userEvent.click(screen.getByRole('button', { name: /^confirm$/i }))
    const patch = vi.mocked(fetch).mock.calls.find(([, i]) => i?.method === 'PATCH')
    expect(JSON.parse(String(patch![1]!.body))).toEqual({
      status: 'blocked',
      comment: 'Waiting on a part',
    })
  })

  it('asks why before cancelling', async () => {
    mount('open')
    await userEvent.click(await screen.findByRole('button', { name: 'Cancelled' }))
    expect(await screen.findByRole('textbox')).toBeInTheDocument()
  })

  it('surfaces a 409 from the server rather than swallowing it', async () => {
    mount('open')
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { code: 'INVALID_TRANSITION', message: 'Cannot move a work order from open to complete' },
        }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    await userEvent.click(await screen.findByRole('button', { name: 'In progress' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Cannot move a work order')
  })
})
