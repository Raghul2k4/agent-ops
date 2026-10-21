import type { SupabaseClient } from '@supabase/supabase-js'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AuthConfigurationError,
  AuthError,
  createAuthGateway,
  createLocalGateway,
  createSupabaseGateway,
  LOCAL_TOKEN_STORAGE_KEY,
  loadAuthMode,
} from '@/lib/auth-client'

const supabaseState = vi.hoisted(() => ({
  configured: false,
  client: null as unknown,
}))

vi.mock('@/lib/supabase', () => ({
  get isSupabaseConfigured() {
    return supabaseState.configured
  },
  get supabase() {
    return supabaseState.client
  },
  assertSupabaseClient: () => supabaseState.client,
}))

vi.mock('@/lib/api-client', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

const { api } = await import('@/lib/api-client')
const mockedApi = vi.mocked(api)

interface FakeAuth {
  getSession: ReturnType<typeof vi.fn>
  onAuthStateChange: ReturnType<typeof vi.fn>
  signInWithPassword: ReturnType<typeof vi.fn>
  signUp: ReturnType<typeof vi.fn>
  signOut: ReturnType<typeof vi.fn>
}

function makeClient() {
  const auth: FakeAuth = {
    getSession: vi.fn(async () => ({ data: { session: null }, error: null })),
    onAuthStateChange: vi.fn(() => ({
      data: { subscription: { unsubscribe: vi.fn() } },
    })),
    signInWithPassword: vi.fn(async () => ({ data: { session: null }, error: null })),
    signUp: vi.fn(async () => ({ data: { session: null, user: null }, error: null })),
    signOut: vi.fn(async () => ({ error: null })),
  }
  return { client: { auth } as unknown as SupabaseClient, auth }
}

beforeEach(() => {
  window.localStorage.clear()
  vi.clearAllMocks()
  supabaseState.configured = false
  supabaseState.client = null
})

describe('createAuthGateway', () => {
  it('returns the local gateway when the API reports local auth', () => {
    const gateway = createAuthGateway({
      auth_mode: 'local',
      local_sign_in_enabled: true,
      supabase_url: null,
    })

    expect(gateway.mode).toBe('local')
  })

  it('refuses to fall back to local credentials when Supabase is unconfigured', () => {
    supabaseState.configured = false

    expect(() =>
      createAuthGateway({
        auth_mode: 'supabase',
        local_sign_in_enabled: false,
        supabase_url: 'https://project.supabase.co',
      }),
    ).toThrow(AuthConfigurationError)
  })

  it('returns the Supabase gateway when the project is configured', () => {
    supabaseState.configured = true
    supabaseState.client = makeClient().client

    const gateway = createAuthGateway({
      auth_mode: 'supabase',
      local_sign_in_enabled: false,
      supabase_url: 'https://project.supabase.co',
    })

    expect(gateway.mode).toBe('supabase')
  })
})

describe('loadAuthMode', () => {
  it('reads the mode from the API', async () => {
    mockedApi.get.mockResolvedValue({
      auth_mode: 'supabase',
      local_sign_in_enabled: false,
      supabase_url: 'https://project.supabase.co',
    })

    const info = await loadAuthMode()

    expect(mockedApi.get).toHaveBeenCalledWith('/auth/mode')
    expect(info.auth_mode).toBe('supabase')
  })
})

describe('Supabase gateway', () => {
  it('returns the access token from the current session', async () => {
    const { client, auth } = makeClient()
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: 'supabase-token' } },
      error: null,
    })

    await expect(createSupabaseGateway(client).getAccessToken()).resolves.toBe(
      'supabase-token',
    )
  })

  it('returns null without a session', async () => {
    const { client } = makeClient()

    await expect(createSupabaseGateway(client).getAccessToken()).resolves.toBeNull()
  })

  it('surfaces provider errors as AuthError', async () => {
    const { client, auth } = makeClient()
    auth.signInWithPassword.mockResolvedValue({
      data: { session: null },
      error: { message: 'Invalid login credentials', code: 'invalid_credentials' },
    })

    const failure = createSupabaseGateway(client).signIn('a@b.co', 'wrong')

    await expect(failure).rejects.toBeInstanceOf(AuthError)
    await failure.catch((error: AuthError) => {
      expect(error.message).toBe('Invalid login credentials')
      expect(error.code).toBe('invalid_credentials')
    })
  })

  it('reports that email confirmation is required when no session is returned', async () => {
    const { client, auth } = makeClient()
    auth.signUp.mockResolvedValue({
      data: { session: null, user: { id: 'user-1' } },
      error: null,
    })

    const outcome = await createSupabaseGateway(client).signUp(
      'new@example.com',
      'Sup3rSecret!2026',
      'New User',
    )

    expect(outcome.needsEmailConfirmation).toBe(true)
    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'Sup3rSecret!2026',
      options: { data: { display_name: 'New User' } },
    })
  })

  it('reports a completed sign-up when a session is returned', async () => {
    const { client, auth } = makeClient()
    auth.signUp.mockResolvedValue({
      data: { session: { access_token: 'token' }, user: { id: 'user-1' } },
      error: null,
    })

    const outcome = await createSupabaseGateway(client).signUp(
      'new@example.com',
      'Sup3rSecret!2026',
      'New User',
    )

    expect(outcome.needsEmailConfirmation).toBe(false)
  })

  it('unsubscribes from auth state changes', () => {
    const { client, auth } = makeClient()
    const unsubscribe = vi.fn()
    auth.onAuthStateChange.mockReturnValue({
      data: { subscription: { unsubscribe } },
    })

    const stop = createSupabaseGateway(client).subscribe(vi.fn())
    stop()

    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })
})

