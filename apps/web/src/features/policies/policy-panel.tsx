import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PauseCircle, PlayCircle, Save } from 'lucide-react'
import { useEffect, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { FieldHint, Label } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Notice } from '@/components/ui/status'
import { Textarea } from '@/components/ui/textarea'
import { policiesApi } from '@/features/policies/api'
import { toolsApi } from '@/features/tools/api'
import { useWorkspace } from '@/features/workspaces/workspace-context'
import { ApiError } from '@/lib/api-client'
import type { RiskLevel } from '@/types/api'

const RISK_LEVELS: RiskLevel[] = ['low', 'medium', 'high', 'critical']

/**
 * The workspace policy editor.
 *
 * Everything here is enforced server-side on the next run: the emergency
 * pause, the tool allow/deny lists, the risk levels that need a human
 * decision and the rate limits.
 */
export function PolicyPanel() {
  const { activeWorkspace, can } = useWorkspace()
  const queryClient = useQueryClient()
  const workspaceId = activeWorkspace?.id ?? ''
  const mayEdit = can('workspace.update')

  const policy = useQuery({
    queryKey: ['policy', workspaceId],
    queryFn: () => policiesApi.read(workspaceId),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const tools = useQuery({
    queryKey: ['tools', workspaceId],
    queryFn: () => toolsApi.list(workspaceId),
    enabled: Boolean(workspaceId),
    retry: false,
  })

  const [allowlist, setAllowlist] = useState<string[]>([])
  const [blocked, setBlocked] = useState<string[]>([])
  const [riskLevels, setRiskLevels] = useState<RiskLevel[]>(['high', 'critical'])
  const [maxToolCalls, setMaxToolCalls] = useState('')
  const [maxRunsPerHour, setMaxRunsPerHour] = useState('')
  const [ttlMinutes, setTtlMinutes] = useState('60')
  const [paused, setPaused] = useState(false)
  const [pauseReason, setPauseReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const current = policy.data
    if (!current) return
    setAllowlist(current.tool_allowlist)
    setBlocked(current.blocked_tools)
    setRiskLevels(current.require_approval_for_risk_levels as RiskLevel[])
    setMaxToolCalls(current.max_tool_calls_per_run?.toString() ?? '')
    setMaxRunsPerHour(current.max_runs_per_hour?.toString() ?? '')
    setTtlMinutes(current.approval_ttl_minutes.toString())
    setPaused(current.execution_paused)
    setPauseReason(current.paused_reason ?? '')
  }, [policy.data])

  const save = useMutation({
    mutationFn: () =>
      policiesApi.update(workspaceId, {
        tool_allowlist: allowlist,
        blocked_tools: blocked,
        require_approval_for_risk_levels: riskLevels,
        max_tool_calls_per_run: maxToolCalls ? Number(maxToolCalls) : null,
        max_runs_per_hour: maxRunsPerHour ? Number(maxRunsPerHour) : null,
        approval_ttl_minutes: ttlMinutes ? Number(ttlMinutes) : 60,
        execution_paused: paused,
        paused_reason: paused ? pauseReason || 'Paused by an administrator.' : null,
        change_note: 'Updated from the workspace policy editor.',
      }),
    onSuccess: async () => {
      setError(null)
      await queryClient.invalidateQueries({ queryKey: ['policy', workspaceId] })
    },
    onError: (mutationError) => {
      setError(
        mutationError instanceof ApiError
          ? mutationError.message
          : 'The policy could not be saved.',
      )
    },
  })

  const toggle = (list: string[], value: string): string[] =>
    list.includes(value) ? list.filter((item) => item !== value) : [...list, value]

  if (!activeWorkspace) return null

  const toolNames = (tools.data ?? []).map((tool) => tool.name)

  return (
    <Card className="mt-4">
      <CardHeader
        title="Execution policy"
        description="Enforced on the server for every run and every tool call. The version is stamped on each run and approval."
        actions={
          policy.data ? <Badge tone="neutral">policy v{policy.data.version}</Badge> : null
        }
      />
      <CardContent className="space-y-4">
        {error ? (
          <Notice tone="danger" title="The policy was not saved">
            {error}
          </Notice>
        ) : null}

        {policy.data?.execution_paused ? (
          <Notice tone="warning" title="Execution is paused">
            {policy.data.paused_reason ?? 'No reason was given.'} New runs are refused until the
            pause is lifted.
          </Notice>
        ) : null}

        <div className="rounded-md border border-[var(--border)] p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-sm font-medium">Emergency pause</p>
              <p className="text-xs text-[var(--muted-foreground)]">
                Refuses every new run in this workspace. Runs already in flight continue.
              </p>
            </div>
            <Button
              size="sm"
              variant={paused ? 'secondary' : 'danger'}
              disabled={!mayEdit || save.isPending}
              onClick={() => {
                setPaused((value) => !value)
                if (paused) setPauseReason('')
              }}
            >
              {paused ? (
                <PlayCircle className="size-3.5" aria-hidden="true" />
              ) : (
                <PauseCircle className="size-3.5" aria-hidden="true" />
              )}
              {paused ? 'Lift the pause' : 'Pause execution'}
            </Button>
          </div>
          {paused ? (
            <div className="mt-3 space-y-1.5">
              <Label htmlFor="pause-reason">Reason</Label>
              <Textarea
                id="pause-reason"
                rows={2}
                value={pauseReason}
                disabled={!mayEdit}
                onChange={(event) => setPauseReason(event.target.value)}
                placeholder="Why execution is paused."
                className="text-sm"
              />
            </div>
          ) : null}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Tools that may run</Label>
            <FieldHint>
              Leave empty to allow every registered tool. The deny list below always wins.
            </FieldHint>
            <div className="flex flex-wrap gap-1.5">
              {toolNames.length === 0 ? (
                <p className="text-xs text-[var(--muted-foreground)]">No tools registered yet.</p>
              ) : null}
              {toolNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={!mayEdit}
                  onClick={() => setAllowlist((current) => toggle(current, name))}
                  className={`rounded-md border px-2 py-1 font-mono text-[11px] disabled:opacity-50 ${
                    allowlist.includes(name)
                      ? 'border-[var(--primary)] text-[var(--primary)]'
                      : 'border-[var(--border)] text-[var(--muted-foreground)]'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Tools that may never run</Label>
            <FieldHint>Blocked tools are refused before the tool body runs.</FieldHint>
            <div className="flex flex-wrap gap-1.5">
              {toolNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  disabled={!mayEdit}
                  onClick={() => setBlocked((current) => toggle(current, name))}
                  className={`rounded-md border px-2 py-1 font-mono text-[11px] disabled:opacity-50 ${
                    blocked.includes(name)
                      ? 'border-[var(--danger)] text-[var(--danger)]'
                      : 'border-[var(--border)] text-[var(--muted-foreground)]'
                  }`}
                >
                  {name}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Risk levels that require a human decision</Label>
          <FieldHint>
            A tool at one of these levels stops the run and waits in the approval queue.
          </FieldHint>
          <div className="flex flex-wrap gap-1.5">
            {RISK_LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                disabled={!mayEdit}
                onClick={() =>
                  setRiskLevels((current) =>
                    current.includes(level)
                      ? current.filter((item) => item !== level)
                      : [...current, level],
                  )
                }
                className={`rounded-md border px-2 py-1 text-[11px] disabled:opacity-50 ${
                  riskLevels.includes(level)
                    ? 'border-[var(--primary)] text-[var(--primary)]'
                    : 'border-[var(--border)] text-[var(--muted-foreground)]'
                }`}
              >
                {level}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="max-tool-calls">Tool calls per run</Label>
            <Input
              id="max-tool-calls"
              type="number"
              min={1}
              disabled={!mayEdit}
              value={maxToolCalls}
              onChange={(event) => setMaxToolCalls(event.target.value)}
              placeholder="Agent limit"
            />
            <FieldHint>Empty uses the agent version's own limit.</FieldHint>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="max-runs">Runs per hour</Label>
            <Input
              id="max-runs"
              type="number"
              min={1}
              disabled={!mayEdit}
              value={maxRunsPerHour}
              onChange={(event) => setMaxRunsPerHour(event.target.value)}
              placeholder="No quota"
            />
            <FieldHint>Empty means no workspace quota.</FieldHint>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ttl">Approval lifetime (minutes)</Label>
            <Input
              id="ttl"
              type="number"
              min={1}
              disabled={!mayEdit}
              value={ttlMinutes}
              onChange={(event) => setTtlMinutes(event.target.value)}
            />
            <FieldHint>An expired request can no longer be decided.</FieldHint>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2">
          {!mayEdit ? (
            <p className="text-xs text-[var(--muted-foreground)]">
              Only an owner or administrator can change the policy.
            </p>
          ) : null}
          <Button
            size="sm"
            loading={save.isPending}
            disabled={!mayEdit || save.isPending}
            onClick={() => save.mutate()}
          >
            <Save className="size-3.5" aria-hidden="true" />
            Save policy
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
