/**
 * SSO (Single Sign-On) related TypeScript types
 * Re-exports from generated types plus frontend-only types
 */

import type { components } from './api-generated'

// Re-export API types from generated (these come from OpenAPI schema)
export type {
  OrganizationSSOSettings,
  SetSSOAllowedRequest,
  CreateOrganizationSSOSettingsRequest,
  UpdateOrganizationSSOSettingsRequest,
  EnabledProvidersResponse,
} from './generated'

/**
 * SSO provider names (frontend-only - not in OpenAPI as a schema)
 */
export type SSOProvider = 'google'

/**
 * SSO authorization URL response (manual - backend returns Dict, not a schema)
 */
export interface SSOAuthorizationResponse {
  authorization_url: string
}

/**
 * SSO callback success response - contains JWT tokens (manual - backend returns Dict)
 */
export interface SSOCallbackSuccessResponse {
  access_token: string
}

/**
 * SSO linking required response - returned when account linking is needed
 */
export interface SSOLinkingRequiredResponse {
  requires_linking: true
  link_token: string
  email: string
  provider: string
}

/**
 * SSO 2FA challenge response - returned when the account is enrolled in 2FA.
 *
 * The backend (``LoginResponseWith2FA``) returns exactly the same shape here as
 * it does from ``POST /auth/login``, so the challenge is completed by the same
 * ``POST /auth/verify-2fa`` round-trip. No session exists yet: no access token
 * is returned and no refresh cookie is set.
 */
export interface SSOCallback2FARequiredResponse {
  requires_2fa: true
  two_factor_token: string
}

/**
 * SSO callback response - union type for success, 2FA challenge, or linking required
 */
export type SSOCallbackResponse =
  | SSOCallbackSuccessResponse
  | SSOCallback2FARequiredResponse
  | SSOLinkingRequiredResponse

/**
 * Request body for ``POST /auth/sso/link``.
 *
 * Sourced straight from the OpenAPI schema rather than hand-written. The link
 * token alone only proves that somebody completed an OAuth flow for an address
 * matching an existing account, so the endpoint additionally requires proof
 * that the caller controls that account -- exactly one of:
 *
 * 1. A bearer session for the same user in the same organization, sent in the
 *    ``Authorization`` header rather than in this body (hence ``password``
 *    being optional).
 * 2. ``password`` -- the existing account's password, re-entered. This is the
 *    signed-out SSO callback path.
 *
 * Keeping this an alias of the generated schema is deliberate: a hand-copy
 * silently drifts when the backend renames or re-types a field, and the call
 * site would keep typechecking right up until it 422s in production.
 */
export type ConfirmLinkRequest = components['schemas']['ConfirmLinkRequest']

/**
 * Type guard to check if response requires linking
 */
export function isSSOLinkingRequired(
  response: SSOCallbackResponse
): response is SSOLinkingRequiredResponse {
  return 'requires_linking' in response && response.requires_linking === true
}

/**
 * Type guard to check if response requires a 2FA challenge.
 *
 * MUST be checked before treating a callback response as a completed login:
 * a challenge response carries no ``access_token``, and storing an undefined
 * token would sign the user out. For an SSO-only account (no password) that is
 * an unrecoverable lockout, since there is no password path to fall back to.
 */
export function isSSOTwoFactorRequired(
  response: SSOCallbackResponse
): response is SSOCallback2FARequiredResponse {
  return 'requires_2fa' in response && response.requires_2fa === true
}
