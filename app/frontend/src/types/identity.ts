/**
 * Types for user identity (connected accounts) management.
 */

export interface UserIdentityResponse {
  id: string
  provider: string
  provider_email: string | null
  linked_at: string
  is_primary: boolean
  can_unlink: boolean
}

export interface UserIdentitiesResponse {
  identities: UserIdentityResponse[]
  created_via: string
  has_password: boolean
  two_factor_policy: 'disabled' | 'optional' | 'mandatory'
  two_factor_enabled: boolean
  requires_setup_for_unlink: boolean
}

export interface UnlinkWithSetupRequest {
  new_password: string
  totp_secret?: string
  totp_code?: string
}

export interface UnlinkIdentityResponse {
  message: string
  message_code: string
}

export interface UnlinkWithSetupResponse {
  message: string
  message_code: string
  backup_codes?: string[]
}
