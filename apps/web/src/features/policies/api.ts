import { api } from '@/lib/api-client'
import type { PolicyRead, RiskLevel } from '@/types/api'

export interface PolicyUpdatePayload {
  tool_allowlist?: string[]
  blocked_tools?: string[]
  disabled_agent_ids?: string[]
  require_approval_for_risk_levels?: RiskLevel[]
  tool_rate_limits?: Record<string, number>
  max_tool_calls_per_run?: number | null
  max_runs_per_hour?: number | null
  approval_ttl_minutes?: number
  execution_paused?: boolean
  paused_reason?: string | null
  change_note?: string | null
}

export const policiesApi = {
  read: (workspaceId: string) =>
    api.get<PolicyRead>(`/policies?workspace_id=${encodeURIComponent(workspaceId)}`),

  update: (workspaceId: string, payload: PolicyUpdatePayload) =>
    api.patch<PolicyRead>(
      `/policies?workspace_id=${encodeURIComponent(workspaceId)}`,
      payload,
    ),
}
