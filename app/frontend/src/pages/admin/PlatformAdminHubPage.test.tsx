import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { PlatformAdminHubPage } from './PlatformAdminHubPage'
import { createAuthState, superAdminUser } from '@/test/fixtures'

describe('PlatformAdminHubPage', () => {
  it('renders sidebar prompt message', () => {
    render(<PlatformAdminHubPage />, {
      preloadedState: createAuthState(superAdminUser),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('renders without errors', () => {
    const { container } = render(<PlatformAdminHubPage />, {
      preloadedState: createAuthState(superAdminUser),
    })

    expect(container).toBeInTheDocument()
  })

  it('displays centered content', () => {
    render(<PlatformAdminHubPage />, {
      preloadedState: createAuthState(superAdminUser),
    })

    const message = screen.getByText('selectFromSidebar')
    expect(message.closest('div')).toHaveClass('text-center')
  })
})
