import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Ban,
  Clock,
  ExternalLink,
  FlaskConical,
  Play,
  RefreshCw,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { JsonView, summarizePayload } from '@/components/ui/json-view'
import { Label } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { ErrorState, LoadingState } from '@/components/ui/states'
import { Notice, RunStatusBadge } from '@/components/ui/status'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/features/shared/page'
import { agentsApi } from '@/features/agents/api'
import { runsApi } from '@/features/runs/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, formatDuration } from '@/lib/utils'
import type { RunRead } from '@/types/api'

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled', 'awaiting_approval'])
const DEMO_PROMPT =
  'Find deals worth more than INR 50,000 that have not been contacted in the last 14 days. Research the customers, prepare personalized follow-up drafts, and show me the proposed actions before anything is sent.'

export function AgentPlaygroundPage() {
  const { agentId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const { activeWorkspace, can } = useWorkspace()
  const queryClient = useQueryClient()
  const [message, setMessage] = useState(DEMO_PROMPT)
  const [runId, setRunId] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)

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

  const agent = agentQuery.data
  const versions = versionsQuery.data ?? []
  const selectedVersionId =
    searchParams.get('version') ??
    agent?.current_published_version_id ??
    versions[0]?.id ??
    ''

  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? null

  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId ?? ''),
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data
      return data && TERMINAL_STATUSES.has(data.status) ? false : 800
    },
  })

  const run = runQuery.data ?? null
  const isActive = run ? !TERMINAL_STATUSES.has(run.status) : false

  const eventsQuery = useQuery({
    queryKey: ['run-events', runId],
    queryFn: () => runsApi.events(runId ?? ''),
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: () => (isActive ? 900 : false),
  })

  const traceQuery = useQuery({
    queryKey: ['run-trace', runId],
    queryFn: () => runsApi.trace(runId ?? ''),
    enabled: Boolean(runId) && Boolean(run && TERMINAL_STATUSES.has(run.status)),
    retry: false,
  })

  useEffect(() => {
    if (!run) return
    if (TERMINAL_STATUSES.has(run.status)) {
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
    }
  }, [run, queryClient])

  const startRun = useMutation({
    mutationFn: () => agentsApi.run(agentId, message.trim(), selectedVersionId || undefined),
    onSuccess: (created: RunRead) => {
      setStartError(null)
      setRunId(created.id)
      void queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
    onError: (error) => {
      setStartError(
        error instanceof ApiError ? error.message : 'The run could not be started.',
      )
    },
  })

  const cancel = useMutation({
    mutationFn: () => runsApi.cancel(runId ?? ''),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['run', runId] })
    },
  })

  const events = eventsQuery.data?.items ?? []
  const simulation = selectedVersion?.configuration.model_name.toLowerCase().includes('simulation')

  const outputMessage = useMemo(() => {
    const value = run?.output?.message
    return typeof value === 'string' ? value : null
  }, [run])

  const pendingApproval = useMemo(() => {
    const value = run?.output?.pending_approval
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
  }, [run])

  const completedActions = useMemo(() => {
    const value = run?.output?.completed_actions
    return Array.isArray(value) ? (value as Record<string, unknown>[]) : []
  }, [run])

  const stoppedBecause = useMemo(() => {
    const value = run?.output?.stopped_because
    return typeof value === 'string' ? value : null
  }, [run])

  if (!activeWorkspace) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <ErrorState title="No active workspace" message="Select a workspace to use the playground." />
      </div>
    )
  }

  if (agentQuery.isLoading) return <LoadingState label="Loading playground…" />
  if (agentQuery.isError || !agent) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <ErrorState
          title="Agent not available"
          message={
            agentQuery.error instanceof ApiError
              ? agentQuery.error.message
              : 'The agent could not be loaded.'
          }
          onRetry={() => void agentQuery.refetch()}
        />
      </div>
    )
  }

  const canRun = can('run.execute')
  const published = Boolean(agent.current_published_version_id)

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-3">
        <Button asChild variant="ghost" size="sm">
          <Link to={`/agents/${agent.id}`}>
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            {agent.name}
          </Link>
        </Button>
      </div>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <FlaskConical className="size-4 text-[var(--muted-foreground)]" aria-hidden="true" />
            Playground
            {selectedVersion ? (
              <Badge tone="primary">v{selectedVersion.version_number}</Badge>
            ) : null}
            {simulation ? <Badge tone="warning">simulation</Badge> : null}
          </span>
        }
        description="Runs execute against an immutable published version through the real backend runtime. Nothing here is mocked."
        actions={
          <Button asChild size="sm" variant="secondary">
            <Link to={`/runs${runId ? `/${runId}` : ''}`}>
              <ExternalLink className="size-3.5" aria-hidden="true" />
              {runId ? 'Open run detail' : 'Run history'}
            </Link>
          </Button>
        }
      />

      {!published ? (
        <Notice tone="warning" title="Publish a version first" className="mb-4">
          The playground only runs published, immutable versions. Open Agent Studio, save the draft
          and publish it.
        </Notice>
      ) : null}

      {simulation ? (
        <Notice tone="warning" title="Simulation output is clearly labelled" className="mb-4">
          This version uses the deterministic simulation provider. Responses are scripted from tool
          results and always start with <code className="font-mono">[SIMULATED]</code>. They are not
          generated by a language model.
        </Notice>
      ) : null}

      {!canRun ? (
        <Notice tone="warning" title="Execution permission required" className="mb-4">
          Your role can inspect runs but not start them. Execution requires an operator, reviewer,
          developer, administrator or owner role.
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader
            title="Request"
            description="The message becomes input.message for the runtime."
          />
          <CardContent className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="playground-version">Version</Label>
              <Select
                id="playground-version"
                value={selectedVersionId}
                onChange={(event) => {
                  const params = new URLSearchParams(searchParams)
                  params.set('version', event.target.value)
                  setSearchParams(params)
                }}
              >
                {versions.length === 0 ? <option value="">No published versions</option> : null}
                {versions.map((version) => (
                  <option key={version.id} value={version.id}>
                    v{version.version_number} · {version.change_summary || 'no summary'}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="playground-message" required>
                Message
              </Label>
              <Textarea
                id="playground-message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                rows={10}
                className="font-sans text-sm"
                placeholder="Ask the agent to do something…"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <button
                  type="button"
                  className="text-[11px] text-[var(--primary)] hover:underline"
                  onClick={() => setMessage(DEMO_PROMPT)}
                >
                  Use the Sales Operations demo request
                </button>
                <span className="text-[11px] text-[var(--muted-foreground)]">
                  {message.length} / 16000
                </span>
              </div>
            </div>

            {startError ? (
              <Notice tone="danger" title="Run rejected">
                {startError}
              </Notice>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button
                loading={startRun.isPending}
                disabled={
                  !canRun ||
                  !published ||
                  !message.trim() ||
                  startRun.isPending ||
                  isActive
                }
                onClick={() => startRun.mutate()}
              >
                <Play className="size-3.5" aria-hidden="true" />
                {isActive ? 'Run in progress' : 'Run agent'}
              </Button>
              {isActive && runId ? (
                <Button
                  variant="danger"
                  size="sm"
                  loading={cancel.isPending}
                  disabled={!can('run.cancel') || cancel.isPending}
                  onClick={() => cancel.mutate()}
                >
                  <Ban className="size-3.5" aria-hidden="true" />
                  Cancel run
                </Button>
              ) : null}
            </div>
            <p className="text-[11px] text-[var(--muted-foreground)]">
              Budgets for this version: {selectedVersion?.configuration.limits.max_steps ?? '—'} steps,{' '}
              {selectedVersion?.configuration.limits.max_wall_clock_seconds ?? '—'} s wall clock,{' '}
              {selectedVersion?.configuration.limits.max_total_tokens.toLocaleString() ?? '—'} tokens.
            </p>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Result"
              description="Persisted run record, updated while the run is active."
              actions={
                run ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => void runQuery.refetch()}
                    aria-label="Refresh run"
                  >
                    <RefreshCw className="size-3.5" aria-hidden="true" />
                  </Button>
                ) : null
              }
            />
            <CardContent className="space-y-3">
              {!run ? (
                <p className="py-8 text-center text-xs text-[var(--muted-foreground)]">
                  No run yet. Send a message to start one.
                </p>
              ) : runQuery.isError ? (
                <ErrorState
                  title="Run unavailable"
                  message={
                    runQuery.error instanceof ApiError
                      ? runQuery.error.message
                      : 'The run could not be loaded.'
                  }
                  onRetry={() => void runQuery.refetch()}
                />
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <RunStatusBadge status={run.status} />
                    <Badge tone="neutral">
                      <Clock className="size-2.5" aria-hidden="true" />
                      {formatDuration(run.duration_ms)}
                    </Badge>
                    <Badge tone="neutral">
                      {run.token_usage.model_calls ?? 0} model calls ·{' '}
                      {run.token_usage.tool_calls ?? 0} tool calls
                    </Badge>
                    <Badge tone="neutral">
                      {run.token_usage.total_tokens ?? 0} tokens
                    </Badge>
                    <Badge tone={run.estimated_cost === null ? 'warning' : 'info'}>
                      {run.estimated_cost === null
                        ? 'cost unavailable'
                        : `$${run.estimated_cost.toFixed(4)}`}
                    </Badge>
                  </div>

                  {run.error_code ? (
                    <Notice tone="danger" title={run.error_code}>
                      {run.error_summary ?? 'The run failed.'}
                    </Notice>
                  ) : null}

                  {run.status === 'awaiting_approval' && pendingApproval ? (
                    <Notice tone="warning" title="Approval required - the tool did not execute">
                      <p>
                        <code className="font-mono">{String(pendingApproval.tool)}</code> is
                        classified as {String(pendingApproval.risk_level)} risk. The run paused
                        before execution and the business record is unchanged. Approval decisions
                        are delivered in milestone M3.
                      </p>
                      <p className="mt-1 font-mono text-[10px] break-all">
                        payload hash: {String(pendingApproval.canonical_arguments_hash)}
                      </p>
                    </Notice>
                  ) : null}

                  {completedActions.length > 0 ? (
                    <div className="rounded-md border border-[var(--border)] p-3">
                      <p className="mb-1 text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                        Completed actions before the run stopped
                      </p>
                      {stoppedBecause ? (
                        <p className="mb-2 text-xs text-[var(--muted-foreground)]">{stoppedBecause}</p>
                      ) : null}
                      <ul className="space-y-2">
                        {completedActions.map((action, index) => (
                          <li
                            key={`${String(action.tool)}-${index}`}
                            className="rounded-md border border-[var(--border)] bg-[var(--background)] px-3 py-2"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <code className="font-mono text-[11px]">{String(action.tool)}</code>
                              {action.risk_level ? (
                                <Badge tone="neutral">{String(action.risk_level)} risk</Badge>
                              ) : null}
                            </div>
                            <JsonView value={action.output ?? {}} label="Result" className="mt-2" />
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {outputMessage ? (
                    <div className="rounded-md border border-[var(--border)] bg-[var(--background)] p-3">
                      <p className="mb-1 text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                        Final message
                      </p>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed">{outputMessage}</p>
                    </div>
                  ) : null}

                  {run.output ? <JsonView value={run.output} label="Full run output" /> : null}

                  <dl className="grid gap-2 text-[11px] text-[var(--muted-foreground)] sm:grid-cols-2">
                    <div>
                      <dt className="uppercase tracking-wide">Run ID</dt>
                      <dd className="truncate font-mono">{run.id}</dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-wide">Started</dt>
                      <dd>{formatDateTime(run.started_at ?? run.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-wide">Completed</dt>
                      <dd>{formatDateTime(run.completed_at)}</dd>
                    </div>
                    <div>
                      <dt className="uppercase tracking-wide">Version</dt>
                      <dd>v{run.version_number ?? '—'}</dd>
                    </div>
                  </dl>

                  {run.estimated_cost === null ? (
                    <p className="text-[11px] text-[var(--muted-foreground)]">
                      Estimated cost is unavailable because this model has no pricing metadata
                      configured. It is not reported as zero.
                    </p>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Execution events"
              description="Persisted in order; the cursor can recover missed events."
              actions={
                eventsQuery.data ? (
                  <Badge tone="neutral">{events.length} events</Badge>
                ) : null
              }
            />
            <CardContent>
              {!runId ? (
                <p className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                  Events appear here once a run starts.
                </p>
              ) : eventsQuery.isLoading ? (
                <LoadingState label="Loading events…" />
              ) : events.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                  No events yet.
                </p>
              ) : (
                <ol className="space-y-2">
                  {events.map((event) => (
                    <li
                      key={event.id}
                      className="rounded-md border border-[var(--border)] px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-[var(--muted-foreground)]">
                          #{event.sequence_number}
                        </span>
                        <code className="font-mono text-[11px]">{event.event_type}</code>
                        <Badge tone="neutral">{event.event_status}</Badge>
                        <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">
                          {formatDateTime(event.occurred_at)}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-[11px] text-[var(--muted-foreground)]">
                        {summarizePayload(event.payload)}
                      </p>
                      <JsonView value={event.payload} label="Payload" className="mt-2" />
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>

          {runId && run && TERMINAL_STATUSES.has(run.status) ? (
            <Card>
              <CardHeader
                title="Trace spans"
                description="One span per agent run, model call and tool call."
              />
              <CardContent>
                {traceQuery.isLoading ? (
                  <LoadingState label="Loading trace…" />
                ) : traceQuery.isError ? (
                  <ErrorState
                    title="Trace unavailable"
                    message={
                      traceQuery.error instanceof ApiError
                        ? traceQuery.error.message
                        : 'The trace could not be loaded.'
                    }
                    onRetry={() => void traceQuery.refetch()}
                  />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                        <tr>
                          <th className="py-1.5 pr-3">Span</th>
                          <th className="py-1.5 pr-3">Type</th>
                          <th className="py-1.5 pr-3">Status</th>
                          <th className="py-1.5 pr-3">Duration</th>
                          <th className="py-1.5">Started</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {traceQuery.data?.spans.map((span) => (
                          <tr key={span.id}>
                            <td className="py-1.5 pr-3 font-mono text-[11px]">
                              {span.parent_span_id ? '└ ' : ''}
                              {span.name}
                            </td>
                            <td className="py-1.5 pr-3">{span.span_type}</td>
                            <td className="py-1.5 pr-3">
                              <Badge tone={span.status === 'ok' ? 'success' : 'danger'}>
                                {span.status}
                              </Badge>
                            </td>
                            <td className="py-1.5 pr-3">{formatDuration(span.duration_ms)}</td>
                            <td className="py-1.5 text-[var(--muted-foreground)]">
                              {formatDateTime(span.started_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
