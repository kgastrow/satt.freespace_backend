/**
 * MSW request handlers for API mocking in tests
 */

import { http, HttpResponse, delay } from 'msw'
import {
  regularUser,
  adminUser,
  superAdminUser,
  currentUserResponse,
  tokens,
  usersInOrg1,
  filesInOrg1,
  filesInOrg2,
  fileSettings,
  fileUsage,
  organizations,
  roles,
  notifications,
  notificationTemplates,
  notificationCategories,
  notificationSettings,
  userNotificationPreference,
} from './fixtures'
import type { User } from '@/types/auth'
import { siteHandlers } from './sitesHandlers'

// Base URL for API - exported for use in test files
export const API_BASE = 'http://localhost:8000/api/v1'

// State management for tests
let currentUser: User = regularUser
let currentToken: string | null = tokens.validAccessToken

/**
 * Set the current user for test scenarios
 */
export function setCurrentUser(user: User) {
  currentUser = user
}

/**
 * Set the current token for test scenarios
 */
export function setCurrentToken(token: string | null) {
  currentToken = token
}

/**
 * Reset to default state
 */
export function resetHandlerState() {
  currentUser = regularUser
  currentToken = tokens.validAccessToken
}

/**
 * Helper to check authorization header
 */
function isAuthorized(request: Request): boolean {
  const auth = request.headers.get('Authorization')
  return auth === `Bearer ${currentToken}` && currentToken !== null
}

/**
 * Helper to get user's organization ID
 */
function getCurrentOrgId(): string {
  return currentUser.organization_id
}

// =============================================================================
// Auth Handlers
// =============================================================================

export const authHandlers = [
  // Check Email (for two-step login flow)
  http.post(`${API_BASE}/auth/check-email`, async ({ request }) => {
    await delay(50)
    const body = (await request.json()) as { email: string; organization_slug: string }

    // Simulate existing users with password auth
    if (body.email === 'user@acme.com' || body.email === 'admin@acme.com' || body.email === 'superadmin@acme.com') {
      return HttpResponse.json({
        exists: true,
        auth_methods: ['password'],
      })
    }

    // Non-existent user
    return HttpResponse.json({
      exists: false,
      auth_methods: [],
    })
  }),

  // Login
  http.post(`${API_BASE}/auth/login`, async ({ request }) => {
    await delay(50)
    const body = (await request.json()) as { email: string; password: string; organization_slug: string }

    if (body.email === 'user@acme.com' && body.password === 'password123') {
      return HttpResponse.json({
        access_token: tokens.validAccessToken,
      })
    }

    if (body.email === 'admin@acme.com' && body.password === 'password123') {
      setCurrentUser(adminUser)
      return HttpResponse.json({
        access_token: tokens.validAccessToken,
      })
    }

    if (body.email === 'superadmin@acme.com' && body.password === 'password123') {
      setCurrentUser(superAdminUser)
      return HttpResponse.json({
        access_token: tokens.validAccessToken,
      })
    }

    return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 })
  }),

  // Logout
  http.post(`${API_BASE}/auth/logout`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    return HttpResponse.json({ message: 'Logged out successfully' })
  }),

  // Refresh Token (reads refresh token from httpOnly cookie)
  http.post(`${API_BASE}/auth/refresh`, async () => {
    await delay(50)
    // In tests, always return success (cookie is httpOnly, not accessible to JS)
    return HttpResponse.json({
      access_token: tokens.validAccessToken,
    })
  }),

  // Get Current User
  http.get(`${API_BASE}/user/me`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    return HttpResponse.json(currentUserResponse(currentUser))
  }),

  // Get User Permissions
  http.get(`${API_BASE}/user/permissions`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    return HttpResponse.json({ permissions: currentUser.permissions || [] })
  }),

  // Register
  http.post(`${API_BASE}/user/register`, async ({ request }) => {
    await delay(50)
    const body = (await request.json()) as {
      email: string
      password: string
      first_name: string
      last_name: string
    }

    if (body.email === 'existing@acme.com') {
      return HttpResponse.json({ detail: 'Email already registered' }, { status: 400 })
    }

    return HttpResponse.json({
      id: 'new-user-id',
      email: body.email,
      message: 'Registration successful. Please verify your email.',
    })
  }),

  // Password Reset Request
  http.post(`${API_BASE}/auth/password-reset/request`, async () => {
    await delay(50)
    return HttpResponse.json({ message: 'Password reset email sent' })
  }),

  // Password Reset Confirm
  http.post(`${API_BASE}/auth/password-reset/confirm`, async ({ request }) => {
    await delay(50)
    const body = (await request.json()) as { token: string }

    if (body.token === 'invalid-token') {
      return HttpResponse.json({ detail: 'Invalid or expired token' }, { status: 400 })
    }

    return HttpResponse.json({ message: 'Password reset successful' })
  }),
]

