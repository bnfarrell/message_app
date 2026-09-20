import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import type { DepartmentOut, LogEntryOut, LogMentionableOut } from '../../api/types'
import { aDepartment } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { LogComposer } from './LogComposer'
import { tokenFor } from './MentionInput'

// TOKEN_RE only matches an id shaped like a real UUID (`[0-9a-f-]{36}`), so fixtures need
// UUID-shaped ids for the pruning tests to exercise the actual regex, not a fake that
// happens to never appear in body text.
const HOUSEKEEPING_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const ANA_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

const HOUSEKEEPING: LogMentionableOut = {
  type: 'department',
  id: HOUSEKEEPING_ID,
  displayName: 'Housekeeping',
  subtitle: 'Department',
}
const ANA: LogMentionableOut = { type: 'user', id: ANA_ID, displayName: 'Ana', subtitle: 'agent' }
const MENTIONABLES: LogMentionableOut[] = [HOUSEKEEPING, ANA]
const DEPARTMENTS: DepartmentOut[] = [
  aDepartment(),
  aDepartment({ id: HOUSEKEEPING_ID, name: 'Housekeeping', type: 'housekeeping' }),
]

const CREATED: LogEntryOut = {
  id: 'log-1',
  authorUserId: 'u-ava',
  authorName: 'Ava Nolan',
  body: 'posted',
  createdAt: '2026-09-19T12:00:00Z',
  pinned: false,
  requiresAck: false,
  ackExpectedCount: 0,
  ackedByMe: false,
  canAck: false,
  shift: 'am',
}

function serve(overrides: { postStatus?: number; postBody?: unknown } = {}) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/log-entries') && !url.includes('mentionables') && init?.method === 'POST') {
      return Promise.resolve(
        new Response(JSON.stringify(overrides.postBody ?? CREATED), {
          status: overrides.postStatus ?? 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }
    const body = url.includes('mentionables') ? MENTIONABLES : url.includes('/departments') ? DEPARTMENTS : []
    return Promise.resolve(
      new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
  })
}

function mount(onPosted = vi.fn()) {
  renderWithProviders(
    <SessionProvider>
      <LogComposer onPosted={onPosted} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'agent' }) },
  )
  return onPosted
}

function postCalls() {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([input, init]) => String(input).includes('/log-entries') && init?.method === 'POST')
}

describe('LogComposer', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits body, department, mentions and the ack audience in one request', async () => {
    mount()
    await screen.findByLabelText('Department')

    const body = screen.getByPlaceholderText('Add to the log…')
    await userEvent.type(body, 'Restocked minibars @Housekeeping')
    await userEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /Housekeeping/ }))

    await userEvent.selectOptions(screen.getByLabelText('Department'), HOUSEKEEPING_ID)

    await userEvent.click(screen.getByLabelText('Requires acknowledgement'))
    const audience = screen.getByPlaceholderText('Who needs to acknowledge this?')
    await userEvent.type(audience, '@Housekeeping')
    await userEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /Housekeeping/ }))

    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(postCalls()).toHaveLength(1))
    const [, init] = postCalls()[0]!
    expect(JSON.parse(String(init!.body))).toEqual({
      body: `Restocked minibars ${tokenFor(HOUSEKEEPING)}`,
      departmentId: HOUSEKEEPING_ID,
      mentions: [{ type: 'department', id: HOUSEKEEPING_ID }],
      requiresAck: true,
      ackAudience: [{ type: 'department', id: HOUSEKEEPING_ID }],
    })
  })

  it('sends multipart when a photo is attached', async () => {
    mount()
    await screen.findByLabelText('Department')

    const body = screen.getByPlaceholderText('Add to the log…')
    // Typed in two steps: text after the mention would otherwise close the picker
    // before the option can be clicked (a space ends the active `@query`).
    await userEvent.type(body, 'Photo of @Housekeeping')
    await userEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /Housekeeping/ }))
    await userEvent.type(body, ' cart')

    const file = new File(['bytes'], 'cart.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Photo'), file)

    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(postCalls()).toHaveLength(1))
    const [, init] = postCalls()[0]!
    expect(init!.body).toBeInstanceOf(FormData)
    const form = init!.body as FormData
    expect(form.get('body')).toBe(`Photo of ${tokenFor(HOUSEKEEPING)} cart`)
    expect(form.get('photo')).toBeInstanceOf(File)
    expect(JSON.parse(String(form.get('mentions')))).toEqual([{ type: 'department', id: HOUSEKEEPING_ID }])
  })

  it('does not submit an empty body', async () => {
    mount()
    await screen.findByLabelText('Department')
    const submit = screen.getByRole('button', { name: 'Post' })
    expect(submit).toBeDisabled()

    const body = screen.getByPlaceholderText('Add to the log…')
    await userEvent.type(body, '   ')
    expect(submit).toBeDisabled()

    await userEvent.type(body, 'Now real content')
    expect(submit).not.toBeDisabled()
  })

  it('shows the server error message when the post fails', async () => {
    mount()
    await screen.findByLabelText('Department')
    const body = screen.getByPlaceholderText('Add to the log…')
    await userEvent.type(body, 'Broken request')

    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ error: { code: 'VALIDATION', message: 'Body is too long' } }), {
        status: 422,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Body is too long')
  })

  it('resets every field after a successful post', async () => {
    const onPosted = mount()
    await screen.findByLabelText('Department')

    const body = screen.getByPlaceholderText('Add to the log…')
    await userEvent.type(body, 'Wrap-up note @Housekeeping')
    await userEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /Housekeeping/ }))
    await userEvent.selectOptions(screen.getByLabelText('Department'), HOUSEKEEPING_ID)
    const file = new File(['bytes'], 'cart.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Photo'), file)
    await userEvent.click(screen.getByLabelText('Requires acknowledgement'))

    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onPosted).toHaveBeenCalledWith(CREATED))
    expect(screen.getByPlaceholderText('Add to the log…')).toHaveValue('')
    expect(screen.getByLabelText('Department')).toHaveValue('')
    expect(screen.getByLabelText('Photo')).toHaveValue('')
    expect(screen.getByLabelText('Requires acknowledgement')).not.toBeChecked()
    expect(screen.queryByPlaceholderText('Who needs to acknowledge this?')).not.toBeInTheDocument()
  })

  it('prunes a mention whose token text was deleted before submit', async () => {
    mount()
    await screen.findByLabelText('Department')

    const body = screen.getByPlaceholderText('Add to the log…')
    await userEvent.type(body, '@Ana')
    await userEvent.click(within(screen.getByRole('listbox')).getByRole('option', { name: /Ana/ }))
    expect(body).toHaveValue(tokenFor(ANA))

    // Delete the inserted token text entirely, then type a fresh body with no mention in it.
    await userEvent.clear(body)
    await userEvent.type(body, 'Never mind, false alarm')

    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(postCalls()).toHaveLength(1))
    const [, init] = postCalls()[0]!
    expect(JSON.parse(String(init!.body)).mentions).toEqual([])
  })
})
