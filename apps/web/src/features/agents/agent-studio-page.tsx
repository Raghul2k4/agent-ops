import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Archive,
  Beaker,
  CheckCircle2,
  Copy,
  FlaskConical,
  History,
  RotateCcw,
  Save,
  Send,
  Wrench,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Segmented } from '@/components/ui/segmented'
import { Select } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ErrorState, LoadingState } from '@/components/ui/states'
import { Notice, RiskBadge } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { agentsApi } from '@/features/agents/api'
import { providersApi } from '@/features/models/api'
import { toolsApi } from '@/features/tools/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, humanize } from '@/lib/utils'
import type { AgentConfiguration, AgentRead, ToolDefinitionRead } from '@/types/api'

type StudioTab = 'configuration' | 'tools' | 'versions'

export function AgentStudioPage() {
  const { agentId = '' } = useParams()
  const { activeWorkspace, can } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<StudioTab>('configuration')
  const [draft, setDraft] = useState<AgentConfiguration | null>(null)
  const [baseline, setBaseline] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pendingRollback, setPendingRollback] = useState<string | null>(null)
  const [showDuplicate, setShowDuplicate] = useState(false)
  const [duplicateName, setDuplicateName] = useState('')
  const [confirmArchive, setConfirmArchive] = useState(false)

  const agentQuery = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => agentsApi.get(agentId),
    enabled: Boolean(agentId),
    retry: false,
  })

  const versionsQuery = useQuery({
    queryKey: ['agent-versions', agentId],
    queryFn: () => agentsApi.versions(agentId),
    enabled: Boolean(agentId),
    retry: false,
  })

  const toolsQuery = useQuery({
    queryKey: ['tools', activeWorkspace?.id],
    queryFn: () => toolsApi.list(activeWorkspace?.id ?? ''),
    enabled: Boolean(activeWorkspace?.id),
    retry: false,
  })

  const providersQuery = useQuery({
    queryKey: ['providers', activeWorkspace?.id],
    queryFn: () => providersApi.list(activeWorkspace?.id ?? ''),
    enabled: Boolean(activeWorkspace?.id),
    retry: false,
  })

  const agent = agentQuery.data

  useEffect(() => {
    if (!agent) return
    setDraft(agent.draft_configuration)
    setBaseline(JSON.stringify(agent.draft_configuration))
    setName(agent.name)
    setDescription(agent.description)
  }, [agent])

  const models = useMemo(() => {
    const options = (providersQuery.data ?? []).flatMap((provider) =>
      provider.models
        .filter((model) => model.enabled)
        .map((model) => ({
          value: `${provider.id}:${model.id}`,
          label: `${provider.display_name} · ${model.display_name ?? model.model_name}`,
          providerId: provider.id,
          modelId: model.id,
          modelName: model.model_name,
          providerType: provider.provider_type,
        })),
    )
    if (draft) {
      const current = `${draft.provider_id}:${draft.model_config_id}`
      if (!options.some((option) => option.value === current)) {
        options.unshift({
          value: current,
          label: `${draft.model_name} (current)`,
          providerId: draft.provider_id,
          modelId: draft.model_config_id,
          modelName: draft.model_name,
          providerType: 'unknown',
        })
      }
    }
    return options
  }, [providersQuery.data, draft])

  const save = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error('The draft is not loaded yet.')
      return agentsApi.update(agentId, {
        name: name.trim(),
        description,
        draft_configuration: draft,
        change_note: changeSummary.trim() || undefined,
      })
    },
    onSuccess: async (updated: AgentRead) => {
      setError(null)
      setDraft(updated.draft_configuration)
      setBaseline(JSON.stringify(updated.draft_configuration))
      setName(updated.name)
      setDescription(updated.description)
      await queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      await queryClient.invalidateQueries({ queryKey: ['agents', updated.workspace_id] })
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The draft could not be saved.',
      )
    },
  })

  const publish = useMutation({
    mutationFn: () => agentsApi.publish(agentId, changeSummary.trim() || 'Published from Agent Studio'),
    onSuccess: async () => {
      setError(null)
      setChangeSummary('')
      await queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      await queryClient.invalidateQueries({ queryKey: ['agent-versions', agentId] })
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The agent could not be published.',
      )
    },
  })

  const rollback = useMutation({
    mutationFn: (versionId: string) => agentsApi.rollback(agentId, versionId),
    onSuccess: async () => {
      setPendingRollback(null)
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      await queryClient.invalidateQueries({ queryKey: ['agent-versions', agentId] })
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The rollback could not be completed.',
      )
    },
  })

  const duplicate = useMutation({
    mutationFn: () => agentsApi.duplicate(agentId, duplicateName.trim()),
    onSuccess: async (copy) => {
      await queryClient.invalidateQueries({ queryKey: ['agents', copy.workspace_id] })
      navigate(`/agents/${copy.id}`)
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The agent could not be duplicated.',
      )
    },
  })

  const archive = useMutation({
    mutationFn: () => agentsApi.archive(agentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['agents'] })
      navigate('/agents')
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The agent could not be archived.',
      )
    },
  })

  if (!activeWorkspace) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <ErrorState title="No active workspace" message="Select a workspace to open Agent Studio." />
      </div>
    )
  }

  if (agentQuery.isLoading) return <LoadingState label="Loading agent…" />
  if (agentQuery.isError || !agent || !draft) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <ErrorState
          title="Agent not available"
          message={
            agentQuery.error instanceof ApiError
              ? agentQuery.error.message
              : 'This agent could not be loaded in your workspace.'
          }
          onRetry={() => void agentQuery.refetch()}
        />
        <div className="mt-4 text-center">
          <Button asChild variant="ghost" size="sm">
            <Link to="/agents">Back to agents</Link>
          </Button>
        </div>
      </div>
    )
  }

  const canWrite = can('agent.write')
  const canPublish = can('agent.publish')
  const dirty =
    JSON.stringify(draft) !== baseline ||
    name !== agent.name ||
    description !== agent.description
  const tools = toolsQuery.data ?? []
  const versions = versionsQuery.data ?? []
  const isSimulation = draft.model_name.toLowerCase().includes('simulation')

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/agents">
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            Agents
          </Link>
        </Button>
      </div>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            {agent.name}
            <Badge tone={agent.status === 'active' ? 'success' : 'neutral'}>{agent.status}</Badge>
            {agent.current_version_number ? (
              <Badge tone="primary">published v{agent.current_version_number}</Badge>
            ) : (
              <Badge tone="warning">never published</Badge>
            )}
            {dirty ? <Badge tone="warning">unsaved changes</Badge> : null}
          </span>
        }
        description={agent.description || 'No description'}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              loading={save.isPending}
              disabled={!canWrite || !dirty || save.isPending}
              onClick={() => save.mutate()}
            >
              <Save className="size-3.5" aria-hidden="true" />
              Save draft
            </Button>
            <Button
              size="sm"
              loading={publish.isPending}
              disabled={!canPublish || dirty || publish.isPending}
              title={dirty ? 'Save the draft before publishing.' : undefined}
              onClick={() => publish.mutate()}
            >
              <Send className="size-3.5" aria-hidden="true" />
              Publish version
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link to={`/agents/${agent.id}/playground`}>
                <FlaskConical className="size-3.5" aria-hidden="true" />
                Playground
              </Link>
            </Button>
          </div>
        }
      />

      {error ? (
        <Notice tone="danger" title="Request failed" className="mb-4">
          {error}
        </Notice>
      ) : null}
      {!canWrite ? (
        <Notice tone="warning" title="Read-only access" className="mb-4">
          Your role can inspect this agent and its traces but cannot edit or publish it.
        </Notice>
      ) : null}
      {isSimulation ? (
        <Notice tone="warning" title="Simulation model selected" className="mb-4">
          This agent uses the deterministic simulation adapter. Its responses are rule-based script
          output, prefixed with <code className="font-mono">[SIMULATED]</code> - not an LLM
          generation. Use it to exercise the runtime offline; connect a real provider for actual
          model output.
        </Notice>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <Segmented
          label="Agent Studio sections"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'configuration', label: 'Configuration' },
            { value: 'tools', label: 'Tools', count: draft.tool_ids.length },
            { value: 'versions', label: 'Versions', count: versions.length },
          ]}
        />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowDuplicate((value) => !value)}>
            <Copy className="size-3.5" aria-hidden="true" />
            Duplicate
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setConfirmArchive(true)}
            disabled={!canWrite}
          >
            <Archive className="size-3.5" aria-hidden="true" />
            Archive
          </Button>
        </div>
      </div>

      {showDuplicate ? (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap items-end gap-3">
            <div className="min-w-56 flex-1 space-y-1.5">
              <Label htmlFor="duplicate-name" required>
                Name for the copy
              </Label>
              <Input
                id="duplicate-name"
                value={duplicateName}
                onChange={(event) => setDuplicateName(event.target.value)}
                placeholder={`${agent.name} copy`}
                maxLength={120}
              />
            </div>
            <Button
              size="sm"
              loading={duplicate.isPending}
              disabled={!canWrite || !duplicateName.trim() || duplicate.isPending}
              onClick={() => duplicate.mutate()}
            >
              Create copy
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowDuplicate(false)}>
              Cancel
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {confirmArchive ? (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">Archive this agent?</p>
              <p className="text-xs text-[var(--muted-foreground)]">
                Archived agents disappear from the list. Historical runs keep referencing their
                immutable versions.
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="danger"
                loading={archive.isPending}
                disabled={!canWrite || archive.isPending}
                onClick={() => archive.mutate()}
              >
                Confirm archive
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirmArchive(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {tab === 'configuration' ? (
        <ConfigurationTab
          agent={agent}
          draft={draft}
          models={models}
          name={name}
          description={description}
          changeSummary={changeSummary}
          canWrite={canWrite}
          onName={setName}
          onDescription={setDescription}
          onChangeSummary={setChangeSummary}
          onChange={(next) => setDraft(next)}
        />
      ) : tab === 'tools' ? (
        <ToolsTab
          tools={tools}
          draft={draft}
          loading={toolsQuery.isLoading}
          canWrite={canWrite}
          onChange={(next) => setDraft(next)}
        />
      ) : (
        <VersionsTab
          versions={versions}
          currentVersionId={agent.current_published_version_id}
          loading={versionsQuery.isLoading}
          canPublish={canPublish}
          pendingRollback={pendingRollback}
          rollbackPending={rollback.isPending}
          onAskRollback={setPendingRollback}
          onConfirmRollback={(versionId) => rollback.mutate(versionId)}
        />
      )}
    </div>
  )
}

function ConfigurationTab({
  agent,
  draft,
  models,
  name,
  description,
  changeSummary,
  canWrite,
  onName,
  onDescription,
  onChangeSummary,
  onChange,
}: {
  agent: AgentRead
  draft: AgentConfiguration
  models: { value: string; label: string; providerId: string; modelId: string; modelName: string }[]
  name: string
  description: string
  changeSummary: string
  canWrite: boolean
  onName: (value: string) => void
  onDescription: (value: string) => void
  onChangeSummary: (value: string) => void
  onChange: (next: AgentConfiguration) => void
}) {
  function patch(partial: Partial<AgentConfiguration>) {
    onChange({ ...draft, ...partial })
  }

  const selectedModel =
    models.find((model) => model.value === `${draft.provider_id}:${draft.model_config_id}`)?.value ??
    ''

  return (
    <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
      <div className="space-y-4">
        <Card>
          <CardHeader title="Identity" description="Metadata is editable without publishing." />
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="studio-name" required>
                Name
              </Label>
              <Input
                id="studio-name"
                value={name}
                onChange={(event) => onName(event.target.value)}
                disabled={!canWrite}
                maxLength={120}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="studio-description">Description</Label>
              <Input
                id="studio-description"
                value={description}
                onChange={(event) => onDescription(event.target.value)}
                disabled={!canWrite}
                maxLength={2000}
              />
            </div>
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="studio-model">Provider and model</Label>
              <Select
                id="studio-model"
                value={selectedModel}
                disabled={!canWrite}
                onChange={(event) => {
                  const model = models.find((item) => item.value === event.target.value)
                  if (!model) return
                  patch({
                    provider_id: model.providerId,
                    model_config_id: model.modelId,
                    model_name: model.modelName,
                  })
                }}
              >
                {models.map((model) => (
                  <option key={model.value} value={model.value}>
                    {model.label}
                  </option>
                ))}
              </Select>
              <FieldHint>
                The model name is snapshotted into the version so historical runs stay
                interpretable.
              </FieldHint>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="System instructions"
            description="Trusted configuration. Retrieved content and tool results are never treated as instructions."
          />
          <CardContent>
            <Label htmlFor="studio-prompt" className="mb-1.5 block" required>
              System prompt
            </Label>
            <Textarea
              id="studio-prompt"
              value={draft.system_prompt}
              onChange={(event) => patch({ system_prompt: event.target.value })}
              disabled={!canWrite}
              rows={14}
              className="min-h-56"
            />
            <p className="mt-1 text-right text-[11px] text-[var(--muted-foreground)]">
              {draft.system_prompt.length} / 32000 characters
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="Change note" description="Stored with the next publish or draft save." />
          <CardContent>
            <Input
              value={changeSummary}
              onChange={(event) => onChangeSummary(event.target.value)}
              placeholder="What changed and why?"
              maxLength={500}
              disabled={!canWrite}
            />
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader title="Sampling parameters" description="Validated by the backend per provider." />
          <CardContent className="grid grid-cols-2 gap-3">
            <NumberField
              id="temperature"
              label="Temperature"
              value={draft.parameters.temperature}
              min={0}
              max={2}
              step={0.1}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ parameters: { ...draft.parameters, temperature: value } })
              }
            />
            <div className="space-y-1.5">
              <Label htmlFor="top-p">Top-p</Label>
              <Input
                id="top-p"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={draft.parameters.top_p ?? ''}
                disabled={!canWrite}
                onChange={(event) =>
                  patch({
                    parameters: {
                      ...draft.parameters,
                      top_p: event.target.value === '' ? null : Number(event.target.value),
                    },
                  })
                }
              />
              <FieldHint>Empty = provider default.</FieldHint>
            </div>
            <NumberField
              id="max-output"
              label="Max output tokens"
              value={draft.parameters.max_output_tokens}
              min={1}
              max={32000}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ parameters: { ...draft.parameters, max_output_tokens: value } })
              }
            />
            <NumberField
              id="timeout"
              label="Model timeout (s)"
              value={draft.parameters.timeout_seconds}
              min={5}
              max={300}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ parameters: { ...draft.parameters, timeout_seconds: value } })
              }
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Execution budgets"
            description="Enforced by the runtime, never by the model."
          />
          <CardContent className="grid grid-cols-2 gap-3">
            <NumberField
              id="max-steps"
              label="Max steps"
              value={draft.limits.max_steps}
              min={1}
              max={24}
              disabled={!canWrite}
              onChange={(value) => patch({ limits: { ...draft.limits, max_steps: value } })}
            />
            <NumberField
              id="max-tools"
              label="Max tool calls"
              value={draft.limits.max_tool_calls}
              min={0}
              max={50}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ limits: { ...draft.limits, max_tool_calls: value } })
              }
            />
            <NumberField
              id="max-wall"
              label="Max duration (s)"
              value={draft.limits.max_wall_clock_seconds}
              min={10}
              max={900}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ limits: { ...draft.limits, max_wall_clock_seconds: value } })
              }
            />
            <NumberField
              id="max-tokens"
              label="Max total tokens"
              value={draft.limits.max_total_tokens}
              min={100}
              max={200000}
              disabled={!canWrite}
              onChange={(value) =>
                patch({ limits: { ...draft.limits, max_total_tokens: value } })
              }
            />
            <NumberField
              id="max-cost"
              label="Max cost (USD)"
              value={draft.limits.max_cost_usd}
              min={0}
              max={100}
              step={0.1}
              disabled={!canWrite}
              onChange={(value) => patch({ limits: { ...draft.limits, max_cost_usd: value } })}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="Published version" />
          <CardContent className="space-y-2 text-xs text-[var(--muted-foreground)]">
            <p>
              Current:{' '}
              {agent.current_version_number
                ? `v${agent.current_version_number}`
                : 'nothing published yet'}
            </p>
            <p>
              Agent ID: <code className="font-mono text-[11px]">{agent.id}</code>
            </p>
            <p>Updated {formatDateTime(agent.updated_at)}</p>
            <FieldHint>
              Publishing creates an immutable snapshot. Historical versions are never modified.
            </FieldHint>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function NumberField({
  id,
  label,
  value,
  min,
  max,
  step = 1,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: number
  min: number
  max: number
  step?: number
  disabled: boolean
  onChange: (value: number) => void
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : ''}
        disabled={disabled}
        onChange={(event) => {
          const parsed = Number(event.target.value)
          onChange(Number.isFinite(parsed) ? parsed : min)
        }}
      />
    </div>
  )
}