// =============================================================================
// User Handlers
// =============================================================================

export const userHandlers = [
  // List Users (cursor-based pagination)
  http.get(`${API_BASE}/users/cursor`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '10')
    const cursor = url.searchParams.get('cursor')

    // Return users only from current organization
    const orgUsers = getCurrentOrgId() === 'org-1' ? usersInOrg1 : []

    // Find starting index based on cursor
    let startIndex = 0
    if (cursor) {
      // Cursor format: "timestamp_uuid" - find the user with this id
      const cursorId = cursor.split('_').pop()
      const cursorIndex = orgUsers.findIndex((u) => u.id === cursorId)
      if (cursorIndex >= 0) {
        startIndex = cursorIndex + 1
      }
    }

    const paginatedUsers = orgUsers.slice(startIndex, startIndex + limit)
    const hasMore = startIndex + limit < orgUsers.length
    const lastUser = paginatedUsers[paginatedUsers.length - 1]
    const nextCursor = hasMore && lastUser
      ? `${lastUser.created_time}_${lastUser.id}`
      : null

    return HttpResponse.json({
      items: paginatedUsers,
      total: orgUsers.length,
      limit,
      next_cursor: nextCursor,
      has_more: hasMore,
    })
  }),

  // List Users (offset-based pagination - legacy)
  http.get(`${API_BASE}/users`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '10')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    // Return users only from current organization
    const orgUsers = getCurrentOrgId() === 'org-1' ? usersInOrg1 : []
    const paginatedUsers = orgUsers.slice(offset, offset + limit)

    return HttpResponse.json({
      items: paginatedUsers,
      total: orgUsers.length,
      limit,
      offset,
    })
  }),

  // Get Single User
  http.get(`${API_BASE}/users/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const orgUsers = getCurrentOrgId() === 'org-1' ? usersInOrg1 : []
    const user = orgUsers.find((u) => u.id === params.id)

    if (!user) {
      return HttpResponse.json({ detail: 'User not found' }, { status: 404 })
    }

    return HttpResponse.json(user)
  }),

  // Create User
  http.post(`${API_BASE}/users`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as {
      email: string
      password: string
      first_name: string
      last_name: string
      is_admin?: boolean
    }

    return HttpResponse.json({
      id: 'new-user-id',
      email: body.email,
      email_verified: false,
      email_deliverable: true,
      phone_verified: false,
      first_name: body.first_name,
      last_name: body.last_name,
      is_admin: body.is_admin || false,
      created_time: new Date().toISOString(),
      updated_time: null,
    })
  }),

  // Update User
  http.put(`${API_BASE}/users/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as Record<string, unknown>
    const orgUsers = getCurrentOrgId() === 'org-1' ? usersInOrg1 : []
    const user = orgUsers.find((u) => u.id === params.id)

    if (!user) {
      return HttpResponse.json({ detail: 'User not found' }, { status: 404 })
    }

    return HttpResponse.json({
      ...user,
      ...body,
    })
  }),

  // Delete User
  http.delete(`${API_BASE}/users/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const orgUsers = getCurrentOrgId() === 'org-1' ? usersInOrg1 : []
    const user = orgUsers.find((u) => u.id === params.id)

    if (!user) {
      return HttpResponse.json({ detail: 'User not found' }, { status: 404 })
    }

    return HttpResponse.json({ message: 'User deleted successfully' })
  }),
]

// =============================================================================
// File Handlers
// =============================================================================

export const fileHandlers = [
  // List Files
  http.get(`${API_BASE}/files`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    // Support SDL filter format: filter[category]=image
    const category = url.searchParams.get('filter[category]')
    const status = url.searchParams.get('filter[status]')
    const limit = parseInt(url.searchParams.get('limit') || '50')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    // Return files only from current organization (tenant isolation)
    let orgFiles = getCurrentOrgId() === 'org-1' ? filesInOrg1 : filesInOrg2

    // Filter by category if specified
    if (category) {
      orgFiles = orgFiles.filter((f) => f.category === category)
    }

    // Filter by status if specified
    if (status) {
      orgFiles = orgFiles.filter((f) => f.status === status)
    }

    const paginatedFiles = orgFiles.slice(offset, offset + limit)

    return HttpResponse.json({
      items: paginatedFiles,
      total: orgFiles.length,
      limit,
      offset,
    })
  }),

  // Get Single File
  http.get(`${API_BASE}/files/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const allFiles = [...filesInOrg1, ...filesInOrg2]
    const file = allFiles.find((f) => f.id === params.id)

    if (!file) {
      return HttpResponse.json({ detail: 'File not found' }, { status: 404 })
    }

    // Tenant isolation: can only access files from own organization
    if (file.organization_id !== getCurrentOrgId() && !currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    return HttpResponse.json(file)
  }),

  // Upload File
  http.post(`${API_BASE}/files/upload`, async ({ request }) => {
    await delay(100)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({
      id: 'new-file-id',
      created_time: new Date().toISOString(),
      organization_id: getCurrentOrgId(),
      uploaded_by_user_id: currentUser.id,
      original_filename: 'uploaded-file.pdf',
      storage_key: `files/${getCurrentOrgId()}/uploaded-file.pdf`,
      content_type: 'application/pdf',
      file_extension: 'pdf',
      size_bytes: 1024,
      storage_provider: 's3',
      bucket_name: 'test-bucket',
      status: 'ready',
      category: 'document',
      extra_data: null,
      download_count: 0,
      last_accessed_time: null,
    })
  }),

  // Get Download URL
  http.get(`${API_BASE}/files/:id/download`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const allFiles = [...filesInOrg1, ...filesInOrg2]
    const file = allFiles.find((f) => f.id === params.id)

    if (!file || (file.organization_id !== getCurrentOrgId() && !currentUser.is_admin)) {
      return HttpResponse.json({ detail: 'File not found' }, { status: 404 })
    }

    return HttpResponse.json({
      download_url: `https://test-bucket.s3.amazonaws.com/${file.storage_key}?signed=true`,
      expires_at: new Date(Date.now() + 3600000).toISOString(),
      filename: file.original_filename,
    })
  }),

  // Delete File
  http.delete(`${API_BASE}/files/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const allFiles = [...filesInOrg1, ...filesInOrg2]
    const file = allFiles.find((f) => f.id === params.id)

    if (!file || (file.organization_id !== getCurrentOrgId() && !currentUser.is_admin)) {
      return HttpResponse.json({ detail: 'File not found' }, { status: 404 })
    }

    return HttpResponse.json({ message: 'File deleted successfully' })
  }),

  // Get User Usage
  http.get(`${API_BASE}/files/usage`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    return HttpResponse.json(fileUsage)
  }),

  // Get File Settings
  http.get(`${API_BASE}/files/settings`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    return HttpResponse.json(fileSettings)
  }),

  // Update File Settings
  http.put(`${API_BASE}/files/settings`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as Record<string, unknown>
    return HttpResponse.json({
      ...fileSettings,
      ...body,
    })
  }),
]

// =============================================================================
// Organization Handlers
// =============================================================================

export const organizationHandlers = [
  // List Organizations (Super Admin only)
  http.get(`${API_BASE}/organizations`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '10')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    const paginatedOrgs = organizations.slice(offset, offset + limit)

    return HttpResponse.json({
      items: paginatedOrgs,
      total: organizations.length,
      limit,
      offset,
    })
  }),

  // Get Single Organization
  http.get(`${API_BASE}/organizations/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const org = organizations.find((o) => o.id === params.id)

    if (!org) {
      return HttpResponse.json({ detail: 'Organization not found' }, { status: 404 })
    }

    // Non-super admins can only see their own organization
    if (!currentUser.is_admin && org.id !== getCurrentOrgId()) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    return HttpResponse.json(org)
  }),

  // Request Organization Deletion
  http.post(`${API_BASE}/organizations/:id/request-deletion`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    return HttpResponse.json({
      message: 'Deletion request submitted',
      organization_id: params.id as string,
      deletion_requested_time: new Date().toISOString(),
    })
  }),

  // Cancel Deletion Request
  http.delete(`${API_BASE}/organizations/:id/request-deletion`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    return HttpResponse.json({
      message: 'Deletion request cancelled',
      organization_id: params.id as string,
    })
  }),

  // Get Organization Members
  http.get(`${API_BASE}/organizations/:id/members`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin && params.id !== getCurrentOrgId()) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    const members = params.id === 'org-1' ? usersInOrg1 : params.id === 'org-2' ? usersInOrg1.slice(0, 1) : []

    return HttpResponse.json({
      items: members,
      total: members.length,
      limit: 50,
      offset: 0,
    })
  }),

  // Remove Organization Member
  http.delete(`${API_BASE}/organizations/:orgId/members/:userId`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
    }

    return HttpResponse.json({ message: 'Member removed successfully' })
  }),
]

