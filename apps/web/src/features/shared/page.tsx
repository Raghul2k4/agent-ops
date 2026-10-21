import type { ReactNode } from 'react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

/**
 * Renders an explicit "not available yet" state for a module whose milestone
 * has not been delivered. The application never shows a fake screen.
 */
export function PlannedModulePage({
  title,
  milestone,
  summary,
  capabilities,
}: {
  title: string
  milestone: string
  summary: string
  capabilities: string[]
}) {
  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <Badge tone="warning">Scheduled for {milestone}</Badge>
      </div>

      <Card>
        <CardHeader
          title="This module is not built yet"
          description="Every control in AgentOps must do something real. This screen is a placeholder that states the current status instead of faking data."
        />
        <CardContent className="space-y-4">
          <p className="text-sm text-[var(--muted-foreground)]">{summary}</p>
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-[var(--muted-foreground)]">
              Planned capabilities
            </p>
            <ul className="space-y-1.5 text-sm text-[var(--foreground)]">
              {capabilities.map((capability) => (
                <li key={capability} className="flex items-start gap-2">
                  <span aria-hidden="true" className="mt-1.5 size-1 rounded-full bg-[var(--primary)]" />
                  {capability}
                </li>
              ))}
            </ul>
          </div>
          <p className="text-xs text-[var(--muted-foreground)]">
            See <code className="font-mono">PLAN.md</code> in the repository root for the milestone
            breakdown and its exit criteria.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-[var(--foreground)]">{title}</h1>
        {description ? (
          <p className="mt-1 text-sm text-[var(--muted-foreground)]">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  )
}
