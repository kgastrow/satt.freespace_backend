import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { AdminCard } from './AdminCard'
import { Settings } from 'lucide-react'

describe('AdminCard', () => {
  const defaultProps = {
    icon: Settings,
    title: 'Organization Settings',
    description: 'Manage organization configuration and preferences',
    to: '/admin/organization',
  }

  it('renders icon, title, and description correctly', () => {
    render(<AdminCard {...defaultProps} />)

    expect(screen.getByText('Organization Settings')).toBeInTheDocument()
    expect(
      screen.getByText('Manage organization configuration and preferences')
    ).toBeInTheDocument()
    expect(screen.getByRole('link')).toBeInTheDocument()
  })

  it('renders as a link to the specified route', () => {
    render(<AdminCard {...defaultProps} />)

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/admin/organization')
  })

  it('renders with custom className', () => {
    render(<AdminCard {...defaultProps} className="border-destructive/20" />)

    const link = screen.getByRole('link')
    const card = link.querySelector('[class*="border-destructive"]')
    expect(card).toBeInTheDocument()
  })

  it('renders the icon component', () => {
    render(<AdminCard {...defaultProps} />)

    // Check for the icon's SVG element
    const link = screen.getByRole('link')
    const svg = link.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('applies hover styles via className', () => {
    render(<AdminCard {...defaultProps} />)

    const link = screen.getByRole('link')
    const card = link.querySelector('[class*="hover:shadow-md"]')
    expect(card).toBeInTheDocument()
  })

  it('renders different content for different props', () => {
    const customProps = {
      icon: Settings,
      title: 'Users',
      description: 'Manage user accounts',
      to: '/admin/users',
    }
    render(<AdminCard {...customProps} />)

    expect(screen.getByText('Users')).toBeInTheDocument()
    expect(screen.getByText('Manage user accounts')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/admin/users')
  })
})