// =============================================================================
// Role Handlers
// =============================================================================

export const roleHandlers = [
  // List Roles
  http.get(`${API_BASE}/roles`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({
      items: roles,
      total: roles.length,
      limit: 50,
      offset: 0,
    })
  }),

  // Assign Role
  http.post(`${API_BASE}/user-roles/assign`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({ message: 'Role assigned successfully' })
  }),

  // Revoke Role
  http.post(`${API_BASE}/user-roles/revoke`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({ message: 'Role revoked successfully' })
  }),

  // Get User Roles
  http.get(`${API_BASE}/user-roles/users/:userId/roles`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '50')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    return HttpResponse.json({
      items: [
        {
          id: 'user-role-1',
          user_id: 'user-1',
          role_id: 'role-1',
          role_name: 'viewer',
          assigned_by: null,
          assigned_by_email: null,
          created_time: '2024-01-01T00:00:00Z',
          deleted_time: null,
        },
      ],
      total: 1,
      limit,
      offset,
    })
  }),
]

// =============================================================================
// Notification Handlers
// =============================================================================

export const notificationHandlers = [
  // List Notifications
  http.get(`${API_BASE}/notifications`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '50')
    const offset = parseInt(url.searchParams.get('offset') || '0')
    // Support SDL filter format: filter[channel]=email, filter[status]=sent, etc.
    const channel = url.searchParams.get('filter[channel]')
    const status = url.searchParams.get('filter[status]')

    let filteredNotifications = [...notifications]
    if (channel) {
      filteredNotifications = filteredNotifications.filter((n) => n.channel === channel)
    }
    if (status) {
      filteredNotifications = filteredNotifications.filter((n) => n.status === status)
    }

    return HttpResponse.json({
      items: filteredNotifications.slice(offset, offset + limit),
      total: filteredNotifications.length,
      limit,
      offset,
    })
  }),

  // Send Notification
  http.post(`${API_BASE}/notifications/send`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as { channel: string; recipient?: string }

    return HttpResponse.json({
      message: 'Notification sent successfully',
      notification: {
        id: 'new-notif-id',
        channel: body.channel,
        provider: 'sendgrid',
        recipient: body.recipient || 'user@acme.com',
        user_id: 'user-1',
        template_id: null,
        subject: 'Test',
        body_preview: 'Test notification...',
        status: 'pending',
        provider_message_id: null,
        error_message: null,
        retry_count: 0,
        bulk_notification_id: null,
        metadata: null,
        created_time: new Date().toISOString(),
        updated_time: null,
      },
    })
  }),

  // Get Templates
  http.get(`${API_BASE}/notifications/templates`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '50')
    const offset = parseInt(url.searchParams.get('offset') || '0')
    // Support SDL filter format: filter[channel]=email
    const channel = url.searchParams.get('filter[channel]')

    let filteredTemplates = [...notificationTemplates]
    if (channel) {
      filteredTemplates = filteredTemplates.filter((t) => t.channel === channel)
    }

    return HttpResponse.json({
      items: filteredTemplates.slice(offset, offset + limit),
      total: filteredTemplates.length,
      limit,
      offset,
    })
  }),

  // Create Template
  http.post(`${API_BASE}/notifications/templates`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as { code: string; name: string; channel: string; body_text: string }

    return HttpResponse.json({
      message: 'Template created successfully',
      template: {
        id: 'new-template-id',
        organization_id: getCurrentOrgId(),
        code: body.code,
        name: body.name,
        description: null,
        channel: body.channel,
        subject: null,
        body_text: body.body_text,
        body_html: null,
        variables: null,
        is_active: true,
        created_time: new Date().toISOString(),
        updated_time: null,
      },
    })
  }),

  // Get Categories
  http.get(`${API_BASE}/notifications/categories`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '50')
    const offset = parseInt(url.searchParams.get('offset') || '0')

    return HttpResponse.json({
      items: notificationCategories.slice(offset, offset + limit),
      total: notificationCategories.length,
      limit,
      offset,
    })
  }),

  // Get Notification Settings
  http.get(`${API_BASE}/notifications/settings`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json(notificationSettings)
  }),

  // Get User Preferences
  http.get(`${API_BASE}/notifications/preferences`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json(userNotificationPreference)
  }),

  // Update User Preferences
  http.put(`${API_BASE}/notifications/preferences`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as Record<string, unknown>

    return HttpResponse.json({
      message: 'Preferences updated successfully',
      preferences: {
        ...userNotificationPreference,
        ...body,
      },
    })
  }),

  // Bulk Notification
  http.post(`${API_BASE}/notifications/bulk`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    const body = (await request.json()) as { name: string; channel: string }

    return HttpResponse.json({
      message: 'Bulk notification created',
      bulk_notification: {
        id: 'bulk-notif-id',
        name: body.name,
        channel: body.channel,
        status: 'pending',
        total_recipients: 10,
        sent_count: 0,
        failed_count: 0,
        scheduled_time: null,
        started_time: null,
        completed_time: null,
        created_time: new Date().toISOString(),
      },
    })
  }),

  // Get Bulk Notification
  http.get(`${API_BASE}/notifications/bulk/:id`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({
      id: params.id as string,
      name: 'Test Bulk',
      channel: 'email',
      status: 'completed',
      total_recipients: 10,
      sent_count: 10,
      failed_count: 0,
      scheduled_time: null,
      started_time: '2024-01-01T00:00:00Z',
      completed_time: '2024-01-01T00:05:00Z',
      created_time: '2024-01-01T00:00:00Z',
    })
  }),
]

