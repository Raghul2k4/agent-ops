import { Command } from 'cmdk'
import { useNavigate } from 'react-router-dom'
import { useMemo } from 'react'

import { NAVIGATION } from '@/routes/navigation'
import { useSession } from '@/features/auth/session-provider'

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const { workspaces } = useSession()

  const items = useMemo(
    () => [
      ...NAVIGATION.map((item) => ({
        id: `nav-${item.id}`,
        label: item.label,
        group: 'Navigate',
        available: item.available,
        run: () => navigate(item.path),
      })),
      ...workspaces.map((workspace) => ({
        id: `ws-${workspace.id}`,
        label: workspace.name,
        group: 'Workspaces',
        available: true,
        run: () => navigate(`/workspace/${workspace.id}`),
      })),
      {
        id: 'action-new-workspace',
        label: 'Create workspace',
        group: 'Actions',
        available: true,
        run: () => navigate('/workspace/new'),
      },
    ],
    [navigate, workspaces],
  )

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      overlayClassName="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
      contentClassName="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-[var(--shadow-lg)] animate-in-fade"
    >
      <Command.Input
        placeholder="Search pages, workspaces and actions…"
        className="w-full border-b border-[var(--border)] bg-transparent px-4 py-3 text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
      />
      <Command.List className="max-h-80 overflow-y-auto p-1">
        <Command.Empty className="px-3 py-6 text-center text-xs text-[var(--muted-foreground)]">
          No matching command.
        </Command.Empty>
        {items.map((item) => (
          <Command.Item
            key={item.id}
            value={`${item.group} ${item.label}`}
            onSelect={() => {
              item.run()
              onOpenChange(false)
            }}
            className="flex cursor-pointer items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-[var(--foreground)] data-[selected=true]:bg-[var(--primary-muted)] data-[selected=true]:text-[var(--primary)]"
          >
            <span>{item.label}</span>
            <span className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">
              {item.available ? item.group : 'planned'}
            </span>
          </Command.Item>
        ))}
      </Command.List>
    </Command.Dialog>
  )
}
