import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { AdminHubPage } from './AdminHubPage'
import { createAuthState, regularUser, adminUser, superAdminUser } from '@/test/fixtures'
import type { User } from '@/types/auth'

describe('AdminHubPage', () => {
  it('shows empty state when user has no admin permissions', () => {
    render(<AdminHubPage />, {
      preloadedState: createAuthState(regularUser),
    })

    expect(screen.getByText('common:adminHub.emptyState')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has admin permissions', () => {
    render(<AdminHubPage />, {
      preloadedState: createAuthState(adminUser),
    })

    // adminUser has these permissions: users:read, users:write, organization:read, audit_logs:read
    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
    expect(screen.queryByText('common:adminHub.emptyState')).not.toBeInTheDocument()
  })

  it('shows sidebar prompt for super admin', () => {
    render(<AdminHubPage />, {
      preloadedState: createAuthState(superAdminUser),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has at least one admin permission', () => {
    const userWithOnePermission: User = {
      ...regularUser,
      permissions: ['audit_logs:read'],
    }

    render(<AdminHubPage />, {
      preloadedState: createAuthState(userWithOnePermission),
    })

    expect(screen.queryByText('common:adminHub.emptyState')).not.toBeInTheDocument()
    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has api_keys permission', () => {
    const userWithApiKeys: User = {
      ...regularUser,
      permissions: ['api_keys:read', 'api_keys:write'],
    }

    render(<AdminHubPage />, {
      preloadedState: createAuthState(userWithApiKeys),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has notification permissions', () => {
    const userWithNotifications: User = {
      ...regularUser,
      permissions: ['notifications:read', 'notifications:write'],
    }

    render(<AdminHubPage />, {
      preloadedState: createAuthState(userWithNotifications),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has files permissions', () => {
    const userWithFiles: User = {
      ...regularUser,
      permissions: ['files:read', 'files:admin'],
    }

    render(<AdminHubPage />, {
      preloadedState: createAuthState(userWithFiles),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })

  it('shows sidebar prompt when user has multiple permission sets', () => {
    const userWithMultiplePerms: User = {
      ...regularUser,
      permissions: [
        'users:read',
        'api_keys:write',
        'audit_logs:read',
        'notifications:send',
      ],
    }

    render(<AdminHubPage />, {
      preloadedState: createAuthState(userWithMultiplePerms),
    })

    expect(screen.getByText('selectFromSidebar')).toBeInTheDocument()
  })
})
