import { type ComponentType } from 'react'
import { lazyNamed } from '@/lib/lazyRoute'

/**
 * Route configuration with metadata for programmatic route generation.
 *
 * This configuration decouples routes from permission checks and provides
 * a single source of truth for all route metadata including permissions,
 * authentication requirements, layouts, and page titles.
 */
export interface RouteConfig {
  /** Route path (e.g., '/admin/users') */
  path: string
  /** Component to render for this route (supports lazy-loaded components) */
  component: ComponentType
  /** Required permissions (OR logic by default) */
  permissions?: string[]
  /** If true, requires ALL permissions. If false, requires ANY (default: false) */
  requireAll?: boolean
  /** If true, requires authentication (default: false) */
  requireAuth?: boolean
  /** If true, only accessible to guests (redirects authenticated users) */
  guestOnly?: boolean
  /** Layout type for this route */
  layout?: 'root' | 'dashboard' | 'admin' | 'platform-admin'
  /** i18n key for page title (e.g., 'admin:users.title') */
  title?: string
  /** i18n key for breadcrumb (e.g., 'admin:navigation.users') */
  breadcrumb?: string
}

// =============================================================================
// Lazy-loaded Page Components
// =============================================================================


// Admin pages (lazy-loaded for code splitting)
const OrganizationSettingsPage = lazyNamed(() => import('@/pages/admin/OrganizationSettingsPage'), 'OrganizationSettingsPage')
const ApiKeysPage = lazyNamed(() => import('@/pages/admin/ApiKeysPage'), 'ApiKeysPage')
const UsersPage = lazyNamed(() => import('@/pages/admin/UsersPage'), 'UsersPage')
const UserDetailPage = lazyNamed(() => import('@/pages/admin/UserDetailPage'), 'UserDetailPage')
const AuditLogsPage = lazyNamed(() => import('@/pages/admin/AuditLogsPage'), 'AuditLogsPage')
const NotificationsPage = lazyNamed(() => import('@/pages/admin/NotificationsPage'), 'NotificationsPage')
const SendNotificationPage = lazyNamed(() => import('@/pages/admin/SendNotificationPage'), 'SendNotificationPage')
const BulkNotificationsPage = lazyNamed(() => import('@/pages/admin/BulkNotificationsPage'), 'BulkNotificationsPage')
const TemplatesPage = lazyNamed(() => import('@/pages/admin/TemplatesPage'), 'TemplatesPage')
const CategoriesPage = lazyNamed(() => import('@/pages/admin/CategoriesPage'), 'CategoriesPage')
const NotificationSettingsPage = lazyNamed(() => import('@/pages/admin/NotificationSettingsPage'), 'NotificationSettingsPage')
const AdminFilesPage = lazyNamed(() => import('@/pages/admin/AdminFilesPage'), 'AdminFilesPage')
const FileSettingsPage = lazyNamed(() => import('@/pages/admin/FileSettingsPage'), 'FileSettingsPage')
const SSOSettingsPage = lazyNamed(() => import('@/pages/admin/SSOSettingsPage'), 'SSOSettingsPage')
const EmailSettingsPage = lazyNamed(() => import('@/pages/admin/EmailSettingsPage'), 'EmailSettingsPage')
const TwoFactorSettingsPage = lazyNamed(() => import('@/pages/admin/TwoFactorSettingsPage'), 'TwoFactorSettingsPage')
const AnnouncementsPage = lazyNamed(() => import('@/pages/admin/AnnouncementsPage'), 'AnnouncementsPage')
const ChangelogPage = lazyNamed(() => import('@/pages/admin/ChangelogPage'), 'ChangelogPage')
const FeedbackListPage = lazyNamed(() => import('@/features/feedback/pages/FeedbackListPage'), 'FeedbackListPage')
const FeedbackDetailPage = lazyNamed(() => import('@/features/feedback/pages/FeedbackDetailPage'), 'FeedbackDetailPage')
const AboutSettingsPage = lazyNamed(() => import('@/pages/admin/AboutSettingsPage'), 'AboutSettingsPage')
const ReportsPage = lazyNamed(() => import('@/pages/admin/ReportsPage'), 'ReportsPage')

// =============================================================================
// Route Configurations
// =============================================================================

/**
 * Admin routes configuration.
 * These routes are rendered within the AdminLayout and require specific permissions.
 */
