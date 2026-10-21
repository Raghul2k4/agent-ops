import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Sparkles } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { ErrorState, Skeleton } from '@/components/ui/states'
import { Notice } from '@/components/ui/status'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import { demoDataApi } from '@/features/tools/api'
import type { DemoSeedResponse } from '@/types/api'

/**
 * Explicit, audited seeding of the fictional CRM dataset.
 *
 * Demo rows carry `is_demo = true` and are never inserted implicitly; the card
 * states clearly that this data is synthetic.
 */
export function DemoDataCard({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient()
  const { can } = useWorkspace()

  const status = useQuery({
    queryKey: ['demo-data', workspaceId],
    queryFn: () => demoDataApi.status(workspaceId),
    retry: false,
  })

  const seed = useMutation({
    mutationFn: () => demoDataApi.seed(workspaceId),
    onSuccess: async (result: DemoSeedResponse) => {
      queryClient.setQueryData(['demo-data', workspaceId], {
        seeded: true,
        customers: result.customers,
        deals: result.deals,
      })
      await queryClient.invalidateQueries({ queryKey: ['demo-data', workspaceId] })
    },
  })

  const allowed = can('workspace.update')

  return (
    <Card>
      <CardHeader
        title="Synthetic demonstration data"
        description="Fictional CRM records used by the built-in tools and the Sales Operations demo."
        actions={
          status.data?.seeded ? <Badge tone="success">seeded</Badge> : <Badge>not seeded</Badge>
        }
      />
      <CardContent className="space-y-3">
        {status.isLoading ? (
          <Skeleton className="h-12 w-full" />
        ) : status.isError ? (
          <ErrorState
            title="Demo data status unavailable"
            message={
              status.error instanceof ApiError
                ? status.error.message
                : 'The demo dataset could not be inspected.'
            }
            onRetry={() => void status.refetch()}
          />
        ) : status.data?.seeded ? (
          <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--muted-foreground)]">
            <span className="inline-flex items-center gap-1.5">
              <Database className="size-3.5" aria-hidden="true" />
              {status.data.customers} customers
            </span>
            <span>{status.data.deals} deals</span>
            <Badge tone="warning">is_demo = true</Badge>
          </div>
        ) : (
          <Notice tone="info" title="Nothing is seeded automatically">
            The CRM tools return real rows from this workspace. Load the fictional dataset to try
            the Sales Operations Assistant; every row is labelled as demonstration data.
          </Notice>
        )}

        {seed.isError ? (
          <Notice tone="danger" title="Seeding failed">
            {seed.error instanceof ApiError ? seed.error.message : 'The dataset was not created.'}
          </Notice>
        ) : null}
        {seed.data ? (
          <Notice tone="success" title={seed.data.created ? 'Demo dataset created' : 'Already seeded'}>
            {seed.data.created
              ? `${seed.data.customers} customers, ${seed.data.deals} deals, ${seed.data.companies} companies and ${seed.data.contacts} contacts were inserted.`
              : 'This workspace already contained the synthetic dataset; no rows were duplicated.'}
          </Notice>
        ) : null}

        {!status.data?.seeded ? (
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              loading={seed.isPending}
              disabled={!allowed || seed.isPending}
              onClick={() => seed.mutate()}
            >
              <Sparkles className="size-3.5" aria-hidden="true" />
              Load synthetic demo data
            </Button>
            {!allowed ? (
              <span className="text-xs text-[var(--muted-foreground)]">
                Requires a workspace administrator.
              </span>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
