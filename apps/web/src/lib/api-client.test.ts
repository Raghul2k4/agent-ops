import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  api,
  ApiError,
  apiRequest,
  setAccessTokenProvider,
} from '@/lib/api-client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('api-client', () => {
  beforeEach(() => {
    setAccessTokenProvider(null)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    setAccessTokenProvider(null)
  })

  it('sends the access token as a bearer header', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    setAccessTokenProvider(async () => 'token-123')

    await api.get('/me')

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const headers = new Headers(init.headers)
    expect(headers.get('Authorization')).toBe('Bearer token-123')
    expect(headers.get('X-CSRF-Token')).toBeNull()
    expect(init.credentials).toBe('omit')
  })

  it('omits the Authorization header when there is no session', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)
    setAccessTokenProvider(async () => null)

    await api.get('/auth/mode')

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).get('Authorization')).toBeNull()
  })

  it('normalises the API error envelope into ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          {
            error: {
              code: 'PERMISSION_DENIED',
              message: 'Not allowed',
              retryable: false,
              request_id: 'req-1',
            },
          },
          403,
        ),
      ),
    )

    const failure = api.get('/workspaces')

    await expect(failure).rejects.toBeInstanceOf(ApiError)
    await failure.catch((error: ApiError) => {
      expect(error.status).toBe(403)
      expect(error.code).toBe('PERMISSION_DENIED')
      expect(error.isForbidden).toBe(true)
      expect(error.requestId).toBe('req-1')
    })
  })

  it('returns undefined for 204 responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(null, { status: 204 })),
    )

    await expect(api.post<void>('/auth/logout')).resolves.toBeUndefined()
  })

  it('serialises a JSON body and sets the content type', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ id: 'ws-1' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/workspaces', { method: 'POST', body: { name: 'Acme' } })

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe(JSON.stringify({ name: 'Acme' }))
  })
})