describe('local gateway', () => {
  it('stores the token returned by the development issuer', async () => {
    const expiresAt = new Date(Date.now() + 60_000).toISOString()
    mockedApi.post.mockResolvedValue({
      access_token: 'local-token',
      token_type: 'bearer',
      expires_at: expiresAt,
      user: {},
      workspaces: [],
    })

    const gateway = createLocalGateway()
    await gateway.signIn('dev@example.com', 'Sup3rSecret!2026')

    expect(mockedApi.post).toHaveBeenCalledWith('/auth/login', {
      email: 'dev@example.com',
      password: 'Sup3rSecret!2026',
    })
    await expect(gateway.getAccessToken()).resolves.toBe('local-token')
    expect(window.localStorage.getItem(LOCAL_TOKEN_STORAGE_KEY)).toContain('local-token')
  })

  it('ignores an expired token and clears it', async () => {
    window.localStorage.setItem(
      LOCAL_TOKEN_STORAGE_KEY,
      JSON.stringify({
        access_token: 'stale-token',
        expires_at: new Date(Date.now() - 1000).toISOString(),
      }),
    )

    await expect(createLocalGateway().getAccessToken()).resolves.toBeNull()
    expect(window.localStorage.getItem(LOCAL_TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('clears the token on sign-out even when the audit call fails', async () => {
    window.localStorage.setItem(
      LOCAL_TOKEN_STORAGE_KEY,
      JSON.stringify({
        access_token: 'local-token',
        expires_at: new Date(Date.now() + 60_000).toISOString(),
      }),
    )
    mockedApi.post.mockRejectedValue(new Error('network down'))

    await expect(createLocalGateway().signOut()).resolves.toBeUndefined()
    expect(window.localStorage.getItem(LOCAL_TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('registers through the API and stores the returned session', async () => {
    mockedApi.post.mockResolvedValue({
      access_token: 'local-token',
      token_type: 'bearer',
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      user: {},
      workspaces: [],
    })

    const outcome = await createLocalGateway().signUp(
      'dev@example.com',
      'Sup3rSecret!2026',
      'Dev User',
    )

    expect(outcome.needsEmailConfirmation).toBe(false)
    expect(mockedApi.post).toHaveBeenCalledWith('/auth/register', {
      email: 'dev@example.com',
      password: 'Sup3rSecret!2026',
      display_name: 'Dev User',
    })
    await expect(createLocalGateway().getAccessToken()).resolves.toBe('local-token')
  })
})
