import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, Beaker, Bot, FlaskConical, Plus, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { FieldError, FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { Notice } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { NoWorkspaceState } from '@/features/shared/no-workspace'
import { agentsApi } from '@/features/agents/api'
import { providersApi } from '@/features/models/api'
import { DemoDataCard } from '@/features/tools/demo-data-card'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/utils'

export function AgentsPage() {
  const { activeWorkspace, can } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const workspaceId = activeWorkspace?.id ?? ''
  const canWrite = can('agent.write')

  const agents = useQuery({
    queryKey: ['agents', workspaceId],
    queryFn: () => agentsApi.list(workspaceId),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const templates = useQuery({
    queryKey: ['agent-templates'],
    queryFn: () => agentsApi.templates(),
    retry: false,
  })

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

  if (!activeWorkspace) return <NoWorkspaceState module="Agent Studio" />

  const hasModel = (providers.data ?? []).some(
    (provider) => provider.models.length > 0 && provider.status !== 'disabled',
  )

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <PageHeader
        title="Agents"
        description="Draft, publish and run versioned agents. Every run uses an immutable published version."
        actions={
          <Button
            size="sm"
            onClick={() => setShowCreate((value) => !value)}
            disabled={!canWrite || !hasModel}
          >
            <Plus className="size-3.5" aria-hidden="true" />
            New agent
          </Button>
        }
      />

      {!canWrite ? (
        <Notice tone="warning" title="Read-only access" className="mb-4">
          Your role can inspect agents and their traces, but creating, editing or publishing agents
          requires a developer, administrator or owner role.
        </Notice>
      ) : null}

      {showCreate ? (
        <CreateAgentCard
          workspaceId={workspaceId}
          templates={templates.data ?? []}
          providers={providers.data ?? []}
          templatesLoading={templates.isLoading}
          onCancel={() => setShowCreate(false)}
          onCreated={(agentId) => {
            setShowCreate(false)
            navigate(`/agents/${agentId}`)
          }}
        />
      ) : null}

      {!hasModel && !providers.isLoading ? (
        <Card className="mb-4">
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium">A registered model is required first</p>
              <p className="mt-1 text-xs text-[var(--muted-foreground)]">
                Configure a provider and register at least one model. The simulation provider is
                deterministic and clearly labelled, so you can exercise the full runtime offline.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                loading={ensureSimulation.isPending}
                disabled={!canWrite || ensureSimulation.isPending}
                onClick={() => ensureSimulation.mutate()}
              >
                <Beaker className="size-3.5" aria-hidden="true" />
                Add simulation provider
              </Button>
              <Button asChild size="sm" variant="secondary">
                <Link to="/models">Open Model Lab</Link>
              </Button>
            </div>
          </CardContent>
          {ensureSimulation.isError ? (
            <div className="border-t border-[var(--border)] px-5 py-3">
              <Notice tone="danger" title="Could not add the provider">
                {ensureSimulation.error instanceof ApiError
                  ? ensureSimulation.error.message
                  : 'The simulation provider was not created.'}
              </Notice>
            </div>
          ) : null}
        </Card>
      ) : null}

      {agents.isLoading ? (
        <LoadingState label="Loading agents…" />
      ) : agents.isError ? (
        <ErrorState
          title="Agents unavailable"
          message={
            agents.error instanceof ApiError
              ? agents.error.message
              : 'The agent list could not be loaded.'
          }
          onRetry={() => void agents.refetch()}
        />
      ) : (agents.data?.length ?? 0) === 0 ? (
        <Card>
          <EmptyState
            icon={<Bot className="size-5" aria-hidden="true" />}
            title="No agents yet"
            description="Create an agent from one of the functional templates, then publish it and run it in the playground."
            action={
              <Button
                size="sm"
                onClick={() => setShowCreate(true)}
                disabled={!canWrite || !hasModel}
              >
                <Plus className="size-3.5" aria-hidden="true" />
                Create your first agent
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {agents.data?.map((agent) => (
            <Card key={agent.id} className="flex flex-col">
              <CardHeader
                title={
                  <span className="flex flex-wrap items-center gap-2">
                    {agent.name}
                    <Badge tone={agent.status === 'active' ? 'success' : 'neutral'}>
                      {agent.status}
                    </Badge>
                  </span>
                }
                description={agent.description || 'No description'}
                actions={
                  agent.current_version_number ? (
                    <Badge tone="primary">v{agent.current_version_number}</Badge>
                  ) : (
                    <Badge tone="warning">draft only</Badge>
                  )
                }
              />
              <CardContent className="flex flex-1 flex-col gap-3">
                <dl className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                      Model
                    </dt>
                    <dd className="truncate font-mono text-[11px]">
                      {agent.draft_configuration.model_name}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                      Tools
                    </dt>
                    <dd>{agent.draft_configuration.tool_ids.length} selected</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                      Updated
                    </dt>
                    <dd>{formatDateTime(agent.updated_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                      Published
                    </dt>
                    <dd>{agent.current_published_version_id ? 'yes' : 'never'}</dd>
                  </div>
                </dl>
                <div className="mt-auto flex flex-wrap gap-2">
                  <Button asChild size="sm" variant="secondary">
                    <Link to={`/agents/${agent.id}`}>
                      Open Studio
                      <ArrowRight className="size-3.5" aria-hidden="true" />
                    </Link>
                  </Button>
                  <Button asChild size="sm" variant="ghost">
                    <Link
                      to={`/agents/${agent.id}/playground`}
                      aria-disabled={!agent.current_published_version_id}
                      onClick={(event) => {
                        if (!agent.current_published_version_id) event.preventDefault()
                      }}
                    >
                      <FlaskConical className="size-3.5" aria-hidden="true" />
                      Playground
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <div className="mt-6">
        <DemoDataCard workspaceId={workspaceId} />
      </div>
    </div>
  )
}

function CreateAgentCard({
  workspaceId,
  templates,
  providers,
  templatesLoading,
  onCancel,
  onCreated,
}: {
  workspaceId: string
  templates: Awaited<ReturnType<typeof agentsApi.templates>>
  providers: Awaited<ReturnType<typeof providersApi.list>>
  templatesLoading: boolean
  onCancel: () => void
  onCreated: (agentId: string) => void
}) {
  const queryClient = useQueryClient()
  const [templateKey, setTemplateKey] = useState('')
  const [name, setName] = useState('')
  const [providerModel, setProviderModel] = useState('')
  const [error, setError] = useState<string | null>(null)

  const models = providers.flatMap((provider) =>
    provider.models
      .filter((model) => model.enabled)
      .map((model) => ({
        value: `${provider.id}:${model.id}`,
        label: `${provider.display_name} · ${model.display_name ?? model.model_name}`,
        providerId: provider.id,
        modelId: model.id,
      })),
  )

  useEffect(() => {
    if (!templateKey && templates.length > 0) {
      const first = templates[0]
      if (first) {
        setTemplateKey(first.key)
        setName(first.name)
      }
    }
  }, [templates, templateKey])

  useEffect(() => {
    if (!providerModel && models.length > 0) {
      setProviderModel(models[0]?.value ?? '')
    }
  }, [models, providerModel])

  const create = useMutation({
    mutationFn: () => {
      const selected = models.find((model) => model.value === providerModel)
      if (!selected) throw new Error('Select a registered model.')
      return agentsApi.create(workspaceId, {
        name: name.trim(),
        template_key: templateKey || null,
        provider_id: selected.providerId,
        model_config_id: selected.modelId,
      })
    },
    onSuccess: async (agent) => {
      await queryClient.invalidateQueries({ queryKey: ['agents', workspaceId] })
      onCreated(agent.id)
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError || mutationError instanceof Error
          ? mutationError.message
          : 'The agent could not be created.',
      )
    },
  })

  const selectedTemplate = templates.find((template) => template.key === templateKey)

  return (
    <Card className="mb-4">
      <CardHeader
        title="Create an agent"
        description="Start from a functional template. The template supplies a system prompt, a tool set and sampling parameters; everything remains editable."
        actions={
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        }
      />
      <CardContent>
        {templatesLoading ? (
          <LoadingState label="Loading templates…" />
        ) : (
          <form
            className="grid gap-4 md:grid-cols-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (!name.trim()) {
                setError('A name is required.')
                return
              }
              create.mutate()
            }}
          >
            <div className="space-y-1.5">
              <Label htmlFor="agent-template" required>
                Template
              </Label>
              <Select
                id="agent-template"
                value={templateKey}
                onChange={(event) => {
                  const next = event.target.value
                  setTemplateKey(next)
                  const template = templates.find((item) => item.key === next)
                  if (template) setName(template.name)
                }}
              >
                {templates.map((template) => (
                  <option key={template.key} value={template.key}>
                    {template.name} · {template.category}
                  </option>
                ))}
              </Select>
              {selectedTemplate ? <FieldHint>{selectedTemplate.description}</FieldHint> : null}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agent-name" required>
                Name
              </Label>
              <Input
                id="agent-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={120}
                placeholder="Sales Operations Assistant"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="agent-model" required>
                Provider and model
              </Label>
              <Select
                id="agent-model"
                value={providerModel}
                onChange={(event) => setProviderModel(event.target.value)}
              >
                {models.map((model) => (
                  <option key={model.value} value={model.value}>
                    {model.label}
                  </option>
                ))}
              </Select>
              <FieldHint>
                The model name is snapshotted into every published version.
              </FieldHint>
            </div>

            {selectedTemplate ? (
              <div className="space-y-1.5">
                <Label>Tools included</Label>
                <div className="flex flex-wrap gap-1.5">
                  {selectedTemplate.tool_names.map((tool) => (
                    <Badge key={tool} tone="neutral">
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {error ? (
              <div className="md:col-span-2">
                <FieldError>{error}</FieldError>
              </div>
            ) : null}

            <div className="md:col-span-2 flex flex-wrap items-center justify-between gap-2">
              <p className="inline-flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
                <Sparkles className="size-3.5" aria-hidden="true" />
                A draft is created first; nothing runs until you publish a version.
              </p>
              <Button type="submit" size="sm" loading={create.isPending}>
                Create draft
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  )
}
