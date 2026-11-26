/**
 * Re-exports from OpenAPI-generated types with friendly names.
 * This provides backwards-compatible imports and reduces verbosity.
 *
 * Usage:
 *   import type { LoginRequest, User } from '@/types/generated'
 *
 * Note: This file re-exports from api-generated.ts which is auto-generated.
 * Run `npm run generate:types` to regenerate when the backend API changes.
 */
import type { components } from './api-generated'

// Type alias helper for cleaner access
type Schema = components['schemas']

// =============================================================================
// Auth Types
// =============================================================================
export type LoginRequest = Schema['LoginRequest']
export type LoginResponse = Schema['AccessTokenResponse']
export type LogoutAllRequest = Schema['LogoutAllRequest']
export type RefreshTokenResponse = Schema['RefreshTokenResponse']
export type RegisterRequest = Schema['RegisterRequest']
export type RegisterResponse = Schema['RegisterResponse']
export type PasswordResetRequestRequest = Schema['PasswordResetRequestRequest']
export type PasswordResetConfirmRequest = Schema['PasswordResetConfirmRequest']
export type VerifyEmailRequest = Schema['VerifyEmailRequest']
export type VerifyOTPRequest = Schema['src__serialisers__user_otp__VerifyOTPRequest']
export type VerifyOTPResponse = Schema['src__serialisers__user_otp__VerifyOTPResponse']
export type SendVerificationEmailRequest = Schema['SendVerificationEmailRequest']
export type SendVerificationEmailResponse = Schema['SendVerificationEmailResponse']
export type GenerateOTPResponse = Schema['GenerateOTPResponse']

// Backwards-compatible aliases for auth
export type PasswordResetRequestPayload = Schema['PasswordResetRequestRequest']
export type PasswordResetConfirmPayload = Schema['PasswordResetConfirmRequest']
// Note: Frontend uses email-based verification with organization_slug for tenant isolation
// Create custom types that match the frontend's expected payload
export interface VerifyEmailOTPPayload {
  email: string
  otp_code: string
  organization_slug: string
}
export interface SendVerificationEmailPayload {
  email: string
  organization_slug: string
}

// =============================================================================
// User Types
// =============================================================================
export type UserDetailResponse = Schema['UserDetailResponse']
export type UserListResponse = Schema['UserEnhancedListResponse']
export type UserProfileResponse = Schema['UserProfileResponse']
export type UserResponse = Schema['UserResponse']
export type AdminCreateUserRequest = Schema['AdminCreateUserRequest']
export type AdminUpdateUserRequest = Schema['AdminUpdateUserRequest']
export type AdminUpdateUserResponse = Schema['AdminUpdateUserResponse']
export type CreateUserApiResponse = Schema['CreateUserApiResponse']
export type DeleteUserApiResponse = Schema['DeleteUserApiResponse']
export type UpdateUserProfileRequest = Schema['UpdateUserProfileRequest']
export type UpdateUserProfileResponse = Schema['UpdateUserProfileResponse']
export type SuspendUserRequest = Schema['SuspendUserRequest']
export type SuspendUserResponse = Schema['SuspendUserResponse']
export type UnsuspendUserResponse = Schema['UnsuspendUserResponse']

// Backwards-compatible aliases for users
export type User = Schema['UserDetailResponse']
export type UsersListResponse = Schema['UserEnhancedListResponse']
export type CreateUserRequest = Schema['AdminCreateUserRequest']
export type UpdateUserRequest = Schema['AdminUpdateUserRequest']
export type ProfileResponse = Schema['UserProfileResponse']
export type CurrentUserResponse = Schema['UserProfileResponse']

// =============================================================================
// Organization Types
// =============================================================================
export type GetOrganizationResponse = Schema['GetOrganizationResponse']
export type ListOrganizationsResponse = Schema['ListOrganizationsResponse']
export type CreateOrganizationRequest = Schema['CreateOrganizationRequest']
export type CreateOrganizationResponse = Schema['CreateOrganizationResponse']
export type UpdateOrganizationAPIRequest = Schema['UpdateOrganizationAPIRequest']
export type UpdateOrganizationResponse = Schema['UpdateOrganizationResponse']
export type DeleteOrganizationResponse = Schema['DeleteOrganizationResponse']
export type RequestDeletionResponse = Schema['RequestDeletionResponse']
export type CancelDeletionResponse = Schema['CancelDeletionResponse']
export type HardDeleteResponse = Schema['HardDeleteResponse']
export type HardDeleteStatusResponse = Schema['HardDeleteStatusResponse']
export type TriggerHardDeleteRequest = Schema['TriggerHardDeleteRequest']
export type TriggerHardDeleteResponse = Schema['TriggerHardDeleteResponse']
export type ListOrganizationMembersResponse = Schema['ListOrganizationMembersResponse']
export type OrganizationMemberResponse = Schema['OrganizationMemberResponse']
export type MemberCountResponse = Schema['MemberCountResponse']
export type RemoveMemberResponse = Schema['RemoveMemberResponse']

