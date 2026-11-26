import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@/test/utils'
import { LoginPage } from './LoginPage'

// Mock the ORG_SLUG environment variable
vi.stubEnv('VITE_ORG_SLUG', 'test-org')

describe('LoginPage', () => {
  const defaultAuthState = {
    auth: {
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      sso: { isLoading: false, error: null, selectedProvider: null },
      twoFactor: { required: false, token: null },
      twoFactorSetupRequired: false,
      enforcementActive: false,
    },
  }

  it('renders login page when not authenticated', () => {
    render(<LoginPage />, {
      preloadedState: defaultAuthState,
    })

    expect(screen.getByText('common:app.name')).toBeInTheDocument()
  })

  it('renders without crashing', () => {
    render(<LoginPage />, {
      preloadedState: defaultAuthState,
    })

    expect(document.body).toBeInTheDocument()
  })

  it('has link to home page', () => {
    render(<LoginPage />, {
      preloadedState: defaultAuthState,
    })

    const homeLink = screen.getByRole('link', { name: /common:app.name/i })
    expect(homeLink).toHaveAttribute('href', '/')
  })
})
