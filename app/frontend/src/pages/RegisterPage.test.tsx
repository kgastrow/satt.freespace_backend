import { describe, it, expect, vi } from 'vitest'
import { render } from '@/test/utils'
import { RegisterPage } from './RegisterPage'

// Mock the register mutation - must mock the entire module
vi.mock('@/features/auth/authApi', async () => {
  const actual = await vi.importActual('@/features/auth/authApi')
  return {
    ...actual,
    useRegisterMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  }
})

describe('RegisterPage', () => {
  it('renders without crashing', () => {
    const { container } = render(<RegisterPage />)
    expect(container).toBeInTheDocument()
  })

  it('renders form element', () => {
    const { container } = render(<RegisterPage />)
    const form = container.querySelector('form')
    expect(form).toBeInTheDocument()
  })
})