// Backwards-compatible aliases for organizations
export type Organization = Schema['GetOrganizationResponse']
export type OrganizationsListResponse = Schema['ListOrganizationsResponse']
export type OrganizationMember = Schema['OrganizationMemberResponse']
export type OrganizationMembersResponse = Schema['ListOrganizationMembersResponse']
export type UpdateOrganizationRequest = Schema['UpdateOrganizationAPIRequest']
export type DeletionRequestResponse = Schema['RequestDeletionResponse']

// =============================================================================
// Role Types
// =============================================================================
export type GetRoleResponse = Schema['GetRoleResponse']
export type ListRolesResponse = Schema['ListRolesResponse']
export type CreateRoleRequest = Schema['CreateRoleRequest']
export type CreateRoleResponse = Schema['CreateRoleResponse']
export type UpdateRoleRequest = Schema['UpdateRoleRequest']
export type UpdateRoleResponse = Schema['UpdateRoleResponse']
export type DeleteRoleResponse = Schema['DeleteRoleResponse']
export type AssignRoleRequest = Schema['AssignRoleRequest']
export type AssignRoleResponse = Schema['AssignRoleResponse']
export type RevokeRoleRequest = Schema['RevokeRoleRequest']
export type RevokeRoleResponse = Schema['RevokeRoleResponse']
export type ListUserRolesResponse = Schema['ListUserRolesResponse']
export type UserRoleResponse = Schema['UserRoleResponse']
export type RoleWithPermissionsResponse = Schema['RoleWithPermissionsResponse']

// Backwards-compatible aliases for roles
export type Role = Schema['GetRoleResponse']
export type RolesListResponse = Schema['ListRolesResponse']
export type UserRole = Schema['UserRoleResponse']

// =============================================================================
// Permission Types
// =============================================================================
export type PermissionResponse = Schema['PermissionResponse']
export type ListPermissionsResponse = Schema['ListPermissionsResponse']
export type CreatePermissionRequest = Schema['CreatePermissionRequest']
export type UpdatePermissionRequest = Schema['UpdatePermissionRequest']
export type PermissionMatrixResponse = Schema['PermissionMatrixResponse']
export type AssignRolePermissionRequest = Schema['AssignRolePermissionRequest']
export type RevokeRolePermissionRequest = Schema['RevokeRolePermissionRequest']

// Backwards-compatible aliases for permissions
export type Permission = Schema['PermissionResponse']
export type PermissionsListResponse = Schema['ListPermissionsResponse']
export type AssignPermissionRequest = Schema['AssignRolePermissionRequest']
export type RevokePermissionRequest = Schema['RevokeRolePermissionRequest']

// =============================================================================
// File Types
// =============================================================================
export type FileResponse = Schema['FileResponse']
export type FileListResponse = Schema['FileListResponse']
export type FileSettingsResponse = Schema['FileSettingsResponse']
export type FileUsageResponse = Schema['FileUsageResponse']
export type OrganizationFileUsageResponse = Schema['OrganizationFileUsageResponse']
export type OrganizationFileSettingsResponse = Schema['OrganizationFileSettingsResponse']
export type ListOrganizationFileSettingsResponse = Schema['ListOrganizationFileSettingsResponse']
export type UploadUrlRequest = Schema['UploadUrlRequest']
export type UploadUrlResponse = Schema['UploadUrlResponse']
export type UploadCompleteRequest = Schema['UploadCompleteRequest']
export type UploadCompleteResponse = Schema['UploadCompleteResponse']
export type DownloadUrlResponse = Schema['DownloadUrlResponse']
export type DeleteFileResponse = Schema['DeleteFileResponse']
export type UpdateFileSettingsRequest = Schema['UpdateFileSettingsRequest']

