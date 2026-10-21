import { cn } from '@/lib/utils'

export interface SegmentedOption<T extends string> {
  value: T
  label: string
  count?: number
}

/**
 * Accessible segmented control implemented with radio inputs.
 * Used for tabs where the panels are rendered inline.
 */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T
  onChange: (value: T) => void
  options: SegmentedOption<T>[]
  label: string
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex flex-wrap items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--surface-muted)] p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              'rounded px-2.5 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus-ring)]',
              active
                ? 'bg-[var(--surface-elevated)] text-[var(--foreground)] shadow-[var(--shadow-sm)]'
                : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)]',
            )}
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="ml-1.5 text-[10px] text-[var(--muted-foreground)]">
                {option.count}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}
