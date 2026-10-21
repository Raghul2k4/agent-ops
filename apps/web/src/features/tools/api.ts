import { api } from '@/lib/api-client'
import type { DemoDatasetRead, DemoSeedResponse, ToolDefinitionRead } from '@/types/api'

export const toolsApi = {
  list: (workspaceId: string) =>
    api.get<ToolDefinitionRead[]>(`/tools?workspace_id=${encodeURIComponent(workspaceId)}`),
}

export const demoDataApi = {
  status: (workspaceId: string) =>
    api.get<DemoDatasetRead>(`/workspaces/${workspaceId}/demo-data`),

  seed: (workspaceId: string) =>
    api.post<DemoSeedResponse>(`/workspaces/${workspaceId}/demo-data`, {}),
}