export const adminRoutes: RouteConfig[] = [
  {
    path: '/admin/organization',
    component: OrganizationSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['organization:read', 'organization:write'],
    title: 'admin:organization.title',
    breadcrumb: 'admin:navigation.organization',
  },
  {
    path: '/admin/api-keys',
    component: ApiKeysPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['api_keys:read', 'api_keys:write', 'api_keys:delete'],
    title: 'admin:apiKeys.title',
    breadcrumb: 'admin:navigation.apiKeys',
  },
  {
    path: '/admin/users',
    component: UsersPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['users:read', 'users:write', 'users:delete'],
    title: 'admin:users.title',
    breadcrumb: 'admin:navigation.users',
  },
  {
    path: '/admin/users/:id',
    component: UserDetailPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['users:read'],
    title: 'admin:users.detail.title',
    breadcrumb: 'admin:navigation.userDetail',
  },
  {
    path: '/admin/audit-logs',
    component: AuditLogsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['audit_logs:read'],
    title: 'admin:auditLogs.title',
    breadcrumb: 'admin:navigation.auditLogs',
  },
  {
    path: '/admin/notifications',
    component: NotificationsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notifications:read', 'notifications:write', 'notifications:send'],
    title: 'admin:notifications.title',
    breadcrumb: 'admin:navigation.notifications',
  },
  {
    path: '/admin/notifications/send',
    component: SendNotificationPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notifications:send'],
    title: 'admin:notifications.sendTitle',
    breadcrumb: 'admin:navigation.sendNotification',
  },
  {
    path: '/admin/notifications/bulk',
    component: BulkNotificationsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notifications:send'],
    title: 'admin:notifications.bulkTitle',
    breadcrumb: 'admin:navigation.bulkNotifications',
  },
  {
    path: '/admin/notifications/templates',
    component: TemplatesPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notification_templates:read', 'notification_templates:write'],
    title: 'admin:notifications.templatesTitle',
    breadcrumb: 'admin:navigation.notificationTemplates',
  },
  {
    path: '/admin/notifications/categories',
    component: CategoriesPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notification_categories:read', 'notification_categories:write'],
    title: 'admin:notifications.categoriesTitle',
    breadcrumb: 'admin:navigation.notificationCategories',
  },
  {
    path: '/admin/notifications/settings',
    component: NotificationSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['notification_settings:read', 'notification_settings:write'],
    title: 'admin:notifications.settingsTitle',
    breadcrumb: 'admin:navigation.notificationSettings',
  },
  {
    path: '/admin/files',
    component: AdminFilesPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['files:read', 'files:write', 'files:delete', 'files:admin'],
    title: 'admin:files.title',
    breadcrumb: 'admin:navigation.files',
  },
  {
    path: '/admin/files/settings',
    component: FileSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['file_settings:read', 'file_settings:write'],
    title: 'admin:files.settingsTitle',
    breadcrumb: 'admin:navigation.fileSettings',
  },
  {
    path: '/admin/sso/settings',
    component: SSOSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['organization:write'],
    title: 'admin:sso.settingsTitle',
    breadcrumb: 'admin:navigation.ssoSettings',
  },
  {
    path: '/admin/email/settings',
    component: EmailSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['email_settings:read', 'email_settings:write'],
    title: 'admin:email.settingsTitle',
    breadcrumb: 'admin:navigation.emailSettings',
  },
  {
    path: '/admin/two-factor',
    component: TwoFactorSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['two_factor:read', 'two_factor:write'],
    title: 'admin:twoFactor.title',
    breadcrumb: 'admin:navigation.twoFactor',
  },
  {
    path: '/admin/announcements',
    component: AnnouncementsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['announcements:read', 'announcements:write', 'announcements:delete'],
    title: 'admin:announcements.title',
    breadcrumb: 'admin:navigation.announcements',
  },
  {
    path: '/admin/changelog',
    component: ChangelogPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['changelog:write'],
    title: 'admin:changelog.pageTitle',
    breadcrumb: 'admin:navigation.changelog',
  },
  {
    path: '/admin/feedback',
    component: FeedbackListPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['feedback:read'],
    title: 'admin:feedback.title',
    breadcrumb: 'admin:navigation.feedback',
  },
  {
    path: '/admin/feedback/:id',
    component: FeedbackDetailPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['feedback:read'],
    title: 'admin:feedback.detailTitle',
    breadcrumb: 'admin:navigation.feedbackDetail',
  },
  {
    path: '/admin/about',
    component: AboutSettingsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['about:write'],
    title: 'admin:about.title',
    breadcrumb: 'admin:navigation.about',
  },
  {
    path: '/admin/reports',
    component: ReportsPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['reports:read'],
    title: 'admin:reports.title',
    breadcrumb: 'admin:navigation.reports',
  },
]

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Get route configuration by path.
 *
 * @param path - Route path to search for
 * @returns Route configuration or undefined if not found
 */
export function getRouteConfig(path: string): RouteConfig | undefined {
  return adminRoutes.find((r) => r.path === path)
}

/**
 * Get all routes for a specific layout.
 *
 * @param layout - Layout type to filter by
 * @returns Array of route configurations for the specified layout
 */
export function getRoutesByLayout(layout: RouteConfig['layout']): RouteConfig[] {
  return adminRoutes.filter((r) => r.layout === layout)
}
