import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SessionProvider } from '../../auth/SessionContext'
import { aWorkOrderPhoto } from '../../test/factories'
import { renderWithProviders, sessionFixture } from '../../test/harness'
import { PhotoPanel } from './PhotoPanel'

function serve(status = 201, body: unknown = aWorkOrderPhoto({ id: 'photo-2' })) {
  vi.mocked(fetch).mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
    ),
  )
}

function mount(photos = [] as ReturnType<typeof aWorkOrderPhoto>[]) {
  return renderWithProviders(
    <SessionProvider>
      <PhotoPanel workOrderId="w-204" photos={photos} />
    </SessionProvider>,
    { session: sessionFixture({ role: 'dept_staff' }) },
  )
}

describe('PhotoPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    serve()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('says None yet with no photos', () => {
    mount([])
    expect(screen.getByText('None yet')).toBeInTheDocument()
  })

  it('renders an existing photo with its kind, time and uploader', () => {
    mount([aWorkOrderPhoto({ kind: 'after', uploadedByName: 'Eli Engineer' })])
    const img = screen.getByRole('img', { name: 'After photo' })
    expect(img).toHaveAttribute('src', '/api/p/prop-a/work-orders/w-204/photos/photo-1')
    expect(screen.getByText(/After ·/)).toHaveTextContent('Eli Engineer')
  })

  it('reveals the kind select and file input on + Add photo', async () => {
    mount()
    await userEvent.click(screen.getByRole('button', { name: '+ Add photo' }))
    expect(screen.getByLabelText('Photo kind')).toBeInTheDocument()
    expect(screen.getByLabelText('Photo file')).toBeInTheDocument()
  })

  // The input's own `accept` already keeps a real file picker from offering a non-image file,
  // so this exercises the client-side guard as the defense-in-depth it is — reachable via
  // drag-and-drop or a renamed file, which `accept` does not stop — via fireEvent, which (unlike
  // userEvent.upload) does not itself honour `accept`.
  it('rejects a non-image file client-side, without calling the server', async () => {
    mount()
    await userEvent.click(screen.getByRole('button', { name: '+ Add photo' }))
    const file = new File(['x'], 'note.txt', { type: 'text/plain' })
    fireEvent.change(screen.getByLabelText('Photo file'), { target: { files: [file] } })
    expect(await screen.findByText(/only jpeg, png or webp/i)).toBeInTheDocument()
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('rejects an oversized file client-side, without calling the server', async () => {
    mount()
    await userEvent.click(screen.getByRole('button', { name: '+ Add photo' }))
    const big = new File([new Uint8Array(8 * 1024 * 1024 + 1)], 'huge.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Photo file'), big)
    expect(await screen.findByText(/over 8 mb/i)).toBeInTheDocument()
    expect(vi.mocked(fetch)).not.toHaveBeenCalled()
  })

  it('uploads a valid file as multipart form data with the chosen kind, and collapses on success', async () => {
    mount()
    await userEvent.click(screen.getByRole('button', { name: '+ Add photo' }))
    await userEvent.selectOptions(screen.getByLabelText('Photo kind'), 'after')
    const file = new File(['bytes'], 'ac.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Photo file'), file)

    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled())
    const [url, init] = vi.mocked(fetch).mock.calls[0]!
    expect(String(url)).toBe('/api/p/prop-a/work-orders/w-204/photos')
    expect(init?.method).toBe('POST')
    // No Content-Type set by us — the browser owns the multipart boundary.
    expect(new Headers(init?.headers).has('Content-Type')).toBe(false)
    const form = init!.body as FormData
    expect(form.get('kind')).toBe('after')
    expect((form.get('photo') as File).name).toBe('ac.png')

    await waitFor(() => expect(screen.getByRole('button', { name: '+ Add photo' })).toBeInTheDocument())
  })

  it('shows the server error mapped through the shared field-errors normaliser', async () => {
    serve(400, { error: { code: 'VALIDATION_FAILED', message: 'bad', details: { photo: 'file_too_large' } } })
    mount()
    await userEvent.click(screen.getByRole('button', { name: '+ Add photo' }))
    const file = new File(['bytes'], 'ac.png', { type: 'image/png' })
    await userEvent.upload(screen.getByLabelText('Photo file'), file)
    expect(await screen.findByText(/over 8 mb/i)).toBeInTheDocument()
  })
})
