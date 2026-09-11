export type ApiInit = Omit<RequestInit, 'body'> & { json?: unknown }

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

let unauthorizedHandler: (() => void) | null = null

/** One global hook, installed by SessionProvider, so an expired session lands on /login once. */
export function onUnauthorized(fn: (() => void) | null): void {
  unauthorizedHandler = fn
}

export function propertyPath(propertyId: string, rest: string): string {
  return `/api/p/${propertyId}/${rest}`
}

function errorFrom(status: number, body: unknown, fallback: string): ApiError {
  const envelope = (body as { error?: { code?: string; message?: string; details?: unknown } })
    ?.error
  return new ApiError(
    status,
    envelope?.code ?? `HTTP_${status}`,
    envelope?.message ?? fallback,
    envelope?.details,
  )
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const { json, headers, ...rest } = init
  const requestHeaders = new Headers(headers)
  if (json !== undefined) requestHeaders.set('Content-Type', 'application/json')

  let response: Response
  try {
    response = await fetch(path, {
      ...rest,
      headers: requestHeaders,
      credentials: 'same-origin',
      body: json === undefined ? undefined : JSON.stringify(json),
    })
  } catch (cause) {
    throw new ApiError(0, 'NETWORK', 'Could not reach the server. Check your connection.', cause)
  }

  if (!response.ok) {
    // A proxy or crash can answer with HTML; never let a parse failure mask the status.
    const body = await response.json().catch(() => null)
    if (response.status === 401) unauthorizedHandler?.()
    throw errorFrom(response.status, body, `Request failed (${response.status})`)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
