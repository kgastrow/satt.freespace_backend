import { Navigate, type RouteObject } from 'react-router-dom'
import { LazyPage, lazyNamed } from '@/lib/lazyRoute'

// =============================================================================
// Lazy-loaded Settings Components
// =============================================================================

// Settings layout (lazy-loaded)
const SettingsLayout = lazyNamed(() => import('@/pages/settings/SettingsLayout'), 'SettingsLayout')

// Account pages
const ProfilePage = lazyNamed(() => import('@/pages/ProfilePage'), 'ProfilePage')
const ConnectedAccountsPage = lazyNamed(() => import('@/pages/settings/ConnectedAccountsPage'), 'ConnectedAccountsPage')
const SessionsPage = lazyNamed(() => import('@/pages/settings/SessionsPage'), 'SessionsPage')
const FilesPage = lazyNamed(() => import('@/pages/FilesPage'), 'FilesPage')

// Preferences pages
const NotificationsPage = lazyNamed(() => import('@/pages/settings/NotificationsPage'), 'NotificationsPage')
const LanguagePage = lazyNamed(() => import('@/pages/settings/LanguagePage'), 'LanguagePage')
const AppearancePage = lazyNamed(() => import('@/pages/settings/AppearancePage'), 'AppearancePage')

// Security pages
const PasswordPage = lazyNamed(() => import('@/pages/settings/PasswordPage'), 'PasswordPage')
const EmailChangePage = lazyNamed(() => import('@/pages/settings/EmailChangePage'), 'EmailChangePage')
const TwoFactorPage = lazyNamed(() => import('@/pages/settings/TwoFactorPage'), 'TwoFactorPage')
const PrivacyPage = lazyNamed(() => import('@/pages/settings/PrivacyPage'), 'PrivacyPage')
const DataExportPage = lazyNamed(() => import('@/pages/settings/DataExportPage'), 'DataExportPage')

// App Settings pages
const ShortcutsPage = lazyNamed(() => import('@/pages/settings/ShortcutsPage'), 'ShortcutsPage')
const AdvancedPage = lazyNamed(() => import('@/pages/settings/AdvancedPage'), 'AdvancedPage')

// Support pages
const FeedbackPage = lazyNamed(() => import('@/pages/settings/FeedbackPage'), 'FeedbackPage')
const AboutPage = lazyNamed(() => import('@/pages/settings/AboutPage'), 'AboutPage')
const ChangelogPage = lazyNamed(() => import('@/pages/settings/ChangelogPage'), 'ChangelogPage')

// Danger Zone pages
const DeleteAccountPage = lazyNamed(() => import('@/pages/settings/DeleteAccountPage'), 'DeleteAccountPage')

// =============================================================================
// Settings Routes
// =============================================================================

export const settingsRoutes: RouteObject[] = [
  // Main settings section with layout
  {
    path: 'settings',
    element: (
      <LazyPage>
        <SettingsLayout />
      </LazyPage>
    ),
    children: [
      // Default redirect to profile
      { index: true, element: <Navigate to="account/profile" replace /> },

      // Account section
      {
        path: 'account/profile',
        element: (
          <LazyPage>
            <ProfilePage />
          </LazyPage>
        ),
      },
      {
        path: 'account/connected',
        element: (
          <LazyPage>
            <ConnectedAccountsPage />
          </LazyPage>
        ),
      },
      {
        path: 'account/sessions',
        element: (
          <LazyPage>
            <SessionsPage />
          </LazyPage>
        ),
      },
      {
        path: 'account/files',
        element: (
          <LazyPage>
            <FilesPage />
          </LazyPage>
        ),
      },

      // Preferences section
      {
        path: 'preferences/notifications',
        element: (
          <LazyPage>
            <NotificationsPage />
          </LazyPage>
        ),
      },
      {
        path: 'preferences/language',
        element: (
          <LazyPage>
            <LanguagePage />
          </LazyPage>
        ),
      },
      {
        path: 'preferences/appearance',
        element: (
          <LazyPage>
            <AppearancePage />
          </LazyPage>
        ),
      },

      // Security section
      {
        path: 'security/password',
        element: (
          <LazyPage>
            <PasswordPage />
          </LazyPage>
        ),
      },
      {
        path: 'security/email',
        element: (
          <LazyPage>
            <EmailChangePage />
          </LazyPage>
        ),
      },
      {
        path: 'security/2fa',
        element: (
          <LazyPage>
            <TwoFactorPage />
          </LazyPage>
        ),
      },
      {
        path: 'security/privacy',
        element: (
          <LazyPage>
            <PrivacyPage />
          </LazyPage>
        ),
      },
      {
        path: 'security/export',
        element: (
          <LazyPage>
            <DataExportPage />
          </LazyPage>
        ),
      },

      // App Settings section
      {
        path: 'app/shortcuts',
        element: (
          <LazyPage>
            <ShortcutsPage />
          </LazyPage>
        ),
      },
      {
        path: 'app/advanced',
        element: (
          <LazyPage>
            <AdvancedPage />
          </LazyPage>
        ),
      },

      // Support section
      {
        path: 'support/feedback',
        element: (
          <LazyPage>
            <FeedbackPage />
          </LazyPage>
        ),
      },
      {
        path: 'support/about',
        element: (
          <LazyPage>
            <AboutPage />
          </LazyPage>
        ),
      },
      {
        path: 'support/changelog',
        element: (
          <LazyPage>
            <ChangelogPage />
          </LazyPage>
        ),
      },

      // Danger Zone section
      {
        path: 'danger/delete',
        element: (
          <LazyPage>
            <DeleteAccountPage />
          </LazyPage>
        ),
      },
    ],
  },

  // Legacy redirects for backward compatibility
  {
    path: 'settings/organization',
    element: <Navigate to="/admin/organization" replace />,
  },
  {
    path: 'settings/api-keys',
    element: <Navigate to="/admin/api-keys" replace />,
  },
  {
    path: 'settings/notifications',
    element: <Navigate to="/settings/preferences/notifications" replace />,
  },
  {
    path: 'settings/two-factor',
    element: <Navigate to="/settings/security/2fa" replace />,
  },
]
