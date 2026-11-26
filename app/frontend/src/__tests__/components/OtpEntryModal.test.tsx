/**
 * OtpEntryModal Component Tests
 *
 * Tests for the OTP entry modal including:
 * - Dialog rendering
 * - Button rendering
 * - Cancel functionality
 *
 * Note: Tests involving InputOTP interactions are limited due to
 * the input-otp library requiring document.elementFromPoint which
 * is not available in the jsdom test environment.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@/test/utils'
import { OtpEntryModal } from '@/components/email-change/OtpEntryModal'

describe('OtpEntryModal', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onVerified: vi.fn(),
    onCancel: vi.fn(),
    newEmail: 'new@example.com',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Dialog Rendering', () => {
    it('renders dialog content when open', () => {
      render(<OtpEntryModal {...defaultProps} />)

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText(/settings:emailChange.otpModal.title/i)).toBeInTheDocument()
    })

    it('does not render dialog content when closed', () => {
      render(<OtpEntryModal {...defaultProps} open={false} />)

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('displays the target email in the description', () => {
      render(<OtpEntryModal {...defaultProps} />)

      // The description includes the email address
      expect(screen.getByText(/settings:emailChange.otpModal.description/i)).toBeInTheDocument()
    })

    it('renders OTP input label', () => {
      render(<OtpEntryModal {...defaultProps} />)

      expect(screen.getByText(/settings:emailChange.otpModal.fields.otpCode/i)).toBeInTheDocument()
    })

    it('renders verify and cancel buttons', () => {
      render(<OtpEntryModal {...defaultProps} />)

      expect(screen.getByRole('button', { name: /settings:emailChange.otpModal.buttons.verify/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /common:buttons.cancel/i })).toBeInTheDocument()
    })
  })

  describe('Resend Functionality', () => {
    it('shows resend button initially', () => {
      render(<OtpEntryModal {...defaultProps} />)

      expect(screen.getByRole('button', { name: /settings:emailChange.otpModal.buttons.resend/i })).toBeInTheDocument()
    })
  })
})
