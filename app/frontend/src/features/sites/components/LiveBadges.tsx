import { useTranslation } from 'react-i18next'
import { CheckCircle2, CircleHelp, OctagonX, TriangleAlert } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { EngineState, ZoneStatus } from '@/types/siteLive'

const STATUS_STYLE: Record<ZoneStatus, { icon: typeof CheckCircle2; className: string }> = {
  AVAILABLE: { icon: CheckCircle2, className: 'border-green-600/40 bg-green-600/10 text-green-700 dark:text-green-400' },
  LIMITED: { icon: TriangleAlert, className: 'border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400' },
  FULL: { icon: OctagonX, className: 'border-red-600/40 bg-red-600/10 text-red-700 dark:text-red-400' },
  UNKNOWN: { icon: CircleHelp, className: 'border-border bg-muted text-muted-foreground' },
}

/** Zone status as the app shows it: icon plus label, never colour alone. */
export function ZoneStatusBadge({ status }: { status: ZoneStatus }) {
  const { t } = useTranslation('sites')
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.UNKNOWN
  const Icon = style.icon
  return (
    <Badge variant="outline" className={cn('gap-1', style.className)}>
      <Icon className="h-3 w-3" aria-hidden />
      {t(`status.${status}`, { defaultValue: status })}
    </Badge>
  )
}

export function EngineStateBadge({ state }: { state: EngineState | null }) {
  const { t } = useTranslation('sites')
  if (!state) return <span className="text-muted-foreground">{t('live.noEngine')}</span>
  const variant = state === 'ACTIVE' ? 'default' : state === 'PENDING' ? 'secondary' : 'outline'
  return <Badge variant={variant}>{t(`engineState.${state}`, { defaultValue: state })}</Badge>
}

export function StaleBadge({ stale }: { stale: boolean }) {
  const { t } = useTranslation('sites')
  if (!stale) return <span className="text-muted-foreground">{t('live.fresh')}</span>
  return (
    <Badge variant="outline" className="gap-1 border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400">
      <TriangleAlert className="h-3 w-3" aria-hidden />
      {t('live.stale')}
    </Badge>
  )
}
