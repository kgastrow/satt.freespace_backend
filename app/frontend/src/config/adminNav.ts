import type { LucideIcon } from 'lucide-react'
import {
  Building2,
  Users,
  ClipboardCheck,
  Key,
  Bell,
  Megaphone,
  FolderOpen,
  KeyRound,
  ShieldCheck,
  FileText,
  MessageSquare,
  Mail,
  Info,
  FileBarChart,
  History,
} from 'lucide-react'

export interface AdminNavItem {
  id: string
  labelKey: string
  path: string
  icon: LucideIcon
  permissions?: string[]
}

export interface AdminNavCategory {
  id: string
  labelKey: string
  icon: LucideIcon
  items: AdminNavItem[]
}

export const adminNavConfig: AdminNavCategory[] = [
  {
    id: 'organization',
    labelKey: 'admin:nav.organization.title',
    icon: Building2,
    items: [
      {
        id: 'settings',
        labelKey: 'admin:nav.organization.settings',
        path: '/admin/organization',
        icon: Building2,
        permissions: ['organization:read', 'organization:write'],
      },
      {
        id: 'sso',
        labelKey: 'admin:nav.organization.sso',
        path: '/admin/sso/settings',
        icon: KeyRound,
        permissions: ['organization:write'],
      },
      {
        id: 'two-factor',
        labelKey: 'admin:nav.organization.twoFactor',
        path: '/admin/two-factor',
        icon: ShieldCheck,
        permissions: ['two_factor:read', 'two_factor:write'],
      },
    ],
  },
  {
    id: 'users',
    labelKey: 'admin:nav.users.title',
    icon: Users,
    items: [
      {
        id: 'manage',
        labelKey: 'admin:nav.users.manage',
        path: '/admin/users',
        icon: Users,
        permissions: ['users:read', 'users:write', 'users:delete'],
      },
      {
        id: 'onboarding',
        labelKey: 'admin:nav.users.onboarding',
        path: '/admin/onboarding-review',
        icon: ClipboardCheck,
        permissions: ['users:read', 'users:write'],
      },
    ],
  },
  {
    id: 'communication',
    labelKey: 'admin:nav.communication.title',
    icon: Bell,
    items: [
      {
        id: 'notifications',
        labelKey: 'admin:nav.communication.notifications',
        path: '/admin/notifications',
        icon: Bell,
        permissions: ['notifications:read', 'notifications:write', 'notifications:send'],
      },
      {
        id: 'announcements',
        labelKey: 'admin:nav.communication.announcements',
        path: '/admin/announcements',
        icon: Megaphone,
        permissions: ['announcements:read', 'announcements:write', 'announcements:delete'],
      },
      {
        id: 'changelog',
        labelKey: 'admin:nav.communication.changelog',
        path: '/admin/changelog',
        icon: History,
        permissions: ['changelog:write'],
      },
      {
        id: 'email-settings',
        labelKey: 'admin:nav.communication.emailSettings',
        path: '/admin/email/settings',
        icon: Mail,
        permissions: ['email_settings:read', 'email_settings:write'],
      },
    ],
  },
  {
    id: 'content',
    labelKey: 'admin:nav.content.title',
    icon: FolderOpen,
    items: [
      {
        id: 'files',
        labelKey: 'admin:nav.content.files',
        path: '/admin/files',
        icon: FolderOpen,
        permissions: ['files:read', 'files:write', 'files:delete', 'files:admin'],
      },
      {
        id: 'api-keys',
        labelKey: 'admin:nav.content.apiKeys',
        path: '/admin/api-keys',
        icon: Key,
        permissions: ['api_keys:read', 'api_keys:write', 'api_keys:delete'],
      },
      {
        id: 'about',
        labelKey: 'admin:nav.content.about',
        path: '/admin/about',
        icon: Info,
        permissions: ['about:write'],
      },
    ],
  },
  {
    id: 'monitoring',
    labelKey: 'admin:nav.monitoring.title',
    icon: FileText,
    items: [
      {
        id: 'audit-logs',
        labelKey: 'admin:nav.monitoring.auditLogs',
        path: '/admin/audit-logs',
        icon: FileText,
        permissions: ['audit_logs:read'],
      },
      {
        id: 'feedback',
        labelKey: 'admin:nav.monitoring.feedback',
        path: '/admin/feedback',
        icon: MessageSquare,
        permissions: ['feedback:read'],
      },
      {
        id: 'reports',
        labelKey: 'admin:nav.monitoring.reports',
        path: '/admin/reports',
        icon: FileBarChart,
        permissions: ['reports:read'],
      },
    ],
  },
]
