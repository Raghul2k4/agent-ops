import { api } from '@/lib/api-client'
import { queryString } from '@/lib/utils'
import type { Page, RunEventList, RunRead, TraceView } from '@/types/api'

export const runsApi = {
  list: (params: {
    workspaceId: string
    status?: string
    agentId?: string
    limit?: number
    offset?: number
  }) =>
    api.get<Page<RunRead>>(
      `/runs${queryString({
        workspace_id: params.workspaceId,
        status: params.status,
        agent_id: params.agentId,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  get: (runId: string) => api.get<RunRead>(`/runs/${runId}`),

  events: (runId: string, afterSeq = 0) =>
    api.get<RunEventList>(`/runs/${runId}/events?after_seq=${afterSeq}`),

  trace: (runId: string) => api.get<TraceView>(`/runs/${runId}/trace`),

  cancel: (runId: string) => api.post<RunRead>(`/runs/${runId}/cancel`, {}),
}
