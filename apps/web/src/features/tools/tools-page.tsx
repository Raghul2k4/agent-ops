import { useQuery } from '@tanstack/react-query'
import { Search, ShieldCheck, Wrench } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { JsonView } from '@/components/ui/json-view'
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/states'
import { Notice, RiskBadge } from '@/components/ui/status'
import { PageHeader } from '@/features/shared/page'
import { NoWorkspaceState } from '@/features/shared/no-workspace'
import { toolsApi } from '@/features/tools/api'
import { DemoDataCard } from '@/features/tools/demo-data-card'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'

export function ToolsPage() {
  const { activeWorkspace } = useWorkspace()
  const [search, setSearch] = useState('')
  const workspaceId = activeWorkspace?.id ?? ''

  const tools = useQuery({
    queryKey: ['tools', workspaceId],
    queryFn: () => toolsApi.list(workspaceId),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const filtered = useMemo(() => {
    const items = tools.data ?? []
    const query = search.trim().toLowerCase()
    if (!query) return items
    return items.filter(
      (tool) =>
        tool.name.toLowerCase().includes(query) ||
        tool.description.toLowerCase().includes(query) ||
        tool.risk_level.toLowerCase().includes(query),
    )
  }, [tools.data, search])

  if (!activeWorkspace) return <NoWorkspaceState module="Tools & Integrations" />

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-8">
      <PageHeader
        title="Tools & Integrations"
        description="The server-side registry of executable tools. A database row is descriptive only; behaviour is resolved from code, so a model can never inject a new tool."
      />

      <Notice tone="info" title="Read-only registry in this milestone" className="mb-4">
        Custom executable tools, connector credentials and the integration directory arrive with the
        automation milestone. Tools listed here are the built-in CRM and knowledge contracts the
        runtime can execute today.
      </Notice>

      <Card className="mb-4">
        <CardHeader
          title="Registered tools"
          description="Arguments are validated with a strict schema, then permissions and approval requirements are enforced before execution."
          actions={<Badge tone="neutral">{tools.data?.length ?? 0} tools</Badge>}
        />
        <CardContent>
          <div className="relative mb-4 max-w-sm">
            <Search
              className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]"
              aria-hidden="true"
            />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Filter by name, description or risk"
              className="pl-8"
              aria-label="Filter tools"
            />
          </div>

          {tools.isLoading ? (
            <LoadingState label="Loading the tool registry…" />
          ) : tools.isError ? (
            <ErrorState
              title="Tool registry unavailable"
              message={
                tools.error instanceof ApiError
                  ? tools.error.message
                  : 'The tool registry could not be loaded.'
              }
              onRetry={() => void tools.refetch()}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Wrench className="size-5" aria-hidden="true" />}
              title={search ? 'No tools match this filter' : 'No tools registered'}
              description={
                search
                  ? 'Try a different name or clear the filter.'
                  : 'The built-in registry is populated lazily when a workspace first reads it.'
              }
              action={
                search ? (
                  <button
                    type="button"
                    className="text-xs text-[var(--primary)] hover:underline"
                    onClick={() => setSearch('')}
                  >
                    Clear filter
                  </button>
                ) : undefined
              }
            />
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {filtered.map((tool) => (
                <Card key={tool.id} className="bg-[var(--surface-muted)]/30">
                  <CardContent className="space-y-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="flex flex-wrap items-center gap-1.5 font-mono text-sm font-medium">
                          <Wrench className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
                          {tool.name}
                        </p>
                        <p className="mt-1 text-xs leading-relaxed text-[var(--muted-foreground)]">
                          {tool.description}
                        </p>
                      </div>
                      <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                        <RiskBadge level={tool.risk_level} />
                        {tool.requires_approval ? (
                          <Badge tone="warning">
                            <ShieldCheck className="size-2.5" aria-hidden="true" />
                            approval
                          </Badge>
                        ) : (
                          <Badge tone="success">no approval</Badge>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone="neutral">v{tool.version}</Badge>
                      <Badge tone="neutral">{tool.timeout_seconds}s timeout</Badge>
                      <Badge tone="neutral">{tool.max_retries} retries</Badge>
                      <Badge tone={tool.idempotent ? 'success' : 'warning'}>
                        {tool.idempotent ? 'idempotent' : 'not idempotent'}
                      </Badge>
                      <Badge tone={tool.enabled ? 'success' : 'neutral'}>
                        {tool.enabled ? 'enabled' : 'disabled'}
                      </Badge>
                      {tool.is_builtin ? <Badge tone="primary">built-in</Badge> : null}
                    </div>

                    <p className="text-[11px] text-[var(--muted-foreground)]">
                      Permissions:{' '}
                      <span className="font-mono">
                        {tool.required_permissions.join(', ') || 'none declared'}
                      </span>
                    </p>

                    <div className="space-y-2">
                      <JsonView value={tool.input_schema} label="Input schema" />
                      <JsonView value={tool.output_schema} label="Output schema" />
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <DemoDataCard workspaceId={workspaceId} />
    </div>
  )
}
