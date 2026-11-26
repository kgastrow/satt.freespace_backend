import { describe, it, expect, vi } from 'vitest'
import { render } from '@/test/utils'
import { ForgotPasswordPage } from './ForgotPasswordPage'

// Mock the password reset mutation - must mock the entire module
vi.mock('@/features/auth/authApi', async () => {
  const actual = await vi.importActual('@/features/auth/authApi')
  return {
    ...actual,
    useRequestPasswordResetMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  }
})

describe('ForgotPasswordPage', () => {
  it('renders without crashing', () => {
    const { container } = render(<ForgotPasswordPage />)
    expect(container).toBeInTheDocument()
  })

  it('renders form element', () => {
    const { container } = render(<ForgotPasswordPage />)
    const form = container.querySelector('form')
    expect(form).toBeInTheDocument()
  })
})
