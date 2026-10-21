import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Beaker, Cpu, Plus, RefreshCw, ServerCog, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { FieldError, FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { Notice, ProviderStatusBadge } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { NoWorkspaceState } from '@/features/shared/no-workspace'
import { providersApi } from '@/features/models/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, humanize } from '@/lib/utils'
import type {
  ModelConfigRead,
  ProviderTestResult,
  ProviderType,
  ProviderWithModels,
} from '@/types/api'

const PROVIDER_TYPES: { value: ProviderType; label: string; hint: string }[] = [
  {
    value: 'simulation',
    label: 'Simulation (deterministic demo)',
    hint: 'Rule-based script, never presented as model output.',
  },
  { value: 'ollama', label: 'Ollama (local)', hint: 'Local runtime at the given base URL.' },
  {
    value: 'openai_compatible',
    label: 'OpenAI-compatible API',
    hint: 'Any endpoint implementing /chat/completions.',
  },
  { value: 'anthropic', label: 'Anthropic Messages API', hint: 'Claude models.' },
]

export function ProvidersPage() {
  const { activeWorkspace, can } = useWorkspace()
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const workspaceId = activeWorkspace?.id ?? ''
  const canWrite = can('provider.write')

  const providers = useQuery({
    queryKey: ['providers', workspaceId],
    queryFn: () => providersApi.list(workspaceId),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const ensureSimulation = useMutation({
    mutationFn: () => providersApi.ensureSimulation(workspaceId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
      await queryClient.invalidateQueries({ queryKey: ['models', workspaceId] })
    },
  })

  if (!activeWorkspace) return <NoWorkspaceState module="Model providers" />

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <PageHeader
        title="Model Lab"
        description="Provider configuration and connection health. Credentials are referenced by environment-variable name and never returned by the API."
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowForm((value) => !value)}
            disabled={!canWrite}
          >
            {showForm ? <X className="size-3.5" aria-hidden="true" /> : <Plus className="size-3.5" aria-hidden="true" />}
            {showForm ? 'Close form' : 'Add provider'}
          </Button>
        }
      />

      <Notice tone="info" title="Model comparison and routing arrive in M5" className="mb-4">
        This milestone delivers provider setup, model registration, health checks and the runtime
        adapter layer. Side-by-side benchmarking is scheduled for the Model Lab milestone M5.
      </Notice>

      {!canWrite ? (
        <Notice tone="warning" title="Read-only access" className="mb-4">
          Your workspace role can inspect providers but not change them.
        </Notice>
      ) : null}

      {showForm ? (
        <ProviderForm
          workspaceId={workspaceId}
          onDone={async () => {
            setShowForm(false)
            await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
            await queryClient.invalidateQueries({ queryKey: ['models', workspaceId] })
          }}
        />
      ) : null}

      {providers.isLoading ? (
        <LoadingState label="Loading providers…" />
      ) : providers.isError ? (
        <ErrorState
          title="Providers unavailable"
          message={
            providers.error instanceof ApiError
              ? providers.error.message
              : 'The provider list could not be loaded.'
          }
          onRetry={() => void providers.refetch()}
        />
      ) : (providers.data?.length ?? 0) === 0 ? (
        <Card>
          <EmptyState
            icon={<ServerCog className="size-5" aria-hidden="true" />}
            title="No model provider configured"
            description="An agent needs a provider and a registered model before it can be published and run. You can start with the clearly labelled deterministic simulation provider."
            action={
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button
                  size="sm"
                  loading={ensureSimulation.isPending}
                  disabled={!canWrite || ensureSimulation.isPending}
                  onClick={() => ensureSimulation.mutate()}
                >
                  <Beaker className="size-3.5" aria-hidden="true" />
                  Add simulation provider
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setShowForm(true)}>
                  Configure a real provider
                </Button>
              </div>
            }
          />
          {ensureSimulation.isError ? (
            <div className="border-t border-[var(--border)] p-4">
              <Notice tone="danger" title="Could not create the provider">
                {ensureSimulation.error instanceof ApiError
                  ? ensureSimulation.error.message
                  : 'The provider was not created.'}
              </Notice>
            </div>
          ) : null}
        </Card>
      ) : (
        <div className="space-y-4">
          {providers.data?.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              workspaceId={workspaceId}
              canWrite={canWrite}
            />
          ))}
          {!providers.data?.some((provider) => provider.provider_type === 'simulation') ? (
            <Card>
              <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">Deterministic simulation provider</p>
                  <p className="text-xs text-[var(--muted-foreground)]">
                    Optional labelled demo provider. Its output is scripted, not generated by an
                    LLM, and every response is prefixed with [SIMULATED].
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={ensureSimulation.isPending}
                  disabled={!canWrite || ensureSimulation.isPending}
                  onClick={() => ensureSimulation.mutate()}
                >
                  <Beaker className="size-3.5" aria-hidden="true" />
                  Add simulation provider
                </Button>
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}

function ProviderForm({
  workspaceId,
  onDone,
}: {
  workspaceId: string
  onDone: () => Promise<void>
}) {
  const [providerType, setProviderType] = useState<ProviderType>('openai_compatible')
  const [displayName, setDisplayName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [secretReference, setSecretReference] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      providersApi.create(workspaceId, {
        provider_type: providerType,
        display_name: displayName.trim(),
        base_url: baseUrl.trim() || null,
        secret_reference: secretReference.trim() || null,
      }),
    onSuccess: async () => {
      setError(null)
      await onDone()
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The provider could not be created.',
      )
    },
  })

  const selected = PROVIDER_TYPES.find((item) => item.value === providerType)

  return (
    <Card className="mb-4">
      <CardHeader
        title="Add a provider"
        description="Only the name of the environment variable is stored. The secret value stays in the server environment."
      />
      <CardContent>
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(event) => {
            event.preventDefault()
            if (!displayName.trim()) {
              setError('A display name is required.')
              return
            }
            mutation.mutate()
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="provider-type" required>
              Provider type
            </Label>
            <Select
              id="provider-type"
              value={providerType}
              onChange={(event) => setProviderType(event.target.value as ProviderType)}
            >
              {PROVIDER_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </Select>
            <FieldHint>{selected?.hint}</FieldHint>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-name" required>
              Display name
            </Label>
            <Input
              id="provider-name"
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Production Claude"
              maxLength={120}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-url">Base URL</Label>
            <Input
              id="provider-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={
                providerType === 'ollama' ? 'http://127.0.0.1:11434' : 'https://api.example.com/v1'
              }
              disabled={providerType === 'simulation'}
            />
            <FieldHint>Leave empty to use the adapter default.</FieldHint>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-secret">Credential environment variable</Label>
            <Input
              id="provider-secret"
              value={secretReference}
              onChange={(event) => setSecretReference(event.target.value.toUpperCase())}
              placeholder="AGENTOPS_LLM_API_KEY"
              pattern="[A-Z][A-Z0-9_]{2,79}"
              disabled={providerType === 'simulation'}
            />
            <FieldHint>
              Example: <code className="font-mono">AGENTOPS_LLM_API_KEY</code>. The API never
              accepts or returns the credential itself.
            </FieldHint>
          </div>

          {error ? (
            <div className="md:col-span-2">
              <FieldError>{error}</FieldError>
            </div>
          ) : null}

          <div className="md:col-span-2 flex justify-end gap-2">
            <Button type="submit" size="sm" loading={mutation.isPending}>
              Create provider
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function ProviderCard({
  provider,
  workspaceId,
  canWrite,
}: {
  provider: ProviderWithModels
  workspaceId: string
  canWrite: boolean
}) {
  const queryClient = useQueryClient()
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null)
  const [showModelForm, setShowModelForm] = useState(false)
  const [editingModelId, setEditingModelId] = useState<string | null>(null)

  const test = useMutation({
    mutationFn: () => providersApi.test(provider.id, workspaceId),
    onSuccess: async (result) => {
      setTestResult(result)
      await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
    },
    onError: (error) => {
      setTestResult({
        ok: false,
        status: 'error',
        message:
          error instanceof ApiError ? error.message : 'The connection test could not be completed.',
        models: [],
        checked_at: new Date().toISOString(),
      })
    },
  })

  const toggle = useMutation({
    mutationFn: () =>
      providersApi.update(provider.id, workspaceId, {
        enabled: provider.status === 'disabled',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
    },
  })

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {provider.display_name}
            <Badge tone="neutral">{humanize(provider.provider_type)}</Badge>
            <ProviderStatusBadge status={provider.status} />
          </span>
        }
        description={
          provider.secret_reference
            ? `Credential: ${provider.secret_reference} (value never returned)`
            : 'No credential reference configured'
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              loading={test.isPending}
              disabled={!canWrite || test.isPending}
              onClick={() => test.mutate()}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              Test connection
            </Button>
            {provider.provider_type !== 'simulation' ? (
              <Button
                size="sm"
                variant="ghost"
                loading={toggle.isPending}
                disabled={!canWrite || toggle.isPending}
                onClick={() => toggle.mutate()}
              >
                {provider.status === 'disabled' ? 'Enable' : 'Disable'}
              </Button>
            ) : null}
          </div>
        }
      />
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
              Base URL
            </p>
            <p className="truncate font-mono text-[11px]">{provider.base_url ?? 'adapter default'}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
              Last checked
            </p>
            <p>{formatDateTime(provider.last_health_check_at)}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
              Secret reference
            </p>
            <p className="truncate font-mono text-[11px]">
              {provider.secret_reference ?? '—'}
              {provider.secret_reference ? (
                <ShieldCheck className="ml-1 inline size-3 text-[var(--success)]" aria-hidden="true" />
              ) : null}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
              Models
            </p>
            <p>{provider.models.length}</p>
          </div>
        </div>

        {provider.last_health_error ? (
          <Notice tone="danger" title="Last health check failed">
            {provider.last_health_error}
          </Notice>
        ) : null}

        {testResult ? (
          <Notice tone={testResult.ok ? 'success' : 'danger'} title={testResult.ok ? 'Connection succeeded' : 'Connection failed'}>
            {testResult.message ?? 'The adapter responded.'}
            {testResult.models.length > 0
              ? ` Discovered models: ${testResult.models.join(', ')}.`
              : ''}
          </Notice>
        ) : null}

        <div>
          <div className="mb-2 flex items-center justify-between gap-2">
            <p className="text-xs font-medium text-[var(--foreground)]">Registered models</p>
            <Button
              size="sm"
              variant="ghost"
              disabled={!canWrite}
              onClick={() => setShowModelForm((value) => !value)}
            >
              <Plus className="size-3.5" aria-hidden="true" />
              Add model
            </Button>
          </div>

          {provider.models.length === 0 ? (
            <p className="rounded-md border border-dashed border-[var(--border)] px-3 py-4 text-xs text-[var(--muted-foreground)]">
              No models registered. An agent cannot be published until a model is registered on a
              provider.
            </p>
          ) : (
            <ul className="divide-y divide-[var(--border)] rounded-md border border-[var(--border)]">
              {provider.models.map((model) => (
                <li key={model.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium">
                      {model.display_name ?? model.model_name}
                      {model.is_default ? (
                        <Badge tone="primary" className="ml-2">
                          default
                        </Badge>
                      ) : null}
                    </p>
                    <p className="truncate font-mono text-[11px] text-[var(--muted-foreground)]">
                      {model.model_name}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <CapabilityChip enabled={model.capabilities.supports_tools} label="tools" />
                    <CapabilityChip
                      enabled={model.capabilities.supports_structured_output}
                      label="structured"
                    />
                    <CapabilityChip
                      enabled={model.capabilities.supports_streaming}
                      label="streaming"
                    />
                    <Badge tone={model.pricing?.input_per_million == null ? 'neutral' : 'info'}>
                      {model.pricing?.input_per_million == null ? 'cost unavailable' : 'priced'}
                    </Badge>
                    {canWrite ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          setEditingModelId((current) => (current === model.id ? null : model.id))
                        }
                      >
                        {editingModelId === model.id ? 'Close' : 'Edit'}
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}

          {editingModelId ? (
            <ModelEditForm
              model={provider.models.find((item) => item.id === editingModelId)!}
              workspaceId={workspaceId}
              onDone={async () => {
                setEditingModelId(null)
                await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
                await queryClient.invalidateQueries({ queryKey: ['models', workspaceId] })
              }}
            />
          ) : null}

          {showModelForm ? (
            <ModelForm
              providerId={provider.id}
              workspaceId={workspaceId}
              onDone={async () => {
                setShowModelForm(false)
                await queryClient.invalidateQueries({ queryKey: ['providers', workspaceId] })
                await queryClient.invalidateQueries({ queryKey: ['models', workspaceId] })
              }}
            />
          ) : null}
        </div>
      </CardContent>
    </Card>
  )
}

function CapabilityChip({ enabled, label }: { enabled: boolean | null | undefined; label: string }) {  if (enabled === null || enabled === undefined) {
    return (
      <Badge tone="neutral">
        <Cpu className="size-2.5" aria-hidden="true" />
        {label} unknown
      </Badge>
    )
  }
  return (
    <Badge tone={enabled ? 'success' : 'neutral'}>
      <Cpu className="size-2.5" aria-hidden="true" />
      {enabled ? label : `no ${label}`}
    </Badge>
  )
}

interface CapabilityDraft {
  supports_tools: boolean | null
  supports_structured_output: boolean | null
  supports_streaming: boolean | null
  context_window: number | null
}

interface PricingDraft {
  input_per_million: number | null
  output_per_million: number | null
}

const EMPTY_CAPABILITIES: CapabilityDraft = {
  supports_tools: null,
  supports_structured_output: null,
  supports_streaming: null,
  context_window: null,
}

const EMPTY_PRICING: PricingDraft = { input_per_million: null, output_per_million: null }

const CAPABILITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'unknown', label: 'Unknown' },
  { value: 'yes', label: 'Supported' },
  { value: 'no', label: 'Not supported' },
]

function capabilityValue(value: boolean | null): string {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return 'unknown'
}

function parseCapability(value: string): boolean | null {
  if (value === 'yes') return true
  if (value === 'no') return false
  return null
}

/** Capabilities are tri-state: unknown is never silently promoted to "yes". */
function capabilitiesPayload(capabilities: CapabilityDraft) {
  return {
    supports_tools: capabilities.supports_tools,
    supports_structured_output: capabilities.supports_structured_output,
    supports_streaming: capabilities.supports_streaming,
    context_window: capabilities.context_window,
  }
}

function pricingPayload(pricing: PricingDraft) {
  return {
    input_per_million: pricing.input_per_million,
    output_per_million: pricing.output_per_million,
  }
}

function CapabilityFields({
  capabilities,
  pricing,
  onCapabilitiesChange,
  onPricingChange,
  className,
}: {
  capabilities: CapabilityDraft
  pricing: PricingDraft
  onCapabilitiesChange: (value: CapabilityDraft) => void
  onPricingChange: (value: PricingDraft) => void
  className?: string
}) {
  const capabilitySelect = (
    id: string,
    label: string,
    value: boolean | null,
    onChange: (value: boolean | null) => void,
  ) => (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select
        id={id}
        value={capabilityValue(value)}
        onChange={(event) => onChange(parseCapability(event.target.value))}
      >
        {CAPABILITY_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
    </div>
  )

  return (
    <div className={className ?? 'grid gap-3 sm:grid-cols-2'}>
      <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
        {capabilitySelect(
          'capability-tools',
          'Tool calling',
          capabilities.supports_tools,
          (value) => onCapabilitiesChange({ ...capabilities, supports_tools: value }),
        )}
        {capabilitySelect(
          'capability-structured',
          'Structured output',
          capabilities.supports_structured_output,
          (value) =>
            onCapabilitiesChange({ ...capabilities, supports_structured_output: value }),
        )}
        {capabilitySelect(
          'capability-streaming',
          'Streaming',
          capabilities.supports_streaming,
          (value) => onCapabilitiesChange({ ...capabilities, supports_streaming: value }),
        )}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="capability-context-window">Context window (tokens)</Label>
        <Input
          id="capability-context-window"
          type="number"
          min={256}
          max={10000000}
          value={capabilities.context_window ?? ''}
          onChange={(event) =>
            onCapabilitiesChange({
              ...capabilities,
              context_window: event.target.value ? Number(event.target.value) : null,
            })
          }
          placeholder="Optional"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="pricing-input">Input price per 1M tokens (USD)</Label>
        <Input
          id="pricing-input"
          type="number"
          min={0}
          step="0.01"
          value={pricing.input_per_million ?? ''}
          onChange={(event) =>
            onPricingChange({
              ...pricing,
              input_per_million: event.target.value ? Number(event.target.value) : null,
            })
          }
          placeholder="Leave empty when unknown"
        />
        <FieldHint>
          Unknown pricing is reported as unavailable, never as zero.
        </FieldHint>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="pricing-output">Output price per 1M tokens (USD)</Label>
        <Input
          id="pricing-output"
          type="number"
          min={0}
          step="0.01"
          value={pricing.output_per_million ?? ''}
          onChange={(event) =>
            onPricingChange({
              ...pricing,
              output_per_million: event.target.value ? Number(event.target.value) : null,
            })
          }
          placeholder="Leave empty when unknown"
        />
      </div>
    </div>
  )
}

function ModelForm({
  providerId,
  workspaceId,
  onDone,
}: {
  providerId: string
  workspaceId: string
  onDone: () => Promise<void>
}) {
  const [modelName, setModelName] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [capabilities, setCapabilities] = useState<CapabilityDraft>(EMPTY_CAPABILITIES)
  const [pricing, setPricing] = useState<PricingDraft>(EMPTY_PRICING)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      providersApi.createModel(providerId, workspaceId, {
        model_name: modelName.trim(),
        display_name: displayName.trim() || null,
        capabilities: capabilitiesPayload(capabilities),
        pricing: pricingPayload(pricing),
      }),
    onSuccess: async () => {
      setModelName('')
      setDisplayName('')
      setCapabilities(EMPTY_CAPABILITIES)
      setPricing(EMPTY_PRICING)
      setError(null)
      await onDone()
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The model could not be registered.',
      )
    },
  })

  return (
    <form
      className="mt-3 grid gap-3 rounded-md border border-[var(--border)] bg-[var(--surface-muted)]/40 p-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
      onSubmit={(event) => {
        event.preventDefault()
        if (!modelName.trim()) {
          setError('A model name is required.')
          return
        }
        mutation.mutate()
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={`model-name-${providerId}`} required>
          Model name
        </Label>
        <Input
          id={`model-name-${providerId}`}
          value={modelName}
          onChange={(event) => setModelName(event.target.value)}
          placeholder="gpt-4o-mini / llama3.1 / claude-sonnet-4"
          maxLength={200}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`model-display-${providerId}`}>Display name</Label>
        <Input
          id={`model-display-${providerId}`}
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          placeholder="Optional label"
          maxLength={200}
        />
      </div>
      <Button type="submit" size="sm" loading={mutation.isPending}>
        Register
      </Button>
      <CapabilityFields
        capabilities={capabilities}
        pricing={pricing}
        onCapabilitiesChange={setCapabilities}
        onPricingChange={setPricing}
        className="sm:col-span-3"
      />
      {error ? (
        <div className="sm:col-span-3">
          <FieldError>{error}</FieldError>
        </div>
      ) : null}
    </form>
  )
}

function ModelEditForm({
  model,
  workspaceId,
  onDone,
}: {
  model: ModelConfigRead
  workspaceId: string
  onDone: () => Promise<void>
}) {
  const [capabilities, setCapabilities] = useState<CapabilityDraft>({
    supports_tools: model.capabilities.supports_tools ?? null,
    supports_structured_output: model.capabilities.supports_structured_output ?? null,
    supports_streaming: model.capabilities.supports_streaming ?? null,
    context_window: model.capabilities.context_window ?? null,
  })
  const [pricing, setPricing] = useState<PricingDraft>({
    input_per_million: model.pricing?.input_per_million ?? null,
    output_per_million: model.pricing?.output_per_million ?? null,
  })
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () =>
      providersApi.updateModel(model.id, workspaceId, {
        capabilities: capabilitiesPayload(capabilities),
        pricing: pricingPayload(pricing),
      }),
    onSuccess: async () => {
      setError(null)
      await onDone()
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The model could not be updated.',
      )
    },
  })

  return (
    <form
      className="mt-3 space-y-3 rounded-md border border-[var(--border)] bg-[var(--surface-muted)]/40 p-3"
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate()
      }}
    >
      <p className="text-xs text-[var(--muted-foreground)]">
        Declare what <span className="font-mono">{model.model_name}</span> actually supports.
        Anything left unknown is reported as unknown instead of assumed.
      </p>
      <CapabilityFields
        capabilities={capabilities}
        pricing={pricing}
        onCapabilitiesChange={setCapabilities}
        onPricingChange={setPricing}
      />
      {error ? <FieldError>{error}</FieldError> : null}
      <div className="flex justify-end">
        <Button type="submit" size="sm" loading={mutation.isPending}>
          Save model metadata
        </Button>
      </div>
    </form>
  )
}
