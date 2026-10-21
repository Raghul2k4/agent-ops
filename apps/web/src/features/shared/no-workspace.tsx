import { Building2 } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/states'

/** Shown when a module needs a workspace but the user is not a member of one. */
export function NoWorkspaceState({ module }: { module: string }) {
  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-10">
      <EmptyState
        icon={<Building2 className="size-5" aria-hidden="true" />}
        title="A workspace is required"
        description={`${module} is scoped to a workspace. Create one to continue - every record, run and credential reference is isolated per workspace.`}
        action={
          <Button asChild size="sm">
            <Link to="/workspace/new">Create workspace</Link>
          </Button>
        }
      />
    </div>
  )
}
