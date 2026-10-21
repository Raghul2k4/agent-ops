import { forwardRef, type SelectHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { className, invalid, children, ...props },
  ref,
) {
  return (
    <select
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'h-9 w-full rounded-md border bg-[var(--surface)] px-2.5 text-sm text-[var(--foreground)] transition-colors',
        'focus-visible:border-[var(--primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
        'disabled:cursor-not-allowed disabled:opacity-60',
        invalid
          ? 'border-[var(--danger)] focus-visible:ring-[var(--danger)]'
          : 'border-[var(--border)]',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
})
