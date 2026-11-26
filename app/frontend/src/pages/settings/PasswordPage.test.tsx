import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@/test/utils'
import { PasswordPage } from './PasswordPage'
import { createAuthState, regularUser } from '@/test/fixtures'

// Mock the password change mutation
vi.mock('@/features/user/userApi', () => ({
  useChangePasswordMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
}))

describe('PasswordPage', () => {
  it('renders password change form', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByText('settings:profile.sections.changePassword.title')).toBeInTheDocument()
  })

  it('has current password input', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByLabelText('settings:profile.fields.currentPassword')).toBeInTheDocument()
  })

  it('has new password input', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByLabelText('settings:profile.fields.newPassword')).toBeInTheDocument()
  })

  it('has confirm password input', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByLabelText('settings:profile.fields.confirmPassword')).toBeInTheDocument()
  })

  it('has submit button', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByRole('button', { name: 'settings:profile.buttons.updatePassword' })).toBeInTheDocument()
  })

  it('shows password requirements', () => {
    render(<PasswordPage />, {
      preloadedState: createAuthState(regularUser),
    })

    // PasswordRequirements component should render
    expect(screen.getByText('passwordRequirements.title')).toBeInTheDocument()
  })
})
