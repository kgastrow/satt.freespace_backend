import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@/test/utils'
import type { RootState } from '@/store'
import { ErrorFallback } from './ErrorFallback'

const componentStack = '\n    at Boom (http://localhost/src/pages/dev/CrashTestPage.tsx:6:9)'

function authState(isAuthenticated: boolean) {
  return {
    auth: { isAuthenticated } as unknown as RootState['auth'],
  }
}

describe('ErrorFallback', () => {
  it('renders the error title and description', () => {
    render(<ErrorFallback error={new Error('boom')} componentStack={componentStack} reset={vi.fn()} />, {
      preloadedState: authState(false),
    })

    expect(screen.getByText('common:errorBoundary.title')).toBeInTheDocument()
    expect(screen.getByText('common:errorBoundary.description')).toBeInTheDocument()
  })

  it('surfaces the auto-captured page and failing component', () => {
    render(<ErrorFallback error={new Error('boom')} componentStack={componentStack} reset={vi.fn()} />, {
      preloadedState: authState(false),
      route: '/dev/crash',
    })

    // pathname comes from window.location (jsdom default '/')
    expect(screen.getByText(window.location.pathname)).toBeInTheDocument()
    // component name is parsed from the stack
    expect(screen.getByText('Boom')).toBeInTheDocument()
  })

  it('calls reset when "Try Again" is clicked', async () => {
    const reset = vi.fn()
    const { user } = render(
      <ErrorFallback error={new Error('boom')} componentStack={componentStack} reset={reset} />,
      { preloadedState: authState(false) }
    )

    await user.click(screen.getByRole('button', { name: 'common:errorBoundary.tryAgain' }))
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('hides the "Report to support" action when not authenticated', () => {
    render(<ErrorFallback error={new Error('boom')} componentStack={componentStack} reset={vi.fn()} />, {
      preloadedState: authState(false),
    })
    expect(
      screen.queryByRole('button', { name: 'common:errorBoundary.reportButton' })
    ).not.toBeInTheDocument()
  })

  it('shows the "Report to support" action when authenticated', () => {
    render(<ErrorFallback error={new Error('boom')} componentStack={componentStack} reset={vi.fn()} />, {
      preloadedState: authState(true),
    })
    expect(
      screen.getByRole('button', { name: 'common:errorBoundary.reportButton' })
    ).toBeInTheDocument()
  })
})
