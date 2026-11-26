/**
 * Test fixtures for integration tests
 * Provides consistent mock data for users, organizations, files, etc.
 */

import type { User, CurrentUserResponse } from '@/types/auth'
import type { FileRecord, FileSettings, FileUsage } from '@/features/files/filesApi'
import type { User as UserRecord } from '@/features/users/usersApi'
import type { Organization } from '@/features/organizations/organizationsApi'
import type { Role } from '@/features/roles/rolesApi'
import type {
  Notification,
  NotificationTemplate,
  NotificationCategory,
  NotificationSettings,
  UserNotificationPreference,
} from '@/features/notifications/notificationsApi'

// =============================================================================
// Organization Fixtures
// =============================================================================

export const organizations: Organization[] = [
  {
    id: 'org-1',
    name: 'Acme Corp',
    slug: 'acme',
    is_active: true,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
    deletion_requested: false,
    deletion_requested_time: null,
  },
  {
    id: 'org-2',
    name: 'Test Corp',
    slug: 'test',
    is_active: true,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
    deletion_requested: false,
    deletion_requested_time: null,
  },
  {
    id: 'org-3',
    name: 'Pending Deletion Corp',
    slug: 'pending-delete',
    is_active: false,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-06-01T00:00:00Z',
    deletion_requested: true,
    deletion_requested_time: '2024-06-01T00:00:00Z',
  },
]

// =============================================================================
// User Fixtures
// =============================================================================

export const regularUser: User = {
  id: 'user-1',
  email: 'user@acme.com',
  first_name: 'Regular',
  last_name: 'User',
  organization_id: 'org-1',
  is_admin: false,
  roles: ['viewer'],
  permissions: [],
}

export const adminUser: User = {
  id: 'user-2',
  email: 'admin@acme.com',
  first_name: 'Admin',
  last_name: 'User',
  organization_id: 'org-1',
  is_admin: false,
  roles: ['admin'],
  permissions: [
    'users:read',
    'users:write',
    'users:delete',
    'roles:read',
    'audit_logs:read',
    'organization:read',
  ],
}

export const superAdminUser: User = {
  id: 'user-3',
  email: 'superadmin@acme.com',
  first_name: 'Super',
  last_name: 'Admin',
  organization_id: 'org-1',
  is_admin: true,
  roles: ['super_admin'],
}

export const otherOrgUser: User = {
  id: 'user-4',
  email: 'user@test.com',
  first_name: 'Other',
  last_name: 'User',
  organization_id: 'org-2',
  is_admin: false,
  roles: ['viewer'],
}

export const currentUserResponse = (user: User): CurrentUserResponse => ({
  id: user.id,
  email: user.email,
  email_verified: true,
  email_deliverable: true,
  phone: null,
  phone_verified: false,
  first_name: user.first_name,
  last_name: user.last_name,
  is_admin: user.is_admin,
  organization_id: user.organization_id,
  roles: [],
  // Note: organization_name and roles are not in the generated UserProfileResponse type
})

export const usersInOrg1: UserRecord[] = [
  {
    id: 'user-1',
    email: 'user@acme.com',
    email_verified: true,
    email_deliverable: true,
    phone_verified: false,
    first_name: 'Regular',
    last_name: 'User',
    is_admin: false,
    created_time: '2024-01-01T00:00:00Z',
    roles: [],
  },
  {
    id: 'user-2',
    email: 'admin@acme.com',
    email_verified: true,
    email_deliverable: true,
    phone_verified: false,
    first_name: 'Admin',
    last_name: 'User',
    is_admin: false,
    created_time: '2024-01-01T00:00:00Z',
    roles: [],
  },
  {
    id: 'user-3',
    email: 'superadmin@acme.com',
    email_verified: true,
    email_deliverable: true,
    phone_verified: false,
    first_name: 'Super',
    last_name: 'Admin',
    is_admin: true,
    created_time: '2024-01-01T00:00:00Z',
    roles: [],
  },
]

