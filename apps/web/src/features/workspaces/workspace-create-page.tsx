import { useMutation, useQueryClient } from '@tanstack/react-query'
import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { FieldError, FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { PageHeader } from '@/features/shared/page'
import { useSession } from '@/features/auth/session-provider'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { api, ApiError } from '@/lib/api-client'
import type { WorkspaceRead } from '@/types/api'

const schema = z.object({
  name: z.string().min(1, 'Enter a workspace name').max(160),
})

type FormValues = z.infer<typeof schema>

export function WorkspaceCreatePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { refresh } = useSession()
  const { setActiveWorkspaceId } = useWorkspace()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: '' },
  })

  const createMutation = useMutation({
    mutationFn: (payload: { name: string }) =>
      api.post<WorkspaceRead>('/workspaces', payload),
    onSuccess: async (workspace) => {
      // `/me` carries the membership list the workspace context reads, so it
      // must be refreshed before the new workspace can become active.
      await refresh()
      setActiveWorkspaceId(workspace.id)
      await queryClient.invalidateQueries({ queryKey: ['workspaces'] })
      navigate(`/workspace/${workspace.id}`)
    },
  })

  async function onSubmit(values: FormValues) {
    try {
      await createMutation.mutateAsync(values)
    } catch (error) {
      if (error instanceof ApiError) {
        setError('root', { message: error.message })
        return
      }
      setError('root', { message: 'Unexpected error. Please try again.' })
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-8">
      <PageHeader
        title="Create a workspace"
        description="Workspaces isolate agents, workflows, runs, evaluations and audit records from each other."
      />

      <Card>
        <CardHeader title="Workspace details" description="You become the owner of this workspace." />
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {errors.root?.message ? (
              <div
                className="rounded-md border border-[var(--danger)]/30 bg-[var(--danger-muted)] px-3 py-2 text-xs text-[var(--danger)]"
                role="alert"
              >
                {errors.root.message}
              </div>
            ) : null}

            <div className="space-y-1.5">
              <Label htmlFor="name" required>
                Name
              </Label>
              <Input
                id="name"
                placeholder="Acme Revenue"
                invalid={Boolean(errors.name)}
                {...register('name')}
              />
              <FieldError>{errors.name?.message}</FieldError>
              <FieldHint>A URL-safe identifier is generated automatically and stays unique.</FieldHint>
            </div>

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
                Cancel
              </Button>
              <Button type="submit" loading={isSubmitting}>
                Create workspace
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
