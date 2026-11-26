/**
 * TagInput Component Tests
 *
 * Tests for the tag input component including:
 * - Basic rendering
 * - Adding tags via Enter key
 * - Removing tags via backspace and click
 * - Duplicate tag prevention
 * - Disabled state
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TagInput } from '@/components/TagInput'

describe('TagInput', () => {
  const defaultProps = {
    value: [] as string[],
    onChange: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders correctly with empty value', () => {
      render(<TagInput {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('placeholder', 'Type and press Enter...')
    })

    it('renders with custom placeholder', () => {
      render(<TagInput {...defaultProps} placeholder="Add a tag..." />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', 'Add a tag...')
    })

    it('renders existing tags as badges', () => {
      render(<TagInput {...defaultProps} value={['react', 'typescript']} />)

      expect(screen.getByText('react')).toBeInTheDocument()
      expect(screen.getByText('typescript')).toBeInTheDocument()
    })

    it('hides placeholder when tags exist', () => {
      render(<TagInput {...defaultProps} value={['react']} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveAttribute('placeholder', '')
    })
  })

  describe('Adding Tags', () => {
    it('adds a tag when Enter is pressed with non-empty input', () => {
      const onChange = vi.fn()
      render(<TagInput value={[]} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'javascript' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith(['javascript'])
    })

    it('converts tag to lowercase', () => {
      const onChange = vi.fn()
      render(<TagInput value={[]} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'JavaScript' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith(['javascript'])
    })

    it('trims whitespace from tags', () => {
      const onChange = vi.fn()
      render(<TagInput value={[]} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '  react  ' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith(['react'])
    })

    it('prevents adding duplicate tags', () => {
      const onChange = vi.fn()
      render(<TagInput value={['react']} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'react' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).not.toHaveBeenCalled()
    })

    it('does not add empty tags', () => {
      const onChange = vi.fn()
      render(<TagInput value={[]} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '   ' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).not.toHaveBeenCalled()
    })

    it('clears input after adding a tag', () => {
      render(<TagInput {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'react' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(input).toHaveValue('')
    })

    it('appends to existing tags', () => {
      const onChange = vi.fn()
      render(<TagInput value={['react']} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'typescript' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(onChange).toHaveBeenCalledWith(['react', 'typescript'])
    })
  })

  describe('Removing Tags', () => {
    it('removes the last tag when Backspace is pressed with empty input', () => {
      const onChange = vi.fn()
      render(<TagInput value={['react', 'typescript']} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.keyDown(input, { key: 'Backspace' })

      expect(onChange).toHaveBeenCalledWith(['react'])
    })

    it('does not remove tag when Backspace is pressed with non-empty input', () => {
      const onChange = vi.fn()
      render(<TagInput value={['react']} onChange={onChange} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: 'type' } })
      fireEvent.keyDown(input, { key: 'Backspace' })

      expect(onChange).not.toHaveBeenCalled()
    })

    it('removes a specific tag when clicking the remove button', () => {
      const onChange = vi.fn()
      render(<TagInput value={['react', 'typescript', 'vue']} onChange={onChange} />)

      // Find the remove button inside the "typescript" badge
      const typescriptBadge = screen.getByText('typescript').closest('span')
      const removeButton = typescriptBadge?.querySelector('button')
      expect(removeButton).toBeInTheDocument()

      fireEvent.click(removeButton!)

      expect(onChange).toHaveBeenCalledWith(['react', 'vue'])
    })
  })

  describe('Disabled State', () => {
    it('disables the input when disabled prop is true', () => {
      render(<TagInput {...defaultProps} disabled />)

      const input = screen.getByRole('textbox')
      expect(input).toBeDisabled()
    })

    it('hides remove buttons when disabled', () => {
      render(<TagInput value={['react']} onChange={vi.fn()} disabled />)

      const reactBadge = screen.getByText('react').closest('span')
      const removeButton = reactBadge?.querySelector('button')
      expect(removeButton).not.toBeInTheDocument()
    })

    it('applies disabled styling to container', () => {
      const { container } = render(<TagInput {...defaultProps} disabled />)

      const wrapper = container.firstChild
      expect(wrapper).toHaveClass('opacity-50')
      expect(wrapper).toHaveClass('cursor-not-allowed')
    })
  })

  describe('Custom Styling', () => {
    it('applies custom className to container', () => {
      const { container } = render(
        <TagInput {...defaultProps} className="custom-class" />
      )

      const wrapper = container.firstChild
      expect(wrapper).toHaveClass('custom-class')
    })
  })
})