export const usersInOrg2: UserRecord[] = [
  {
    id: 'user-4',
    email: 'user@test.com',
    email_verified: true,
    email_deliverable: true,
    phone_verified: false,
    first_name: 'Other',
    last_name: 'User',
    is_admin: false,
    created_time: '2024-01-01T00:00:00Z',
    roles: [],
  },
]

// =============================================================================
// Role Fixtures
// =============================================================================

export const roles: Role[] = [
  {
    id: 'role-1',
    name: 'owner',
    description: 'Organization owner with full access',
    is_default_on_registration: false,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
  },
  {
    id: 'role-2',
    name: 'admin',
    description: 'Can manage users, roles, and organization settings',
    is_default_on_registration: false,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
  },
  {
    id: 'role-3',
    name: 'member',
    description: 'Standard team member with access to resources',
    is_default_on_registration: true,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
  },
  {
    id: 'role-4',
    name: 'viewer',
    description: 'Read-only access',
    is_default_on_registration: false,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: '2024-01-01T00:00:00Z',
  },
]

// =============================================================================
// File Fixtures
// =============================================================================

export const filesInOrg1: FileRecord[] = [
  {
    id: 'file-1',
    created_time: '2024-01-01T00:00:00Z',
    organization_id: 'org-1',
    uploaded_by_user_id: 'user-1',
    original_filename: 'document.pdf',
    storage_key: 'files/org-1/document.pdf',
    content_type: 'application/pdf',
    file_extension: 'pdf',
    size_bytes: 1024000,
    storage_provider: 's3',
    bucket_name: 'test-bucket',
    status: 'ready',
    category: 'document',
    extra_data: null,
    download_count: 5,
    last_accessed_time: '2024-01-15T00:00:00Z',
    is_public: false,
  },
  {
    id: 'file-2',
    created_time: '2024-01-02T00:00:00Z',
    organization_id: 'org-1',
    uploaded_by_user_id: 'user-2',
    original_filename: 'image.png',
    storage_key: 'files/org-1/image.png',
    content_type: 'image/png',
    file_extension: 'png',
    size_bytes: 512000,
    storage_provider: 's3',
    bucket_name: 'test-bucket',
    status: 'ready',
    category: 'image',
    extra_data: null,
    download_count: 10,
    last_accessed_time: '2024-01-20T00:00:00Z',
    is_public: false,
  },
]

export const filesInOrg2: FileRecord[] = [
  {
    id: 'file-3',
    created_time: '2024-01-01T00:00:00Z',
    organization_id: 'org-2',
    uploaded_by_user_id: 'user-4',
    original_filename: 'other-doc.pdf',
    storage_key: 'files/org-2/other-doc.pdf',
    content_type: 'application/pdf',
    file_extension: 'pdf',
    size_bytes: 2048000,
    storage_provider: 's3',
    bucket_name: 'test-bucket',
    status: 'ready',
    category: 'document',
    extra_data: null,
    download_count: 2,
    last_accessed_time: '2024-01-10T00:00:00Z',
    is_public: false,
  },
]

export const fileSettings: FileSettings = {
  id: 'settings-1',
  organization_id: 'org-1',
  max_file_size_bytes: 10485760, // 10MB
  max_video_size_bytes: 104857600, // 100MB
  allowed_extensions: ['pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx'],
  user_storage_quota_bytes: 104857600, // 100MB
  org_storage_quota_bytes: 1073741824, // 1GB
  signed_url_expiry_seconds: 3600,
  deleted_file_retention_days: 30,
}

export const fileUsage: FileUsage = {
  total_files: 2,
  total_size_bytes: 1536000,
  image_count: 1,
  image_size_bytes: 512000,
  video_count: 0,
  video_size_bytes: 0,
  document_count: 1,
  document_size_bytes: 1024000,
  other_count: 0,
  other_size_bytes: 0,
  user_quota_bytes: 104857600,
  user_quota_used_percent: 1.47,
}

