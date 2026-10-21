import type { HTMLAttributes, ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info'

const TONE_CLASSES: Record<Tone, string> = {
  neutral:
    'bg-[var(--surface-muted)] text-[var(--muted-foreground)] border-[var(--border)]',
  primary: 'bg-[var(--primary-muted)] text-[var(--primary)] border-[var(--primary)]/30',
  success: 'bg-[var(--success-muted)] text-[var(--success)] border-[var(--success)]/30',
  warning: 'bg-[var(--warning-muted)] text-[var(--warning)] border-[var(--warning)]/30',
  danger: 'bg-[var(--danger-muted)] text-[var(--danger)] border-[var(--danger)]/30',
  info: 'bg-[var(--primary-muted)] text-[var(--secondary)] border-[var(--secondary)]/30',
}

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  children: ReactNode
}

export function Badge({ tone = 'neutral', className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4',
        TONE_CLASSES[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  )
}

/** A status dot paired with a text label - status is never conveyed by colour alone. */
export function StatusDot({ tone = 'neutral', label }: { tone?: Tone; label: string }) {
  const dotColor: Record<Tone, string> = {
    neutral: 'bg-[var(--muted-foreground)]',
    primary: 'bg-[var(--primary)]',
    success: 'bg-[var(--success)]',
    warning: 'bg-[var(--warning)]',
    danger: 'bg-[var(--danger)]',
    info: 'bg-[var(--secondary)]',
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--muted-foreground)]">
      <span className={cn('size-1.5 rounded-full', dotColor[tone])} aria-hidden="true" />
      {label}
    </span>
  )
}
