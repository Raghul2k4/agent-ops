import { Building2, Check, ChevronDown, Plus, Settings2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { cn } from '@/lib/utils'

export function WorkspaceSwitcher() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const { workspaces, activeWorkspace, setActiveWorkspaceId, isLoading } = useWorkspace()

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [])

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
          {isLoading ? 'Loading…' : (activeWorkspace?.name ?? 'No workspace')}
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
              {workspaces.map((workspace) => {
                const isActive = workspace.id === activeWorkspace?.id
                return (
                  <li key={workspace.id}>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setActiveWorkspaceId(workspace.id)
                        setOpen(false)
                      }}
                      className={cn(
                        'flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-[var(--surface-muted)]',
                        isActive
                          ? 'text-[var(--primary)]'
                          : 'text-[var(--foreground)]',
                      )}
                    >
                      <span className="flex min-w-0 items-center gap-1.5">
                        {isActive ? (
                          <Check className="size-3 shrink-0" aria-hidden="true" />
                        ) : (
                          <span className="size-3 shrink-0" aria-hidden="true" />
                        )}
                        <span className="truncate">{workspace.name}</span>
                      </span>
                      {workspace.role ? (
                        <span className="shrink-0 text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
                          {workspace.role}
                        </span>
                      ) : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
          {activeWorkspace ? (
            <div className="mt-1 border-t border-[var(--border)] pt-1">
              <Button asChild variant="ghost" size="sm" className="w-full justify-start">
                <Link to={`/workspace/${activeWorkspace.id}`} onClick={() => setOpen(false)}>
                  <Settings2 className="size-3.5" aria-hidden="true" />
                  Workspace settings
                </Link>
              </Button>
            </div>
          ) : null}
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
