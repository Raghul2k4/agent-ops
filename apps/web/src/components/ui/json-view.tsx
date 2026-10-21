import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/lib/utils'

/** A collapsible, copyable JSON view for technical payloads. */
export function JsonView({
  value,
  label = 'JSON',
  defaultOpen = false,
  className,
}: {
  value: unknown
  label?: string
  defaultOpen?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(defaultOpen)
  const serialized = JSON.stringify(value, null, 2) ?? 'null'

  return (
    <div className={cn('rounded-md border border-[var(--border)]', className)}>
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
      >
        <span className="font-medium">{label}</span>
        <ChevronDown
          className={cn('size-3.5 transition-transform', open ? 'rotate-180' : '')}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <pre className="max-h-80 overflow-auto border-t border-[var(--border)] bg-[var(--background)] px-3 py-2 font-mono text-[11px] leading-relaxed text-[var(--foreground)]">
          {serialized}
        </pre>
      ) : null}
    </div>
  )
}

/** A compact summary of a payload without dumping the whole object. */
export function summarizePayload(payload: Record<string, unknown>): string {
  const preferred = ['tool', 'name', 'status', 'note', 'message', 'error', 'step']
  const parts = preferred
    .filter((key) => payload[key] !== undefined && payload[key] !== null)
    .map((key) => `${key}=${String(payload[key])}`)
  if (parts.length > 0) return parts.join(' · ')
  const serialized = JSON.stringify(payload)
  return serialized.length > 120 ? `${serialized.slice(0, 117)}…` : serialized
}
