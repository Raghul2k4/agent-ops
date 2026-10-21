import { NavLink } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { NAVIGATION } from '@/routes/navigation'
import { cn } from '@/lib/utils'

export function Sidebar({
  collapsed,
  onToggle,
}: {
  collapsed: boolean
  onToggle: () => void
}) {
  return (
    <aside
      className={cn(
        'flex h-full shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)] transition-[width] duration-200',
        collapsed ? 'w-16' : 'w-60',
      )}
      aria-label="Primary navigation"
    >
      <div className="flex h-14 items-center gap-2 border-b border-[var(--border)] px-3">
        <div className="grid size-7 shrink-0 place-items-center rounded-md bg-[var(--primary)] text-[var(--primary-foreground)]">
          <span className="text-xs font-bold">A</span>
        </div>
        {!collapsed ? (
          <span className="truncate text-sm font-semibold tracking-tight">AgentOps</span>
        ) : null}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {NAVIGATION.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.id}>
                <NavLink
                  to={item.path}
                  end={item.path === '/'}
                  title={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    cn(
                      'group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition-colors',
                      isActive
                        ? 'bg-[var(--primary-muted)] text-[var(--primary)]'
                        : 'text-[var(--muted-foreground)] hover:bg-[var(--surface-muted)] hover:text-[var(--foreground)]',
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  {!collapsed ? <span className="truncate">{item.label}</span> : null}
                  {!collapsed && !item.available ? (
                    <Badge tone="warning" className="ml-auto shrink-0">
                      {item.milestone}
                    </Badge>
                  ) : null}
                </NavLink>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="border-t border-[var(--border)] p-2">
        <button
          type="button"
          onClick={onToggle}
          className="flex w-full items-center justify-center rounded-md px-2 py-1.5 text-xs text-[var(--muted-foreground)] hover:bg-[var(--surface-muted)] hover:text-[var(--foreground)]"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '»' : '« Collapse'}
        </button>
      </div>
    </aside>
  )
}
