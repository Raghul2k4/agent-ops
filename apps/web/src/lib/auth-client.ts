/**
 * Authentication gateway.
 *
 * The API is the source of truth for which issuer owns identity
 * (`GET /auth/mode`). Two gateways implement the same contract:
 *
 * * **Supabase** - sign-in happens directly against the project's Auth server
 *   with the publishable key; the SDK stores and refreshes the session and the
 *   access token is sent to the API as a bearer token.
 * * **Local** - the development issuer. The token comes from the API's
 *   `/auth/login` endpoint and is kept in `localStorage`. It only works when the
 *   API runs with `AUTH_MODE=local`, which is refused outside development/test.
 *
 * Keeping both behind one interface means the session provider, the API client
 * and every screen are identical in both modes.
 */

import type { SupabaseClient } from '@supabase/supabase-js'

import { api } from '@/lib/api-client'
import { assertSupabaseClient, isSupabaseConfigured, supabase } from '@/lib/supabase'
import type { AuthModeInfo, AuthResponse } from '@/types/api'

export type AuthMode = 'supabase' | 'local'

export interface SignUpOutcome {
  /**
   * `true` when Supabase created the identity but requires the user to confirm
   * their email address before a session exists.
   */
  needsEmailConfirmation: boolean
}

export interface AuthGateway {
  readonly mode: AuthMode
  /** The current access token, or `null` when there is no valid session. */
  getAccessToken(): Promise<string | null>
  /** Notify when the underlying session appears, disappears or rotates. */
  subscribe(listener: () => void): () => void
  signIn(email: string, password: string): Promise<void>
  signUp(email: string, password: string, displayName: string): Promise<SignUpOutcome>
  signOut(): Promise<void>
}

/** Error raised by an authentication provider (as opposed to the AgentOps API). */
export class AuthError extends Error {
  readonly code: string | undefined

  constructor(message: string, code?: string) {
    super(message)
    this.name = 'AuthError'
    this.code = code
  }
}

export class AuthConfigurationError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthConfigurationError'
  }
}

export async function loadAuthMode(): Promise<AuthModeInfo> {
  return api.get<AuthModeInfo>('/auth/mode')
}

export function createSupabaseGateway(client: SupabaseClient): AuthGateway {
  return {
    mode: 'supabase',

    async getAccessToken() {
      const { data, error } = await client.auth.getSession()
      if (error) throw new AuthError(error.message, error.code)
      return data.session?.access_token ?? null
    },

    subscribe(listener) {
      // The callback must stay synchronous: awaiting other Supabase calls
      // inside `onAuthStateChange` deadlocks the client.
      const { data } = client.auth.onAuthStateChange(() => {
        listener()
      })
      return () => {
        data.subscription.unsubscribe()
      }
    },

    async signIn(email, password) {
      const { error } = await client.auth.signInWithPassword({ email, password })
      if (error) throw new AuthError(error.message, error.code)
    },

    async signUp(email, password, displayName) {
      const { data, error } = await client.auth.signUp({
        email,
        password,
        options: { data: { display_name: displayName } },
      })
      if (error) throw new AuthError(error.message, error.code)
      return { needsEmailConfirmation: data.session === null }
    },

    async signOut() {
      const { error } = await client.auth.signOut()
      if (error) throw new AuthError(error.message, error.code)
    },
  }
}

interface StoredLocalToken {
  access_token: string
  expires_at: string
}

const LOCAL_TOKEN_KEY = 'agentops.local.token'

function readLocalToken(): StoredLocalToken | null {
  try {
    const raw = window.localStorage.getItem(LOCAL_TOKEN_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as StoredLocalToken
    if (!parsed.access_token || !parsed.expires_at) return null
    if (new Date(parsed.expires_at).getTime() <= Date.now()) {
      window.localStorage.removeItem(LOCAL_TOKEN_KEY)
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function createLocalGateway(): AuthGateway {
  const listeners = new Set<() => void>()
  const notify = () => {
    for (const listener of listeners) listener()
  }

  return {
    mode: 'local',

    async getAccessToken() {
      return readLocalToken()?.access_token ?? null
    },

    subscribe(listener) {
      listeners.add(listener)
      // Another tab signing in or out must update this one too.
      const onStorage = (event: StorageEvent) => {
        if (event.key === LOCAL_TOKEN_KEY) listener()
      }
      window.addEventListener('storage', onStorage)
      return () => {
        listeners.delete(listener)
        window.removeEventListener('storage', onStorage)
      }
    },

    async signIn(email, password) {
      const response = await api.post<AuthResponse>('/auth/login', { email, password })
      const stored: StoredLocalToken = {
        access_token: response.access_token,
        expires_at: response.expires_at,
      }
      window.localStorage.setItem(LOCAL_TOKEN_KEY, JSON.stringify(stored))
      notify()
    },

    async signUp(email, password, displayName) {
      const response = await api.post<AuthResponse>('/auth/register', {
        email,
        password,
        display_name: displayName,
      })
      const stored: StoredLocalToken = {
        access_token: response.access_token,
        expires_at: response.expires_at,
      }
      window.localStorage.setItem(LOCAL_TOKEN_KEY, JSON.stringify(stored))
      notify()
      return { needsEmailConfirmation: false }
    },

    async signOut() {
      try {
        await api.post<void>('/auth/logout')
      } catch {
        // The token is client-side; a failed audit call must not trap the user
        // in a signed-in state. Removal below is what ends the session.
      }
      window.localStorage.removeItem(LOCAL_TOKEN_KEY)
      notify()
    },
  }
}

/**
 * Build the gateway the API says this deployment uses.
 *
 * When Supabase owns identity but the bundle has no project URL / publishable
 * key, this throws a configuration error that the UI renders as an actionable
 * setup message - it never falls back to a local credential path.
 */
export function createAuthGateway(info: AuthModeInfo): AuthGateway {
  if (info.auth_mode === 'local') {
    return createLocalGateway()
  }
  if (!isSupabaseConfigured) {
    throw new AuthConfigurationError(
      'This deployment authenticates with Supabase, but the web build has no Supabase project configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY, then rebuild.',
    )
  }
  return createSupabaseGateway(supabase ?? assertSupabaseClient())
}

export const LOCAL_TOKEN_STORAGE_KEY = LOCAL_TOKEN_KEY
