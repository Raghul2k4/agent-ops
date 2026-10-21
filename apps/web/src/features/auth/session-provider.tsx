import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react'

import { api, ApiError } from '@/lib/api-client'
import type { AuthResponse, MeResponse, UserRead, WorkspaceRead } from '@/types/api'

interface SessionContextValue {
  user: UserRead | null
  workspaces: WorkspaceRead[]
  isLoading: boolean
  isAuthenticated: boolean
  error: ApiError | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (payload: {
    email: string
    password: string
    display_name: string
  }) => Promise<void>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}

interface SessionData {
  user: UserRead | null
  workspaces: WorkspaceRead[]
}

const SessionContext = createContext<SessionContextValue | null>(null)

const ME_QUERY_KEY = ['me'] as const

export function SessionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const meQuery = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: () => api.get<MeResponse>('/me'),
    retry: false,
    staleTime: 60_000,
  })

  const applyAuth = useCallback(
    (payload: AuthResponse) => {
      queryClient.setQueryData<SessionData>(ME_QUERY_KEY, {
        user: payload.user,
        workspaces: payload.workspaces,
      })
    },
    [queryClient],
  )

  const signInMutation = useMutation({
    mutationFn: (payload: { email: string; password: string }) =>
      api.post<AuthResponse>('/auth/login', payload),
    onSuccess: applyAuth,
  })

  const signUpMutation = useMutation({
    mutationFn: (payload: { email: string; password: string; display_name: string }) =>
      api.post<AuthResponse>('/auth/register', payload),
    onSuccess: applyAuth,
  })

  const signOutMutation = useMutation({
    mutationFn: () => api.post<void>('/auth/logout'),
    onSuccess: () => {
      queryClient.setQueryData<SessionData>(ME_QUERY_KEY, { user: null, workspaces: [] })
      queryClient.removeQueries({ queryKey: ['workspaces'] })
    },
  })

  const value = useMemo<SessionContextValue>(
    () => ({
      user: meQuery.data?.user ?? null,
      workspaces: meQuery.data?.workspaces ?? [],
      isLoading: meQuery.isLoading,
      isAuthenticated: Boolean(meQuery.data?.user),
      error: meQuery.error instanceof ApiError ? meQuery.error : null,
      signIn: async (email, password) => {
        await signInMutation.mutateAsync({ email, password })
      },
      signUp: async (payload) => {
        await signUpMutation.mutateAsync(payload)
      },
      signOut: async () => {
        await signOutMutation.mutateAsync()
      },
      refresh: async () => {
        await queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
      },
    }),
    [meQuery.data, meQuery.isLoading, meQuery.error, signInMutation, signUpMutation, signOutMutation, queryClient],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used inside a SessionProvider')
  }
  return context
}
