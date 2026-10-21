import { BrowserRouter } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ui/error-boundary'
import { SessionProvider } from '@/features/auth/session-provider'
import { WorkspaceProvider } from '@/features/workspaces/workspace-context'
import { QueryProvider } from '@/providers/query-provider'
import { AppRoutes } from '@/routes/router'

export function App() {
  return (
    <ErrorBoundary>
      <QueryProvider>
        <SessionProvider>
          <WorkspaceProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </WorkspaceProvider>
        </SessionProvider>
      </QueryProvider>
    </ErrorBoundary>
  )
}
