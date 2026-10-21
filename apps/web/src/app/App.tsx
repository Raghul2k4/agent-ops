import { BrowserRouter } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ui/error-boundary'
import { SessionProvider } from '@/features/auth/session-provider'
import { QueryProvider } from '@/providers/query-provider'
import { AppRoutes } from '@/routes/router'

export function App() {
  return (
    <ErrorBoundary>
      <QueryProvider>
        <SessionProvider>
          <BrowserRouter>
            <AppRoutes />
          </BrowserRouter>
        </SessionProvider>
      </QueryProvider>
    </ErrorBoundary>
  )
}
