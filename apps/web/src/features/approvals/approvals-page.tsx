import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock, RefreshCw, ShieldAlert, ShieldCheck, XCircle } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { JsonView } from '@/components/ui/json-view'
import { Label } from '@/components/ui/field'
import { Select } from '@/components/ui/select'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { Notice } from '@/components/ui/status'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader } from '@/features/shared/page'
import { NoWorkspaceState } from '@/features/shared/no-workspace'
import { approvalsApi } from '@/features/approvals/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/utils'
import type { ApprovalDecision, ApprovalRead } from '@/types/api'

const STATUS_FILTERS = [
  { value: 'pending', label: 'Pending' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'changes_requested', label: 'Changes requested' },
  { value: 'executed', label: 'Executed' },
  { value: 'expired', label: 'Expired' },
  { value: '', label: 'All requests' },
]

const RISK_TONE: Record<string, 'neutral' | 'info' | 'warning' | 'danger'> = {
  low: 'neutral',
  medium: 'info',
  high: 'warning',
  critical: 'danger',
}

function statusTone(status: string): 'neutral' | 'info' | 'success' | 'warning' | 'danger' {
  switch (status) {
    case 'pending':
      return 'warning'
    case 'approved':
    case 'executed':
      return 'success'
    case 'rejected':
    case 'revoked':
      return 'danger'
    case 'changes_requested':
      return 'info'
    default:
      return 'neutral'
  }
}

