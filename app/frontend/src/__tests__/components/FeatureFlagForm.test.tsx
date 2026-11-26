/**
 * FeatureFlagForm Component Tests
 *
 * Tests for the feature flag form including:
 * - Form rendering
 * - Field validation (required, format)
 * - Form submission
 * - Edit mode (key disabled)
 * - Cancel functionality
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { FeatureFlagForm } from '@/components/feature-flags/FeatureFlagForm'
import type { FeatureFlag } from '@/features/featureFlags/featureFlagsApi'

describe('FeatureFlagForm', () => {
  const defaultProps = {
    onSubmit: vi.fn(),
    onCancel: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders all form fields', () => {
      render(<FeatureFlagForm {...defaultProps} />)

      expect(screen.getByLabelText(/featureFlags.form.key/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/featureFlags.form.name/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/featureFlags.form.description/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/featureFlags.form.defaultEnabled/i)).toBeInTheDocument()
    })

    it('renders save and cancel buttons', () => {
      render(<FeatureFlagForm {...defaultProps} />)

      expect(screen.getByRole('button', { name: /featureFlags.form.save/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /featureFlags.form.cancel/i })).toBeInTheDocument()
    })

    it('renders with initial data in edit mode', () => {
      const initialData: FeatureFlag = {
        id: 'flag-1',
        key: 'test_feature',
        name: 'Test Feature',
        description: 'A test feature flag',
        default_enabled: true,
        created_time: '2024-01-01T00:00:00Z',
        updated_time: '2024-01-01T00:00:00Z',
      }

      render(<FeatureFlagForm {...defaultProps} initialData={initialData} />)

      expect(screen.getByLabelText(/featureFlags.form.key/i)).toHaveValue('test_feature')
      expect(screen.getByLabelText(/featureFlags.form.name/i)).toHaveValue('Test Feature')
      expect(screen.getByLabelText(/featureFlags.form.description/i)).toHaveValue('A test feature flag')
    })

    it('disables key field in edit mode', () => {
      const initialData: FeatureFlag = {
        id: 'flag-1',
        key: 'test_feature',
        name: 'Test Feature',
        description: 'A test feature flag',
        default_enabled: true,
        created_time: '2024-01-01T00:00:00Z',
        updated_time: '2024-01-01T00:00:00Z',
      }

      render(<FeatureFlagForm {...defaultProps} initialData={initialData} />)

      expect(screen.getByLabelText(/featureFlags.form.key/i)).toBeDisabled()
    })

    it('enables key field in create mode', () => {
      render(<FeatureFlagForm {...defaultProps} />)

      expect(screen.getByLabelText(/featureFlags.form.key/i)).not.toBeDisabled()
    })
  })

  describe('Validation - Key Field', () => {
    it('shows error when key is empty', async () => {
      const { user } = render(<FeatureFlagForm {...defaultProps} />)

      // Fill name (required) but leave key empty
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText(/featureFlags.validation.keyRequired/i)).toBeInTheDocument()
      })
    })

    it('shows error for invalid key format (uppercase)', async () => {
      const { user } = render(<FeatureFlagForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'Invalid_Key')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText(/featureFlags.validation.keyFormat/i)).toBeInTheDocument()
      })
    })

    it('shows error for invalid key format (spaces)', async () => {
      const { user } = render(<FeatureFlagForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'invalid key')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText(/featureFlags.validation.keyFormat/i)).toBeInTheDocument()
      })
    })

    it('accepts valid key format with lowercase, numbers, hyphens, and underscores', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'valid-key_123')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({ key: 'valid-key_123' })
        )
      })
    })
  })

  describe('Validation - Name Field', () => {
    it('shows error when name is empty', async () => {
      const { user } = render(<FeatureFlagForm {...defaultProps} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'test_key')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText(/featureFlags.validation.nameRequired/i)).toBeInTheDocument()
      })
    })
  })

  describe('Form Submission', () => {
    it('calls onSubmit with form data when valid', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'new_feature')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'New Feature')
      await user.type(screen.getByLabelText(/featureFlags.form.description/i), 'A new feature description')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          key: 'new_feature',
          name: 'New Feature',
          description: 'A new feature description',
          default_enabled: false,
        })
      })
    })

    it('does not call onSubmit when form is invalid', async () => {
      const onSubmit = vi.fn()
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      // Submit with empty required fields
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText(/featureFlags.validation.keyRequired/i)).toBeInTheDocument()
      })

      expect(onSubmit).not.toHaveBeenCalled()
    })

    it('disables submit button while submitting', () => {
      render(<FeatureFlagForm {...defaultProps} isSubmitting />)

      expect(screen.getByRole('button', { name: /featureFlags.form.saving/i })).toBeDisabled()
    })

    it('shows saving text while submitting', () => {
      render(<FeatureFlagForm {...defaultProps} isSubmitting />)

      expect(screen.getByRole('button', { name: /featureFlags.form.saving/i })).toBeInTheDocument()
    })

    it('displays root error from API failure', async () => {
      const onSubmit = vi.fn().mockRejectedValue({
        data: { detail: 'Feature flag key already exists' },
      })
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'existing_key')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(screen.getByText('Feature flag key already exists')).toBeInTheDocument()
      })
    })
  })

  describe('Cancel Functionality', () => {
    it('calls onCancel when cancel button is clicked', async () => {
      const onCancel = vi.fn()
      const { user } = render(<FeatureFlagForm {...defaultProps} onCancel={onCancel} />)

      await user.click(screen.getByRole('button', { name: /featureFlags.form.cancel/i }))

      expect(onCancel).toHaveBeenCalled()
    })
  })

  describe('Default Enabled Toggle', () => {
    it('default_enabled is false by default', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'test_key')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')
      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({ default_enabled: false })
        )
      })
    })

    it('can toggle default_enabled to true', async () => {
      const onSubmit = vi.fn().mockResolvedValue(undefined)
      const { user } = render(<FeatureFlagForm {...defaultProps} onSubmit={onSubmit} />)

      await user.type(screen.getByLabelText(/featureFlags.form.key/i), 'test_key')
      await user.type(screen.getByLabelText(/featureFlags.form.name/i), 'Test Feature')

      // Click the switch to enable
      const switchElement = screen.getByRole('switch')
      await user.click(switchElement)

      await user.click(screen.getByRole('button', { name: /featureFlags.form.save/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({ default_enabled: true })
        )
      })
    })
  })
})
