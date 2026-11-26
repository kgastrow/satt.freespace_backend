import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { User, AuthState } from '@/types/auth'
import type { SSOProvider } from '@/types/sso'
import { authApi } from './authApi'
import { ssoApi } from './ssoApi'

const initialState: AuthState = {
  user: null,
  token: null,
  isAuthenticated: false,
  isLoading: true, // Will bootstrap via silent refresh
  twoFactor: {
    required: false,
    token: null,
  },
  twoFactorSetupRequired: false,
  enforcementActive: false,
  sso: {
    isLoading: false,
    error: null,
    selectedProvider: null,
  },
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    /**
     * Set credentials after successful login
     * Refresh token is in httpOnly cookie (not in Redux)
     */
    setCredentials: (
      state,
      action: PayloadAction<{ token: string }>
    ) => {
      state.token = action.payload.token
      state.isAuthenticated = true
      state.isLoading = false
    },

    /**
     * Set user data after fetching current user
     */
    setUser: (state, action: PayloadAction<User>) => {
      state.user = action.payload
      state.isAuthenticated = true
      state.isLoading = false
    },

    /**
     * Update access token after refresh
     */
    updateToken: (state, action: PayloadAction<string>) => {
      state.token = action.payload
    },

    /**
     * Clear all auth state on logout
     * Refresh token cookie is cleared by the backend on POST /auth/logout
     */
    logout: (state, _action: PayloadAction<{ reason?: string } | undefined>): void => {
      void _action // Action payload is used by middleware for toast messages
      state.user = null
      state.token = null
      state.isAuthenticated = false
      state.isLoading = false
      state.twoFactor.required = false
      state.twoFactor.token = null
      state.twoFactorSetupRequired = false
      state.enforcementActive = false
    },

    /**
     * Set loading state
     */
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },

    /**
     * Mark auth as initialized (no valid token found)
     */
    initializeAuth: (state) => {
      state.isLoading = false
    },

    /**
     * Set SSO loading state
     */
    setSSOLoading: (state, action: PayloadAction<boolean>) => {
      state.sso.isLoading = action.payload
      if (action.payload) {
        state.sso.error = null
      }
    },

    /**
     * Set SSO error
     */
    setSSOError: (state, action: PayloadAction<string | null>) => {
      state.sso.error = action.payload
      state.sso.isLoading = false
    },

    /**
     * Set selected SSO provider
     */
    setSelectedSSOProvider: (state, action: PayloadAction<SSOProvider | null>) => {
      state.sso.selectedProvider = action.payload
    },

    /**
     * Clear SSO state
     */
    clearSSOState: (state) => {
      state.sso.isLoading = false
      state.sso.error = null
      state.sso.selectedProvider = null
    },

    /**
     * Set 2FA required state with token
     */
    set2FARequired: (state, action: PayloadAction<{ token: string }>) => {
      state.twoFactor.required = true
      state.twoFactor.token = action.payload.token
      state.isLoading = false
    },

    /**
     * Clear 2FA state
     */
    clear2FA: (state) => {
      state.twoFactor.required = false
      state.twoFactor.token = null
    },
  },
  extraReducers: (builder) => {
    // Handle successful login (with or without 2FA)
    builder.addMatcher(
      authApi.endpoints.login.matchFulfilled,
      (state, action) => {
        // Check if 2FA is required
        if ('requires_2fa' in action.payload && action.payload.requires_2fa) {
          state.twoFactor.required = true
          state.twoFactor.token = action.payload.two_factor_token
          state.isLoading = false
        } else if ('access_token' in action.payload) {
          // Regular login flow - refresh token is in httpOnly cookie
          state.token = action.payload.access_token
          state.isAuthenticated = true
          state.isLoading = false
          const payload = action.payload as typeof action.payload & {
            requires_2fa_setup?: boolean
            enforcement_active?: boolean
          }
          state.twoFactorSetupRequired = payload.requires_2fa_setup || false
          state.enforcementActive = payload.enforcement_active || false
        }
      }
    )

    // Handle successful 2FA verification
    builder.addMatcher(
      authApi.endpoints.verify2FA.matchFulfilled,
      (state, action) => {
        state.token = action.payload.access_token
        state.isAuthenticated = true
        state.isLoading = false
        state.twoFactor.required = false
        state.twoFactor.token = null
      }
    )

    // Handle successful email verification (auto-login after registration)
    builder.addMatcher(
      authApi.endpoints.verifyEmailOTP.matchFulfilled,
      (state, action) => {
        state.token = action.payload.access_token
        state.isAuthenticated = true
        state.isLoading = false
      }
    )

    // Handle successful user fetch
    // NOTE: Do NOT set isLoading=false here - let AuthProvider control that
    // after all auth queries complete (user, permissions, session)
    builder.addMatcher(
      authApi.endpoints.getCurrentUser.matchFulfilled,
      (state, action) => {
        // Type assertion to handle avatar_url which may not be in generated types yet
        const payload = action.payload as typeof action.payload & {
          avatar_url?: string | null
        }
        state.user = {
          id: payload.id,
          email: payload.email,
          first_name: payload.first_name || '',
          last_name: payload.last_name || '',
          organization_id: payload.organization_id || '',
          is_admin: payload.is_admin,
          avatar_url: payload.avatar_url || null,
          roles: payload.roles?.map((r) => r.name) || [],
          // Preserve existing permissions - they are loaded separately via getUserPermissions
          // and should not be cleared when user data is refetched
          permissions: state.user?.permissions,
        }
        state.isAuthenticated = true
        // isLoading remains true until AuthProvider finishes loading all auth data
      }
    )

    // Handle failed user fetch (token invalid)
    builder.addMatcher(
      authApi.endpoints.getCurrentUser.matchRejected,
      (state) => {
        state.user = null
        state.token = null
        state.isAuthenticated = false
        state.isLoading = false
      }
    )

    // Handle successful permissions fetch
    builder.addMatcher(
      authApi.endpoints.getUserPermissions.matchFulfilled,
      (state, action) => {
        if (state.user) {
          state.user.permissions = action.payload.permissions
        }
      }
    )

    // Handle successful token refresh
    builder.addMatcher(
      authApi.endpoints.refreshToken.matchFulfilled,
      (state, action) => {
        state.token = action.payload.access_token
      }
    )

    // Handle successful logout
    builder.addMatcher(authApi.endpoints.logout.matchFulfilled, (state) => {
      state.user = null
      state.token = null
      state.isAuthenticated = false
      state.isLoading = false
    })

    // Handle SSO callback success. The endpoint has THREE fulfilled outcomes and
    // they must be told apart -- a 2FA challenge carries no access_token, so
    // letting it fall through to the linking branch would leave the user on a
    // dead end with their challenge token dropped. For an SSO-only account
    // (no password) that is a hard lockout.
    builder.addMatcher(
      ssoApi.endpoints.handleSSOCallback.matchFulfilled,
      (state, action) => {
        state.sso.isLoading = false
        state.sso.error = null

        if ('requires_2fa' in action.payload && action.payload.requires_2fa) {
          // 2FA challenge - NOT a session. Stash the challenge token in the same
          // place the password login does so the shared TwoFactorVerification
          // screen picks it up; OAuthCallback handles the redirect to /login.
          state.twoFactor.required = true
          state.twoFactor.token = action.payload.two_factor_token
          state.isAuthenticated = false
          state.isLoading = false
        } else if ('access_token' in action.payload) {
          // Full session issued - refresh token is in the httpOnly cookie.
          state.token = action.payload.access_token
          state.isAuthenticated = true
          state.isLoading = false
        }
        // Otherwise: linking required - loading states are already cleared above
        // and OAuthCallback handles the redirect to /sso/confirm-link.
      }
    )

    // Handle SSO account linking success
    builder.addMatcher(
      ssoApi.endpoints.confirmAccountLink.matchFulfilled,
      (state, action) => {
        state.token = action.payload.access_token
        state.isAuthenticated = true
        state.isLoading = false
        state.sso.isLoading = false
        state.sso.error = null
      }
    )

    // Handle SSO callback error
    builder.addMatcher(
      ssoApi.endpoints.handleSSOCallback.matchRejected,
      (state, action) => {
        state.sso.isLoading = false
        state.sso.error = action.error.message || 'SSO authentication failed'
      }
    )
  },
})

export const {
  setCredentials,
  setUser,
  updateToken,
  logout,
  setLoading,
  initializeAuth,
  setSSOLoading,
  setSSOError,
  setSelectedSSOProvider,
  clearSSOState,
  set2FARequired,
  clear2FA,
} = authSlice.actions

export default authSlice.reducer
