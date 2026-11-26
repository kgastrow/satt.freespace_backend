/**
 * MSW server setup for integration tests
 */

import { setupServer } from 'msw/node'
import { beforeAll, afterEach, afterAll } from 'vitest'
import { handlers, resetHandlerState, resetMaintenanceState } from './handlers'

// Create the MSW server with default handlers
export const server = setupServer(...handlers)

// Re-export handler state functions and API_BASE for use in tests
export {
  setCurrentUser,
  setCurrentToken,
  resetHandlerState,
  API_BASE,
  resetMaintenanceState,
  addMaintenanceHistoryItem,
} from './handlers'

/**
 * Setup function to be called in test files
 * Returns cleanup functions
 */
export function setupMswServer() {
  beforeAll(() => {
    server.listen({ onUnhandledRequest: 'warn' })
  })

  afterEach(() => {
    server.resetHandlers()
    resetHandlerState()
    resetMaintenanceState()
  })

  afterAll(() => {
    server.close()
  })

  return server
}
