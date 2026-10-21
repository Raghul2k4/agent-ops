import type { LabelHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

export interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean
}

export function Label({ className, required, children, ...props }: LabelProps) {
  return (
    <label
      className={cn(
        'text-xs font-medium text-[var(--muted-foreground)]',
        className,
      )}
      {...props}
    >
      {children}
      {required ? (
        <span className="ml-0.5 text-[var(--danger)]" aria-hidden="true">
          *
        </span>
      ) : null}
    </label>
  )
}

export function FieldError({ children }: { children?: React.ReactNode }) {
  if (!children) return null
  return (
    <p className="text-xs text-[var(--danger)]" role="alert">
      {children}
    </p>
  )
}

export function FieldHint({ children }: { children?: React.ReactNode }) {
  if (!children) return null
  return <p className="text-xs text-[var(--muted-foreground)]">{children}</p>
}
