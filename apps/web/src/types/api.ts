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

/**
 * Response of the development auth endpoints (`AUTH_MODE=local`).
 *
 * In Supabase mode the browser obtains the token from the Supabase SDK instead;
 * this shape is not used there.
 */
export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: UserRead
  workspaces: WorkspaceRead[]
}

/** Public description of how this deployment authenticates browsers. */
export interface AuthModeInfo {
  auth_mode: 'supabase' | 'local'
  local_sign_in_enabled: boolean
  supabase_url: string | null
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
