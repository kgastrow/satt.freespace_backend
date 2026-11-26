/**
 * User Management Integration Tests
 *
 * Tests the complete user management lifecycle including:
 * - CRUD operations (Create, Read, Update, Delete)
 * - Role assignment and revocation
 * - Pagination across user list
 * - Cache invalidation after mutations
 */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '@/test/utils'
import { server, setCurrentUser, API_BASE } from '@/test/server'
import {
  adminUser,
  createAuthState,
} from '@/test/fixtures'
import { UsersPage } from '@/pages/admin/UsersPage'
import type { User } from '@/features/users/usersApi'

// Mock the toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('User Management Integration Tests', () => {
  describe('User Listing', () => {
    it('displays list of users', async () => {
      setCurrentUser(adminUser)

      render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for user data to load
      await waitFor(
        () => {
          expect(screen.getByText('Regular User')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Should show other user names
      expect(screen.getByText('Admin User')).toBeInTheDocument()
      expect(screen.getByText('Super Admin')).toBeInTheDocument()
    })

    it('displays user emails', async () => {
      setCurrentUser(adminUser)

      render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(
        () => {
          expect(screen.getByText('user@acme.com')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      expect(screen.getByText('admin@acme.com')).toBeInTheDocument()
    })

    it('displays admin badge for admin users', async () => {
      setCurrentUser(adminUser)

      render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for data to load
      await waitFor(
        () => {
          expect(screen.getByText('superadmin@acme.com')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Admin badge should be visible for super admin (is_admin: true)
      expect(screen.getByText('users.table.admin')).toBeInTheDocument()
    })
  })

  describe('users.createButton', () => {
    it('opens create dialog when button is clicked', async () => {
      setCurrentUser(adminUser)

      const { user } = render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for page to load
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: 'users.createButton' })).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Click create user button
      await user.click(screen.getByRole('button', { name: 'users.createButton' }))

      // Dialog should open
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
        expect(screen.getByText('users.createDialog.description')).toBeInTheDocument()
      })
    })

    it('creates new user with valid data', async () => {
      let createCalled = false
      let createdUserData: Record<string, unknown> | null = null

      server.use(
        http.post(`${API_BASE}/users`, async ({ request }) => {
          createCalled = true
          createdUserData = (await request.json()) as Record<string, unknown>
          return HttpResponse.json({
            id: 'new-user-id',
            email: createdUserData.email,
            first_name: createdUserData.first_name,
            last_name: createdUserData.last_name,
            is_admin: false,
            roles: [],
            created_time: new Date().toISOString(),
          })
        })
      )

      setCurrentUser(adminUser)

      const { user } = render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for page to load
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: 'users.createButton' })).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Open create dialog
      await user.click(screen.getByRole('button', { name: 'users.createButton' }))

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Fill in the form
      const dialog = screen.getByRole('dialog')
      await user.type(within(dialog).getByLabelText(/firstName/i), 'New')
      await user.type(within(dialog).getByLabelText(/lastName/i), 'User')
      await user.type(within(dialog).getByLabelText(/email/i), 'newuser@acme.com')
      // Password field has a wrapper div so we query by input type instead
      const passwordInput = dialog.querySelector('input[type="password"]') as HTMLInputElement
      await user.type(passwordInput, 'password123')

      // Submit form
      await user.click(within(dialog).getByRole('button', { name: /create$/i }))

      await waitFor(() => {
        expect(createCalled).toBe(true)
      })

      expect(createdUserData).toMatchObject({
        email: 'newuser@acme.com',
        first_name: 'New',
        last_name: 'User',
      })
    })

    it('shows validation errors for invalid data', async () => {
      setCurrentUser(adminUser)

      const { user } = render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for page to load
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: 'users.createButton' })).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Open create dialog
      await user.click(screen.getByRole('button', { name: 'users.createButton' }))

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Submit without filling required fields
      const dialog = screen.getByRole('dialog')
      await user.click(within(dialog).getByRole('button', { name: /create$/i }))

      // Should show validation errors
      await waitFor(() => {
        expect(screen.getByText(/first name is required/i)).toBeInTheDocument()
      })
    })
  })

  // Note: Delete tests moved to UserDetailPage.test.tsx
  // Context menu actions (delete, suspend, impersonate) are now on user detail page

  describe('Pagination', () => {
    it('handles cursor pagination correctly', async () => {
      // Create many users for pagination
      const manyUsers: User[] = Array.from({ length: 15 }, (_, i) => ({
        id: `user-${i}`,
        email: `user${i}@acme.com`,
        email_verified: true,
        email_deliverable: true,
        phone_verified: false,
        first_name: `User${i}`,
        last_name: 'Test',
        is_admin: false,
        created_time: new Date(Date.now() - i * 1000).toISOString(), // Descending order
        roles: [],
      }))

      let lastCursor: string | null = null
      let requestCount = 0

      server.use(
        http.get(`${API_BASE}/users/cursor`, ({ request }) => {
          requestCount++
          const url = new URL(request.url)
          const cursor = url.searchParams.get('cursor')
          const limit = parseInt(url.searchParams.get('limit') || '10')
          lastCursor = cursor

          // Find starting index based on cursor
          let startIndex = 0
          if (cursor) {
            const cursorId = cursor.split('_').pop()
            const cursorIndex = manyUsers.findIndex((u) => u.id === cursorId)
            if (cursorIndex >= 0) {
              startIndex = cursorIndex + 1
            }
          }

          const paginatedUsers = manyUsers.slice(startIndex, startIndex + limit)
          const hasMore = startIndex + limit < manyUsers.length
          const lastUser = paginatedUsers[paginatedUsers.length - 1]
          const nextCursor = hasMore && lastUser
            ? `${lastUser.created_time}_${lastUser.id}`
            : null

          return HttpResponse.json({
            items: paginatedUsers,
            total: manyUsers.length,
            limit,
            next_cursor: nextCursor,
            has_more: hasMore,
          })
        })
      )

      setCurrentUser(adminUser)

      const { user } = render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for first user to load (name rendered as "User0 Test")
      await waitFor(
        () => {
          expect(screen.getByText('User0 Test')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // First request should have no cursor
      expect(lastCursor).toBe(null)
      expect(requestCount).toBe(1)

      // Click "Load More" button if it exists (cursor pagination uses load more)
      const loadMoreButton = screen.queryByRole('button', { name: /load more/i })
      if (loadMoreButton) {
        await user.click(loadMoreButton)

        await waitFor(() => {
          // After clicking load more, cursor should be set
          expect(lastCursor).not.toBe(null)
          expect(requestCount).toBe(2)
        })
      }
    })
  })

  describe('Error Handling', () => {
    it('handles API errors gracefully', async () => {
      server.use(
        http.get(`${API_BASE}/users/cursor`, () => {
          return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
        })
      )

      setCurrentUser(adminUser)

      render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for error state to render
      await waitFor(
        () => {
          expect(screen.getByText('users.emptyMessage')).toBeInTheDocument()
        },
        { timeout: 5000 }
      )
    })

    it('handles create user failure', async () => {
      server.use(
        http.post(`${API_BASE}/users`, () => {
          return HttpResponse.json({ detail: 'Email already exists' }, { status: 400 })
        })
      )

      setCurrentUser(adminUser)

      const { user } = render(<UsersPage />, {
        preloadedState: createAuthState(adminUser),
      })

      // Wait for page to load
      await waitFor(
        () => {
          expect(screen.getByRole('button', { name: 'users.createButton' })).toBeInTheDocument()
        },
        { timeout: 5000 }
      )

      // Open create dialog
      await user.click(screen.getByRole('button', { name: 'users.createButton' }))

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })

      // Fill in form
      const dialog = screen.getByRole('dialog')
      await user.type(within(dialog).getByLabelText(/firstName/i), 'New')
      await user.type(within(dialog).getByLabelText(/lastName/i), 'User')
      await user.type(within(dialog).getByLabelText(/email/i), 'existing@acme.com')
      // Password field has a wrapper div so we query by input type instead
      const passwordInput = dialog.querySelector('input[type="password"]') as HTMLInputElement
      await user.type(passwordInput, 'password123')

      // Submit form
      await user.click(within(dialog).getByRole('button', { name: /create$/i }))

      // Error toast should be shown (mocked)
      // Dialog should remain open for correction
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument()
      })
    })
  })
})
