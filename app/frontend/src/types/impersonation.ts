/**
 * Impersonation types - for super admin user impersonation
 */

import type { User } from './auth'

/**
 * Impersonation session model (matches backend ImpersonationSessionResponse)
 */
export interface ImpersonationSession {
  id: string
  created_time: string
  impersonator_id: string
  target_user_id: string
  target_organization_id: string
  ended_time: string | null
  ip_address: string
  user_agent: string
}

/**
 * Response for checking current impersonation session status
 * Matches backend ImpersonationSessionStatusResponse
 */
export interface ImpersonationSessionStatusResponse {
  active: boolean
  session?: ImpersonationSession
}

/**
 * Request payload for starting impersonation
 */
export interface StartImpersonationRequest {
  user_id: string
}

/**
 * Response when starting impersonation (includes the impersonation token)
 * Matches backend StartImpersonationResponse
 */
export interface ImpersonationResponse {
  impersonation_token: string
  session: ImpersonationSession
  message: string
}

/**
 * Response when ending impersonation (includes original admin token)
 * Matches backend EndImpersonationResponse
 */
export interface EndImpersonationResponse {
  access_token: string
  session: ImpersonationSession
  message: string
}

/**
 * Impersonation history item
 */
export interface ImpersonationHistoryItem {
  id: string
  created_time: string
  ended_time: string | null
  impersonator: {
    id: string
    email: string
    first_name: string
    last_name: string
  }
  target_user: {
    id: string
    email: string
    first_name: string
    last_name: string
  }
  target_organization: {
    id: string
    name: string
  }
  duration_seconds: number | null
  ip_address: string
}

/**
 * Impersonation state for Redux store
 */
export interface ImpersonationState {
  isImpersonating: boolean
  originalUser: User | null // The admin who initiated impersonation
  targetUser: User | null // The user being impersonated
  sessionId: string | null
  sessionStartedAt: string | null
  originalToken: string | null // Original admin token to restore on end
  originalRefreshToken: string | null // Original admin refresh token to restore on end
}

/**
 * Basic info about the impersonator for history display
 * Matches backend ImpersonatorInfo
 */
export interface ImpersonatorInfo {
  id: string
  email: string
  first_name: string | null
  last_name: string | null
}

/**
 * Single item in user's impersonation history (when they were impersonated)
 * Matches backend MyImpersonationHistoryItem
 */
export interface MyImpersonationHistoryItem {
  id: string
  created_time: string
  ended_time: string
  impersonator: ImpersonatorInfo
}

/**
 * Paginated response for user's impersonation history
 * Matches backend MyImpersonationHistoryResponse
 */
export interface MyImpersonationHistoryResponse {
  items: MyImpersonationHistoryItem[]
  total: number
  limit: number
  offset: number
}

/**
 * Query parameters for fetching user's impersonation history
 */
export interface MyImpersonationHistoryParams {
  limit?: number
  offset?: number
}
