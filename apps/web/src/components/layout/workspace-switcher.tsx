import { useQuery } from '@tanstack/react-query'
import { Building2, Check, ChevronDown, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { api } from '@/lib/api-client'
import type { WorkspaceRead } from '@/types/api'
import { cn } from '@/lib/utils'

export function WorkspaceSwitcher() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  const workspacesQuery = useQuery({
    queryKey: ['workspaces'],
    queryFn: () => api.get<WorkspaceRead[]>('/workspaces'),
  })

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [])

  const workspaces = workspacesQuery.data ?? []

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex h-8 items-center gap-2 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2.5 text-xs font-medium text-[var(--foreground)] hover:bg-[var(--surface-muted)]"
      >
        <Building2 className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
        <span className="max-w-40 truncate">
          {workspaces.length > 0 ? workspaces[0]?.name : 'No workspace'}
        </span>
        <ChevronDown className="size-3.5 text-[var(--muted-foreground)]" aria-hidden="true" />
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute left-0 top-full z-50 mt-1 w-64 animate-in-fade rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-1 shadow-[var(--shadow-lg)]"
        >
          {workspaces.length === 0 ? (
            <p className="px-2 py-3 text-xs text-[var(--muted-foreground)]">
              You are not a member of any workspace yet.
            </p>
          ) : (
            <ul className="max-h-64 overflow-y-auto">
              {workspaces.map((workspace) => (
                <li key={workspace.id}>
                  <Link
                    role="menuitem"
                    to={`/workspace/${workspace.id}`}
                    onClick={() => setOpen(false)}
                    className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-xs text-[var(--foreground)] hover:bg-[var(--surface-muted)]"
                  >
                    <span className="truncate">{workspace.name}</span>
                    {workspace.role ? (
                      <span className="shrink-0 text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                        {workspace.role}
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-1 border-t border-[var(--border)] pt-1">
            <Button asChild variant="ghost" size="sm" className="w-full justify-start">
              <Link to="/workspace/new" onClick={() => setOpen(false)}>
                <Plus className="size-3.5" aria-hidden="true" />
                Create workspace
              </Link>
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function ActiveWorkspaceBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] text-[var(--muted-foreground)]">
      <Check className={cn('size-3 text-[var(--success)]')} aria-hidden="true" />
      {name}
    </span>
  )
}
