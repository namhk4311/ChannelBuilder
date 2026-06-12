import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

interface ErrorBoundaryProps {
  children: ReactNode
  /** Tên sub-app để log/report. Default "subapp". */
  appName?: string
  /** Custom fallback render. Default: inline card với nút retry. */
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

/**
 * Chặn lỗi render để app không trắng trang — hiện fallback + nút thử lại.
 * Dùng ở top-level `app.tsx`, bao quanh routes.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // TODO: wire to host telemetry if available
    console.error(`[${this.props.appName ?? 'subapp'}] boundary caught:`, error, info.componentStack)
  }

  private reset = (): void => this.setState({ error: null })

  render(): ReactNode {
    const { error } = this.state
    if (!error) return this.props.children

    if (this.props.fallback) return this.props.fallback(error, this.reset)

    return (
      <div className="flex min-h-[240px] flex-col items-center justify-center gap-4 rounded-lg border border-border bg-card p-8 text-center">
        <h2 className="text-lg font-semibold text-foreground">Đã có lỗi xảy ra</h2>
        <p className="max-w-md text-sm text-muted-foreground">
          {error.message || 'Unknown error'}
        </p>
        <Button onClick={this.reset} variant="outline">Thử lại</Button>
      </div>
    )
  }
}
