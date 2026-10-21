import { Component, type ErrorInfo, type ReactNode } from 'react'

import { ErrorState } from '@/components/ui/states'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  error: Error | null
}

/** Catches render-time errors so a broken screen never blanks the application. */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('ui.error', error, info.componentStack)
  }

  override render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children
    if (this.props.fallback) return this.props.fallback
    return (
      <div className="p-6">
        <ErrorState
          title="This view crashed"
          message={error.message}
          onRetry={() => this.setState({ error: null })}
        />
      </div>
    )
  }
}
