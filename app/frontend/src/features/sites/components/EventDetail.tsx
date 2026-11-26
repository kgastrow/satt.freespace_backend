import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { formatDayClock } from '../engineTimers'
import { DEVICE_OUTCOMES } from '../eventFilters'
import type { SiteEvent } from '@/types/siteLive'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h4 className="text-sm font-medium">{title}</h4>
      {children}
    </div>
  )
}

const jsonText = (value: unknown) => JSON.stringify(value, null, 2)

/**
 * Detail of one event: rendered message, figures, device counts per reason,
 * fan-out timing and repeat count. Counts only - no device identifiers exist
 * in the log (BF-35), and "SENT" reads "accepted by FCM", never "delivered"
 * (BF-69).
 */
export function EventDetail({ event, timeZone }: { event: SiteEvent; timeZone: string }) {
  const { t } = useTranslation('sites')
  const counts = event.counts ?? {}
  const countKeys = [
    ...DEVICE_OUTCOMES.filter((k) => k in counts),
    ...Object.keys(counts).filter((k) => !(DEVICE_OUTCOMES as readonly string[]).includes(k)),
  ]
  const hasFanout = event.fanout_status !== null || event.fcm_latency_ms !== null

  return (
    <div className="grid gap-4 p-4 md:grid-cols-2" data-testid={`event-detail-${event.id}`}>
      {(event.rendered_title || event.rendered_body) && (
        <Section title={t('events.detail.message')}>
          <div className="rounded-md border bg-background p-3 text-sm">
            {event.rendered_title && <p className="font-medium">{event.rendered_title}</p>}
            {event.rendered_body && <p>{event.rendered_body}</p>}
          </div>
        </Section>
      )}

      <Section title={t('events.detail.repeat')}>
        <p className="text-sm">
          {t('events.detail.repeatValue', { count: event.repeat_count })}
          {event.repeat_count > 1 && event.last_seen_at && (
            <span className="text-muted-foreground">
              {' '}
              {t('events.detail.lastSeen', {
                at: formatDayClock(event.last_seen_at, timeZone) ?? '-',
              })}
            </span>
          )}
        </p>
      </Section>

      {countKeys.length > 0 && (
        <Section title={t('events.detail.counts')}>
          <ul className="flex flex-wrap gap-2">
            {countKeys.map((key) => (
              <li key={key}>
                <Badge variant="secondary" className="gap-1">
                  {t(`events.outcomes.${key}`, { defaultValue: key })}
                  <span className="tabular-nums">{counts[key]}</span>
                </Badge>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {hasFanout && (
        <Section title={t('events.detail.fanout')}>
          <p className="text-sm">
            {event.fanout_status
              ? t(`events.fanoutStatus.${event.fanout_status}`, { defaultValue: event.fanout_status })
              : null}
            {event.fcm_latency_ms !== null && (
              <span className="text-muted-foreground">
                {' '}
                {t('events.detail.latency', { ms: event.fcm_latency_ms })}
              </span>
            )}
          </p>
        </Section>
      )}

      {event.figures && Object.keys(event.figures).length > 0 && (
        <Section title={t('events.detail.figures')}>
          <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
            {jsonText(event.figures)}
          </pre>
        </Section>
      )}

      {event.details && Object.keys(event.details).length > 0 && (
        <Section title={t('events.detail.details')}>
          <pre className="max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs">
            {jsonText(event.details)}
          </pre>
        </Section>
      )}
    </div>
  )
}