// Backwards-compatible aliases for files
export type FileRecord = Schema['FileResponse']
export type FileSettings = Schema['FileSettingsResponse']
export type FileUsage = Schema['FileUsageResponse']
export type OrgFileUsage = Schema['OrganizationFileUsageResponse']
export type UpdateFileSettingsResponse = Schema['FileSettingsResponse']
export type MediaUse = Schema['MediaUse']

// MediaUse enum values for convenience
export const MediaUse = {
  AVATAR: 'avatar' as const,
  ANNOUNCEMENT: 'announcement' as const,
  HELP_ARTICLE: 'help_article' as const,
  OTHER: 'other' as const,
}

// =============================================================================
// Audit Log Types
// =============================================================================
export type AuditLogResponse = Schema['AuditLogResponse']
export type AuditLogListResponse = Schema['AuditLogListResponse']
export type ResourceHistoryResponse = Schema['ResourceHistoryResponse']

// Backwards-compatible aliases for audit logs
export type AuditLog = Schema['AuditLogResponse']
export type AuditLogsListResponse = Schema['AuditLogListResponse']

// =============================================================================
// Notification Types
// =============================================================================
export type NotificationResponse = Schema['NotificationResponse']
export type NotificationDetailResponse = Schema['NotificationDetailResponse']
export type NotificationListResponse = Schema['NotificationListResponse']
export type SendNotificationRequest = Schema['SendNotificationRequest']
export type SendNotificationResponse = Schema['SendNotificationResponse']
export type RecipientFilter = Schema['RecipientFilter']

// Bulk Notifications
export type BulkNotificationResponse = Schema['BulkNotificationResponse']
export type CreateBulkNotificationRequest = Schema['CreateBulkNotificationRequest']
export type CreateBulkNotificationResponse = Schema['CreateBulkNotificationResponse']
export type CancelBulkNotificationResponse = Schema['CancelBulkNotificationResponse']

// Templates
export type TemplateResponse = Schema['src__serialisers__notification__TemplateResponse']
export type TemplateListResponse = Schema['src__serialisers__notification__TemplateListResponse']
export type CreateTemplateRequest = Schema['CreateTemplateRequest']
export type CreateTemplateResponse = Schema['CreateTemplateResponse']
export type UpdateTemplateRequest = Schema['UpdateTemplateRequest']
export type UpdateTemplateResponse = Schema['src__serialisers__notification__UpdateTemplateResponse']
export type DeleteTemplateResponse = Schema['DeleteTemplateResponse']

// System Templates
export type SystemTemplateResponse = Schema['SystemTemplateResponse']
export type ListSystemTemplatesResponse = Schema['ListSystemTemplatesResponse']
export type CreateSystemTemplateRequest = Schema['CreateSystemTemplateRequest']
export type CreateSystemTemplateResponse = Schema['CreateSystemTemplateResponse']
export type UpdateSystemTemplateRequest = Schema['UpdateSystemTemplateRequest']
export type UpdateSystemTemplateResponse = Schema['UpdateSystemTemplateResponse']
export type DeleteSystemTemplateResponse = Schema['DeleteSystemTemplateResponse']

// Categories
export type CategoryResponse = Schema['CategoryResponse']
export type CategoryListResponse = Schema['CategoryListResponse']
export type CreateCategoryRequest = Schema['CreateCategoryRequest']
export type CreateCategoryResponse = Schema['CreateCategoryResponse']
export type UpdateCategoryRequest = Schema['UpdateCategoryRequest']
export type UpdateCategoryResponse = Schema['UpdateCategoryResponse']
export type DeleteCategoryResponse = Schema['DeleteCategoryResponse']
export type CategoryWithPreferenceResponse = Schema['CategoryWithPreferenceResponse']
export type CategoryPreferencesResponse = Schema['CategoryPreferencesResponse']
export type UpdateCategoryPreferenceRequest = Schema['UpdateCategoryPreferenceRequest']
export type UpdateCategoryPreferenceResponse = Schema['UpdateCategoryPreferenceResponse']

// System Categories
export type SystemCategoryResponse = Schema['SystemCategoryResponse']
export type ListSystemCategoriesResponse = Schema['ListSystemCategoriesResponse']
export type CreateSystemCategoryRequest = Schema['CreateSystemCategoryRequest']
export type CreateSystemCategoryResponse = Schema['CreateSystemCategoryResponse']

