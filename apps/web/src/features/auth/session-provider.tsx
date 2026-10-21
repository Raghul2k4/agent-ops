import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { api, ApiError, setAccessTokenProvider } from '@/lib/api-client'
import {
  AuthConfigurationError,
  createAuthGateway,
  loadAuthMode,
  type AuthGateway,
  type AuthMode,
  type SignUpOutcome,
} from '@/lib/auth-client'
import type { AuthModeInfo, MeResponse, UserRead, WorkspaceRead } from '@/types/api'

interface SessionContextValue {
  user: UserRead | null
  workspaces: WorkspaceRead[]
  isLoading: boolean
  isAuthenticated: boolean
  /** True when a token exists, even if the profile request has not succeeded yet. */
  hasActiveSession: boolean
  /** How this deployment authenticates browsers, once known. */
  authMode: AuthMode | null
  /** Set when the auth layer cannot be initialised (e.g. missing Supabase env). */
  configurationError: string | null
  error: ApiError | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (payload: {
    email: string
    password: string
    display_name: string
  }) => Promise<SignUpOutcome>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}

const SessionContext = createContext<SessionContextValue | null>(null)

const ME_QUERY_KEY = ['me'] as const

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const [gateway, setGateway] = useState<AuthGateway | null>(null)
  const [modeInfo, setModeInfo] = useState<AuthModeInfo | null>(null)
  const [configurationError, setConfigurationError] = useState<string | null>(null)
  const [hasSession, setHasSession] = useState(false)
  const [ready, setReady] = useState(false)
  // Bumped whenever the auth provider reports a session change; it is part of
  // the `/me` key so the profile is re-read after sign-in and dropped on sign-out.
  const [sessionVersion, setSessionVersion] = useState(0)
  const gatewayRef = useRef<AuthGateway | null>(null)

  useEffect(() => {
    let cancelled = false
    let unsubscribe: (() => void) | undefined

    async function bootstrap() {
      try {
        const info = await loadAuthMode()
        if (cancelled) return

        const nextGateway = createAuthGateway(info)
        if (cancelled) return

        gatewayRef.current = nextGateway
        setAccessTokenProvider(() => nextGateway.getAccessToken())
        setModeInfo(info)
        setGateway(nextGateway)

        unsubscribe = nextGateway.subscribe(() => {
          setSessionVersion((version) => version + 1)
        })

        const token = await nextGateway.getAccessToken()
        if (cancelled) return
        setHasSession(Boolean(token))
      } catch (error) {
        if (cancelled) return
        setConfigurationError(
          error instanceof AuthConfigurationError || error instanceof ApiError
            ? error.message
            : 'Authentication could not be initialised.',
        )
      } finally {
        if (!cancelled) setReady(true)
      }
    }

    void bootstrap()

    return () => {
      cancelled = true
      unsubscribe?.()
      setAccessTokenProvider(null)
      gatewayRef.current = null
    }
  }, [])

  // Re-read the token whenever the provider reports a change (sign-in,
  // sign-out, refresh, another tab).
  useEffect(() => {
    const current = gatewayRef.current
    if (!current) return
    let cancelled = false
    void current
      .getAccessToken()
      .then((token) => {
        if (!cancelled) setHasSession(Boolean(token))
      })
      .catch(() => {
        if (!cancelled) setHasSession(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionVersion, gateway])

  const meQuery = useQuery({
    queryKey: [...ME_QUERY_KEY, sessionVersion],
    queryFn: () => api.get<MeResponse>('/me'),
    enabled: ready && hasSession && Boolean(gateway),
    retry: false,
    staleTime: 30_000,
  })

  // A stored token that the API rejects (revoked, expired, user deleted) must
  // not leave the UI in a half-authenticated state: drop it and show sign-in.
  useEffect(() => {
    if (meQuery.error instanceof ApiError && meQuery.error.isUnauthorized) {
      setHasSession(false)
    }
  }, [meQuery.error])

  const signIn = useCallback(
    async (email: string, password: string) => {
      const current = gatewayRef.current
      if (!current) throw new Error('Authentication is not available in this deployment.')
      await current.signIn(email, password)
      const token = await current.getAccessToken()
      setHasSession(Boolean(token))
      setSessionVersion((version) => version + 1)
    },
    [],
  )

  const signUp = useCallback(
    async (payload: { email: string; password: string; display_name: string }) => {
      const current = gatewayRef.current
      if (!current) throw new Error('Authentication is not available in this deployment.')
      const outcome = await current.signUp(payload.email, payload.password, payload.display_name)
      if (!outcome.needsEmailConfirmation) {
        const token = await current.getAccessToken()
        setHasSession(Boolean(token))
        setSessionVersion((version) => version + 1)
      }
      return outcome
    },
    [],
  )

  const signOut = useCallback(async () => {
    const current = gatewayRef.current
    if (current) {
      if (current.mode === 'supabase') {
        // Record the sign-out in the audit trail while the token is still valid.
        await api.post<void>('/auth/logout').catch(() => undefined)
      }
      await current.signOut()
    }
    queryClient.removeQueries({ queryKey: ['workspaces'] })
    queryClient.removeQueries({ queryKey: ME_QUERY_KEY })
    setHasSession(false)
    setSessionVersion((version) => version + 1)
  }, [queryClient])

  const value = useMemo<SessionContextValue>(
    () => ({
      user: meQuery.data?.user ?? null,
      workspaces: meQuery.data?.workspaces ?? [],
      isLoading: !ready || (hasSession && meQuery.isLoading),
      isAuthenticated: Boolean(meQuery.data?.user),
      hasActiveSession: hasSession,
      authMode: modeInfo?.auth_mode ?? null,
      configurationError,
      error: meQuery.error instanceof ApiError ? meQuery.error : null,
      signIn,
      signUp,
      signOut,
      refresh: async () => {
        await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
      },
    }),
    [
      ready,
      hasSession,
      meQuery.data,
      meQuery.isLoading,
      meQuery.error,
      modeInfo,
      configurationError,
      signIn,
      signUp,
      signOut,
      queryClient,
    ],  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used inside a SessionProvider')
  }
  return context
}