// =============================================================================
// Notification Fixtures
// =============================================================================

export const notifications: Notification[] = [
  {
    id: 'notif-1',
    channel: 'email',
    recipient: 'user@acme.com',
    status: 'delivered',
    provider_message_id: 'msg-123',
    created_time: '2024-01-01T00:00:00Z',
  },
  {
    id: 'notif-2',
    channel: 'sms',
    recipient: '+1234567890',
    status: 'sent',
    provider_message_id: 'msg-456',
    created_time: '2024-01-02T00:00:00Z',
  },
]

export const notificationTemplates: NotificationTemplate[] = [
  {
    id: 'template-1',
    organization_id: 'org-1',
    code: 'welcome',
    name: 'Welcome Email',
    description: 'Sent to new users',
    channel: 'email',
    subject: 'Welcome to {{org_name}}',
    body_text: 'Hello {{first_name}}, welcome to our platform!',
    body_html: '<h1>Hello {{first_name}}</h1><p>Welcome to our platform!</p>',
    variables: null,
    is_active: true,
    created_time: '2024-01-01T00:00:00Z',
    updated_time: null,
  },
]

export const notificationCategories: NotificationCategory[] = [
  {
    id: 'category-1',
    organization_id: 'org-1',
    code: 'marketing',
    name: 'Marketing',
    description: 'Marketing communications',
    default_enabled: true,
    user_configurable: true,
    display_order: 1,
    created_time: '2024-01-01T00:00:00Z',
  },
  {
    id: 'category-2',
    organization_id: 'org-1',
    code: 'transactional',
    name: 'Transactional',
    description: 'Important account notifications',
    default_enabled: true,
    user_configurable: false,
    display_order: 0,
    created_time: '2024-01-01T00:00:00Z',
  },
]

export const notificationSettings: NotificationSettings = {
  id: 'settings-1',
  organization_id: 'org-1',
  email_enabled: true,
  sms_enabled: true,
  whatsapp_enabled: false,
  in_app_enabled: true,
  web_push_enabled: false,
  sms_provider: 'twilio',
  whatsapp_provider: null,
  notification_retention_days: 90,
  sms_rate_limit: 100,
  whatsapp_rate_limit: 100,
  email_sender_name: 'Acme Corp',
  sms_sender_id: 'ACME',
  created_time: '2024-01-01T00:00:00Z',
  updated_time: null,
}

export const userNotificationPreference: UserNotificationPreference = {
  id: 'pref-1',
  user_id: 'user-1',
  organization_id: 'org-1',
  email_enabled: true,
  sms_enabled: true,
  whatsapp_enabled: false,
  in_app_enabled: true,
  web_push_enabled: false,
  quiet_hours_enabled: true,
  quiet_hours_start: '22:00',
  quiet_hours_end: '08:00',
  quiet_hours_timezone: 'America/New_York',
  created_time: '2024-01-01T00:00:00Z',
  updated_time: null,
}

// =============================================================================
// Auth Token Fixtures
// =============================================================================

export const tokens = {
  validAccessToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEifQ.test',
  validRefreshToken: 'refresh-token-valid',
  expiredAccessToken: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTEiLCJleHAiOjB9.expired',
  invalidToken: 'invalid-token',
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Create an auth state for testing
 */
export function createAuthState(user: User | null, isAuthenticated = true) {
  return {
    auth: {
      user,
      token: isAuthenticated ? tokens.validAccessToken : null,
      isAuthenticated,
      isLoading: false,
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
    },
  }
}

/**
 * Create unauthenticated state
 */
export function createUnauthenticatedState() {
  return {
    auth: {
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
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
    },
  }
}

/**
 * Create loading auth state
 */
export function createLoadingAuthState() {
  return {
    auth: {
      user: null,
      token: tokens.validAccessToken,
      isAuthenticated: false,
      isLoading: true,
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
    },
  }
}
