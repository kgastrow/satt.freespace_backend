import type { LucideIcon } from 'lucide-react'
import {
  Building2,
  Shield,
  Key,
  Gauge,
  Flag,
  UserCog,
  HelpCircle,
  Clock,
  ScrollText,
  Wrench,
  BarChart3,
  Settings,
  Activity,
} from 'lucide-react'

export interface PlatformAdminNavItem {
  id: string
  labelKey: string
  path: string
  icon: LucideIcon
}

export interface PlatformAdminNavCategory {
  id: string
  labelKey: string
  icon: LucideIcon
  items: PlatformAdminNavItem[]
}

export const platformAdminNavConfig: PlatformAdminNavCategory[] = [
  {
    id: 'organizations',
    labelKey: 'platformAdmin:nav.organizations.title',
    icon: Building2,
    items: [
      {
        id: 'manage',
        labelKey: 'platformAdmin:nav.organizations.manage',
        path: '/platform-admin/organizations',
        icon: Building2,
      },
    ],
  },
  {
    id: 'access',
    labelKey: 'platformAdmin:nav.access.title',
    icon: Shield,
    items: [
      {
        id: 'roles',
        labelKey: 'platformAdmin:nav.access.roles',
        path: '/platform-admin/roles',
        icon: Shield,
      },
      {
        id: 'permissions',
        labelKey: 'platformAdmin:nav.access.permissions',
        path: '/platform-admin/permissions',
        icon: Key,
      },
      {
        id: 'user-types',
        labelKey: 'platformAdmin:nav.access.userTypes',
        path: '/platform-admin/user-types',
        icon: UserCog,
      },
    ],
  },
  {
    id: 'platform',
    labelKey: 'platformAdmin:nav.platform.title',
    icon: Flag,
    items: [
      {
        id: 'feature-flags',
        labelKey: 'platformAdmin:nav.platform.featureFlags',
        path: '/platform-admin/feature-flags',
        icon: Flag,
      },
      {
        id: 'api-rate-limits',
        labelKey: 'platformAdmin:nav.platform.apiRateLimits',
        path: '/platform-admin/api-key-rate-limits',
        icon: Gauge,
      },
      {
        id: 'maintenance',
        labelKey: 'platformAdmin:nav.platform.maintenance',
        path: '/platform-admin/maintenance',
        icon: Wrench,
      },
      {
        id: 'system-config',
        labelKey: 'platformAdmin:nav.platform.systemConfig',
        path: '/platform-admin/system-config',
        icon: Settings,
      },
    ],
  },
  {
    id: 'content',
    labelKey: 'platformAdmin:nav.content.title',
    icon: HelpCircle,
    items: [
      {
        id: 'help-center',
        labelKey: 'platformAdmin:nav.content.helpCenter',
        path: '/platform-admin/help-center',
        icon: HelpCircle,
      },
    ],
  },
  {
    id: 'monitoring',
    labelKey: 'platformAdmin:nav.monitoring.title',
    icon: ScrollText,
    items: [
      {
        id: 'metrics',
        labelKey: 'platformAdmin:nav.monitoring.metrics',
        path: '/platform-admin/metrics',
        icon: BarChart3,
      },
      {
        id: 'background-jobs',
        labelKey: 'platformAdmin:nav.monitoring.backgroundJobs',
        path: '/platform-admin/background-jobs',
        icon: Activity,
      },
      {
        id: 'cron-jobs',
        labelKey: 'platformAdmin:nav.monitoring.cronJobs',
        path: '/platform-admin/cron-jobs',
        icon: Clock,
      },
      {
        id: 'request-logs',
        labelKey: 'platformAdmin:nav.monitoring.requestLogs',
        path: '/platform-admin/request-logs',
        icon: ScrollText,
      },
    ],
  },
]
