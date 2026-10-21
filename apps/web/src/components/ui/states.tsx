import type { ReactNode } from 'react'
import { AlertTriangle, Inbox, Loader2, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn('animate-pulse rounded-md bg-[var(--surface-muted)]', className)}
      aria-hidden="true"
    />
  )
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div
      className="flex items-center justify-center gap-2 py-16 text-sm text-[var(--muted-foreground)]"
      role="status"
      aria-live="polite"
    >
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      {label}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string
  description?: string
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-[var(--muted-foreground)]">
        {icon ?? <Inbox className="size-5" aria-hidden="true" />}
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--foreground)]">{title}</p>
        {description ? (
          <p className="mx-auto mt-1 max-w-md text-xs text-[var(--muted-foreground)]">{description}</p>
        ) : null}
      </div>
      {action}
    </div>
  )
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  retrying,
}: {
  title?: string
  message?: string
  onRetry?: () => void
  retrying?: boolean
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center"
      role="alert"
    >
      <div className="rounded-lg border border-[var(--danger)]/30 bg-[var(--danger-muted)] p-3 text-[var(--danger)]">
        <AlertTriangle className="size-5" aria-hidden="true" />
      </div>
      <div>
        <p className="text-sm font-medium text-[var(--foreground)]">{title}</p>
        {message ? (
          <p className="mx-auto mt-1 max-w-md text-xs text-[var(--muted-foreground)]">{message}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry} loading={retrying}>
          {!retrying ? <RefreshCw className="size-3.5" aria-hidden="true" /> : null}
          Try again
        </Button>
      ) : null}
    </div>
  )
}
