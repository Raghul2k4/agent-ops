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

export interface Page<T> {
  items: T[]
  total: number
  has_more: boolean
}

/* ------------------------------------------------------------------------- */
/* Models and providers                                                      */
/* ------------------------------------------------------------------------- */

export type ProviderType = 'ollama' | 'openai_compatible' | 'anthropic' | 'simulation'

export interface ModelCapabilities {
  /** `null` means unknown - the capability was never confirmed. */
  supports_tools: boolean | null
  supports_structured_output: boolean | null
  supports_streaming: boolean | null
  context_window: number | null
}

export interface ModelPricing {
  input_per_million: number | null
  output_per_million: number | null
}

export interface ModelConfigRead {
  id: string
  workspace_id: string
  provider_id: string
  provider_type: string
  provider_display_name: string
  model_name: string
  display_name: string | null
  capabilities: Partial<ModelCapabilities>
  default_parameters: Record<string, unknown>
  pricing: Partial<ModelPricing>
  enabled: boolean
  is_default: boolean
  created_at: string
  updated_at: string
}

export interface ProviderRead {
  id: string
  workspace_id: string
  provider_type: ProviderType | string
  display_name: string
  base_url: string | null
  /** Environment-variable name only. The credential value is never returned. */
  secret_reference: string | null
  has_secret_reference: boolean
  configuration: Record<string, unknown>
  status: string
  last_health_check_at: string | null
  last_health_error: string | null
  created_at: string
  updated_at: string
}

export interface ProviderWithModels extends ProviderRead {
  models: ModelConfigRead[]
}

export interface ProviderTestResult {
  ok: boolean
  status: string
  message: string | null
  models: string[]
  checked_at: string
}

/* ------------------------------------------------------------------------- */
/* Tools                                                                     */
/* ------------------------------------------------------------------------- */

export interface ToolDefinitionRead {
  id: string
  workspace_id: string | null
  name: string
  version: number
  description: string
  input_schema: Record<string, unknown>
  output_schema: Record<string, unknown>
  risk_level: string
  required_permissions: string[]
  requires_approval: boolean
  timeout_seconds: number
  max_retries: number
  idempotent: boolean
  enabled: boolean
  is_builtin: boolean
}

/* ------------------------------------------------------------------------- */
/* Agents                                                                    */
/* ------------------------------------------------------------------------- */

export interface ModelParameters {
  temperature: number
  top_p: number | null
  max_output_tokens: number
  timeout_seconds: number
}

export interface ExecutionLimits {
  max_steps: number
  max_tool_calls: number
  max_wall_clock_seconds: number
  max_total_tokens: number
  max_cost_usd: number
}

export interface AgentConfiguration {
  provider_id: string
  model_config_id: string
  model_name: string
  system_prompt: string
  parameters: ModelParameters
  limits: ExecutionLimits
  tool_ids: string[]
  input_schema: Record<string, unknown> | null
  output_schema: Record<string, unknown> | null
  streaming: boolean
}

export interface AgentRead {
  id: string
  workspace_id: string
  name: string
  description: string
  status: string
  draft_configuration: AgentConfiguration
  current_published_version_id: string | null
  current_version_number: number | null
  created_by: string | null
  created_at: string
  updated_at: string
}

export interface AgentVersionRead {
  id: string
  workspace_id: string
  agent_id: string
  version_number: number
  configuration: AgentConfiguration
  configuration_hash: string
  change_summary: string
  created_by: string | null
  created_at: string
}

export interface AgentTemplateRead {
  key: string
  name: string
  description: string
  category: string
  system_prompt: string
  tool_names: string[]
  parameters: ModelParameters
}

/* ------------------------------------------------------------------------- */
/* Runs and traces                                                           */
/* ------------------------------------------------------------------------- */

export type RunStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
  | 'awaiting_approval'

export interface RunRead {
  id: string
  workspace_id: string
  agent_id: string
  agent_name: string | null
  agent_version_id: string
  version_number: number | null
  initiated_by: string | null
  status: RunStatus | string
  input: Record<string, unknown>
  output: Record<string, unknown> | null
  model_config_id: string | null
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  token_usage: {
    input_tokens?: number
    output_tokens?: number
    total_tokens?: number
    model_calls?: number
    tool_calls?: number
    [key: string]: unknown
  }
  estimated_cost: number | null
  error_code: string | null
  error_summary: string | null
  replay_of_run_id: string | null
  /** The approval request this run is waiting for, when it is paused. */
  pending_approval_id: string | null
  /** True when the run is a safe replay of an earlier run. */
  replay_mode: boolean
  created_at: string
}

export interface RunEventRead {
  id: string
  sequence_number: number
  event_type: string
  event_status: string
  payload: Record<string, unknown>
  occurred_at: string
}

export interface RunEventList {
  items: RunEventRead[]
  last_sequence: number
  run_status: string
  has_more: boolean
}

export interface TraceSpanRead {
  id: string
  parent_span_id: string | null
  span_type: string
  name: string
  status: string
  started_at: string
  ended_at: string | null
  duration_ms: number | null
  attributes: Record<string, unknown>
}

export interface TraceView {
  run_id: string
  spans: TraceSpanRead[]
}

/* ------------------------------------------------------------------------- */
/* Workspace policy and approvals                                             */
/* ------------------------------------------------------------------------- */

export type ApprovalStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'changes_requested'
  | 'expired'
  | 'executed'
  | 'revoked'

export type ApprovalDecision = 'approve' | 'reject' | 'request_changes'

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface PolicyRead {
  workspace_id: string
  version: number
  tool_allowlist: string[]
  blocked_tools: string[]
  disabled_agent_ids: string[]
  require_approval_for_risk_levels: RiskLevel[]
  tool_rate_limits: Record<string, number>
  max_tool_calls_per_run: number | null
  max_runs_per_hour: number | null
  approval_ttl_minutes: number
  execution_paused: boolean
  paused_reason: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export interface ApprovalRead {
  id: string
  workspace_id: string
  run_id: string
  agent_version_id: string | null
  tool_definition_id: string | null
  tool_name: string
  risk_level: RiskLevel | string
  /** SHA-256 of the canonical payload. A decision must quote this exact hash. */
  canonical_arguments_hash: string
  arguments: Record<string, unknown>
  requested_by: string | null
  status: ApprovalStatus | string
  decision: string | null
  decided_by: string | null
  decided_at: string | null
  review_note: string | null
  policy_version: number
  expires_at: string
  created_at: string
  is_expired: boolean
}

export interface ApprovalDecisionResponse {
  approval: ApprovalRead
  run_status: string
  run_id: string
  message: string
}

/* ------------------------------------------------------------------------- */
/* Synthetic demonstration data                                              */
/* ------------------------------------------------------------------------- */

export interface DemoDatasetRead {
  seeded: boolean
  customers: number
  deals: number
}

export interface DemoSeedResponse extends DemoDatasetRead {
  created: boolean
  companies: number
  contacts: number
}
