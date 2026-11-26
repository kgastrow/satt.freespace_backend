import type { LucideIcon } from 'lucide-react'
import {
  Building2,
  Settings,
  MapPin,
  MessageSquareText,
  KeyRound,
  Activity,
  ScrollText,
  LineChart,
  Smartphone,
} from 'lucide-react'
import { SITE_PERMISSIONS } from './permissions'

export interface SiteTab {
  id: string
  /** i18n key (sites namespace) */
  labelKey: string
  /** Path relative to /admin/sites/:siteId ('' = overview) */
  path: string
  icon: LucideIcon
  /** Any one of these shows the tab; omit = always shown */
  permissions?: string[]
}

/**
 * EXTENSION POINT: the tabs of the site detail shell, in display order.
 *
 * To add a page:
 *   1. add an entry here (labelKey in locales/en/sites.json under `tabs`),
 *   2. add a route `/admin/sites/:siteId/<path>` in config/routes.ts whose
 *      component renders its content inside <SiteDetailShell>,
 *   3. use `useSitePermissions()` for write controls.
 * The shell hides tabs whose permissions the user lacks.
 */
export const siteTabs: SiteTab[] = [
  { id: 'overview', labelKey: 'sites:tabs.overview', path: '', icon: Building2, permissions: [SITE_PERMISSIONS.read] },
  { id: 'live', labelKey: 'sites:tabs.live', path: 'live', icon: Activity, permissions: [SITE_PERMISSIONS.read] },
  { id: 'history', labelKey: 'sites:tabs.history', path: 'history', icon: LineChart, permissions: [SITE_PERMISSIONS.read] },
  { id: 'events', labelKey: 'sites:tabs.events', path: 'events', icon: ScrollText, permissions: [SITE_PERMISSIONS.eventsRead] },
  { id: 'devices', labelKey: 'sites:tabs.devices', path: 'devices', icon: Smartphone, permissions: [SITE_PERMISSIONS.read] },
  { id: 'settings', labelKey: 'sites:tabs.settings', path: 'settings', icon: Settings, permissions: [SITE_PERMISSIONS.read] },
  { id: 'zones', labelKey: 'sites:tabs.zones', path: 'zones', icon: MapPin, permissions: [SITE_PERMISSIONS.read] },
  { id: 'templates', labelKey: 'sites:tabs.templates', path: 'templates', icon: MessageSquareText, permissions: [SITE_PERMISSIONS.read] },
  { id: 'ingest-keys', labelKey: 'sites:tabs.ingestKeys', path: 'ingest-keys', icon: KeyRound, permissions: [SITE_PERMISSIONS.read] },
]

export const siteTabPath = (siteId: string, tab: SiteTab) =>
  tab.path ? `/admin/sites/${siteId}/${tab.path}` : `/admin/sites/${siteId}`
