import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aConversationDetail, aDraftPrompt, aGuest } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { DraftPromptBanner } from './DraftPromptBanner'

function mount(detail = aConversationDetail({ draftPrompts: [aDraftPrompt()] }), onUse = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <DraftPromptBanner conversation={detail} onUseDraft={onUse} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onUse
}

describe('DraftPromptBanner', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders nothing when there is no pending prompt', () => {
    const { container } = renderWithProviders(
      <SessionProvider>
        <DraftPromptBanner conversation={aConversationDetail()} onUseDraft={vi.fn()} />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    expect(container.querySelector('[data-testid="draft-prompt"]')).toBeNull()
  })

  it('renders nothing for a prompt that is already sent or dismissed', () => {
    const { container } = renderWithProviders(
      <SessionProvider>
        <DraftPromptBanner
          conversation={aConversationDetail({ draftPrompts: [aDraftPrompt({ status: 'sent' })] })}
          onUseDraft={vi.fn()}
        />
      </SessionProvider>,
      { session: sessionFixture({ role: 'agent' }) },
    )
    expect(container.querySelector('[data-testid="draft-prompt"]')).toBeNull()
  })

  it('states the work order, its title, the room and the guest (§5.3 copy)', async () => {
    mount()
    const banner = await screen.findByTestId('draft-prompt')
    expect(banner).toHaveTextContent('AC not cooling')
    expect(banner).toHaveTextContent('412')
    expect(banner).toHaveTextContent('Sarah')
    expect(banner).toHaveTextContent(/is complete/i)
  })

  it('falls back to "the guest" when the guest has no first name', async () => {
    mount(
      aConversationDetail({
        guest: aGuest({ firstName: null, lastName: null }),
        draftPrompts: [aDraftPrompt()],
      }),
    )
    expect(await screen.findByTestId('draft-prompt')).toHaveTextContent('the guest')
  })

  it('hands the draft body up on Use draft', async () => {
    const onUse = mount()
    await userEvent.click(await screen.findByRole('button', { name: /use draft/i }))
    expect(onUse).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'd-1', body: expect.stringContaining('engineering') }),
    )
  })

  it('dismisses through the API', async () => {
    mount()
    await userEvent.click(await screen.findByRole('button', { name: /dismiss/i }))
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([u]) => String(u).includes('/draft-prompts/d-1/dismiss'))
    expect(call).toBeDefined()
    expect(call![1]).toMatchObject({ method: 'POST' })
  })

  it('shows every pending prompt, not just the first', async () => {
    mount(
      aConversationDetail({
        draftPrompts: [aDraftPrompt({ id: 'd-1' }), aDraftPrompt({ id: 'd-2', workOrderId: 'w-9' })],
      }),
    )
    expect(await screen.findAllByTestId('draft-prompt')).toHaveLength(2)
  })
})
