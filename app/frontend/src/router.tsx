import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RootLayout } from '@/layouts/RootLayout'
import { DashboardLayout } from '@/layouts/DashboardLayout'
import { AuthGuard } from '@/components/AuthGuard'
import { PermissionGate } from '@/components/PermissionGate'
import { RouteErrorPage } from '@/pages/RouteErrorPage'
import { settingsRoutes } from '@/routes/settingsRoutes'
import { adminRoutes } from '@/config/routes'
import { generateRoutes } from '@/lib/route-generator'
import { LazyPage, lazyNamed } from '@/lib/lazyRoute'

// =============================================================================
// Lazy-loaded Page Components
// =============================================================================

// Public pages
const LoginPage = lazyNamed(() => import('@/pages/LoginPage'), 'LoginPage')
const RegisterPage = lazyNamed(() => import('@/pages/RegisterPage'), 'RegisterPage')
const VerifyEmailPage = lazyNamed(() => import('@/pages/VerifyEmailPage'), 'VerifyEmailPage')
const ForgotPasswordPage = lazyNamed(() => import('@/pages/ForgotPasswordPage'), 'ForgotPasswordPage')
const ResetPasswordPage = lazyNamed(() => import('@/pages/ResetPasswordPage'), 'ResetPasswordPage')
const NotFoundPage = lazyNamed(() => import('@/pages/NotFoundPage'), 'NotFoundPage')
const UnsubscribePage = lazyNamed(() => import('@/pages/UnsubscribePage'), 'UnsubscribePage')
const OAuthCallback = lazyNamed(() => import('@/pages/OAuthCallback'), 'OAuthCallback')
const SSOConfirmLinkPage = lazyNamed(() => import('@/pages/SSOConfirmLinkPage'), 'SSOConfirmLinkPage')
const HelpCenterPage = lazyNamed(() => import('@/pages/HelpCenterPage'), 'HelpCenterPage')
const HelpArticlePage = lazyNamed(() => import('@/pages/HelpArticlePage'), 'HelpArticlePage')

// Dev-only: error boundary test page. The lazy import lives inside the
// `import.meta.env.DEV` branch so production builds dead-code-eliminate it
// entirely (no chunk emitted) rather than just hiding the route.
const devRoutes = import.meta.env.DEV
  ? (() => {
      const CrashTestPage = lazyNamed(
        () => import('@/pages/dev/CrashTestPage'),
        'CrashTestPage'
      )
      return [
        {
          path: 'dev/crash',
          element: (
            <LazyPage>
              <CrashTestPage />
            </LazyPage>
          ),
        },
      ]
    })()
  : []

// Authenticated pages
const DashboardPage = lazyNamed(() => import('@/pages/DashboardPage'), 'DashboardPage')
const OnboardingPage = lazyNamed(() => import('@/pages/OnboardingPage'), 'OnboardingPage')
const SetupTwoFactorPage = lazyNamed(() => import('@/pages/SetupTwoFactorPage'), 'SetupTwoFactorPage')
const NotificationsFullPage = lazyNamed(() => import('@/pages/NotificationsPage'), 'NotificationsPage')

// Admin layouts
const AdminLayout = lazyNamed(() => import('@/pages/admin/AdminLayout'), 'AdminLayout')
const PlatformAdminLayout = lazyNamed(() => import('@/pages/admin/PlatformAdminLayout'), 'PlatformAdminLayout')

// Admin pages (not yet migrated to route config)
const RolesPage = lazyNamed(() => import('@/pages/admin/RolesPage'), 'RolesPage')
const MetricsPage = lazyNamed(() => import('@/pages/admin/MetricsPage'), 'MetricsPage')
const OnboardingReviewPage = lazyNamed(() => import('@/pages/admin/OnboardingReviewPage'), 'OnboardingReviewPage')

// Super admin pages
const OrganizationsPage = lazyNamed(() => import('@/pages/admin/OrganizationsPage'), 'OrganizationsPage')
const OrganizationMembersPage = lazyNamed(() => import('@/pages/admin/OrganizationMembersPage'), 'OrganizationMembersPage')
const PermissionsPage = lazyNamed(() => import('@/pages/admin/PermissionsPage'), 'PermissionsPage')
const AppKeysPage = lazyNamed(() => import('@/pages/admin/AppKeysPage'), 'AppKeysPage')
const CronJobsPage = lazyNamed(() => import('@/pages/admin/CronJobsPage'), 'CronJobsPage')
const FeatureFlagsPage = lazyNamed(() => import('@/pages/admin/FeatureFlagsPage'), 'FeatureFlagsPage')
const UserTypesPage = lazyNamed(() => import('@/pages/admin/UserTypesPage'), 'UserTypesPage')
const OnboardingStepsPage = lazyNamed(() => import('@/pages/admin/OnboardingStepsPage'), 'OnboardingStepsPage')
const SystemConfigPage = lazyNamed(() => import('@/pages/admin/SystemConfigPage'), 'SystemConfigPage')

