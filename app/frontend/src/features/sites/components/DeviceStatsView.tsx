import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { DeviceStatsResponse } from '@/types/siteLive'

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardContent className="space-y-1 pt-6">
        <p className="text-sm text-muted-foreground">{label}</p>
        <p className="text-3xl font-semibold tabular-nums">{value}</p>
      </CardContent>
    </Card>
  )
}

function CountTable({
  title,
  head,
  rows,
  empty,
}: {
  title: string
  head: string
  rows: Array<{ key: string; label: React.ReactNode; count: number }>
  empty: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{empty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{head}</TableHead>
                <TableHead className="text-right" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell>{row.label}</TableCell>
                  <TableCell className="text-right tabular-nums">{row.count}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Device statistics: counts only (BF-35 - no device identifiers exist in the
 * back office). `showSites` adds the per-site breakdown (section-level page).
 */
export function DeviceStatsView({
  stats,
  showSites = false,
}: {
  stats: DeviceStatsResponse
  showSites?: boolean
}) {
  const { t } = useTranslation('sites')
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2">
        <Tile label={t('devices.total')} value={stats.total_devices} />
        <Tile label={t('devices.optedIn')} value={stats.opted_in} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <CountTable
          title={t('devices.byPlatform')}
          head={t('devices.platform')}
          empty={t('devices.empty')}
          rows={stats.by_platform.map((p) => ({
            key: p.platform,
            label: t(`devices.platforms.${p.platform}`, { defaultValue: p.platform }),
            count: p.count,
          }))}
        />
        <CountTable
          title={t('devices.byVersion')}
          head={t('devices.version')}
          empty={t('devices.empty')}
          rows={stats.by_app_version.map((v) => ({
            key: v.app_version ?? '__unknown__',
            label: v.app_version ?? (
              <span className="text-muted-foreground">{t('devices.unknownVersion')}</span>
            ),
            count: v.count,
          }))}
        />
      </div>
      {showSites && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('devices.bySite')}</CardTitle>
            <CardDescription>{t('devices.bySiteDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            {stats.by_site.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('devices.empty')}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('devices.site')}</TableHead>
                    <TableHead className="text-right">{t('devices.devices')}</TableHead>
                    <TableHead className="text-right">{t('devices.optedInShort')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stats.by_site.map((site) => (
                    <TableRow key={site.site_id}>
                      <TableCell>
                        <span className="font-medium">{site.name}</span>{' '}
                        <code className="text-xs text-muted-foreground">{site.slug}</code>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{site.devices}</TableCell>
                      <TableCell className="text-right tabular-nums">{site.opted_in}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