// =============================================================================
// SSO Handlers
// =============================================================================

export const ssoHandlers = [
  // Get Enabled SSO Providers (public endpoint for login page)
  http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, async () => {
    await delay(50)
    // Return empty providers by default (no SSO enabled)
    return HttpResponse.json({
      providers: [],
    })
  }),

  // Get SSO Settings (authenticated)
  http.get(`${API_BASE}/organization-sso-settings`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    return HttpResponse.json({
      id: 'sso-settings-1',
      organization_id: getCurrentOrgId(),
      sso_allowed: false,
      google_enabled: false,
      google_client_id: null,
      created_time: '2024-01-01T00:00:00Z',
      updated_time: null,
    })
  }),

  // Update SSO Settings (admin only)
  http.put(`${API_BASE}/organization-sso-settings`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    // Check if user is admin (super admin, owner, or admin role)
    const isUserAdmin =
      currentUser.is_admin || currentUser.roles?.includes('owner') || currentUser.roles?.includes('admin')

    if (!isUserAdmin) {
      return HttpResponse.json({ detail: 'Admin access required' }, { status: 403 })
    }

    const body = (await request.json()) as Record<string, unknown>

    return HttpResponse.json({
      id: 'sso-settings-1',
      organization_id: getCurrentOrgId(),
      sso_allowed: true,
      google_enabled: body.google_enabled ?? false,
      google_client_id: body.google_client_id ?? null,
      created_time: '2024-01-01T00:00:00Z',
      updated_time: new Date().toISOString(),
    })
  }),

  // Get SSO Settings for specific org (super admin only)
  http.get(`${API_BASE}/organization-sso-settings/organization/:orgId`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Super admin access required' }, { status: 403 })
    }

    // Return 404 for orgs without SSO settings
    return HttpResponse.json({ detail: 'SSO settings not found' }, { status: 404 })
  }),

  // Set SSO allowed for org (super admin only)
  http.put(`${API_BASE}/organization-sso-settings/organization/:orgId/allow`, async ({ request, params }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }

    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Super admin access required' }, { status: 403 })
    }

    const body = (await request.json()) as { sso_allowed: boolean }

    return HttpResponse.json({
      id: 'sso-settings-1',
      organization_id: params.orgId as string,
      sso_allowed: body.sso_allowed,
      google_enabled: false,
      google_client_id: null,
      created_time: '2024-01-01T00:00:00Z',
      updated_time: new Date().toISOString(),
    })
  }),
]

