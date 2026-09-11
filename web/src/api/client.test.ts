import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, api, onUnauthorized, propertyPath } from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    onUnauthorized(null)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns the parsed body directly — there is no envelope', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, [{ id: 'c1' }]))
    await expect(api<{ id: string }[]>('/api/p/p1/conversations')).resolves.toEqual([{ id: 'c1' }])
  })

  it('sends cookies so the HttpOnly sid session is used', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(200, {}))
    await api('/api/auth/me')
    expect(vi.mocked(fetch).mock.calls[0]![1]).toMatchObject({ credentials: 'same-origin' })
  })

  it('serialises `json` as a POST body with the right content type', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(201, { id: 'w1' }))
    await api('/api/p/p1/work-orders', { method: 'POST', json: { title: 'AC' } })
    const init = vi.mocked(fetch).mock.calls[0]![1]!
    expect(init.body).toBe('{"title":"AC"}')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('sends a raw body and does not set a JSON content type when `body` is used instead of `json`', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await api('/api/hooks/sms/inbound', {
      method: 'POST',
      body: new URLSearchParams({ From: '+15551234567' }),
    })
    const init = vi.mocked(fetch).mock.calls[0]![1]!
    expect(String(init.body)).toBe('From=%2B15551234567')
    expect(new Headers(init.headers).get('Content-Type')).toBeNull()
  })

  it('resolves to undefined on 204 without trying to parse a body', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }))
    await expect(api('/api/p/p1/notifications/n1/read', { method: 'POST' })).resolves
      .toBeUndefined()
  })

  it('unwraps the error envelope into an ApiError carrying code and status', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(422, {
        error: { code: 'CONSENT_OPTED_OUT', message: 'Guest has opted out', details: { a: 1 } },
      }),
    )
    const err = await api('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({
      status: 422,
      code: 'CONSENT_OPTED_OUT',
      message: 'Guest has opted out',
      details: { a: 1 },
    })
  })

  it('still throws a usable ApiError when the body is not JSON', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('<html>502</html>', { status: 502 }))
    const err = await api('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 502, code: 'HTTP_502' })
    expect((err as ApiError).message).toBeTruthy()
  })

  it('calls the unauthorized hook on 401 and still rejects', async () => {
    const seen = vi.fn()
    onUnauthorized(seen)
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(401, { error: { code: 'UNAUTHORIZED', message: 'Session expired' } }),
    )
    await expect(api('/api/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(seen).toHaveBeenCalledOnce()
  })

  it('does not fire the unauthorized hook for 403 — that is a role problem, not a session one', async () => {
    const seen = vi.fn()
    onUnauthorized(seen)
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(403, { error: { code: 'FORBIDDEN', message: 'Not your property' } }),
    )
    await expect(api('/api/p/other/conversations')).rejects.toBeInstanceOf(ApiError)
    expect(seen).not.toHaveBeenCalled()
  })

  it('builds property-scoped paths', () => {
    expect(propertyPath('p1', 'conversations?filter=all')).toBe('/api/p/p1/conversations?filter=all')
  })

  it('turns a network failure into an ApiError rather than a raw TypeError', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    const err = await api('/x').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 0, code: 'NETWORK' })
  })
})
