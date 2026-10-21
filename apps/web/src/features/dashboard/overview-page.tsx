import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Building2, Database, Server, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useSession } from '@/features/auth/session-provider'
import { PageHeader } from '@/features/shared/page'
import { rootGet } from '@/lib/api-client'
import type { HealthStatus, ReadinessStatus } from '@/types/api'

export function OverviewPage() {
  const { user, workspaces, isLoading } = useSession()

  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => rootGet<HealthStatus>('/health'),
    retry: false,
    refetchInterval: 30_000,
  })

  const readiness = useQuery({
    queryKey: ['readiness'],
    queryFn: () => rootGet<ReadinessStatus>('/ready'),
    retry: false,
    refetchInterval: 30_000,
  })

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <PageHeader
        title={user ? `Welcome back, ${user.display_name.split(' ')[0]}` : 'Overview'}
        description="Platform foundation is live. Execution modules arrive in the milestones listed in PLAN.md."
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader title="API service" description="Liveness of the backend process" />
          <CardContent>
            {health.isLoading ? (
              <Skeleton className="h-5 w-32" />
            ) : health.isError ? (
              <StatusDot tone="danger" label="Unreachable" />
            ) : (
              <div className="space-y-1">
                <StatusDot tone="success" label={health.data?.status ?? 'unknown'} />
                <p className="font-mono text-xs text-[var(--muted-foreground)]">
                  v{health.data?.version} · {health.data?.environment}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="Dependencies" description="Readiness checks" />
          <CardContent>
            {readiness.isLoading ? (
              <Skeleton className="h-5 w-32" />
            ) : readiness.isError ? (
              <StatusDot tone="danger" label="Unreachable" />
            ) : (
              <ul className="space-y-1.5">
                {Object.entries(readiness.data?.checks ?? {}).map(([name, state]) => (
                  <li key={name}>
                    <StatusDot
                      tone={state === 'ok' ? 'success' : 'danger'}
                      label={`${name}: ${state}`}
                    />
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader title="Your workspaces" description="Tenant boundaries you can access" />
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-5 w-24" />
            ) : (
              <p className="tabular text-2xl font-semibold">{workspaces.length}</p>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Workspaces"
          description="Agents, workflows, runs, evaluations and audit records are scoped to a workspace."
          actions={
            <Button asChild size="sm">
              <Link to="/workspace/new">
                <Building2 className="size-3.5" aria-hidden="true" />
                New workspace
              </Link>
            </Button>
          }
        />
        {isLoading ? (
          <CardContent className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </CardContent>
        ) : workspaces.length === 0 ? (
          <EmptyState
            title="No workspace yet"
            description="A workspace is the tenant boundary for everything in AgentOps. Create one to continue."
            icon={<Building2 className="size-5" aria-hidden="true" />}
            action={
              <Button asChild size="sm">
                <Link to="/workspace/new">Create workspace</Link>
              </Button>
            }
          />
        ) : (
          <ul className="divide-y divide-[var(--border)]">
            {workspaces.map((workspace) => (
              <li key={workspace.id}>
                <Link
                  to={`/workspace/${workspace.id}`}
                  className="flex items-center justify-between gap-3 px-5 py-3 transition-colors hover:bg-[var(--surface-muted)]"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--foreground)]">
                      {workspace.name}
                    </p>
                    <p className="font-mono text-xs text-[var(--muted-foreground)]">
                      {workspace.slug}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    {workspace.member_count !== null ? (
                      <span className="text-xs text-[var(--muted-foreground)]">
                        {workspace.member_count} member
                        {workspace.member_count === 1 ? '' : 's'}
                      </span>
                    ) : null}
                    <Badge tone="primary">{workspace.role}</Badge>
                    <ArrowRight className="size-4 text-[var(--muted-foreground)]" aria-hidden="true" />
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader
            title="What is working now"
            description="Delivered and verified in milestone M1."
          />
          <CardContent>
            <ul className="space-y-2 text-sm">
              {[
                'Supabase Auth sign-in and sign-out with verified bearer tokens',
                'Cryptographic token verification against the project JWKS',
                'Workspace creation, membership and role management',
                'Tenant isolation: non-members receive "not found", never data',
                'Append-only audit trail for authentication and workspace events',
                'Liveness and readiness probes with dependency checks',
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-[var(--success)]" aria-hidden="true" />
                  <span className="text-[var(--foreground)]">{item}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader
            title="Next milestones"
            description="Each module is enabled only when its backend, persistence and tests exist."
          />
          <CardContent>
            <ul className="space-y-3">
              {[
                { icon: Server, label: 'M2 · Agents, model providers, tool registry, runtime' },
                { icon: Server, label: 'M3 · Approvals, budgets, policies, traces' },
                { icon: Server, label: 'M4 · Visual workflow builder and execution engine' },
                { icon: Database, label: 'M5-M6 · Dashboard, Model Lab, evaluations, knowledge' },
              ].map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-sm">
                  <item.icon className="size-3.5 shrink-0 text-[var(--muted-foreground)]" aria-hidden="true" />
                  <span className="text-[var(--muted-foreground)]">{item.label}</span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-xs text-[var(--muted-foreground)]">
              Progress is tracked in <code className="font-mono">docs/roadmap.md</code>.
            </p>
          </CardContent>
        </Card>
      </div>

      {health.isError ? (
        <div className="mt-4">
          <ErrorState
            title="The API is not reachable"
            message="Start the backend with: uvicorn app.main:app --reload --port 8000"
            onRetry={() => void health.refetch()}
          />
        </div>
      ) : null}
    </div>
  )
}
