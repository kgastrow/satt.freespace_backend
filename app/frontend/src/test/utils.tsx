import type { ReactElement, ReactNode } from 'react'
import { render, type RenderOptions, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect } from 'vitest'
import { Provider } from 'react-redux'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { configureStore } from '@reduxjs/toolkit'
import { enableMapSet } from 'immer'
import { api } from '@/store/api'
import authReducer from '@/features/auth/authSlice'
import impersonationReducer from '@/features/impersonation/impersonationSlice'
import websocketReducer from '@/features/websocket/websocketSlice'
import inAppNotificationsReducer from '@/features/in-app-notifications/inAppNotificationsSlice'
import announcementsReducer from '@/features/announcements/announcementsSlice'
import featureFlagsReducer from '@/features/featureFlags/featureFlagsSlice'
import maintenanceReducer from '@/features/maintenance/maintenanceSlice'
import preferencesReducer from '@/features/preferences/preferencesSlice'
import changelogReducer from '@/features/changelog/changelogSlice'
import type { RootState } from '@/store'

// Enable Immer support for Map and Set objects in Redux state
enableMapSet()

interface WrapperProps {
  children: ReactNode
}

export type TestStore = ReturnType<typeof createTestStore>

/**
 * Create a test store with optional preloaded state
 */
export function createTestStore(preloadedState: Partial<RootState> = {}) {
  return configureStore({
    reducer: {
      [api.reducerPath]: api.reducer,
      auth: authReducer,
      impersonation: impersonationReducer,
      websocket: websocketReducer,
      inAppNotifications: inAppNotificationsReducer,
      announcements: announcementsReducer,
      featureFlags: featureFlagsReducer,
      maintenance: maintenanceReducer,
      preferences: preferencesReducer,
      changelog: changelogReducer,
    },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({
        serializableCheck: {
          // Ignore Set objects in announcements state - Immer's enableMapSet() handles these
          ignoredPaths: ['announcements.locallyDismissedIds'],
          ignoredActions: [],
        },
      }).concat(api.middleware),
    preloadedState: preloadedState as RootState,
  })
}

interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  preloadedState?: Partial<RootState>
  route?: string
  routes?: Array<{ path: string; element: ReactElement }>
  store?: TestStore
}

/**
 * Custom render function that wraps components with necessary providers
 * Includes Redux store and React Router
 */
function customRender(
  ui: ReactElement,
  {
    preloadedState = {},
    route = '/',
    routes,
    store = createTestStore(preloadedState),
    ...renderOptions
  }: CustomRenderOptions = {}
) {
  function Wrapper({ children }: WrapperProps) {
    // If routes are provided, render with Routes component for navigation testing
    if (routes) {
      return (
        <Provider store={store}>
          <MemoryRouter initialEntries={[route]}>
            <Routes>
              {routes.map((r) => (
                <Route key={r.path} path={r.path} element={r.element} />
              ))}
            </Routes>
          </MemoryRouter>
        </Provider>
      )
    }

    return (
      <Provider store={store}>
        <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
      </Provider>
    )
  }

  const user = userEvent.setup()

  return {
    store,
    user,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  }
}

/**
 * Wait for loading state to complete
 */
export async function waitForLoadingToComplete() {
  await waitFor(() => {
    const loadingElements = document.querySelectorAll('[class*="animate-pulse"]')
    expect(loadingElements.length).toBe(0)
  })
}

/**
 * Wait for an element to be removed from the document
 */
export async function waitForElementToBeRemoved(
  callback: () => HTMLElement | null,
  options?: { timeout?: number }
) {
  await waitFor(
    () => {
      expect(callback()).not.toBeInTheDocument()
    },
    { timeout: options?.timeout || 5000 }
  )
}

/**
 * Clear storage (localStorage and sessionStorage)
 */
export function clearStorage() {
  localStorage.clear()
  sessionStorage.clear()
}

/**
 * Set up storage with auth tokens
 * @deprecated Tokens are now stored in-memory (Redux) and httpOnly cookies. This is a no-op kept for test compatibility.
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function setupStorageWithAuth(_accessToken: string, _refreshToken: string) {
  // No-op: refresh tokens are now in httpOnly cookies, access tokens in Redux memory only
}

/**
 * Get current location pathname from MemoryRouter
 * Note: This only works if you're using the routes option in customRender
 */
export function getCurrentPath(): string {
  // This is a workaround since MemoryRouter doesn't expose location directly
  // In real tests, we check for rendered content to verify navigation
  return window.location.pathname
}

export * from '@testing-library/react'
export { customRender as render, userEvent }
