import { forwardRef, type TextareaHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { className, invalid, rows = 4, ...props },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(
        'w-full resize-y rounded-md border bg-[var(--surface)] px-3 py-2 font-mono text-xs leading-relaxed text-[var(--foreground)] placeholder:font-sans placeholder:text-[var(--muted-foreground)] transition-colors',
        'focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
        'disabled:cursor-not-allowed disabled:opacity-60',
        invalid
          ? 'border-[var(--danger)] focus-visible:ring-[var(--danger)]'
          : 'border-[var(--border)]',
        className,
      )}
      {...props}
    />
  )
})
