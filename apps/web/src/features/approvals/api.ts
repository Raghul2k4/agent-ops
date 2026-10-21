import { api } from '@/lib/api-client'
import { queryString } from '@/lib/utils'
import type {
  ApprovalDecision,
  ApprovalDecisionResponse,
  ApprovalRead,
  Page,
} from '@/types/api'

export const approvalsApi = {
  list: (params: {
    workspaceId: string
    status?: string
    runId?: string
    toolName?: string
    limit?: number
    offset?: number
  }) =>
    api.get<Page<ApprovalRead>>(
      `/approvals${queryString({
        workspace_id: params.workspaceId,
        status: params.status,
        run_id: params.runId,
        tool_name: params.toolName,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  get: (approvalId: string) => api.get<ApprovalRead>(`/approvals/${approvalId}`),

  /**
   * Record a decision. The hash is the one the reviewer was shown: the server
   * refuses the decision when the payload changed in the meantime.
   */
  decide: (
    approvalId: string,
    payload: { decision: ApprovalDecision; arguments_hash: string; note?: string | null },
  ) => api.post<ApprovalDecisionResponse>(`/approvals/${approvalId}/decision`, payload),

  revoke: (approvalId: string) => api.post<ApprovalRead>(`/approvals/${approvalId}/revoke`, {}),
}
