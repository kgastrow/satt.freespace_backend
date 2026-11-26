import { describe, it, expect } from 'vitest'
import { render } from '@/test/utils'
import { FormSkeleton } from './FormSkeleton'

describe('FormSkeleton', () => {
  it('renders with default number of fields', () => {
    const { container } = render(<FormSkeleton />)

    // Check that skeleton elements are rendered
    const skeletons = container.querySelectorAll('.animate-pulse')
    // Default 4 fields: each field has label (1) + input (1) = 8, plus button (1) = 9 total
    expect(skeletons.length).toBe(9)
  })

  it('renders custom number of fields when specified', () => {
    const { container } = render(<FormSkeleton fields={2} />)

    // 2 fields: each field has label (1) + input (1) = 4, plus button (1) = 5 total
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(5)
  })

  it('renders with single field', () => {
    const { container } = render(<FormSkeleton fields={1} />)

    // 1 field: label (1) + input (1) + button (1) = 3 total
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('renders with many fields', () => {
    const { container } = render(<FormSkeleton fields={8} />)

    // 8 fields: each field has label (1) + input (1) = 16, plus button (1) = 17 total
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(17)
  })

  it('applies custom className', () => {
    const { container } = render(<FormSkeleton className="custom-form-class" />)

    const formContainer = container.querySelector('.custom-form-class')
    expect(formContainer).toBeInTheDocument()
  })

  it('renders label skeletons with correct dimensions', () => {
    const { container } = render(<FormSkeleton fields={1} />)

    // Label skeleton should have h-4 w-32 classes
    const labelSkeleton = container.querySelector('.h-4.w-32')
    expect(labelSkeleton).toBeInTheDocument()
  })

  it('renders input field skeletons with correct dimensions', () => {
    const { container } = render(<FormSkeleton fields={1} />)

    // Input skeleton should have h-10 w-full classes
    const inputSkeleton = container.querySelector('.h-10.w-full.rounded-md')
    expect(inputSkeleton).toBeInTheDocument()
  })

  it('renders button skeleton at the bottom', () => {
    const { container } = render(<FormSkeleton fields={2} />)

    // Button skeleton should have h-10 w-32 classes and be in a pt-4 container
    const buttonContainer = container.querySelector('.pt-4')
    expect(buttonContainer).toBeInTheDocument()

    const buttonSkeleton = container.querySelector('.pt-4 .h-10.w-32.rounded-md')
    expect(buttonSkeleton).toBeInTheDocument()
  })

  it('renders with zero fields', () => {
    const { container } = render(<FormSkeleton fields={0} />)

    // Only button skeleton should be rendered
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(1)

    // Button should still be present
    const buttonSkeleton = container.querySelector('.h-10.w-32.rounded-md')
    expect(buttonSkeleton).toBeInTheDocument()
  })

  it('has proper spacing between fields', () => {
    const { container } = render(<FormSkeleton fields={3} />)

    // Main container should have space-y-6 class
    const mainContainer = container.querySelector('.space-y-6')
    expect(mainContainer).toBeInTheDocument()

    // Each field should have space-y-2 class
    const fieldContainers = container.querySelectorAll('.space-y-2')
    // Should have 3 field containers (one for each field)
    expect(fieldContainers.length).toBe(3)
  })

  it('button has top padding', () => {
    const { container } = render(<FormSkeleton />)

    // Button container should have pt-4 class
    const buttonContainer = container.querySelector('.pt-4')
    expect(buttonContainer).toBeInTheDocument()
  })

  it('renders all skeletons with pulse animation', () => {
    const { container } = render(<FormSkeleton fields={2} />)

    // All skeleton elements should have animate-pulse class
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)

    // Verify all are Skeleton components by checking for the animate-pulse class
    skeletons.forEach((skeleton) => {
      expect(skeleton.classList.contains('animate-pulse')).toBe(true)
    })
  })
})
