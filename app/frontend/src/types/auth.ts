/**
 * Auth types - re-exports from generated types plus frontend-only types
 */

// Re-export API types from generated (these come from OpenAPI schema)
export type {
  LoginRequest,
  LoginResponse,
  RefreshTokenResponse,
  RegisterRequest,
  RegisterResponse,
  PasswordResetRequestPayload,
  PasswordResetConfirmPayload,
  VerifyEmailOTPPayload,
  SendVerificationEmailPayload,
  CurrentUserResponse,
  LogoutAllRequest,
} from './generated'

/**
 * User model representing an authenticated user (frontend-only)
 * This is a simplified version for local state, not from API
 */
export interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  organization_id: string
  is_admin: boolean
  avatar_url?: string | null
  full_avatar_url?: string | null
  roles?: string[]
  permissions?: string[]
}

/**
 * Auth state for Redux store (frontend-only)
 */
export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  twoFactor: {
    required: boolean
    token: string | null
  }
  twoFactorSetupRequired: boolean
  enforcementActive: boolean
  sso: {
    isLoading: boolean
    error: string | null
    selectedProvider: string | null
  }
}

/**
 * Generic message response (frontend-only convenience type)
 */
export interface MessageResponse {
  message: string
}

/**
 * 2FA-related types (frontend-only, will be in generated types after backend deployment)
 */
export interface LoginResponseWith2FA {
  requires_2fa: boolean
  two_factor_token: string
}

export interface Verify2FARequest {
  two_factor_token: string
  code: string
}

/**
 * Check email request for two-step login flow
 */
export interface CheckEmailRequest {
  email: string
  organization_slug: string
}

/**
 * Check email response - indicates available auth methods
 */
export interface CheckEmailResponse {
  exists: boolean
  auth_methods: string[]
}
