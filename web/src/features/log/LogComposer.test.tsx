import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import type { DepartmentOut, LogEntryOut, LogMentionableOut, LogTemplateOut } from '../../api/types'
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

const NIGHT_AUDIT: LogTemplateOut = {
  id: 't-night',
  name: 'Night Audit',
  shift: 'overnight',
  active: true,
  position: 0,
  usedCount: 4,
  audience: [],
  fields: [
    { id: 'f-arr', position: 0, label: 'Arrivals actual', fieldType: 'integer', required: true, active: true },
    { id: 'f-occ', position: 1, label: 'Occupancy', fieldType: 'percent', required: true, active: true },
    { id: 'f-adr', position: 2, label: 'ADR', fieldType: 'decimal', required: false, active: true },
    { id: 'f-mgr', position: 3, label: 'Duty manager', fieldType: 'short_text', required: false, active: true },
    { id: 'f-hand', position: 4, label: 'Handover', fieldType: 'long_text', required: false, active: true },
  ],
}

function serveTemplates(templates: LogTemplateOut[], post?: { status: number; body: unknown }) {
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const reply = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
    if (init?.method === 'POST') return reply(post?.body ?? CREATED, post?.status ?? 201)
    if (url.includes('/log-entries/templates')) return reply(templates)
    if (url.includes('mentionables')) return reply(MENTIONABLES)
    if (url.includes('/departments')) return reply(DEPARTMENTS)
    return reply([])
  })
}

describe('LogComposer with templates', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows no picker when no template is usable', async () => {
    serveTemplates([])
    mount()
    await screen.findByLabelText('Department')
    expect(screen.queryByLabelText('Use a template')).not.toBeInTheDocument()
  })

  it('renders each field type once a template is chosen, and clears it again', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')

    expect(screen.getByLabelText(/^Arrivals actual/)).toHaveAttribute('inputmode', 'numeric')
    expect(screen.getByLabelText(/^Occupancy/)).toHaveAttribute('inputmode', 'decimal')
    expect(screen.getByText('%')).toBeInTheDocument()
    expect(screen.getByLabelText(/^ADR/)).toHaveAttribute('inputmode', 'decimal')
    expect(screen.getByLabelText(/^Duty manager/).tagName).toBe('INPUT')
    expect(screen.getByLabelText(/^Handover/).tagName).toBe('TEXTAREA')
    expect(screen.getByLabelText(/^Arrivals actual/)).toHaveAttribute('aria-required', 'true')
    expect(screen.getByLabelText(/^ADR/)).toHaveAttribute('aria-required', 'false')
    expect(screen.getByLabelText('Notes (optional)')).toBe(screen.getByPlaceholderText('Add to the log…'))

    await userEvent.selectOptions(screen.getByLabelText('Use a template'), '')
    expect(screen.queryByLabelText(/^Arrivals actual/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Notes (optional)')).not.toBeInTheDocument()
  })

  it('keeps Post disabled until every required field is filled, notes or not', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    const post = screen.getByRole('button', { name: 'Post' })
    await userEvent.type(screen.getByPlaceholderText('Add to the log…'), 'Quiet night')
    expect(post).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    expect(post).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '   ')
    expect(post).toBeDisabled() // blank is unanswered
    await userEvent.clear(screen.getByLabelText(/^Occupancy/))
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87')
    expect(post).not.toBeDisabled()
  })

  it('sends templateId and the answered fieldValues, numbers as numbers', async () => {
    serveTemplates([NIGHT_AUDIT])
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87.5')
    await userEvent.type(screen.getByLabelText(/^Duty manager/), ' Sam ')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(postCalls()).toHaveLength(1))
    expect(JSON.parse(String(postCalls()[0]![1]!.body))).toMatchObject({
      body: '',
      templateId: 't-night',
      fieldValues: [
        { fieldId: 'f-arr', value: 38 },
        { fieldId: 'f-occ', value: 87.5 },
        { fieldId: 'f-mgr', value: 'Sam' },
      ],
    })
  })

  it('shows the server’s reason beside the field it names', async () => {
    serveTemplates([NIGHT_AUDIT], {
      status: 400,
      body: { error: { code: 'VALIDATION_FAILED', message: 'Some template fields need attention',
                       details: { 'f-occ': 'out_of_range', 'f-arr': 'not_whole' } } },
    })
    mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '12.5')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '140')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    expect(await screen.findByText('That value is out of range.')).toBeInTheDocument()
    expect(screen.getByText('Enter a whole number.')).toBeInTheDocument()
    expect(screen.getByLabelText(/^Occupancy/)).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent('Some template fields need attention')
  })

  it('resets the template and its answers after a successful post', async () => {
    serveTemplates([NIGHT_AUDIT])
    const onPosted = mount()
    await userEvent.selectOptions(await screen.findByLabelText('Use a template'), 't-night')
    await userEvent.type(screen.getByLabelText(/^Arrivals actual/), '38')
    await userEvent.type(screen.getByLabelText(/^Occupancy/), '87')
    await userEvent.click(screen.getByRole('button', { name: 'Post' }))

    await waitFor(() => expect(onPosted).toHaveBeenCalledWith(CREATED))
    expect(screen.getByLabelText('Use a template')).toHaveValue('')
    expect(screen.queryByLabelText(/^Arrivals actual/)).not.toBeInTheDocument()
  })
})
