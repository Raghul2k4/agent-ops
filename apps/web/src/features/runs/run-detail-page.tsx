import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Ban, Clock, FlaskConical, RefreshCw, RotateCcw, ShieldAlert } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { JsonView, summarizePayload } from '@/components/ui/json-view'
import { ErrorState, LoadingState } from '@/components/ui/states'
import { Notice, RunStatusBadge } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { runsApi } from '@/features/runs/api'
import { useRunEventStream } from '@/features/runs/use-run-event-stream'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, formatDuration } from '@/lib/utils'
import type { RunEventList } from '@/types/api'

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled', 'awaiting_approval'])

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const { can } = useWorkspace()
  const queryClient = useQueryClient()

  const runQuery = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId),
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data
      return data && TERMINAL_STATUSES.has(data.status) ? false : 800
    },
  })

  const run = runQuery.data ?? null
  const active = run ? !TERMINAL_STATUSES.has(run.status) : false

  const eventsQuery = useQuery({
    queryKey: ['run-events', runId],
    queryFn: () => runsApi.events(runId),
    enabled: Boolean(runId),
    retry: false,
    refetchInterval: () => (active ? 900 : false),
  })

  // Live updates: the server pushes new events and the client recovers any
  // it missed with the sequence cursor.
  useRunEventStream(runId, (incoming) => {
    queryClient.setQueryData<RunEventList>(['run-events', runId], (current) => {
      if (!current) return current
      const known = new Set(current.items.map((item) => item.id))
      const fresh = incoming.filter((item) => !known.has(item.id))
      if (fresh.length === 0) return current
      return {
        ...current,
        items: [...current.items, ...fresh].sort((a, b) => a.sequence_number - b.sequence_number),
        last_sequence: Math.max(current.last_sequence, ...fresh.map((item) => item.sequence_number)),
      }
    })
    void runQuery.refetch()
  })

  const traceQuery = useQuery({
    queryKey: ['run-trace', runId],
    queryFn: () => runsApi.trace(runId),
    enabled: Boolean(runId) && Boolean(run && TERMINAL_STATUSES.has(run.status)),
    retry: false,
  })

  const cancel = useMutation({
    mutationFn: () => runsApi.cancel(runId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['run', runId] })
      await queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
  })

  const replay = useMutation({
    mutationFn: () => runsApi.replay(runId),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ['runs'] })
      await queryClient.invalidateQueries({ queryKey: ['run', created.id] })
    },
  })

  if (runQuery.isLoading) return <LoadingState label="Loading run…" />
  if (runQuery.isError || !run) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-10">
        <ErrorState
          title="Run not available"
          message={
            runQuery.error instanceof ApiError
              ? runQuery.error.message
              : 'This run could not be loaded in your workspace.'
          }
          onRetry={() => void runQuery.refetch()}
        />
        <div className="mt-4 text-center">
          <Button asChild variant="ghost" size="sm">
            <Link to="/runs">Back to runs</Link>
          </Button>
        </div>
      </div>
    )
  }

  const outputMessage =
    typeof run.output?.message === 'string' ? run.output.message : null
  const pendingApproval =
    run.output?.pending_approval && typeof run.output.pending_approval === 'object'
      ? (run.output.pending_approval as Record<string, unknown>)
      : null
  const completedActions = Array.isArray(run.output?.completed_actions)
    ? (run.output.completed_actions as Record<string, unknown>[])
    : []
  const stoppedBecause =
    typeof run.output?.stopped_because === 'string' ? run.output.stopped_because : null
  const events = eventsQuery.data?.items ?? []

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <div className="mb-3">
        <Button asChild variant="ghost" size="sm">
          <Link to="/runs">
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            Runs &amp; Traces
          </Link>
        </Button>
      </div>

      <PageHeader
        title={
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-base">{run.id.slice(0, 8)}</span>
            <RunStatusBadge status={run.status} />
            <Badge tone="neutral">v{run.version_number ?? '—'}</Badge>
            {run.replay_of_run_id ? <Badge tone="info">replay</Badge> : null}
          </span>
        }
        description={`${run.agent_name ?? 'Agent'} · started ${formatDateTime(run.started_at ?? run.created_at)}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {active ? (
              <Button
                size="sm"
                variant="danger"
                loading={cancel.isPending}
                disabled={!can('run.cancel') || cancel.isPending}
                onClick={() => cancel.mutate()}
              >
                <Ban className="size-3.5" aria-hidden="true" />
                Cancel run
              </Button>
            ) : null}
            <Button
              size="sm"
              variant="secondary"
              loading={replay.isPending}
              disabled={!can('run.execute') || replay.isPending}
              onClick={() => replay.mutate()}
            >
              <RotateCcw className="size-3.5" aria-hidden="true" />
              Replay safely
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => {
                void runQuery.refetch()
                void eventsQuery.refetch()
              }}
              loading={runQuery.isFetching}
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              Refresh
            </Button>
            <Button asChild size="sm" variant="ghost">
              <Link to={`/agents/${run.agent_id}/playground`}>
                <FlaskConical className="size-3.5" aria-hidden="true" />
                Playground
              </Link>
            </Button>
          </div>
        }
      />

      {replay.isError ? (
        <Notice tone="danger" title="The replay was not started" className="mb-4">
          {replay.error instanceof ApiError ? replay.error.message : 'The replay could not start.'}
        </Notice>
      ) : null}

      {replay.isSuccess ? (
        <Notice tone="info" title="Safe replay started" className="mb-4">
          A new run was created from this one. Tools that change a business record still need a
          fresh approval.{' '}
          <Link className="text-[var(--primary)] hover:underline" to={`/runs/${replay.data.id}`}>
            Open the replay
          </Link>
          .
        </Notice>
      ) : null}

      {cancel.isError ? (
        <Notice tone="danger" title="Cancellation failed" className="mb-4">
          {cancel.error instanceof ApiError ? cancel.error.message : 'The run was not cancelled.'}
        </Notice>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Outcome" description="Persisted terminal or in-flight state." />
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">
                  <Clock className="size-2.5" aria-hidden="true" />
                  {formatDuration(run.duration_ms)}
                </Badge>
                <Badge tone="neutral">
                  {run.token_usage.model_calls ?? 0} model calls ·{' '}
                  {run.token_usage.tool_calls ?? 0} tool calls
                </Badge>
                <Badge tone="neutral">
                  {run.token_usage.input_tokens ?? 0} in / {run.token_usage.output_tokens ?? 0} out
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
                    <code className="font-mono">{String(pendingApproval.tool)}</code> is classified
                    as {String(pendingApproval.risk_level)} risk. The run paused before execution;
                    the business record is unchanged.
                  </p>
                  <p className="mt-1 break-all font-mono text-[10px]">
                    payload hash: {String(pendingApproval.canonical_arguments_hash)}
                  </p>
                  {run.pending_approval_id ? (
                    <p className="mt-2">
                      <Link
                        className="inline-flex items-center gap-1 text-[var(--primary)] hover:underline"
                        to="/approvals"
                      >
                        <ShieldAlert className="size-3" aria-hidden="true" />
                        Review it in the approval queue
                      </Link>
                    </p>
                  ) : null}
                </Notice>
              ) : null}

              {run.replay_mode ? (
                <Notice tone="info" title="Safe replay">
                  This run replays an earlier run. Tools that change a business record were not
                  repeated: they wait for a fresh decision.
                  {run.replay_of_run_id ? (
                    <>
                      {' '}
                      <Link
                        className="text-[var(--primary)] hover:underline"
                        to={`/runs/${run.replay_of_run_id}`}
                      >
                        Open the source run
                      </Link>
                      .
                    </>
                  ) : null}
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
                        <JsonView
                          value={action.output ?? {}}
                          label="Result"
                          className="mt-2"
                        />
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

              {run.input.message ? (
                <div className="rounded-md border border-[var(--border)] p-3">
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                    Input message
                  </p>
                  <p className="whitespace-pre-wrap text-xs leading-relaxed">
                    {String(run.input.message)}
                  </p>
                </div>
              ) : null}

              {run.output ? <JsonView value={run.output} label="Full run output" /> : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Execution events"
              description="Ordered by sequence number. Payloads are sanitized before persistence."
              actions={<Badge tone="neutral">{events.length} events</Badge>}
            />
            <CardContent>
              {eventsQuery.isLoading ? (
                <LoadingState label="Loading events…" />
              ) : eventsQuery.isError ? (
                <ErrorState
                  title="Events unavailable"
                  message={
                    eventsQuery.error instanceof ApiError
                      ? eventsQuery.error.message
                      : 'The event log could not be loaded.'
                  }
                  onRetry={() => void eventsQuery.refetch()}
                />
              ) : events.length === 0 ? (
                <p className="py-6 text-center text-xs text-[var(--muted-foreground)]">
                  No events recorded yet.
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
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Run details" />
            <CardContent>
              <dl className="space-y-2 text-[11px]">
                <Detail label="Run ID" value={<span className="font-mono">{run.id}</span>} />
                <Detail
                  label="Agent"
                  value={<Link className="text-[var(--primary)] hover:underline" to={`/agents/${run.agent_id}`}>{run.agent_name ?? run.agent_id}</Link>}
                />
                <Detail label="Agent version" value={`v${run.version_number ?? '—'} (${run.agent_version_id.slice(0, 8)})`} />
                <Detail label="Model config" value={<span className="font-mono">{run.model_config_id?.slice(0, 8) ?? '—'}</span>} />
                <Detail label="Initiated by" value={<span className="font-mono">{run.initiated_by?.slice(0, 8) ?? '—'}</span>} />
                <Detail label="Created" value={formatDateTime(run.created_at)} />
                <Detail label="Started" value={formatDateTime(run.started_at)} />
                <Detail label="Completed" value={formatDateTime(run.completed_at)} />
                <Detail label="Replay of" value={run.replay_of_run_id ?? 'not a replay'} />
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader
              title="Trace spans"
              description="Hierarchical execution spans persisted by the runtime."
            />
            <CardContent>
              {!TERMINAL_STATUSES.has(run.status) ? (
                <p className="py-4 text-center text-xs text-[var(--muted-foreground)]">
                  Spans appear when the run reaches a terminal or paused state.
                </p>
              ) : traceQuery.isLoading ? (
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
              ) : (traceQuery.data?.spans.length ?? 0) === 0 ? (
                <p className="py-4 text-center text-xs text-[var(--muted-foreground)]">
                  No spans were recorded for this run.
                </p>
              ) : (
                <ul className="space-y-2">
                  {traceQuery.data?.spans.map((span) => (
                    <li
                      key={span.id}
                      className="rounded-md border border-[var(--border)] px-3 py-2"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <code className="font-mono text-[11px]">{span.span_type}</code>
                        <Badge tone={span.status === 'ok' ? 'success' : 'danger'}>
                          {span.status}
                        </Badge>
                        <span className="ml-auto text-[10px] text-[var(--muted-foreground)]">
                          {formatDuration(span.duration_ms)}
                        </span>
                      </div>
                      <p className="mt-1 truncate text-xs">
                        {span.parent_span_id ? '└ ' : ''}
                        {span.name}
                      </p>
                      <JsonView value={span.attributes} label="Attributes" className="mt-2" />
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-1.5 last:border-0 last:pb-0">
      <dt className="shrink-0 text-[var(--muted-foreground)]">{label}</dt>
      <dd className="min-w-0 truncate text-right">{value}</dd>
    </div>
  )
}
