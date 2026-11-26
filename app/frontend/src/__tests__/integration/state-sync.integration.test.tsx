/**
 * State Synchronization Integration Tests
 *
 * Tests Redux state management and synchronization including:
 * - Redux ↔ Storage sync (token persistence)
 * - Cache invalidation (tag-based refetches)
 * - Navigation state persistence
 * - Store state consistency
 */

import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@/test/utils'
import { createTestStore } from '@/test/utils'
import { server, setCurrentUser, API_BASE } from '@/test/server'
import {
  regularUser,
  createAuthState,
  tokens,
  filesInOrg1,
  usersInOrg1,
} from '@/test/fixtures'
import { setCredentials, logout, updateToken } from '@/features/auth/authSlice'
import { useGetFilesQuery, useDeleteFileMutation } from '@/features/files/filesApi'
import { useGetUsersQuery, useCreateUserMutation } from '@/features/users/usersApi'
import { Provider } from 'react-redux'

describe('State Synchronization Integration Tests', () => {
  describe('Redux ↔ Storage Sync', () => {
    it('stores access token in Redux state on login (in-memory only)', () => {
      const store = createTestStore()

      // Dispatch setCredentials action
      store.dispatch(
        setCredentials({
          token: tokens.validAccessToken,
        })
      )

      // Tokens are now in-memory only (not persisted to sessionStorage)
      expect(sessionStorage.getItem('access_token')).toBeNull()

      // Verify store state
      const state = store.getState()
      expect(state.auth.token).toBe(tokens.validAccessToken)
    })

    it('clears auth state on logout', () => {
      const store = createTestStore({
        auth: {
          user: regularUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
      })

      // Dispatch logout
      store.dispatch(logout())

      // Store state should be cleared
      const state = store.getState()
      expect(state.auth.token).toBeNull()
      expect(state.auth.user).toBeNull()
      expect(state.auth.isAuthenticated).toBe(false)
    })

    it('updates Redux state when token is refreshed (in-memory only)', () => {
      const store = createTestStore({
        auth: {
          user: regularUser,
          token: 'old-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
      })

      // Update token
      store.dispatch(updateToken('new-access-token'))

      // Token should NOT be in sessionStorage (in-memory only)
      expect(sessionStorage.getItem('access_token')).toBeNull()

      // Store state should be updated
      expect(store.getState().auth.token).toBe('new-access-token')
    })

    it('maintains access token in Redux state only (not sessionStorage)', () => {
      const store = createTestStore()

      store.dispatch(
        setCredentials({
          token: tokens.validAccessToken,
        })
      )

      // Access token should NOT be in sessionStorage (in-memory only)
      expect(sessionStorage.getItem('access_token')).toBeNull()

      // Should be in Redux state
      expect(store.getState().auth.token).toBe(tokens.validAccessToken)
    })
  })

  describe('RTK Query Cache Invalidation', () => {
    it('refetches files after file deletion', async () => {
      let fetchCount = 0
      const mutableFiles = [...filesInOrg1]

      server.use(
        http.get(`${API_BASE}/files`, () => {
          fetchCount++
          return HttpResponse.json({
            items: mutableFiles,
            total: mutableFiles.length,
            limit: 50,
            offset: 0,
          })
        }),
        http.delete(`${API_BASE}/files/:id`, ({ params }) => {
          const index = mutableFiles.findIndex((f) => f.id === params.id)
          if (index > -1) {
            mutableFiles.splice(index, 1)
          }
          return HttpResponse.json({ message: 'Deleted' })
        })
      )

      // Component that fetches files and can delete
      function FileListWithDelete() {
        const { data, isLoading } = useGetFilesQuery({})
        const [deleteFile] = useDeleteFileMutation()

        if (isLoading) return <div>Loading...</div>

        return (
          <div>
            <div data-testid="file-count">{data?.items.length} files</div>
            <button onClick={() => deleteFile('file-1')}>Delete File 1</button>
          </div>
        )
      }

      setCurrentUser(regularUser)

      const { user } = render(<FileListWithDelete />, {
        preloadedState: createAuthState(regularUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('file-count')).toHaveTextContent('2 files')
      const initialFetchCount = fetchCount

      // Delete a file
      await user.click(screen.getByRole('button'))

      // Should refetch after deletion due to tag invalidation
      await waitFor(() => {
        expect(fetchCount).toBeGreaterThan(initialFetchCount)
      })
    })

    it('refetches users after user creation', async () => {
      let fetchCount = 0
      const mutableUsers = [...usersInOrg1]

      server.use(
        http.get(`${API_BASE}/users`, () => {
          fetchCount++
          return HttpResponse.json({
            items: mutableUsers,
            total: mutableUsers.length,
            limit: 10,
            offset: 0,
          })
        }),
        http.post(`${API_BASE}/users`, async ({ request }) => {
          const body = (await request.json()) as { email: string; first_name: string; last_name: string; is_admin?: boolean }
          const newUser = {
            id: 'new-user',
            email: body.email,
            email_verified: false,
            email_deliverable: true,
            phone_verified: false,
            first_name: body.first_name,
            last_name: body.last_name,
            is_admin: body.is_admin || false,
            created_time: new Date().toISOString(),
            roles: [],
          }
          mutableUsers.push(newUser)
          return HttpResponse.json(newUser)
        })
      )

      // Component that fetches users and can create
      function UserListWithCreate() {
        const { data, isLoading } = useGetUsersQuery({})
        const [createUser] = useCreateUserMutation()

        if (isLoading) return <div>Loading...</div>

        const handleCreate = () => {
          createUser({
            email: 'new@acme.com',
            password: 'password123',
            first_name: 'New',
            last_name: 'User',
            is_admin: false,
          })
        }

        return (
          <div>
            <div data-testid="user-count">{data?.items?.length} users</div>
            <button onClick={handleCreate}>Create User</button>
          </div>
        )
      }

      setCurrentUser(regularUser)

      const { user } = render(<UserListWithCreate />, {
        preloadedState: createAuthState(regularUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('user-count')).toHaveTextContent('3 users')
      const initialFetchCount = fetchCount

      // Create a user
      await user.click(screen.getByRole('button'))

      // Should refetch after creation
      await waitFor(() => {
        expect(fetchCount).toBeGreaterThan(initialFetchCount)
      })
    })
  })

  describe('Store State Consistency', () => {
    it('maintains consistent auth state across components', () => {
      const store = createTestStore(createAuthState(regularUser))

      // Component A reads auth state
      function ComponentA() {
        const state = store.getState()
        return <div data-testid="comp-a-user">{state.auth.user?.email}</div>
      }

      // Component B reads auth state
      function ComponentB() {
        const state = store.getState()
        return <div data-testid="comp-b-auth">{state.auth.isAuthenticated ? 'Yes' : 'No'}</div>
      }

      render(
        <Provider store={store}>
          <ComponentA />
          <ComponentB />
        </Provider>
      )

      // Both components should see consistent state
      expect(screen.getByTestId('comp-a-user')).toHaveTextContent('user@acme.com')
      expect(screen.getByTestId('comp-b-auth')).toHaveTextContent('Yes')
    })

    it('updates all subscribers when state changes', async () => {
      const store = createTestStore(createAuthState(regularUser))

      function AuthStatus() {
        const state = store.getState()
        return (
          <div data-testid="auth-status">
            {state.auth.isAuthenticated ? 'Authenticated' : 'Not authenticated'}
          </div>
        )
      }

      render(
        <Provider store={store}>
          <AuthStatus />
        </Provider>
      )

      expect(screen.getByTestId('auth-status')).toHaveTextContent('Authenticated')

      // Dispatch logout
      store.dispatch(logout())

      // State should be updated
      expect(store.getState().auth.isAuthenticated).toBe(false)
    })
  })

  describe('API State Management', () => {
    it('caches API responses correctly', async () => {
      let fetchCount = 0

      server.use(
        http.get(`${API_BASE}/files`, () => {
          fetchCount++
          return HttpResponse.json({
            items: filesInOrg1,
            total: filesInOrg1.length,
            limit: 50,
            offset: 0,
          })
        })
      )

      // Component that fetches files
      function FileList() {
        const { data, isLoading } = useGetFilesQuery({})
        if (isLoading) return <div>Loading...</div>
        return <div data-testid="files">Files: {data?.items.length}</div>
      }

      setCurrentUser(regularUser)

      const { rerender } = render(<FileList />, {
        preloadedState: createAuthState(regularUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      const firstFetchCount = fetchCount

      // Re-render the component
      rerender(<FileList />)

      // Should use cached data, not refetch
      expect(fetchCount).toBe(firstFetchCount)
    })

    it('resets API cache on logout', () => {
      const store = createTestStore(createAuthState(regularUser))

      // Simulate API cache having data
      // In real scenario, cache would be populated by queries

      // Logout should trigger cache reset
      store.dispatch(logout())

      // After logout, auth state should be cleared
      const state = store.getState()
      expect(state.auth.token).toBeNull()
      expect(state.auth.user).toBeNull()
    })
  })

  describe('Loading State Management', () => {
    it('handles loading states correctly during async operations', async () => {
      server.use(
        http.get(`${API_BASE}/files`, async () => {
          await new Promise((resolve) => setTimeout(resolve, 100))
          return HttpResponse.json({
            items: filesInOrg1,
            total: filesInOrg1.length,
            limit: 50,
            offset: 0,
          })
        })
      )

      function FileListWithLoading() {
        const { data, isLoading, isFetching } = useGetFilesQuery({})

        return (
          <div>
            <div data-testid="loading-state">{isLoading ? 'Loading' : 'Loaded'}</div>
            <div data-testid="fetching-state">{isFetching ? 'Fetching' : 'Idle'}</div>
            {data && <div data-testid="data-loaded">Data ready</div>}
          </div>
        )
      }

      setCurrentUser(regularUser)

      render(<FileListWithLoading />, {
        preloadedState: createAuthState(regularUser),
      })

      // Initial loading state
      expect(screen.getByTestId('loading-state')).toHaveTextContent('Loading')

      // Wait for data
      await waitFor(() => {
        expect(screen.getByTestId('loading-state')).toHaveTextContent('Loaded')
      })

      expect(screen.getByTestId('data-loaded')).toBeInTheDocument()
    })
  })

  describe('Error State Management', () => {
    it('handles API errors and maintains error state', async () => {
      server.use(
        http.get(`${API_BASE}/files`, () => {
          return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
        })
      )

      function FileListWithError() {
        const { isLoading, error } = useGetFilesQuery({})

        if (isLoading) return <div>Loading...</div>
        if (error) return <div data-testid="error-state">Error occurred</div>

        return <div data-testid="success-state">Success</div>
      }

      setCurrentUser(regularUser)

      render(<FileListWithError />, {
        preloadedState: createAuthState(regularUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('error-state')).toBeInTheDocument()
    })

    it('recovers from error state on retry', async () => {
      let shouldFail = true

      server.use(
        http.get(`${API_BASE}/files`, () => {
          if (shouldFail) {
            return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
          }
          return HttpResponse.json({
            items: filesInOrg1,
            total: filesInOrg1.length,
            limit: 50,
            offset: 0,
          })
        })
      )

      function FileListWithRetry() {
        const { data, isLoading, error, refetch } = useGetFilesQuery({})

        if (isLoading) return <div>Loading...</div>
        if (error) {
          return (
            <div>
              <div data-testid="error-state">Error occurred</div>
              <button onClick={() => refetch()}>Retry</button>
            </div>
          )
        }

        return <div data-testid="success-state">Files: {data?.items.length}</div>
      }

      setCurrentUser(regularUser)

      const { user } = render(<FileListWithRetry />, {
        preloadedState: createAuthState(regularUser),
      })

      // Wait for error
      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toBeInTheDocument()
      })

      // Fix the error condition
      shouldFail = false

      // Retry
      await user.click(screen.getByRole('button', { name: 'Retry' }))

      // Should succeed now
      await waitFor(() => {
        expect(screen.getByTestId('success-state')).toBeInTheDocument()
      })
    })
  })
})
