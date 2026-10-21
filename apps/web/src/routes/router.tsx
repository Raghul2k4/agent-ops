import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'

import { AppShell } from '@/components/layout/app-shell'
import { ErrorBoundary } from '@/components/ui/error-boundary'
import { LoadingState } from '@/components/ui/states'
import { LoginPage } from '@/features/auth/login-page'
import { RegisterPage } from '@/features/auth/register-page'
import { useSession } from '@/features/auth/session-provider'
import { OverviewPage } from '@/features/dashboard/overview-page'
import { PlannedModulePage } from '@/features/shared/page'
import { WorkspaceCreatePage } from '@/features/workspaces/workspace-create-page'
import { WorkspaceDetailPage } from '@/features/workspaces/workspace-detail-page'

function RequireSession({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useSession()
  const location = useLocation()

  if (isLoading) {
    return <LoadingState label="Checking your session…" />
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  return <>{children}</>
}

export function AppRoutes() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route
          element={
            <RequireSession>
              <AppShell />
            </RequireSession>
          }
        >
          <Route index element={<OverviewPage />} />
          <Route path="/workspace" element={<OverviewPage />} />
          <Route path="/workspace/new" element={<WorkspaceCreatePage />} />
          <Route path="/workspace/:workspaceId" element={<WorkspaceDetailPage />} />

          <Route
            path="/agents"
            element={
              <PlannedModulePage
                title="Agents"
                milestone="M2"
                summary="Agent Studio arrives in milestone M2 with versioned configuration, a real playground and the registered tool catalogue."
                capabilities={[
                  'Draft and immutable published agent versions with rollback',
                  'Capability-aware model and parameter selection',
                  'Playground backed by the real backend runtime, not a mock',
                  'Eight functional agent templates',
                ]}
              />
            }
          />
          <Route
            path="/workflows"
            element={
              <PlannedModulePage
                title="Workflows"
                milestone="M4"
                summary="The visual workflow builder and its execution engine arrive in milestone M4."
                capabilities={[
                  'React Flow canvas with typed ports, undo/redo and autosave',
                  '13 node contracts with typed configuration schemas',
                  'Graph validation before every run',
                  'Node-level traces, checkpoints and approval pauses',
                ]}
              />
            }
          />
          <Route
            path="/runs"
            element={
              <PlannedModulePage
                title="Runs & Traces"
                milestone="M3"
                summary="Run history and hierarchical traces arrive in milestone M3."
                capabilities={[
                  'Server-side filtering over persisted runs',
                  'Hierarchical trace timeline with sanitized payloads',
                  'Cancellation and safe replay',
                  'Live updates over SSE with a resumable cursor',
                ]}
              />
            }
          />
          <Route
            path="/evaluations"
            element={
              <PlannedModulePage
                title="Evaluations"
                milestone="M6"
                summary="Evaluation suites, deterministic scorers and regression gates arrive in milestone M6."
                capabilities={[
                  'Suite and case builder with fixture isolation',
                  'Exact-match, schema, rule, tool-accuracy and groundedness scorers',
                  'Reproducible reports with regression comparison',
                  'Release gates that fail when a measurement is missing',
                ]}
              />
            }
          />
          <Route
            path="/models"
            element={
              <PlannedModulePage
                title="Model Lab"
                milestone="M5"
                summary="Provider configuration, health checks and model comparison arrive in milestones M2 and M5."
                capabilities={[
                  'Ollama, OpenAI-compatible and Anthropic adapters with capability metadata',
                  'Secret storage that never returns a stored credential',
                  'Side-by-side comparison over identical benchmark cases',
                  'Cost and latency reporting with sample counts',
                ]}
              />
            }
          />
          <Route
            path="/knowledge"
            element={
              <PlannedModulePage
                title="Knowledge & Memory"
                milestone="M6"
                summary="Document ingestion, retrieval and agent memory arrive in milestone M6."
                capabilities={[
                  'PDF, TXT, Markdown, DOCX and CSV ingestion with size and type validation',
                  'Configurable chunking and embeddings',
                  'Retrieval with metadata filters, top-K and citations',
                  'Typed agent memory with provenance and expiry',
                ]}
              />
            }
          />
          <Route
            path="/tools"
            element={
              <PlannedModulePage
                title="Tools & Integrations"
                milestone="M2"
                summary="The tool registry and integration directory arrive in milestone M2."
                capabilities={[
                  'Server-side registry with strict argument validation',
                  'Risk classification and approval requirements per tool',
                  'Nine built-in CRM tools over synthetic data',
                  'SSRF-safe generic HTTP connector',
                ]}
              />
            }
          />
          <Route
            path="/approvals"
            element={
              <PlannedModulePage
                title="Approvals"
                milestone="M3"
                summary="The human-in-the-loop approval queue arrives in milestone M3."
                capabilities={[
                  'Approvals bound to a canonical hash of the exact proposed action',
                  'Expiry, policy version and permission re-validation at execution time',
                  'Approve, reject and request-changes decisions with an audit trail',
                  'Budgets, rate limits and an emergency pause switch',
                ]}
              />
            }
          />
          <Route
            path="/analytics"
            element={
              <PlannedModulePage
                title="Analytics"
                milestone="M5"
                summary="Usage analytics and spend reporting arrive in milestone M5."
                capabilities={[
                  'Latency percentiles and success trends from persisted runs',
                  'Token and cost estimates with explicit "unavailable" states',
                  'Cost per successful task and approval turnaround',
                  'Provider availability and workspace quota reporting',
                ]}
              />
            }
          />

          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </ErrorBoundary>
  )
}

function NotFoundPage() {
  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-16 text-center">
      <p className="font-mono text-xs uppercase tracking-widest text-[var(--muted-foreground)]">
        404
      </p>
      <h1 className="mt-2 text-lg font-semibold">This page does not exist</h1>
      <p className="mt-1 text-sm text-[var(--muted-foreground)]">
        Use the sidebar or the command palette (Ctrl+K) to reach a module.
      </p>
    </div>
  )
}
