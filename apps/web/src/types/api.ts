/** Shared API types mirroring the backend Pydantic schemas. */

export type WorkspaceRole = 'owner' | 'admin' | 'developer' | 'operator' | 'reviewer' | 'viewer'

export interface UserRead {
  id: string
  email: string
  display_name: string
  status: string
  created_at: string
}

export interface WorkspaceRead {
  id: string
  name: string
  slug: string
  owner_id: string
  role: WorkspaceRole | null
  member_count: number | null
  settings: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface MemberRead {
  id: string
  user_id: string
  email: string
  display_name: string
  role: WorkspaceRole
  status: string
  created_at: string
}

export interface AuthResponse {
  user: UserRead
  workspaces: WorkspaceRead[]
  expires_at: string
}

export interface MeResponse {
  user: UserRead
  workspaces: WorkspaceRead[]
}

export interface HealthStatus {
  status: string
  app: string
  version: string
  environment: string
}

export interface ReadinessStatus {
  status: string
  checks: Record<string, string>
}
