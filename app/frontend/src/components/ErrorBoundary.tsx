import { Component, type ReactNode } from 'react'
import { withTranslation, type WithTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'

interface ErrorBoundaryOwnProps {
  children: ReactNode
  /**
   * Optional fallback component to render on error
   */
  fallback?: ReactNode
  /**
   * Optional render-prop fallback. Receives the caught error, the React
   * component stack, and a reset callback. Takes precedence over `fallback`.
   * Use this when the fallback needs the error context (e.g. to build a
   * support report). Only valid below the Redux/i18n providers.
   */
  renderFallback?: (args: {
    error: Error
    componentStack: string | null
    reset: () => void
  }) => ReactNode
}

type ErrorBoundaryProps = ErrorBoundaryOwnProps & WithTranslation

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
  componentStack: string | null
}

/**
 * Error boundary component that catches JavaScript errors in child components
 * and displays a fallback UI instead of crashing the entire app.
 *
 * @example
 * <ErrorBoundary>
 *   <App />
 * </ErrorBoundary>
 *
 * @example
 * // With custom fallback
 * <ErrorBoundary fallback={<CustomErrorPage />}>
 *   <App />
 * </ErrorBoundary>
 */
class ErrorBoundaryClass extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null, componentStack: null }
  }

  static getDerivedStateFromError(
    error: Error,
  ): Pick<ErrorBoundaryState, 'hasError' | 'error'> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    // Log error for debugging (kept intentionally for production error visibility)
    console.error('ErrorBoundary caught an error:', error, errorInfo)

    // Capture the component stack so a fallback can surface "what component"
    // failed in a support report.
    this.setState({ componentStack: errorInfo.componentStack ?? null })

    // Optional: Integrate error reporting service (e.g., Sentry, Bugsnag)
    // Example integration:
    //   import * as Sentry from '@sentry/react'
    //   Sentry.captureException(error, { extra: { componentStack: errorInfo.componentStack } })
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null, componentStack: null })
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError && this.state.error) {
      // Use render-prop fallback if provided (receives error context)
      if (this.props.renderFallback) {
        return this.props.renderFallback({
          error: this.state.error,
          componentStack: this.state.componentStack,
          reset: this.handleReset,
        })
      }

      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback
      }

      // Default error UI
      const { t } = this.props
      return (
        <div className="flex min-h-screen items-center justify-center p-4">
          <Card className="w-full max-w-md">
            <CardHeader>
              <CardTitle>{t('errorBoundary.title')}</CardTitle>
              <CardDescription>
                {t('errorBoundary.description')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {import.meta.env.DEV && this.state.error && (
                <div className="rounded-md bg-destructive/10 p-4">
                  <p className="text-sm font-medium text-destructive">
                    {this.state.error.message}
                  </p>
                  <ScrollArea className="mt-2 max-h-40">
                    <pre className="text-xs text-muted-foreground">
                      {this.state.error.stack}
                    </pre>
                  </ScrollArea>
                </div>
              )}
              <div className="flex gap-2">
                <Button onClick={this.handleReset} variant="outline">
                  {t('errorBoundary.tryAgain')}
                </Button>
                <Button onClick={this.handleReload}>{t('errorBoundary.reloadPage')}</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )
    }

    return this.props.children
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryClass)
