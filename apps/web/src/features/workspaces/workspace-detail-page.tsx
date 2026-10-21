import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { UserPlus } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardHeader } from '@/components/ui/card'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { PageHeader } from '@/features/shared/page'
import { PolicyPanel } from '@/features/policies/policy-panel'
import { api, ApiError } from '@/lib/api-client'
import type { MemberRead, WorkspaceRead } from '@/types/api'
import { formatDateTime } from '@/lib/utils'

export function WorkspaceDetailPage() {
  const { workspaceId = '' } = useParams()
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const workspaceQuery = useQuery({
    queryKey: ['workspace', workspaceId],
    queryFn: () => api.get<WorkspaceRead>(`/workspaces/${workspaceId}`),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const membersQuery = useQuery({
    queryKey: ['workspace-members', workspaceId],
    queryFn: () => api.get<MemberRead[]>(`/workspaces/${workspaceId}/members`),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const roleMutation = useMutation({
    mutationFn: (payload: { memberId: string; role: string }) =>
      api.patch<MemberRead>(
        `/workspaces/${workspaceId}/members/${payload.memberId}`,
        { role: payload.role },
      ),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['workspace-members', workspaceId] })
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'Could not update the member role.',
      )
    },
  })

  if (workspaceQuery.isLoading) return <LoadingState label="Loading workspace…" />
  if (workspaceQuery.isError) {
    return (
      <div className="px-6 py-8">
        <ErrorState
          title="Workspace not available"
          message={
            workspaceQuery.error instanceof ApiError
              ? workspaceQuery.error.message
              : 'The workspace could not be loaded.'
          }
          onRetry={() => void workspaceQuery.refetch()}
        />
      </div>
    )
  }

  const workspace = workspaceQuery.data

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <PageHeader
        title={workspace?.name ?? 'Workspace'}
        description={`Slug: ${workspace?.slug} · Your role: ${workspace?.role ?? 'unknown'}`}
        actions={<Badge tone="primary">{workspace?.member_count ?? 0} members</Badge>}
      />

      {error ? (
        <div
          className="mb-4 rounded-md border border-[var(--danger)]/30 bg-[var(--danger-muted)] px-3 py-2 text-xs text-[var(--danger)]"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <Card>
        <CardHeader
          title="Members"
          description="Roles are enforced on the server for every request."
          actions={
            <Button variant="secondary" size="sm" disabled title="Member invitations arrive in M3">
              <UserPlus className="size-3.5" aria-hidden="true" />
              Add member
            </Button>
          }
        />
        {membersQuery.isLoading ? (
          <LoadingState label="Loading members…" />
        ) : membersQuery.isError ? (
          <ErrorState
            title="Members unavailable"
            message={
              membersQuery.error instanceof ApiError
                ? membersQuery.error.message
                : 'The member list could not be loaded.'
            }
            onRetry={() => void membersQuery.refetch()}
          />
        ) : (membersQuery.data?.length ?? 0) === 0 ? (
          <EmptyState title="No members yet" description="Invite your team to collaborate." />
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {membersQuery.data?.map((member) => (
              <li
                key={member.id}
                className="flex flex-wrap items-center justify-between gap-3 px-5 py-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-[var(--foreground)]">
                    {member.display_name}
                  </p>
                  <p className="truncate text-xs text-[var(--muted-foreground)]">{member.email}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--muted-foreground)]">
                    since {formatDateTime(member.created_at)}
                  </span>
                  <Badge tone={member.role === 'owner' ? 'primary' : 'neutral'}>{member.role}</Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={
                      member.role === 'owner' ||
                      roleMutation.isPending ||
                      !['owner', 'admin'].includes(workspace?.role ?? '')
                    }
                    onClick={() =>
                      roleMutation.mutate({
                        memberId: member.id,
                        role: member.role === 'viewer' ? 'developer' : 'viewer',
                      })
                    }
                  >
                    {member.role === 'viewer' ? 'Make developer' : 'Make viewer'}
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <PolicyPanel />
    </div>
  )
}
