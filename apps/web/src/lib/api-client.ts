/**
 * Typed API client.
 *
 * Every mutating request automatically carries the double-submit CSRF token
 * that the backend issued in the `agentops_csrf` cookie. Failures are
 * normalised into {@link ApiError} so the UI can branch on a stable error code
 * instead of parsing messages.
 */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? '/api/v1'

export const CSRF_COOKIE_NAME = 'agentops_csrf'

export interface ApiErrorBody {
  code: string
  message: string
  retryable: boolean
  details?: Record<string, unknown>
  request_id?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly retryable: boolean
  readonly details: Record<string, unknown> | undefined
  readonly requestId: string | undefined

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.retryable = body.retryable
    this.details = body.details
    this.requestId = body.request_id
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }

  get isForbidden(): boolean {
    return this.status === 403
  }

  get isNotFound(): boolean {
    return this.status === 404
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie
    .split('; ')
    .find((entry) => entry.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  /** Send a JSON body (default) or a raw body (e.g. FormData). */
  raw?: boolean
  /** Skip the CSRF header (used by the initial unauthenticated calls). */
  skipCsrf?: boolean
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, raw, skipCsrf, headers, ...rest } = options
  const method = (rest.method ?? 'GET').toUpperCase()
  const requestHeaders = new Headers(headers)

  let payload: BodyInit | undefined
  if (body !== undefined && body !== null) {
    if (raw) {
      payload = body as BodyInit
    } else {
      requestHeaders.set('Content-Type', 'application/json')
      payload = JSON.stringify(body)
    }
  }

  if (!skipCsrf && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = readCookie(CSRF_COOKIE_NAME)
    if (csrf) requestHeaders.set('X-CSRF-Token', csrf)
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    method,
    headers: requestHeaders,
    body: payload,
    credentials: 'include',
  })

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type') ?? ''
  const isJson = contentType.includes('application/json')
  const data: unknown = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    const errorBody: ApiErrorBody =
      isJson && data && typeof data === 'object' && 'error' in data
        ? (data as { error: ApiErrorBody }).error
        : {
            code: 'INTERNAL_ERROR',
            message: `Request failed with status ${response.status}`,
            retryable: response.status >= 500,
          }
    throw new ApiError(response.status, errorBody)
  }

  return data as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'DELETE' }),
}

/**
 * Fetch a server-root endpoint (health / readiness live outside `/api/v1`).
 */
export async function rootGet<T>(path: string): Promise<T> {
  const response = await fetch(path, { credentials: 'include' })
  const contentType = response.headers.get('content-type') ?? ''
  const data: unknown = contentType.includes('application/json')
    ? await response.json()
    : await response.text()
  if (!response.ok) {
    throw new ApiError(response.status, {
      code: 'INTERNAL_ERROR',
      message: `Request failed with status ${response.status}`,
      retryable: false,
    })
  }
  return data as T
}
