/**
 * IdentityVerificationModal Component Tests
 *
 * Tests for the identity verification modal including:
 * - Dialog rendering
 * - Tab switching between password and 2FA
 * - Password validation
 * - Form submission
 * - Cancel functionality
 *
 * Note: Tests involving InputOTP interactions are limited due to
 * the input-otp library requiring document.elementFromPoint which
 * is not available in the jsdom test environment.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { IdentityVerificationModal } from '@/components/email-change/IdentityVerificationModal'
import { server, API_BASE } from '@/test/server'
import { http, HttpResponse } from 'msw'

describe('IdentityVerificationModal', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onVerified: vi.fn(),
    onCancel: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Dialog Rendering', () => {
    it('renders dialog content when open', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/settings:emailChange.identityModal.title/i)).toBeInTheDocument()
      expect(screen.getByText(/settings:emailChange.identityModal.description/i)).toBeInTheDocument()
    })

    it('does not render dialog content when closed', () => {
      render(<IdentityVerificationModal {...defaultProps} open={false} />)

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('renders verification method tabs', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      expect(screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.password/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.twoFactor/i })).toBeInTheDocument()
    })

    it('renders verify and cancel buttons', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      expect(screen.getByRole('button', { name: /settings:emailChange.identityModal.buttons.verify/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /common:buttons.cancel/i })).toBeInTheDocument()
    })
  })

  describe('Password Tab', () => {
    it('shows password tab by default', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      const passwordTab = screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.password/i })
      expect(passwordTab).toHaveAttribute('data-state', 'active')
    })

    it('renders password input field in password tab', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      // Check for the password label which indicates the field exists
      expect(screen.getByText(/settings:emailChange.identityModal.fields.password/i)).toBeInTheDocument()
    })

    it('has password visibility toggle button', () => {
      render(<IdentityVerificationModal {...defaultProps} />)

      // The show/hide password button should exist
      expect(screen.getByRole('button', { name: /showPassword|hidePassword/i })).toBeInTheDocument()
    })
  })

  describe('Password Validation', () => {
    it('shows error when password is empty on submit', async () => {
      const { user } = render(<IdentityVerificationModal {...defaultProps} />)

      await user.click(screen.getByRole('button', { name: /settings:emailChange.identityModal.buttons.verify/i }))

      await waitFor(() => {
        expect(screen.getByText(/auth:validation.passwordRequired/i)).toBeInTheDocument()
      })
    })
  })

  describe('Password Form Submission', () => {
    it('calls API with password when form is valid', async () => {
      let apiCalled = false
      let requestBody: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/users/me/email/change/verify`, async ({ request }) => {
          apiCalled = true
          requestBody = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({ message: 'Identity verified', message_code: 'identity_verified' })
        })
      )

      const { user } = render(<IdentityVerificationModal {...defaultProps} />)

      // Get the dialog to scope our search
      const dialog = screen.getByRole('dialog')
      // Use the form item structure to find the password input
      const formItems = dialog.querySelectorAll('[data-slot="form-item"]')
      const passwordFormItem = formItems[0] // First form item in password tab is the password field
      const input = passwordFormItem?.querySelector('input')

      if (input) {
        await user.type(input, 'MyPassword123!')
      }

      await user.click(screen.getByRole('button', { name: /settings:emailChange.identityModal.buttons.verify/i }))

      await waitFor(() => {
        expect(apiCalled).toBe(true)
        expect(requestBody).toEqual({
          verification_method: 'password',
          verification_value: 'MyPassword123!',
        })
      })
    })

    it('calls onVerified on successful password verification', async () => {
      const onVerified = vi.fn()

      server.use(
        http.post(`${API_BASE}/users/me/email/change/verify`, () => {
          return HttpResponse.json({ message: 'Identity verified', message_code: 'identity_verified' })
        })
      )

      const { user } = render(<IdentityVerificationModal {...defaultProps} onVerified={onVerified} />)

      const dialog = screen.getByRole('dialog')
      const formItems = dialog.querySelectorAll('[data-slot="form-item"]')
      const passwordFormItem = formItems[0]
      const input = passwordFormItem?.querySelector('input')

      if (input) {
        await user.type(input, 'MyPassword123!')
      }

      await user.click(screen.getByRole('button', { name: /settings:emailChange.identityModal.buttons.verify/i }))

      await waitFor(() => {
        expect(onVerified).toHaveBeenCalled()
      })
    })
  })

  describe('Two-Factor Tab', () => {
    it('switches to 2FA tab when clicked', async () => {
      const { user } = render(<IdentityVerificationModal {...defaultProps} />)

      await user.click(screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.twoFactor/i }))

      const twoFactorTab = screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.twoFactor/i })
      expect(twoFactorTab).toHaveAttribute('data-state', 'active')
    })

    it('renders 2FA input label when 2FA tab is active', async () => {
      const { user } = render(<IdentityVerificationModal {...defaultProps} />)

      await user.click(screen.getByRole('tab', { name: /settings:emailChange.identityModal.tabs.twoFactor/i }))

      expect(screen.getByText(/settings:emailChange.identityModal.fields.twoFactorCode/i)).toBeInTheDocument()
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onCancel when cancel button is clicked', async () => {
      const onCancel = vi.fn()
      const { user } = render(<IdentityVerificationModal {...defaultProps} onCancel={onCancel} />)

      await user.click(screen.getByRole('button', { name: /common:buttons.cancel/i }))

      expect(onCancel).toHaveBeenCalled()
    })
  })
})
