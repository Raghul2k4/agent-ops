import {
  Activity,
  BarChart3,
  Blocks,
  BrainCircuit,
  FlaskConical,
  Gauge,
  Library,
  Plug,
  ShieldCheck,
  Users,
  Workflow,
  type LucideIcon,
} from 'lucide-react'

export interface NavigationItem {
  id: string
  label: string
  path: string
  icon: LucideIcon
  /** Milestone in which the module becomes functional (see PLAN.md). */
  milestone: string
  available: boolean
}

/**
 * The eleven primary navigation areas from `AGENTS.md` §7.
 *
 * Items that are not yet functional are still listed but are explicitly
 * marked as unavailable - no control in this application pretends to work
 * before it does.
 */
export const NAVIGATION: NavigationItem[] = [
  { id: 'overview', label: 'Overview', path: '/', icon: Gauge, milestone: 'M1', available: true },
  { id: 'agents', label: 'Agents', path: '/agents', icon: BrainCircuit, milestone: 'M2', available: false },
  { id: 'workflows', label: 'Workflows', path: '/workflows', icon: Workflow, milestone: 'M4', available: false },
  { id: 'runs', label: 'Runs & Traces', path: '/runs', icon: Activity, milestone: 'M3', available: false },
  { id: 'evaluations', label: 'Evaluations', path: '/evaluations', icon: FlaskConical, milestone: 'M6', available: false },
  { id: 'models', label: 'Model Lab', path: '/models', icon: Blocks, milestone: 'M5', available: false },
  { id: 'knowledge', label: 'Knowledge & Memory', path: '/knowledge', icon: Library, milestone: 'M6', available: false },
  { id: 'tools', label: 'Tools & Integrations', path: '/tools', icon: Plug, milestone: 'M2', available: false },
  { id: 'approvals', label: 'Approvals', path: '/approvals', icon: ShieldCheck, milestone: 'M3', available: false },
  { id: 'analytics', label: 'Analytics', path: '/analytics', icon: BarChart3, milestone: 'M5', available: false },
  {
    id: 'workspace',
    label: 'Workspace & Administration',
    path: '/workspace',
    icon: Users,
    milestone: 'M1',
    available: true,
  },
]
