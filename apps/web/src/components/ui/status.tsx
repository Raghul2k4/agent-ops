import { AlertTriangle, CheckCircle2, Info, ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'

const RUN_STATUS_TONES: Record<string, Tone> = {
  queued: 'neutral',
  running: 'primary',
  succeeded: 'success',
  failed: 'danger',
  cancelled: 'warning',
  awaiting_approval: 'warning',
}

export function runStatusTone(status: string): Tone {
  return RUN_STATUS_TONES[status] ?? 'neutral'
}

export function RunStatusBadge({ status }: { status: string }) {
  return (
    <Badge tone={runStatusTone(status)}>
      <span
        className={cn(
          'size-1.5 rounded-full bg-current',
          status === 'running' ? 'animate-pulse' : '',
        )}
        aria-hidden="true"
      />
      {status.replace(/_/g, ' ')}
    </Badge>
  )
}

const RISK_TONES: Record<string, Tone> = {
  low: 'success',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
}

export function RiskBadge({ level }: { level: string }) {
  return <Badge tone={RISK_TONES[level] ?? 'neutral'}>{level} risk</Badge>
}

const PROVIDER_STATUS_TONES: Record<string, Tone> = {
  connected: 'success',
  unconfigured: 'neutral',
  error: 'danger',
  disabled: 'warning',
}

export function ProviderStatusBadge({ status }: { status: string }) {
  return <Badge tone={PROVIDER_STATUS_TONES[status] ?? 'neutral'}>{status}</Badge>
}

const EVENT_STATUS_TONES: Record<string, Tone> = {
  ok: 'success',
  warning: 'warning',
  error: 'danger',
  cancelled: 'warning',
  info: 'neutral',
}

export function EventStatusBadge({ status }: { status: string }) {
  return <Badge tone={EVENT_STATUS_TONES[status] ?? 'neutral'}>{status}</Badge>
}

export function Notice({
  tone = 'info',
  title,
  children,
  className,
}: {
  tone?: 'info' | 'warning' | 'danger' | 'success'
  title?: string
  children: ReactNode
  className?: string
}) {
  const styles: Record<string, string> = {
    info: 'border-[var(--primary)]/30 bg-[var(--primary-muted)] text-[var(--foreground)]',
    warning: 'border-[var(--warning)]/30 bg-[var(--warning-muted)] text-[var(--foreground)]',
    danger: 'border-[var(--danger)]/30 bg-[var(--danger-muted)] text-[var(--foreground)]',
    success: 'border-[var(--success)]/30 bg-[var(--success-muted)] text-[var(--foreground)]',
  }
  const Icon =
    tone === 'danger'
      ? ShieldAlert
      : tone === 'warning'
        ? AlertTriangle
        : tone === 'success'
          ? CheckCircle2
          : Info
  const iconColor: Record<string, string> = {
    info: 'text-[var(--primary)]',
    warning: 'text-[var(--warning)]',
    danger: 'text-[var(--danger)]',
    success: 'text-[var(--success)]',
  }

  return (
    <div
      className={cn('flex items-start gap-2.5 rounded-md border px-3 py-2.5', styles[tone], className)}
      role={tone === 'danger' ? 'alert' : 'status'}
    >
      <Icon className={cn('mt-0.5 size-4 shrink-0', iconColor[tone])} aria-hidden="true" />
      <div className="min-w-0 space-y-1">
        {title ? <p className="text-xs font-semibold">{title}</p> : null}
        <div className="text-xs leading-relaxed text-[var(--muted-foreground)]">{children}</div>
      </div>
    </div>
  )
}
