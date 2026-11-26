import type { Middleware } from '@reduxjs/toolkit'
import { toast } from '@/lib/toast'
import { logout } from '@/features/auth/authSlice'

/**
 * Middleware to handle logout side effects (toast and redirect)
 *
 * When a logout action is dispatched with specific reasons,
 * shows a toast message and redirects to login page.
 *
 * Supported reasons:
 * - 'session-expired': Token refresh failed
 * - 'impersonation-ended': Admin impersonation session was ended externally
 */
export const authMiddleware: Middleware = () => (next) => (action) => {
  // Call the next middleware/reducer first
  const result = next(action)

  // Check if this is a logout action
  if (logout.match(action)) {
    const reason = action.payload && typeof action.payload === 'object' ? action.payload.reason : undefined

    // Show toast and redirect for session expiration
    if (reason === 'session-expired') {
      toast.error('Your session has expired. Please log in again.', { category: 'auth' })
      // Redirect to login page
      window.location.href = '/login'
    }

    // Show toast and redirect for ended impersonation session
    if (reason === 'impersonation-ended') {
      toast.warning('Impersonation session has ended.', { category: 'auth' })
      // Redirect to login page
      window.location.href = '/login'
    }
  }

  return result
}
