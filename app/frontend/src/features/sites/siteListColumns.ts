import { createElement } from 'react'
import type { AdvancedColumn } from '@/components/AdvancedDataTable'
import type { Site } from '@/types/site'
import type { SiteSummaryItem } from '@/types/siteLive'
import { AgeText } from './components/AgeText'
import { EngineStateBadge, StaleBadge } from './components/LiveBadges'

/**
 * Live columns appended to the sites list (BF-76): data age, stale flag,
 * engine state, occupancy, recommendation and devices opted in. The managed /
 * shadow mode is already a column of the list itself. The figures come from
 * `GET /admin/sites/summary` (liveApi.ts), keyed by site id; while it loads
 * (or for a site it does not list) cells show a dash.
 */
export function siteListExtraColumns(
  t: (key: string, values?: Record<string, unknown>) => string,
  summary?: Map<string, SiteSummaryItem>
): AdvancedColumn<Site>[] {
  const dash = createElement('span', { className: 'text-muted-foreground' }, '-')
  const cell =
    (render: (item: SiteSummaryItem) => React.ReactNode) =>
    (site: Site): React.ReactNode => {
      const item = summary?.get(site.id)
      return item ? render(item) : dash
    }
  return [
    {
      key: 'data_age',
      header: t('sites:list.columns.dataAge'),
      cell: cell((s) => createElement(AgeText, { seconds: s.age_seconds })),
    },
    {
      key: 'stale',
      header: t('sites:list.columns.data'),
      cell: cell((s) => createElement(StaleBadge, { stale: s.stale })),
    },
    {
      key: 'engine_state',
      header: t('sites:list.columns.engine'),
      cell: cell((s) => createElement(EngineStateBadge, { state: s.engine_state as never })),
    },
    {
      key: 'occupancy',
      header: t('sites:list.columns.occupancy'),
      cell: cell((s) =>
        s.occupancy_pct === null
          ? dash
          : t('sites:list.occupancyValue', {
              pct: s.occupancy_pct,
              occupied: s.occupied ?? 0,
              capacity: s.capacity ?? 0,
            })
      ),
    },
    {
      key: 'recommendation',
      header: t('sites:list.columns.recommendation'),
      hiddenOnMobile: true,
      cell: cell((s) => s.recommended_zone_name ?? s.recommended_zone_slug ?? dash),
    },
    {
      key: 'devices_opted_in',
      header: t('sites:list.columns.devices'),
      hiddenOnMobile: true,
      cell: cell((s) => s.devices_opted_in),
    },
  ]
}