// Settings & Preferences
export type NotificationSettingsResponse = Schema['NotificationSettingsResponse']
export type UpdateNotificationSettingsRequest = Schema['UpdateNotificationSettingsRequest']
export type UpdateNotificationSettingsResponse = Schema['UpdateNotificationSettingsResponse']
export type UserNotificationPreferenceResponse = Schema['UserNotificationPreferenceResponse']
export type UpdateUserPreferenceRequest = Schema['UpdateUserPreferenceRequest']
export type UpdateUserPreferenceResponse = Schema['UpdateUserPreferenceResponse']

// Providers
export type NotificationProviderResponse = Schema['NotificationProviderResponse']
export type ListNotificationProvidersResponse = Schema['ListNotificationProvidersResponse']
export type CreateNotificationProviderRequest = Schema['CreateNotificationProviderRequest']
export type CreateNotificationProviderResponse = Schema['CreateNotificationProviderResponse']
export type UpdateNotificationProviderRequest = Schema['UpdateNotificationProviderRequest']
export type UpdateNotificationProviderResponse = Schema['UpdateNotificationProviderResponse']
export type DeleteNotificationProviderResponse = Schema['DeleteNotificationProviderResponse']

// Unsubscribe
export type UnsubscribeInfoResponse = Schema['UnsubscribeInfoResponse']
export type UnsubscribeRequest = Schema['UnsubscribeRequest']
export type UnsubscribeResponse = Schema['UnsubscribeResponse']

// Backwards-compatible aliases for notifications
export type Notification = Schema['NotificationResponse']
export type NotificationTemplate = Schema['src__serialisers__notification__TemplateResponse']
export type NotificationCategory = Schema['CategoryResponse']
export type CategoryWithPreference = Schema['CategoryWithPreferenceResponse']
export type BulkNotification = Schema['BulkNotificationResponse']
export type NotificationSettings = Schema['NotificationSettingsResponse']
export type UserNotificationPreference = Schema['UserNotificationPreferenceResponse']

// =============================================================================
// SSO Types
// =============================================================================
export type OrganizationSSOSettingsResponse = Schema['OrganizationSSOSettingsResponse']
export type CreateOrganizationSSOSettingsRequest = Schema['CreateOrganizationSSOSettingsRequest']
export type UpdateOrganizationSSOSettingsRequest = Schema['UpdateOrganizationSSOSettingsRequest']
export type SetSSOAllowedRequest = Schema['SetSSOAllowedRequest']
export type EnabledProvidersResponse = Schema['src__serialisers__organization_sso_settings__EnabledProvidersResponse']

// Backwards-compatible aliases for SSO
export type OrganizationSSOSettings = Schema['OrganizationSSOSettingsResponse']
export type UpdateOrganizationSSOSettingsResponse = Schema['OrganizationSSOSettingsResponse']

// =============================================================================
// Metrics Types
// =============================================================================
export type MetricsSummaryResponse = Schema['MetricsSummaryResponse']
export type UserMetrics = Schema['UserMetrics']
export type RequestMetrics = Schema['RequestMetrics']
export type DatabaseMetrics = Schema['DatabaseMetrics']
export type CacheMetrics = Schema['CacheMetrics']
export type JobMetrics = Schema['JobMetrics']
export type SystemMetrics = Schema['SystemMetrics']

// Rate limit metrics (added to MetricsSummaryResponse in backend)
// TODO: Remove this interface after regenerating types with `npm run generate:types`
export interface RateLimitMetrics {
  total_violations: number
  top_endpoints: Record<string, number>
  top_ips: Record<string, number>
}

// Extended MetricsSummary that includes rate_limit field from backend
// TODO: Remove this after regenerating types with `npm run generate:types`
export type MetricsSummary = Schema['MetricsSummaryResponse'] & {
  rate_limit?: RateLimitMetrics
}

// =============================================================================
// Version Types
// =============================================================================
// Note: VersionResponse not provided by backend - defined locally for frontend version checking
export interface VersionResponse {
  version: string
  commit_hash: string
  build_time: string
}

// Backwards-compatible aliases for version
export type VersionInfo = VersionResponse

// =============================================================================
// Validation Types
// =============================================================================
export type ValidationError = Schema['ValidationError']
export type HTTPValidationError = Schema['HTTPValidationError']

// =============================================================================
// Re-export the raw types for advanced usage
// =============================================================================
export type { components, paths } from './api-generated'
