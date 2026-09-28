import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

type Props = { children: ReactNode }
type State = { error: Error | null }

/** Catches render/lifecycle errors thrown by whatever page is currently routed (e.g. a page
 * assuming an API shape that doesn't hold) so a single page crash can't unmount the whole app —
 * the sidebar (rendered outside this boundary, in Layout) stays usable and the user can navigate
 * away or reload. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error('Unhandled error in page:', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="flex flex-col items-start gap-3 rounded-md border border-bad/40 bg-bad/10 p-5">
        <div className="flex items-center gap-2 text-bad">
          <AlertTriangle size={18} />
          <span className="text-sm font-semibold">Something went wrong rendering this page</span>
        </div>
        <pre className="max-w-full overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted">{error.message}</pre>
        <button type="button" className="btn btn-sm btn-primary" onClick={() => window.location.reload()}>
          Reload page
        </button>
      </div>
    )
  }
}