export function ApprovalsPage() {
  const { activeWorkspace, can } = useWorkspace()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [message, setMessage] = useState<string | null>(null)
  const workspaceId = activeWorkspace?.id ?? ''
  const mayDecide = can('approval.decide')

  const approvals = useQuery({
    queryKey: ['approvals', workspaceId, status],
    queryFn: () =>
      approvalsApi.list({ workspaceId, status: status || undefined, limit: 50 }),
    enabled: Boolean(workspaceId),
    retry: false,
    refetchInterval: 15_000,
  })

  const decide = useMutation({
    mutationFn: (payload: { id: string; decision: ApprovalDecision; hash: string }) =>
      approvalsApi.decide(payload.id, {
        decision: payload.decision,
        arguments_hash: payload.hash,
        note: notes[payload.id]?.trim() || null,
      }),
    onSuccess: async (result) => {
      setMessage(result.message)
      await queryClient.invalidateQueries({ queryKey: ['approvals'] })
      await queryClient.invalidateQueries({ queryKey: ['runs'] })
    },
    onError: (error) => {
      setMessage(
        error instanceof ApiError ? error.message : 'The decision could not be recorded.',
      )
    },
  })

  if (!activeWorkspace) return <NoWorkspaceState module="Approvals" />

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <PageHeader
        title="Approvals"
        description="Every protected action waits here. A decision is bound to the exact payload that was reviewed, so approving one action can never authorise another."
        actions={
          <Button
            size="sm"
            variant="secondary"
            onClick={() => void approvals.refetch()}
            loading={approvals.isFetching}
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            Refresh
          </Button>
        }
      />

      {message ? (
        <Notice tone="info" title="Decision recorded" className="mb-4">
          {message}
        </Notice>
      ) : null}

      {!mayDecide ? (
        <Notice tone="warning" title="Read-only access" className="mb-4">
          Your role can inspect approval requests but not decide them.
        </Notice>
      ) : null}

      <Card>
        <CardHeader
          title="Approval queue"
          description="Pending requests first. Each one shows the tool, the exact arguments and the payload hash."
          actions={
            <Select
              aria-label="Filter approvals by status"
              value={status}
              className="h-8 w-44 text-xs"
              onChange={(event) => setStatus(event.target.value)}
            >
              {STATUS_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          }
        />

        {approvals.isLoading ? (
          <LoadingState label="Loading approval requests…" />
        ) : approvals.isError ? (
          <ErrorState
            title="Approvals unavailable"
            message={
              approvals.error instanceof ApiError
                ? approvals.error.message
                : 'The approval queue could not be loaded.'
            }
            onRetry={() => void approvals.refetch()}
          />
        ) : (approvals.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            icon={<ShieldCheck className="size-5" aria-hidden="true" />}
            title="Nothing waiting for a decision"
            description="Requests appear here when a run proposes a protected action. Read-only tools never need one."
            action={
              <Button asChild size="sm" variant="secondary">
                <Link to="/runs">Open Runs</Link>
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {approvals.data?.items.map((approval) => (
              <ApprovalCard
                key={approval.id}
                approval={approval}
                mayDecide={mayDecide}
                note={notes[approval.id] ?? ''}
                onNoteChange={(value) =>
                  setNotes((current) => ({ ...current, [approval.id]: value }))
                }
                onDecide={(decision) =>
                  decide.mutate({
                    id: approval.id,
                    decision,
                    hash: approval.canonical_arguments_hash,
                  })
                }
                pending={decide.isPending}
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  )
}

function ApprovalCard({
  approval,
  mayDecide,
  note,
  onNoteChange,
  onDecide,
  pending,
}: {
  approval: ApprovalRead
  mayDecide: boolean
  note: string
  onNoteChange: (value: string) => void
  onDecide: (decision: ApprovalDecision) => void
  pending: boolean
}) {
  const decidable = approval.status === 'pending' && !approval.is_expired

  return (
    <li className="space-y-3 px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <code className="font-mono text-sm">{approval.tool_name}</code>
        <Badge tone={RISK_TONE[approval.risk_level] ?? 'neutral'}>
          <ShieldAlert className="size-2.5" aria-hidden="true" />
          {approval.risk_level} risk
        </Badge>
        <Badge tone={statusTone(approval.status)}>{approval.status.replace(/_/g, ' ')}</Badge>
        <span className="ml-auto flex items-center gap-1 text-[11px] text-[var(--muted-foreground)]">
          <Clock className="size-3" aria-hidden="true" />
          {approval.is_expired ? 'expired' : `expires ${formatDateTime(approval.expires_at)}`}
        </span>
      </div>

      <p className="text-[11px] text-[var(--muted-foreground)]">
        Proposed for run{' '}
        <Link className="font-mono text-[var(--primary)] hover:underline" to={`/runs/${approval.run_id}`}>
          {approval.run_id.slice(0, 8)}
        </Link>{' '}
        · policy v{approval.policy_version} · requested {formatDateTime(approval.created_at)}
      </p>

      <JsonView value={approval.arguments} label="Exact proposed arguments" />

      <p className="break-all font-mono text-[10px] text-[var(--muted-foreground)]">
        payload hash: {approval.canonical_arguments_hash}
      </p>

      {approval.review_note ? (
        <p className="rounded-md border border-[var(--border)] bg-[var(--surface-muted)]/40 px-3 py-2 text-xs">
          <span className="font-medium">Reviewer note:</span> {approval.review_note}
        </p>
      ) : null}

      {decidable && mayDecide ? (
        <div className="space-y-2 rounded-md border border-[var(--border)] p-3">
          <Label htmlFor={`note-${approval.id}`}>Decision note (optional)</Label>
          <Textarea
            id={`note-${approval.id}`}
            rows={2}
            value={note}
            onChange={(event) => onNoteChange(event.target.value)}
            placeholder="Why this action is (or is not) safe to run."
            className="text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              loading={pending}
              disabled={pending}
              onClick={() => onDecide('approve')}
            >
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              Approve this exact action
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={pending}
              onClick={() => onDecide('reject')}
            >
              <XCircle className="size-3.5" aria-hidden="true" />
              Reject
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={pending}
              onClick={() => onDecide('request_changes')}
            >
              Request changes
            </Button>
          </div>
          <p className="text-[10px] text-[var(--muted-foreground)]">
            The decision is bound to the payload hash above. If the proposed action changed in the
            meantime, the server refuses it.
          </p>
        </div>
      ) : null}

      {approval.status === 'pending' && approval.is_expired ? (
        <Notice tone="warning" title="Expired">
          This request can no longer be decided. The run stays paused until it is cancelled.
        </Notice>
      ) : null}
    </li>
  )
}
