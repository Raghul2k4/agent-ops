import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { useSession } from '@/features/auth/session-provider'
import type { WorkspaceRead, WorkspaceRole } from '@/types/api'

const STORAGE_KEY = 'agentops.active-workspace'

export type WorkspacePermission =
  | 'agent.write'
  | 'agent.publish'
  | 'provider.write'
  | 'tool.write'
  | 'run.execute'
  | 'run.cancel'
  | 'workspace.update'

const WRITE_ROLES: WorkspaceRole[] = ['owner', 'admin', 'developer']
const RUN_ROLES: WorkspaceRole[] = ['owner', 'admin', 'developer', 'operator', 'reviewer']

/** Mirrors the server permission matrix for rendering decisions only. */
export function roleCan(role: WorkspaceRole | null, permission: WorkspacePermission): boolean {
  if (!role) return false
  switch (permission) {
    case 'agent.write':
    case 'agent.publish':
    case 'provider.write':
    case 'tool.write':
      return WRITE_ROLES.includes(role)
    case 'run.execute':
    case 'run.cancel':
      return RUN_ROLES.includes(role)
    case 'workspace.update':
      return role === 'owner' || role === 'admin'
    default:
      return false
  }
}

interface WorkspaceContextValue {
  workspaces: WorkspaceRead[]
  activeWorkspace: WorkspaceRead | null
  activeWorkspaceId: string | null
  isLoading: boolean
  setActiveWorkspaceId: (workspaceId: string) => void
  can: (permission: WorkspacePermission) => boolean
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)

function readStoredWorkspaceId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { workspaces, isLoading } = useSession()
  const [activeWorkspaceId, setActiveId] = useState<string | null>(readStoredWorkspaceId)

  useEffect(() => {
    if (workspaces.length === 0) {
      setActiveId(null)
      return
    }
    setActiveId((current) => {
      if (current && workspaces.some((workspace) => workspace.id === current)) {
        return current
      }
      return workspaces[0]?.id ?? null
    })
  }, [workspaces])

  const setActiveWorkspaceId = useCallback((workspaceId: string) => {
    setActiveId(workspaceId)
    try {
      window.localStorage.setItem(STORAGE_KEY, workspaceId)
    } catch {
      // Storage can be unavailable (private mode); selection still works in memory.
    }
  }, [])

  const value = useMemo<WorkspaceContextValue>(() => {
    const activeWorkspace =
      workspaces.find((workspace) => workspace.id === activeWorkspaceId) ?? null
    return {
      workspaces,
      activeWorkspace,
      activeWorkspaceId: activeWorkspace?.id ?? null,
      isLoading,
      setActiveWorkspaceId,
      can: (permission) => roleCan(activeWorkspace?.role ?? null, permission),
    }
  }, [workspaces, activeWorkspaceId, isLoading, setActiveWorkspaceId])

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext)
  if (!context) {
    throw new Error('useWorkspace must be used inside <WorkspaceProvider>.')
  }
  return context
}
