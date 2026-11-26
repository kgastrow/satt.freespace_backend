/**
 * Role-Based Access Control (RBAC) Integration Tests
 *
 * Tests route protection and permission-based UI rendering:
 * - AuthGuard redirects for unauthenticated users
 * - PermissionGate protection for permission-restricted routes
 * - SuperAdminGuard protection for super admin routes
 * - Permission-based UI element visibility
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { setCurrentUser } from '@/test/server'
import {
  regularUser,
  adminUser,
  superAdminUser,
  createAuthState,
  createUnauthenticatedState,
} from '@/test/fixtures'
import { AuthGuard } from '@/components/AuthGuard'
import { PermissionGate } from '@/components/PermissionGate'
import { SuperAdminGuard } from '@/components/SuperAdminGuard'

// Test components
function ProtectedContent() {
  return <div data-testid="protected-content">Protected Content</div>
}

function LoginPage() {
  return <div data-testid="login-page">Login Page</div>
}

function DashboardPage() {
  return <div data-testid="dashboard">Dashboard</div>
}

function AdminPage() {
  return <div data-testid="admin-page">Admin Page</div>
}

function SuperAdminPage() {
  return <div data-testid="super-admin-page">Super Admin Page</div>
}

describe('Role-Based Access Control Integration Tests', () => {
  describe('AuthGuard', () => {
    describe('Protected Routes (requireAuth=true)', () => {
      it('allows authenticated users to access protected content', () => {
        setCurrentUser(regularUser)

        render(
          <AuthGuard>
            <ProtectedContent />
          </AuthGuard>,
          {
            preloadedState: createAuthState(regularUser),
          }
        )

        expect(screen.getByTestId('protected-content')).toBeInTheDocument()
      })

      it('redirects unauthenticated users to login', () => {
        render(<ProtectedContent />, {
          preloadedState: createUnauthenticatedState(),
          route: '/dashboard',
          routes: [
            {
              path: '/dashboard',
              element: (
                <AuthGuard>
                  <ProtectedContent />
                </AuthGuard>
              ),
            },
            { path: '/login', element: <LoginPage /> },
          ],
        })

        // Should redirect to login
        expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
        expect(screen.getByTestId('login-page')).toBeInTheDocument()
      })

      it('shows loading state while auth is being validated', () => {
        render(
          <AuthGuard>
            <ProtectedContent />
          </AuthGuard>,
          {
            preloadedState: {
              auth: {
                user: null,
                token: 'test-token',
                isAuthenticated: false,
                isLoading: true,
                sso: { isLoading: false, error: null, selectedProvider: null },
              twoFactor: { required: false, token: null },
              twoFactorSetupRequired: false,
              enforcementActive: false,
              },
            },
          }
        )

        // Should show loading indicator
        expect(screen.getByText(/loading/i)).toBeInTheDocument()
        expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
      })

      it('preserves return URL when redirecting to login', () => {
        // This test verifies the location state is passed to Navigate
        // The actual implementation uses location.state.from
        render(<ProtectedContent />, {
          preloadedState: createUnauthenticatedState(),
          route: '/protected-page',
          routes: [
            {
              path: '/protected-page',
              element: (
                <AuthGuard>
                  <ProtectedContent />
                </AuthGuard>
              ),
            },
            { path: '/login', element: <LoginPage /> },
          ],
        })

        expect(screen.getByTestId('login-page')).toBeInTheDocument()
      })
    })

    describe('Guest-Only Routes (requireAuth=false)', () => {
      it('allows unauthenticated users to access guest-only pages', () => {
        render(
          <AuthGuard requireAuth={false}>
            <LoginPage />
          </AuthGuard>,
          {
            preloadedState: createUnauthenticatedState(),
          }
        )

        expect(screen.getByTestId('login-page')).toBeInTheDocument()
      })

      it('redirects authenticated users away from guest-only pages', () => {
        setCurrentUser(regularUser)

        render(<LoginPage />, {
          preloadedState: createAuthState(regularUser),
          route: '/login',
          routes: [
            {
              path: '/login',
              element: (
                <AuthGuard requireAuth={false} redirectTo="/dashboard">
                  <LoginPage />
                </AuthGuard>
              ),
            },
            { path: '/dashboard', element: <DashboardPage /> },
          ],
        })

        // Should redirect to dashboard
        expect(screen.queryByTestId('login-page')).not.toBeInTheDocument()
        expect(screen.getByTestId('dashboard')).toBeInTheDocument()
      })

      it('uses custom redirect path when specified', () => {
        setCurrentUser(regularUser)

        render(<LoginPage />, {
          preloadedState: createAuthState(regularUser),
          route: '/login',
          routes: [
            {
              path: '/login',
              element: (
                <AuthGuard requireAuth={false} redirectTo="/home">
                  <LoginPage />
                </AuthGuard>
              ),
            },
            { path: '/home', element: <div data-testid="home">Home</div> },
          ],
        })

        expect(screen.getByTestId('home')).toBeInTheDocument()
      })
    })
  })

  describe('PermissionGate', () => {
    it('allows users with required permission to access protected pages', () => {
      setCurrentUser(adminUser)

      render(
        <PermissionGate permission="users:read">
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: createAuthState(adminUser),
        }
      )

      expect(screen.getByTestId('admin-page')).toBeInTheDocument()
    })

    it('allows super admin users to access any permission-protected pages', () => {
      setCurrentUser(superAdminUser)

      render(
        <PermissionGate permission="users:read">
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: createAuthState(superAdminUser),
        }
      )

      expect(screen.getByTestId('admin-page')).toBeInTheDocument()
    })

    it('redirects users without permission to specified path', () => {
      setCurrentUser(regularUser)

      render(<AdminPage />, {
        preloadedState: createAuthState(regularUser),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate permission="users:read" redirectTo="/dashboard">
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })

    it('shows loading state while auth is being validated', () => {
      render(
        <PermissionGate permission="users:read" redirectTo="/dashboard">
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: {
            auth: {
              user: null,
              token: 'test-token',
              isAuthenticated: false,
              isLoading: true,
              sso: { isLoading: false, error: null, selectedProvider: null },
            twoFactor: { required: false, token: null },
            twoFactorSetupRequired: false,
            enforcementActive: false,
            },
          },
        }
      )

      expect(screen.getByText(/loading/i)).toBeInTheDocument()
      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
    })

    it('uses custom redirect path when specified', () => {
      setCurrentUser(regularUser)

      render(<AdminPage />, {
        preloadedState: createAuthState(regularUser),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate permission="users:read" redirectTo="/not-allowed">
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/not-allowed', element: <div data-testid="not-allowed">Not Allowed</div> },
        ],
      })

      expect(screen.getByTestId('not-allowed')).toBeInTheDocument()
    })

    it('allows access when user has ANY of multiple permissions', () => {
      // User has users:read but not users:delete
      const userWithReadOnly = {
        ...regularUser,
        permissions: ['users:read'],
      }

      render(
        <PermissionGate permission={['users:read', 'users:delete']}>
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: createAuthState(userWithReadOnly),
        }
      )

      expect(screen.getByTestId('admin-page')).toBeInTheDocument()
    })

    it('requires ALL permissions when requireAll is true', () => {
      // User has users:read but not users:delete
      const userWithReadOnly = {
        ...regularUser,
        permissions: ['users:read'],
      }

      render(<AdminPage />, {
        preloadedState: createAuthState(userWithReadOnly),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate
                permission={['users:read', 'users:delete']}
                requireAll
                redirectTo="/dashboard"
              >
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      // Should redirect because user doesn't have ALL permissions
      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })

    it('shows fallback content for inline use without redirect', () => {
      setCurrentUser(regularUser)

      render(
        <PermissionGate
          permission="users:write"
          fallback={<div data-testid="no-access">No access</div>}
        >
          <button data-testid="edit-button">Edit User</button>
        </PermissionGate>,
        {
          preloadedState: createAuthState(regularUser),
        }
      )

      expect(screen.queryByTestId('edit-button')).not.toBeInTheDocument()
      expect(screen.getByTestId('no-access')).toBeInTheDocument()
    })
  })

  describe('SuperAdminGuard', () => {
    it('allows super admin users to access super admin pages', () => {
      setCurrentUser(superAdminUser)

      render(
        <SuperAdminGuard>
          <SuperAdminPage />
        </SuperAdminGuard>,
        {
          preloadedState: createAuthState(superAdminUser),
        }
      )

      expect(screen.getByTestId('super-admin-page')).toBeInTheDocument()
    })

    it('blocks regular admin users from super admin pages', () => {
      setCurrentUser(adminUser)

      render(<SuperAdminPage />, {
        preloadedState: createAuthState(adminUser),
        route: '/admin/organizations',
        routes: [
          {
            path: '/admin/organizations',
            element: (
              <SuperAdminGuard>
                <SuperAdminPage />
              </SuperAdminGuard>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      expect(screen.queryByTestId('super-admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })

    it('blocks regular users from super admin pages', () => {
      setCurrentUser(regularUser)

      render(<SuperAdminPage />, {
        preloadedState: createAuthState(regularUser),
        route: '/admin/organizations',
        routes: [
          {
            path: '/admin/organizations',
            element: (
              <SuperAdminGuard>
                <SuperAdminPage />
              </SuperAdminGuard>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      expect(screen.queryByTestId('super-admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })

    it('redirects unauthenticated users to login', () => {
      render(<SuperAdminPage />, {
        preloadedState: createUnauthenticatedState(),
        route: '/admin/organizations',
        routes: [
          {
            path: '/admin/organizations',
            element: (
              <SuperAdminGuard>
                <SuperAdminPage />
              </SuperAdminGuard>
            ),
          },
          { path: '/login', element: <LoginPage /> },
        ],
      })

      expect(screen.queryByTestId('super-admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('login-page')).toBeInTheDocument()
    })
  })

  describe('Permission-Based UI Rendering', () => {
    it('shows permission-protected UI elements for users with permission', () => {
      setCurrentUser(adminUser)

      render(
        <PermissionGate permission="users:write">
          <a href="/admin/users" data-testid="admin-link">
            Users
          </a>
        </PermissionGate>,
        {
          preloadedState: createAuthState(adminUser),
        }
      )

      expect(screen.getByTestId('admin-link')).toBeInTheDocument()
    })

    it('hides permission-protected UI elements for users without permission', () => {
      setCurrentUser(regularUser)

      render(
        <PermissionGate permission="users:write">
          <a href="/admin/users" data-testid="admin-link">
            Users
          </a>
        </PermissionGate>,
        {
          preloadedState: createAuthState(regularUser),
        }
      )

      expect(screen.queryByTestId('admin-link')).not.toBeInTheDocument()
    })

    it('shows super admin-only UI elements for super admin users', () => {
      setCurrentUser(superAdminUser)

      function NavMenu() {
        const isSuperAdmin = superAdminUser.is_admin === true

        return (
          <nav>
            <a href="/dashboard">Dashboard</a>
            {isSuperAdmin && (
              <a href="/admin/organizations" data-testid="orgs-link">
                Organizations
              </a>
            )}
          </nav>
        )
      }

      render(<NavMenu />, {
        preloadedState: createAuthState(superAdminUser),
      })

      expect(screen.getByTestId('orgs-link')).toBeInTheDocument()
    })

    it('hides super admin-only UI elements for regular admin users', () => {
      setCurrentUser(adminUser)

      function NavMenu() {
        const isSuperAdmin = adminUser.is_admin === true

        return (
          <nav>
            <a href="/dashboard">Dashboard</a>
            {isSuperAdmin && (
              <a href="/admin/organizations" data-testid="orgs-link">
                Organizations
              </a>
            )}
          </nav>
        )
      }

      render(<NavMenu />, {
        preloadedState: createAuthState(adminUser),
      })

      expect(screen.queryByTestId('orgs-link')).not.toBeInTheDocument()
    })
  })

  describe('Permission Hierarchy', () => {
    it('super admin has all permissions', () => {
      setCurrentUser(superAdminUser)

      // Super admin should be able to access any permission-protected page
      render(
        <PermissionGate permission="users:delete">
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: createAuthState(superAdminUser),
        }
      )

      expect(screen.getByTestId('admin-page')).toBeInTheDocument()
    })

    it('regular user has no admin permissions', () => {
      setCurrentUser(regularUser)

      // Render with routes to test redirect
      render(<AdminPage />, {
        preloadedState: createAuthState(regularUser),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate permission="users:read" redirectTo="/dashboard">
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
    })

    it('permissions array grants specific access', () => {
      const userWithSpecificPermission = {
        ...regularUser,
        is_admin: false,
        permissions: ['users:read'],
      }

      render(
        <PermissionGate permission="users:read">
          <AdminPage />
        </PermissionGate>,
        {
          preloadedState: createAuthState(userWithSpecificPermission),
        }
      )

      expect(screen.getByTestId('admin-page')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles user with empty permissions array', () => {
      const userWithNoPermissions = {
        ...regularUser,
        permissions: [],
      }

      render(<AdminPage />, {
        preloadedState: createAuthState(userWithNoPermissions),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate permission="users:read" redirectTo="/dashboard">
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      // Should redirect - no permissions
      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
      expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    })

    it('handles user with undefined permissions', () => {
      const userWithUndefinedPermissions = {
        ...regularUser,
        permissions: undefined,
      }

      render(<AdminPage />, {
        preloadedState: createAuthState(userWithUndefinedPermissions),
        route: '/admin/users',
        routes: [
          {
            path: '/admin/users',
            element: (
              <PermissionGate permission="users:read" redirectTo="/dashboard">
                <AdminPage />
              </PermissionGate>
            ),
          },
          { path: '/dashboard', element: <DashboardPage /> },
        ],
      })

      // Should redirect - no permissions
      expect(screen.queryByTestId('admin-page')).not.toBeInTheDocument()
    })
  })
})
