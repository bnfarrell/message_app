import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from './ui'

type State = { error: Error | null }

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="grid h-full place-items-center bg-bg p-8 text-center">
        <div className="max-w-sm">
          <p className="text-sm font-semibold text-text">Something broke on this screen.</p>
          <p className="mt-2 text-xs text-text3">{this.state.error.message}</p>
          <Button className="mt-4" onClick={() => window.location.reload()}>
            Reload
          </Button>
        </div>
      </div>
    )
  }
}
