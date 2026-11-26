/**
 * ChangePasswordDialog Component Tests
 *
 * Tests for the change password dialog including:
 * - Dialog rendering when open/closed
 * - Form field validation
 * - Password confirmation matching
 * - Form submission
 * - Loading state
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { ChangePasswordDialog } from '@/components/user/ChangePasswordDialog'

describe('ChangePasswordDialog', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onSubmit: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Dialog Rendering', () => {
    it('renders dialog content when open', () => {
      render(<ChangePasswordDialog {...defaultProps} />)

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/settings:profile.sections.changePassword.title/i)).toBeInTheDocument()
      expect(screen.getByText(/settings:profile.sections.changePassword.description/i)).toBeInTheDocument()
    })

    it('does not render dialog content when closed', () => {
      render(<ChangePasswordDialog {...defaultProps} open={false} />)

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders all password fields', () => {
      render(<ChangePasswordDialog {...defaultProps} />)

      expect(screen.getByLabelText(/settings:profile.fields.currentPassword/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/settings:profile.fields.newPassword/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/settings:profile.fields.confirmPassword/i)).toBeInTheDocument()
    })

    it('renders submit and cancel buttons', () => {
      render(<ChangePasswordDialog {...defaultProps} />)

      expect(screen.getByRole('button', { name: /settings:profile.buttons.updatePassword/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /common:buttons.cancel/i })).toBeInTheDocument()
    })
  })

  describe('Validation - Current Password', () => {
    it('shows error when current password is empty', async () => {
      const { user } = render(<ChangePasswordDialog {...defaultProps} />)

      // Fill new password but leave current empty
      await user.type(screen.getByLabelText(/settings:profile.fields.newPassword/i), 'NewPassword123!')
      await user.type(screen.getByLabelText(/settings:profile.fields.confirmPassword/i), 'NewPassword123!')
      await user.click(screen.getByRole('button', { name: /settings:profile.buttons.updatePassword/i }))

      await waitFor(() => {
        expect(screen.getByText(/auth:validation.currentPasswordRequired/i)).toBeInTheDocument()
      })
    })
  })

  describe('Validation - Password Confirmation', () => {
    it('shows error when passwords do not match', async () => {
      const { user } = render(<ChangePasswordDialog {...defaultProps} />)

      await user.type(screen.getByLabelText(/settings:profile.fields.currentPassword/i), 'CurrentPass123!')
      await user.type(screen.getByLabelText(/settings:profile.fields.newPassword/i), 'NewPassword123!')
      await user.type(screen.getByLabelText(/settings:profile.fields.confirmPassword/i), 'DifferentPassword123!')
      await user.click(screen.getByRole('button', { name: /settings:profile.buttons.updatePassword/i }))

      await waitFor(() => {
        expect(screen.getByText(/auth:validation.passwordsNoMatch/i)).toBeInTheDocument()
      })
    })
  })

  describe('Form Submission', () => {
    it('calls onSubmit with current and new password when valid', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const { user } = render(<ChangePasswordDialog {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/settings:profile.fields.currentPassword/i), 'CurrentPass123!')
      await user.type(screen.getByLabelText(/settings:profile.fields.newPassword/i), 'NewPassword123!')
      await user.type(screen.getByLabelText(/settings:profile.fields.confirmPassword/i), 'NewPassword123!')
      await user.click(screen.getByRole('button', { name: /settings:profile.buttons.updatePassword/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          currentPassword: 'CurrentPass123!',
          newPassword: 'NewPassword123!',
        })
      })
    })

    it('does not call onSubmit when form is invalid', async () => {
      const onSubmit = vi.fn()
      const { user } = render(<ChangePasswordDialog {...defaultProps} onSubmit={onSubmit} />)

      // Submit with empty fields
      await user.click(screen.getByRole('button', { name: /settings:profile.buttons.updatePassword/i }))

      await waitFor(() => {
        expect(screen.getByText(/auth:validation.currentPasswordRequired/i)).toBeInTheDocument()
      })

      expect(onSubmit).not.toHaveBeenCalled()
    })
  })

  describe('Loading State', () => {
    it('disables submit button while loading', () => {
      render(<ChangePasswordDialog {...defaultProps} isLoading />)

      expect(screen.getByRole('button', { name: /settings:profile.buttons.updating/i })).toBeDisabled()
    })

    it('shows updating text while loading', () => {
      render(<ChangePasswordDialog {...defaultProps} isLoading />)

      expect(screen.getByRole('button', { name: /settings:profile.buttons.updating/i })).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('displays error message from error prop', async () => {
      render(<ChangePasswordDialog {...defaultProps} error="Incorrect current password" />)

      await waitFor(() => {
        expect(screen.getByText('Incorrect current password')).toBeInTheDocument()
      })
    })

    it('displays error in styled container', async () => {
      render(
        <ChangePasswordDialog {...defaultProps} error="Incorrect current password" />
      )

      await waitFor(() => {
        // The error is displayed in a styled div with the error text
        const errorText = screen.getByText('Incorrect current password')
        expect(errorText).toBeInTheDocument()
        // Check that it's inside a styled container (checking parent has rounded-md class)
        expect(errorText.closest('div')).toHaveClass('rounded-md')
      })
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onOpenChange with false when cancel is clicked', async () => {
      const onOpenChange = vi.fn()
      const { user } = render(<ChangePasswordDialog {...defaultProps} onOpenChange={onOpenChange} />)

      await user.click(screen.getByRole('button', { name: /common:buttons.cancel/i }))

      expect(onOpenChange).toHaveBeenCalledWith(false)
    })
  })

  describe('Form Reset', () => {
    it('resets form when dialog reopens', async () => {
      const { rerender, user } = render(<ChangePasswordDialog {...defaultProps} />)

      // Type in some values
      await user.type(screen.getByLabelText(/settings:profile.fields.currentPassword/i), 'SomePassword')

      // Close dialog
      rerender(<ChangePasswordDialog {...defaultProps} open={false} />)

      // Reopen dialog
      rerender(<ChangePasswordDialog {...defaultProps} open={true} />)

      // Field should be empty
      expect(screen.getByLabelText(/settings:profile.fields.currentPassword/i)).toHaveValue('')
    })
  })

  describe('Password Input Types', () => {
    it('renders password fields with type password', () => {
      render(<ChangePasswordDialog {...defaultProps} />)

      expect(screen.getByLabelText(/settings:profile.fields.currentPassword/i)).toHaveAttribute('type', 'password')
      expect(screen.getByLabelText(/settings:profile.fields.newPassword/i)).toHaveAttribute('type', 'password')
      expect(screen.getByLabelText(/settings:profile.fields.confirmPassword/i)).toHaveAttribute('type', 'password')
    })

    it('has correct autocomplete attributes', () => {
      render(<ChangePasswordDialog {...defaultProps} />)

      expect(screen.getByLabelText(/settings:profile.fields.currentPassword/i)).toHaveAttribute('autocomplete', 'current-password')
      expect(screen.getByLabelText(/settings:profile.fields.newPassword/i)).toHaveAttribute('autocomplete', 'new-password')
      expect(screen.getByLabelText(/settings:profile.fields.confirmPassword/i)).toHaveAttribute('autocomplete', 'new-password')
    })
  })
})
