import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { NotFoundPage } from './NotFoundPage'

describe('NotFoundPage', () => {
  it('renders 404 heading', () => {
    render(<NotFoundPage />)

    expect(screen.getByText('404')).toBeInTheDocument()
  })

  it('shows not found title', () => {
    render(<NotFoundPage />)

    expect(screen.getByText('errors:notFound.title')).toBeInTheDocument()
  })

  it('shows description text', () => {
    render(<NotFoundPage />)

    expect(screen.getByText('errors:notFound.description')).toBeInTheDocument()
  })

  it('has home button with link', () => {
    render(<NotFoundPage />)

    const homeLink = screen.getByRole('link', { name: /errors:notFound.goHome/i })
    expect(homeLink).toHaveAttribute('href', '/')
  })

  it('has go back button', () => {
    render(<NotFoundPage />)

    expect(screen.getByRole('button', { name: /errors:notFound.goBack/i })).toBeInTheDocument()
  })
})
