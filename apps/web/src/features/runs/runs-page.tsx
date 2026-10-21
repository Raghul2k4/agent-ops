import { useQuery } from '@tanstack/react-query'
import { ArrowRight, ListFilter, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Select } from '@/components/ui/select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { RunStatusBadge } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { NoWorkspaceState } from '@/features/shared/no-workspace'
import { runsApi } from '@/features/runs/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, formatDuration } from '@/lib/utils'

const STATUSES = ['', 'queued', 'running', 'succeeded', 'failed', 'cancelled', 'awaiting_approval']

export function RunsPage() {
  const { activeWorkspace } = useWorkspace()
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const limit = 25
  const workspaceId = activeWorkspace?.id ?? ''

  const runs = useQuery({
    queryKey: ['runs', workspaceId, status, offset],
    queryFn: () => runsApi.list({ workspaceId, status: status || undefined, limit, offset }),
    enabled: Boolean(workspaceId),
    retry: false,
    refetchInterval: 15_000,
  })

  if (!activeWorkspace) return <NoWorkspaceState module="Runs & Traces" />

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <PageHeader
        title="Runs & Traces"
        description="Every execution is persisted with ordered events, usage, cost when available and a hierarchical trace."
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void runs.refetch()}
            loading={runs.isFetching}
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      <Card>
        <CardHeader
          title="Execution history"
          description="Server-side filtered and paginated over persisted rows."
          actions={
            <div className="flex items-center gap-2">
              <ListFilter className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
              <Select
                aria-label="Filter by status"
                value={status}
                className="h-8 w-40 text-xs"
                onChange={(event) => {
                  setStatus(event.target.value)
                  setOffset(0)
                }}
              >
                {STATUSES.map((value) => (
                  <option key={value} value={value}>
                    {value === '' ? 'All statuses' : value.replace(/_/g, ' ')}
                  </option>
                ))}
              </Select>
            </div>
          }
        />

        {runs.isLoading ? (
          <LoadingState label="Loading runs…" />
        ) : runs.isError ? (
          <ErrorState
            title="Runs unavailable"
            message={
              runs.error instanceof ApiError
                ? runs.error.message
                : 'The run history could not be loaded.'
            }
            onRetry={() => void runs.refetch()}
          />
        ) : (runs.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title={status ? 'No runs match this filter' : 'No runs yet'}
            description={
              status
                ? 'Clear the status filter or start a run from an agent playground.'
                : 'Start a run from Agent Studio to create the first persisted trace.'
            }
            action={
              <Button asChild size="sm" variant="secondary">
                <Link to="/agents">Open Agents</Link>
              </Button>
            }
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-[var(--border)] text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                  <tr>
                    <th className="px-5 py-2">Run</th>
                    <th className="px-3 py-2">Agent</th>
                    <th className="px-3 py-2">Version</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Started</th>
                    <th className="px-3 py-2">Duration</th>
                    <th className="px-3 py-2">Tokens</th>
                    <th className="px-3 py-2">Cost</th>
                    <th className="px-5 py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {runs.data?.items.map((run) => (
                    <tr key={run.id} className="hover:bg-[var(--surface-muted)]/50">
                      <td className="px-5 py-2.5 font-mono text-[11px]">{run.id.slice(0, 8)}</td>
                      <td className="max-w-40 truncate px-3 py-2.5">{run.agent_name ?? '—'}</td>
                      <td className="px-3 py-2.5">v{run.version_number ?? '—'}</td>
                      <td className="px-3 py-2.5">
                        <RunStatusBadge status={run.status} />
                      </td>
                      <td className="px-3 py-2.5 text-[var(--muted-foreground)]">
                        {formatDateTime(run.started_at ?? run.created_at)}
                      </td>
                      <td className="px-3 py-2.5">{formatDuration(run.duration_ms)}</td>
                      <td className="px-3 py-2.5">{run.token_usage.total_tokens ?? 0}</td>
                      <td className="px-3 py-2.5">
                        {run.estimated_cost === null ? (
                          <Badge tone="warning">unavailable</Badge>
                        ) : (
                          `$${run.estimated_cost.toFixed(4)}`
                        )}
                      </td>
                      <td className="px-5 py-2.5 text-right">
                        <Button asChild size="sm" variant="ghost">
                          <Link to={`/runs/${run.id}`}>
                            Inspect
                            <ArrowRight className="size-3.5" aria-hidden="true" />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <CardContent className="flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border)]">
              <p className="text-xs text-[var(--muted-foreground)]">
                {runs.data?.total ?? 0} total · showing {offset + 1}–
                {offset + (runs.data?.items.length ?? 0)}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={!runs.data?.has_more}
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </Button>
              </div>
            </CardContent>
          </>
        )}
      </Card>
    </div>
  )
}