// =============================================================================
// Maintenance Handlers
// =============================================================================

// Maintenance history state for tests
let maintenanceHistoryItems: Array<{
  id: string
  status: string
  scheduled_start: string | null
  scheduled_end: string | null
  actual_start: string | null
  actual_end: string | null
  message: string | null
  started_by: { id: string; first_name: string | null; last_name: string | null; email: string } | null
  ended_by: { id: string; first_name: string | null; last_name: string | null; email: string } | null
  created_time: string
}> = []

let maintenanceConfig = {
  enabled: false,
  message: null as string | null,
  scheduled_start: null as string | null,
  scheduled_end: null as string | null,
  allow_super_admin: true,
}

/**
 * Reset maintenance state for tests
 */
export function resetMaintenanceState() {
  maintenanceHistoryItems = []
  maintenanceConfig = {
    enabled: false,
    message: null,
    scheduled_start: null,
    scheduled_end: null,
    allow_super_admin: true,
  }
}

/**
 * Add a maintenance history item for tests
 */
export function addMaintenanceHistoryItem(item: (typeof maintenanceHistoryItems)[0]) {
  maintenanceHistoryItems.unshift(item)
}

export const maintenanceHandlers = [
  // Get maintenance status (public)
  http.get(`${API_BASE}/maintenance/status`, async () => {
    await delay(50)
    return HttpResponse.json({
      enabled: maintenanceConfig.enabled,
      message: maintenanceConfig.message,
      scheduled_start: maintenanceConfig.scheduled_start,
      scheduled_end: maintenanceConfig.scheduled_end,
      allow_super_admin: maintenanceConfig.allow_super_admin,
    })
  }),

  // Get maintenance config (admin only)
  http.get(`${API_BASE}/admin/maintenance`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Super admin access required' }, { status: 403 })
    }

    return HttpResponse.json({
      enabled: maintenanceConfig.enabled,
      message: maintenanceConfig.message,
      scheduled_start: maintenanceConfig.scheduled_start,
      scheduled_end: maintenanceConfig.scheduled_end,
      allow_super_admin: maintenanceConfig.allow_super_admin,
      updated_time: new Date().toISOString(),
      updated_by_user_id: currentUser.id,
    })
  }),

  // Update maintenance config (admin only)
  http.put(`${API_BASE}/admin/maintenance`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Super admin access required' }, { status: 403 })
    }

    const body = (await request.json()) as {
      enabled: boolean
      message?: string | null
      scheduled_start?: string | null
      scheduled_end?: string | null
      allow_super_admin?: boolean
    }

    const wasEnabled = maintenanceConfig.enabled

    // Update config
    maintenanceConfig.enabled = body.enabled
    maintenanceConfig.message = body.message ?? maintenanceConfig.message
    maintenanceConfig.scheduled_start = body.scheduled_start ?? maintenanceConfig.scheduled_start
    maintenanceConfig.scheduled_end = body.scheduled_end ?? maintenanceConfig.scheduled_end
    maintenanceConfig.allow_super_admin = body.allow_super_admin ?? maintenanceConfig.allow_super_admin

    // Create history record if enabling
    if (body.enabled && !wasEnabled) {
      maintenanceHistoryItems.unshift({
        id: `history-${Date.now()}`,
        status: 'active',
        scheduled_start: body.scheduled_start ?? null,
        scheduled_end: body.scheduled_end ?? null,
        actual_start: new Date().toISOString(),
        actual_end: null,
        message: body.message ?? null,
        started_by: {
          id: currentUser.id,
          first_name: currentUser.first_name,
          last_name: currentUser.last_name,
          email: currentUser.email,
        },
        ended_by: null,
        created_time: new Date().toISOString(),
      })
    }

    // Update history record if disabling
    if (!body.enabled && wasEnabled) {
      const activeItem = maintenanceHistoryItems.find((item) => item.status === 'active')
      if (activeItem) {
        activeItem.status = 'completed'
        activeItem.actual_end = new Date().toISOString()
        activeItem.ended_by = {
          id: currentUser.id,
          first_name: currentUser.first_name,
          last_name: currentUser.last_name,
          email: currentUser.email,
        }
      }
    }

    return HttpResponse.json({
      message: 'Maintenance configuration updated successfully',
      message_code: 'maintenance.updated',
      config: {
        enabled: maintenanceConfig.enabled,
        message: maintenanceConfig.message,
        scheduled_start: maintenanceConfig.scheduled_start,
        scheduled_end: maintenanceConfig.scheduled_end,
        allow_super_admin: maintenanceConfig.allow_super_admin,
        updated_time: new Date().toISOString(),
        updated_by_user_id: currentUser.id,
      },
    })
  }),

  // Get maintenance history (admin only)
  http.get(`${API_BASE}/admin/maintenance/history`, async ({ request }) => {
    await delay(50)
    if (!isAuthorized(request)) {
      return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
    }
    if (!currentUser.is_admin) {
      return HttpResponse.json({ detail: 'Super admin access required' }, { status: 403 })
    }

    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '10')
    const offset = parseInt(url.searchParams.get('offset') || '0')
    const statusFilter = url.searchParams.get('status')

    let items = maintenanceHistoryItems
    if (statusFilter) {
      items = items.filter((item) => item.status === statusFilter)
    }

    const paginatedItems = items.slice(offset, offset + limit)

    return HttpResponse.json({
      items: paginatedItems,
      total: items.length,
      limit,
      offset,
    })
  }),
]

// =============================================================================
// Combined Handlers
// =============================================================================

export const handlers = [
  ...authHandlers,
  ...userHandlers,
  ...fileHandlers,
  ...organizationHandlers,
  ...roleHandlers,
  ...notificationHandlers,
  ...ssoHandlers,
  ...maintenanceHandlers,
  ...siteHandlers,
]