// Help Center admin pages
const AdminHelpCenterPage = lazyNamed(() => import('@/pages/admin/HelpCenterPage'), 'HelpCenterPage')
const HelpArticlesPage = lazyNamed(() => import('@/pages/admin/HelpArticlesPage'), 'HelpArticlesPage')
const HelpFaqsPage = lazyNamed(() => import('@/pages/admin/HelpFaqsPage'), 'HelpFaqsPage')
const HelpCategoriesPage = lazyNamed(() => import('@/pages/admin/HelpCategoriesPage'), 'HelpCategoriesPage')

// Platform admin pages (not yet migrated to route config)
const ApiKeyRateLimitsPage = lazyNamed(() => import('@/pages/admin/ApiKeyRateLimitsPage'), 'ApiKeyRateLimitsPage')
const RequestLogsPage = lazyNamed(() => import('@/pages/admin/RequestLogsPage'), 'RequestLogsPage')
const MaintenanceSettingsPage = lazyNamed(() => import('@/pages/admin/MaintenanceSettingsPage'), 'MaintenanceSettingsPage')
const BackgroundJobsPage = lazyNamed(() => import('@/pages/admin/BackgroundJobsPage'), 'BackgroundJobsPage')

export const router = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    errorElement: <RouteErrorPage />,
    children: [
      // Redirect root to dashboard
      {
        index: true,
        element: (
          <AuthGuard>
            <Navigate to="/dashboard" replace />
          </AuthGuard>
        ),
      },

      // Dev-only: trigger a render error to test the ErrorBoundary/ErrorFallback.
      // Visit /dev/crash and click the button. Omitted from production builds.
      ...devRoutes,

      // Public/guest pages
      {
        path: 'login',
        element: (
          <AuthGuard requireAuth={false} redirectTo="/dashboard">
            <LazyPage>
              <LoginPage />
            </LazyPage>
          </AuthGuard>
        ),
      },
      {
        path: 'register',
        element: (
          <AuthGuard requireAuth={false} redirectTo="/dashboard">
            <LazyPage>
              <RegisterPage />
            </LazyPage>
          </AuthGuard>
        ),
      },
      {
        path: 'verify-email',
        element: (
          <LazyPage>
            <VerifyEmailPage />
          </LazyPage>
        ),
      },
      {
        path: 'forgot-password',
        element: (
          <AuthGuard requireAuth={false} redirectTo="/dashboard">
            <LazyPage>
              <ForgotPasswordPage />
            </LazyPage>
          </AuthGuard>
        ),
      },
      {
        path: 'reset-password',
        element: (
          <AuthGuard requireAuth={false} redirectTo="/dashboard">
            <LazyPage>
              <ResetPasswordPage />
            </LazyPage>
          </AuthGuard>
        ),
      },
      {
        path: 'unsubscribe',
        element: (
          <LazyPage>
            <UnsubscribePage />
          </LazyPage>
        ),
      },
      {
        path: 'oauth/callback',
        element: (
          <LazyPage>
            <OAuthCallback />
          </LazyPage>
        ),
      },
      {
        path: 'sso/confirm-link',
        element: (
          <AuthGuard requireAuth={false} redirectTo="/dashboard">
            <LazyPage>
              <SSOConfirmLinkPage />
            </LazyPage>
          </AuthGuard>
        ),
      },
      {
        path: 'help-center',
        element: (
          <LazyPage>
            <HelpCenterPage />
          </LazyPage>
        ),
      },
      {
        path: 'help-center/:slug',
        element: (
          <LazyPage>
            <HelpArticlePage />
          </LazyPage>
        ),
      },

      // 2FA setup page (authenticated but standalone, no dashboard layout)
      {
        path: 'setup-2fa',
        element: (
          <AuthGuard>
            <LazyPage>
              <SetupTwoFactorPage />
            </LazyPage>
          </AuthGuard>
        ),
      },

      // Authenticated pages with dashboard layout
      {
        element: (
          <AuthGuard>
            <DashboardLayout />
          </AuthGuard>
        ),
        children: [
          {
            path: 'dashboard',
            element: (
              <LazyPage>
                <DashboardPage />
              </LazyPage>
            ),
          },
          {
            path: 'onboarding',
            element: (
              <LazyPage>
                <OnboardingPage />
              </LazyPage>
            ),
          },
          {
            path: 'profile',
            element: <Navigate to="/settings/account/profile" replace />,
          },
          {
            path: 'files',
            element: <Navigate to="/settings/account/files" replace />,
          },
          ...settingsRoutes,

          // Notifications full page
          {
            path: 'notifications',
            element: (
              <LazyPage>
                <NotificationsFullPage />
              </LazyPage>
            ),
          },

          // Admin pages with AdminLayout
          // Routes are generated from config/routes.ts using route-generator
          {
            path: 'admin',
            element: (
              <LazyPage>
                <AdminLayout />
              </LazyPage>
            ),
            children: [
              {
                index: true,
                element: <Navigate to="/admin/organization" replace />,
              },
              // Generated admin routes from configuration
              ...generateRoutes(adminRoutes).map((route) => ({
                // Strip '/admin/' prefix since we're already in the admin path context
                path: route.path?.replace(/^\/admin\//, ''),
                element: route.element,
              })),
            ],
          },

          // Onboarding review - standalone page (breakout from admin sidebar)
          {
            path: 'admin/onboarding-review',
            element: (
              <PermissionGate
                permission={['users:read', 'users:write']}
                redirectTo="/dashboard"
              >
                <LazyPage>
                  <OnboardingReviewPage />
                </LazyPage>
              </PermissionGate>
            ),
          },

          // Platform Admin pages with PlatformAdminLayout
          {
            path: 'platform-admin',
            element: (
              <LazyPage>
                <PlatformAdminLayout />
              </LazyPage>
            ),
            children: [
              {
                index: true,
                element: <Navigate to="/platform-admin/organizations" replace />,
              },
              {
                path: 'organizations',
                element: (
                  <LazyPage>
                    <OrganizationsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'organizations/:id/members',
                element: (
                  <LazyPage>
                    <OrganizationMembersPage />
                  </LazyPage>
                ),
              },
              {
                path: 'app-keys',
                element: (
                  <LazyPage>
                    <AppKeysPage />
                  </LazyPage>
                ),
              },
              {
                path: 'roles',
                element: (
                  <LazyPage>
                    <RolesPage />
                  </LazyPage>
                ),
              },
              {
                path: 'permissions',
                element: (
                  <LazyPage>
                    <PermissionsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'api-key-rate-limits',
                element: (
                  <LazyPage>
                    <ApiKeyRateLimitsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'metrics',
                element: (
                  <LazyPage>
                    <MetricsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'background-jobs',
                element: (
                  <LazyPage>
                    <BackgroundJobsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'cron-jobs',
                element: (
                  <LazyPage>
                    <CronJobsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'feature-flags',
                element: (
                  <LazyPage>
                    <FeatureFlagsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'user-types',
                element: (
                  <LazyPage>
                    <UserTypesPage />
                  </LazyPage>
                ),
              },
              {
                path: 'user-types/:id/steps',
                element: (
                  <LazyPage>
                    <OnboardingStepsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'request-logs',
                element: (
                  <LazyPage>
                    <RequestLogsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'maintenance',
                element: (
                  <LazyPage>
                    <MaintenanceSettingsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'system-config',
                element: (
                  <LazyPage>
                    <SystemConfigPage />
                  </LazyPage>
                ),
              },
              // Help Center admin pages
              {
                path: 'help-center',
                element: (
                  <LazyPage>
                    <AdminHelpCenterPage />
                  </LazyPage>
                ),
              },
              {
                path: 'help-center/articles',
                element: (
                  <LazyPage>
                    <HelpArticlesPage />
                  </LazyPage>
                ),
              },
              {
                path: 'help-center/faqs',
                element: (
                  <LazyPage>
                    <HelpFaqsPage />
                  </LazyPage>
                ),
              },
              {
                path: 'help-center/categories',
                element: (
                  <LazyPage>
                    <HelpCategoriesPage />
                  </LazyPage>
                ),
              },
            ],
          },
        ],
      },

      // 404
      {
        path: '*',
        element: (
          <LazyPage>
            <NotFoundPage />
          </LazyPage>
        ),
      },
    ],
  },
])
