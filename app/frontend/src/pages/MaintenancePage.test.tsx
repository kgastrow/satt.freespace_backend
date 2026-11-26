import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { MaintenancePage } from './MaintenancePage'

describe('MaintenancePage', () => {
  const defaultMaintenanceState = {
    maintenance: {
      isMaintenanceActive: true,
      message: null,
      scheduledEnd: null,
      lastChecked: null,
    },
  }

  it('renders maintenance title', () => {
    render(<MaintenancePage />, {
      preloadedState: defaultMaintenanceState,
    })

    expect(screen.getByText('maintenance.title')).toBeInTheDocument()
  })

  it('renders without crashing', () => {
    render(<MaintenancePage />, {
      preloadedState: defaultMaintenanceState,
    })

    expect(document.body).toBeInTheDocument()
  })

  it('shows custom message when provided', () => {
    render(<MaintenancePage />, {
      preloadedState: {
        maintenance: {
          isMaintenanceActive: true,
          message: 'Custom maintenance message',
          scheduledEnd: null,
          lastChecked: null,
        },
      },
    })

    expect(screen.getByText('Custom maintenance message')).toBeInTheDocument()
  })
})
