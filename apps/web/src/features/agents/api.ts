import { api } from '@/lib/api-client'
import type {
  AgentRead,
  AgentTemplateRead,
  AgentVersionRead,
  RunRead,
} from '@/types/api'

export interface AgentCreatePayload {
  name: string
  description?: string
  template_key?: string | null
  provider_id: string
  model_config_id: string
  system_prompt?: string
  tool_names?: string[]
}

export interface AgentDraftUpdate {
  name?: string
  description?: string
  draft_configuration?: unknown
  change_note?: string
}

export const agentsApi = {
  list: (workspaceId: string) =>
    api.get<AgentRead[]>(`/agents?workspace_id=${encodeURIComponent(workspaceId)}`),

  templates: () => api.get<AgentTemplateRead[]>('/agents/templates'),

  get: (agentId: string) => api.get<AgentRead>(`/agents/${agentId}`),

  create: (workspaceId: string, payload: AgentCreatePayload) =>
    api.post<AgentRead>(`/agents?workspace_id=${encodeURIComponent(workspaceId)}`, payload),

  update: (agentId: string, payload: AgentDraftUpdate) =>
    api.patch<AgentRead>(`/agents/${agentId}`, payload),

  versions: (agentId: string) =>
    api.get<AgentVersionRead[]>(`/agents/${agentId}/versions`),

  publish: (agentId: string, changeSummary: string) =>
    api.post<AgentVersionRead>(`/agents/${agentId}/publish`, {
      change_summary: changeSummary,
    }),

  rollback: (agentId: string, versionId: string) =>
    api.post<AgentVersionRead>(`/agents/${agentId}/rollback`, { version_id: versionId }),

  duplicate: (agentId: string, name: string) =>
    api.post<AgentRead>(`/agents/${agentId}/duplicate`, { name }),

  archive: (agentId: string) => api.post<AgentRead>(`/agents/${agentId}/archive`, {}),

  run: (agentId: string, message: string, versionId?: string) =>
    api.post<RunRead>(`/agents/${agentId}/run`, {
      input: { message },
      ...(versionId ? { version_id: versionId } : {}),
    }),
}