function ToolsTab({
  tools,
  draft,
  loading,
  canWrite,
  onChange,
}: {
  tools: ToolDefinitionRead[]
  draft: AgentConfiguration
  loading: boolean
  canWrite: boolean
  onChange: (next: AgentConfiguration) => void
}) {
  function toggle(toolId: string) {
    const selected = draft.tool_ids.includes(toolId)
    onChange({
      ...draft,
      tool_ids: selected
        ? draft.tool_ids.filter((id) => id !== toolId)
        : [...draft.tool_ids, toolId],
    })
  }

  if (loading) return <LoadingState label="Loading the tool registry…" />

  return (
    <div className="space-y-3">
      <Notice tone="info" title="Tools execute on the server">
        Models may propose a tool name and arguments, but the executor resolves the tool from the
        server-side registry, validates arguments with a strict schema, checks permissions and
        enforces approval requirements. A selected tool can never bypass those checks.
      </Notice>
      <div className="grid gap-3 md:grid-cols-2">
        {tools.map((tool) => {
          const checked = draft.tool_ids.includes(tool.id)
          return (
            <Card key={tool.id} className={checked ? 'border-[var(--primary)]/40' : undefined}>
              <CardContent className="space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <label className="flex cursor-pointer items-start gap-2.5">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={!canWrite}
                      onChange={() => toggle(tool.id)}
                      className="mt-0.5 size-3.5 accent-[var(--primary)]"
                    />
                    <span>
                      <span className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                        <Wrench className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
                        {tool.name}
                        {checked ? (
                          <CheckCircle2 className="size-3.5 text-[var(--success)]" aria-label="selected" />
                        ) : null}
                      </span>
                      <span className="mt-1 block text-xs text-[var(--muted-foreground)]">
                        {tool.description}
                      </span>
                    </span>
                  </label>
                  <RiskBadge level={tool.risk_level} />
                </div>
                <div className="flex flex-wrap gap-1.5">
                  <Badge tone="neutral">v{tool.version}</Badge>
                  <Badge tone="neutral">{tool.timeout_seconds}s timeout</Badge>
                  <Badge tone={tool.idempotent ? 'success' : 'warning'}>
                    {tool.idempotent ? 'idempotent' : 'not idempotent'}
                  </Badge>
                  {tool.requires_approval ? (
                    <Badge tone="warning">requires approval</Badge>
                  ) : (
                    <Badge tone="success">no approval</Badge>
                  )}
                </div>
                <p className="text-[11px] text-[var(--muted-foreground)]">
                  Requires: {tool.required_permissions.join(', ') || 'none'}
                </p>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}

function VersionsTab({
  versions,
  currentVersionId,
  loading,
  canPublish,
  pendingRollback,
  rollbackPending,
  onAskRollback,
  onConfirmRollback,
}: {
  versions: Awaited<ReturnType<typeof agentsApi.versions>>
  currentVersionId: string | null
  loading: boolean
  canPublish: boolean
  pendingRollback: string | null
  rollbackPending: boolean
  onAskRollback: (versionId: string | null) => void
  onConfirmRollback: (versionId: string) => void
}) {
  if (loading) return <LoadingState label="Loading versions…" />
  if (versions.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-[var(--muted-foreground)]">
          No published versions. Save the draft and publish a version before running the agent.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {versions.map((version) => {
        const current = version.id === currentVersionId
        return (
          <Card key={version.id} className={current ? 'border-[var(--primary)]/40' : undefined}>
            <CardHeader
              title={
                <span className="flex flex-wrap items-center gap-2">
                  <History className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
                  Version {version.version_number}
                  {current ? <Badge tone="primary">currently published</Badge> : null}
                </span>
              }
              description={version.change_summary || 'No change summary recorded'}
              actions={
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{formatDateTime(version.created_at)}</Badge>
                  {!current ? (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={!canPublish}
                      onClick={() => onAskRollback(version.id)}
                    >
                      <RotateCcw className="size-3.5" aria-hidden="true" />
                      Roll back
                    </Button>
                  ) : null}
                </div>
              }
            />
            <CardContent className="space-y-3">
              <dl className="grid gap-2 text-xs sm:grid-cols-3">
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                    Model
                  </dt>
                  <dd className="truncate font-mono text-[11px]">
                    {version.configuration.model_name}
                  </dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                    Tools
                  </dt>
                  <dd>{version.configuration.tool_ids.length}</dd>
                </div>
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                    Configuration hash
                  </dt>
                  <dd className="truncate font-mono text-[11px]" title={version.configuration_hash}>
                    {version.configuration_hash.slice(0, 16)}…
                  </dd>
                </div>
              </dl>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">
                  steps ≤ {version.configuration.limits.max_steps}
                </Badge>
                <Badge tone="neutral">
                  tokens ≤ {version.configuration.limits.max_total_tokens.toLocaleString()}
                </Badge>
                <Badge tone="neutral">
                  {humanize(version.configuration.model_name)}
                </Badge>
                <Button asChild size="sm" variant="ghost">
                  <Link to={`/agents/${version.agent_id}/playground?version=${version.id}`}>
                    <Beaker className="size-3.5" aria-hidden="true" />
                    Run this version
                  </Link>
                </Button>
              </div>

              {pendingRollback === version.id ? (
                <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-[var(--warning)]/30 bg-[var(--warning-muted)] px-3 py-2">
                  <p className="text-xs">
                    Roll the published pointer back to version {version.version_number}? New runs
                    will use this snapshot.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={rollbackPending}
                      disabled={rollbackPending}
                      onClick={() => onConfirmRollback(version.id)}
                    >
                      Confirm rollback
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => onAskRollback(null)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
