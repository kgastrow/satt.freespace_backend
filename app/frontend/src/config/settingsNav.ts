import type { LucideIcon } from 'lucide-react'
import {
  User,
  Link2,
  Monitor,
  FolderOpen,
  Bell,
  Languages,
  Palette,
  Lock,
  Mail,
  KeyRound,
  Shield,
  Download,
  Keyboard,
  Settings,
  HelpCircle,
  MessageSquare,
  Info,
  History,
  Trash2,
} from 'lucide-react'

export interface SettingsNavItem {
  id: string
  labelKey: string
  path: string
  icon: LucideIcon
  external?: boolean // For items that navigate outside settings (e.g., profile)
  // Optional visibility condition
  visibilityKey?: 'twoFactorAvailable' | 'multipleLanguagesAvailable'
}

export interface SettingsNavCategory {
  id: string
  labelKey: string
  icon: LucideIcon
  items: SettingsNavItem[]
}

export interface SettingsVisibilityFlags {
  twoFactorAvailable: boolean
  multipleLanguagesAvailable: boolean
}

/**
 * Filter settings navigation based on visibility flags.
 * Items with a visibilityKey are only shown if the corresponding flag is true.
 */
export function filterSettingsNav(
  config: SettingsNavCategory[],
  flags: SettingsVisibilityFlags
): SettingsNavCategory[] {
  return config
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => {
        if (!item.visibilityKey) return true
        return flags[item.visibilityKey]
      }),
    }))
    .filter((category) => category.items.length > 0)
}

export const settingsNavConfig: SettingsNavCategory[] = [
  {
    id: 'account',
    labelKey: 'settings:nav.account.title',
    icon: User,
    items: [
      {
        id: 'profile',
        labelKey: 'settings:nav.account.profile',
        path: '/settings/account/profile',
        icon: User,
      },
      {
        id: 'connected',
        labelKey: 'settings:nav.account.connected',
        path: '/settings/account/connected',
        icon: Link2,
      },
      {
        id: 'sessions',
        labelKey: 'settings:nav.account.sessions',
        path: '/settings/account/sessions',
        icon: Monitor,
      },
      {
        id: 'files',
        labelKey: 'settings:nav.account.files',
        path: '/settings/account/files',
        icon: FolderOpen,
      },
    ],
  },
  {
    id: 'preferences',
    labelKey: 'settings:nav.preferences.title',
    icon: Bell,
    items: [
      {
        id: 'notifications',
        labelKey: 'settings:nav.preferences.notifications',
        path: '/settings/preferences/notifications',
        icon: Bell,
      },
      {
        id: 'language',
        labelKey: 'settings:nav.preferences.language',
        path: '/settings/preferences/language',
        icon: Languages,
        visibilityKey: 'multipleLanguagesAvailable',
      },
      {
        id: 'appearance',
        labelKey: 'settings:nav.preferences.appearance',
        path: '/settings/preferences/appearance',
        icon: Palette,
      },
    ],
  },
  {
    id: 'security',
    labelKey: 'settings:nav.security.title',
    icon: Shield,
    items: [
      {
        id: 'password',
        labelKey: 'settings:nav.security.password',
        path: '/settings/security/password',
        icon: Lock,
      },
      {
        id: 'email',
        labelKey: 'settings:nav.security.email',
        path: '/settings/security/email',
        icon: Mail,
      },
      {
        id: '2fa',
        labelKey: 'settings:nav.security.twoFactor',
        path: '/settings/security/2fa',
        icon: KeyRound,
        visibilityKey: 'twoFactorAvailable',
      },
      {
        id: 'privacy',
        labelKey: 'settings:nav.security.privacy',
        path: '/settings/security/privacy',
        icon: Shield,
      },
      {
        id: 'export',
        labelKey: 'settings:nav.security.export',
        path: '/settings/security/export',
        icon: Download,
      },
    ],
  },
  {
    id: 'app',
    labelKey: 'settings:nav.app.title',
    icon: Settings,
    items: [
      {
        id: 'shortcuts',
        labelKey: 'settings:nav.app.shortcuts',
        path: '/settings/app/shortcuts',
        icon: Keyboard,
      },
      {
        id: 'advanced',
        labelKey: 'settings:nav.app.advanced',
        path: '/settings/app/advanced',
        icon: Settings,
      },
    ],
  },
  {
    id: 'support',
    labelKey: 'settings:nav.support.title',
    icon: HelpCircle,
    items: [
      {
        id: 'feedback',
        labelKey: 'settings:nav.support.feedback',
        path: '/settings/support/feedback',
        icon: MessageSquare,
      },
      {
        id: 'about',
        labelKey: 'settings:nav.support.about',
        path: '/settings/support/about',
        icon: Info,
      },
      {
        id: 'changelog',
        labelKey: 'settings:nav.support.changelog',
        path: '/settings/support/changelog',
        icon: History,
      },
    ],
  },
  {
    id: 'danger',
    labelKey: 'settings:nav.danger.title',
    icon: Trash2,
    items: [
      {
        id: 'delete',
        labelKey: 'settings:nav.danger.delete',
        path: '/settings/danger/delete',
        icon: Trash2,
      },
    ],
  },
]
