import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { DashboardPage } from './DashboardPage'
import { createAuthState, regularUser, adminUser, superAdminUser } from '@/test/fixtures'

describe('DashboardPage', () => {
  it('renders welcome message', () => {
    render(<DashboardPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  it('renders without crashing for regular user', () => {
    render(<DashboardPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(document.body).toBeInTheDocument()
  })

  it('renders without crashing for admin user', () => {
    render(<DashboardPage />, {
      preloadedState: createAuthState(adminUser),
    })

    expect(document.body).toBeInTheDocument()
  })

  it('renders without crashing for super admin user', () => {
    render(<DashboardPage />, {
      preloadedState: createAuthState(superAdminUser),
    })

    expect(document.body).toBeInTheDocument()
  })
})
