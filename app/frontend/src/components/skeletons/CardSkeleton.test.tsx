import { describe, it, expect } from 'vitest'
import { render } from '@/test/utils'
import { CardSkeleton } from './CardSkeleton'

describe('CardSkeleton', () => {
  it('renders default variant by default', () => {
    const { container } = render(<CardSkeleton />)

    // Check that skeleton elements are rendered (animate-pulse class)
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)

    // Default variant has CardHeader and CardContent structure
    const cardHeader = container.querySelector('[class*="space-y"]')
    expect(cardHeader).toBeInTheDocument()
  })

  it('renders stats variant correctly', () => {
    const { container } = render(<CardSkeleton variant="stats" />)

    // Stats variant should have skeleton elements
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)

    // Stats variant has specific structure with flex layout
    const flexContainer = container.querySelector('.flex.items-center.gap-4')
    expect(flexContainer).toBeInTheDocument()

    // Should have an icon placeholder (12x12 rounded)
    const iconSkeleton = container.querySelector('.h-12.w-12.rounded-lg')
    expect(iconSkeleton).toBeInTheDocument()
  })

  it('renders grid-item variant correctly', () => {
    const { container } = render(<CardSkeleton variant="grid-item" />)

    // Grid-item variant should have skeleton elements
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)

    // Grid-item has image placeholder (h-32)
    const imageSkeleton = container.querySelector('.h-32.w-full.rounded-md')
    expect(imageSkeleton).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<CardSkeleton className="custom-class" />)

    // Card should have the custom class
    const card = container.querySelector('.custom-class')
    expect(card).toBeInTheDocument()
  })

  it('applies custom className to stats variant', () => {
    const { container } = render(
      <CardSkeleton variant="stats" className="custom-stats" />
    )

    const card = container.querySelector('.custom-stats')
    expect(card).toBeInTheDocument()
  })

  it('applies custom className to grid-item variant', () => {
    const { container } = render(
      <CardSkeleton variant="grid-item" className="custom-grid" />
    )

    const card = container.querySelector('.custom-grid')
    expect(card).toBeInTheDocument()
  })

  it('default variant has multiple skeleton lines', () => {
    const { container } = render(<CardSkeleton variant="default" />)

    // Default variant should have multiple skeleton lines in CardContent
    const skeletons = container.querySelectorAll('.animate-pulse')
    // Should have at least header skeletons (2) + content skeletons (3) = 5
    expect(skeletons.length).toBeGreaterThanOrEqual(5)
  })

  it('stats variant has two skeleton elements', () => {
    const { container } = render(<CardSkeleton variant="stats" />)

    // Stats variant: icon (1) + label (1) + value (1) = 3 skeletons
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('grid-item variant has three skeleton elements', () => {
    const { container } = render(<CardSkeleton variant="grid-item" />)

    // Grid-item variant: image (1) + title (1) + subtitle (1) = 3 skeletons
    const skeletons = container.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('renders with Card component structure', () => {
    const { container } = render(<CardSkeleton />)

    // Should have Card component structure
    const card = container.querySelector('[class*="rounded"]')
    expect(card).toBeInTheDocument()
  })
})
