import { api } from '@/lib/api-client'
import type {
  ModelConfigRead,
  ProviderTestResult,
  ProviderType,
  ProviderWithModels,
} from '@/types/api'

export interface ProviderCreatePayload {
  provider_type: ProviderType
  display_name: string
  base_url?: string | null
  secret_reference?: string | null
  configuration?: Record<string, unknown>
}

export interface ModelCreatePayload {
  model_name: string
  display_name?: string | null
  capabilities?: Record<string, unknown>
  pricing?: Record<string, unknown> | null
  enabled?: boolean
  is_default?: boolean
}

export interface ModelUpdatePayload {
  display_name?: string | null
  capabilities?: Record<string, unknown>
  pricing?: Record<string, unknown> | null
  enabled?: boolean
  is_default?: boolean
}

export const providersApi = {
  list: (workspaceId: string) =>
    api.get<ProviderWithModels[]>(
      `/models/providers?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),

  ensureSimulation: (workspaceId: string) =>
    api.post<ProviderWithModels>(
      `/models/providers/simulation?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),

  create: (workspaceId: string, payload: ProviderCreatePayload) =>
    api.post<ProviderWithModels>(
      `/models/providers?workspace_id=${encodeURIComponent(workspaceId)}`,
      payload,
    ),

  update: (
    providerId: string,
    workspaceId: string,
    payload: { display_name?: string; enabled?: boolean; base_url?: string | null },
  ) =>
    api.patch<ProviderWithModels>(
      `/models/providers/${providerId}?workspace_id=${encodeURIComponent(workspaceId)}`,
      payload,
    ),

  test: (providerId: string, workspaceId: string) =>
    api.post<ProviderTestResult>(
      `/models/providers/${providerId}/test?workspace_id=${encodeURIComponent(workspaceId)}`,
    ),

  createModel: (providerId: string, workspaceId: string, payload: ModelCreatePayload) =>
    api.post<ModelConfigRead>(
      `/models/providers/${providerId}/models?workspace_id=${encodeURIComponent(workspaceId)}`,
      payload,
    ),

  models: (workspaceId: string) =>
    api.get<ModelConfigRead[]>(`/models?workspace_id=${encodeURIComponent(workspaceId)}`),

  updateModel: (modelId: string, workspaceId: string, payload: ModelUpdatePayload) =>
    api.patch<ModelConfigRead>(
      `/models/${modelId}?workspace_id=${encodeURIComponent(workspaceId)}`,
      payload,
    ),
}
