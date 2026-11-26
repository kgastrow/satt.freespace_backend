import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { TooltipContentProps } from 'recharts'
import { cn } from '@/lib/utils'
import { formatClock } from '../engineTimers'
import { hourTicks, type ShapedHistory } from '../historySeries'

/**
 * Chart colours (dataviz reference palette, categorical slots 1-8 in fixed
 * order; light and dark steps). Slot 1 is the site, zones take slots 2-8 in
 * response order. Defined as CSS variables so theme switching is one place.
 */
const SERIES_VARS = [
  '--viz-1', '--viz-2', '--viz-3', '--viz-4', '--viz-5', '--viz-6', '--viz-7', '--viz-8',
] as const

/** Zones that can be drawn: slots 2-8. */
export const MAX_CHART_ZONES = SERIES_VARS.length - 1

const THEME_CLASSES = [
  '[--viz-1:#257de0] dark:[--viz-1:#338ced]',
  '[--viz-2:#f47230] dark:[--viz-2:#e76624]',
  '[--viz-3:#00b894] dark:[--viz-3:#00a888]',
  '[--viz-4:#f2a600] dark:[--viz-4:#d28e05]',
  '[--viz-5:#ee7fac] dark:[--viz-5:#e24d8b]',
  '[--viz-6:#008a17] dark:[--viz-6:#0aac23]',
  '[--viz-7:#6a4ce2] dark:[--viz-7:#9887ef]',
  '[--viz-8:#ec4647] dark:[--viz-8:#eb6263]',
  '[--viz-ref:#666666] dark:[--viz-ref:#9c9c9c]',
  '[--viz-grid:#e5e5e5] dark:[--viz-grid:#333333]',
].join(' ')

interface OccupancyChartProps {
  shaped: ShapedHistory
  siteName: string
  timeZone: string
  triggerPct: number
  resetPct: number
}

function ChartTooltip({
  active,
  payload,
  label,
  names,
  timeZone,
}: Partial<TooltipContentProps<number, string>> & {
  names: Record<string, string>
  timeZone: string
}) {
  const { t } = useTranslation('sites')
  if (!active || !payload || payload.length === 0) return null
  const time = formatClock(new Date(Number(label)).toISOString(), timeZone)
  return (
    <div className="rounded-md border bg-popover p-3 text-sm text-popover-foreground shadow-md">
      <p className="mb-1 font-medium">{time}</p>
      <ul className="space-y-0.5">
        {payload.map((entry) => (
          <li key={String(entry.dataKey)} className="flex items-center gap-2">
            <span
              aria-hidden
              className="inline-block h-2 w-2 rounded-full"
              style={{ background: entry.color }}
            />
            <span>{names[String(entry.dataKey)]}</span>
            <span className="ml-auto tabular-nums">
              {entry.value === null || entry.value === undefined
                ? t('history.noData')
                : `${entry.value}%`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export function OccupancyChart({
  shaped,
  siteName,
  timeZone,
  triggerPct,
  resetPct,
}: OccupancyChartProps) {
  const { t } = useTranslation('sites')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [showTable, setShowTable] = useState(false)

  const names = useMemo(() => {
    const map: Record<string, string> = {}
    for (const s of shaped.series) map[s.key] = s.zoneId === null ? siteName : s.name
    return map
  }, [shaped.series, siteName])

  const colourOf = (index: number) => `var(${SERIES_VARS[index] ?? SERIES_VARS[0]})`
  const visible = shaped.series.filter((s) => !hidden.has(s.key))
  const ticks = useMemo(() => hourTicks(shaped.domain), [shaped.domain])

  const toggle = (key: string) =>
    setHidden((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  return (
    <div className={cn('space-y-3', THEME_CLASSES)} data-testid="occupancy-chart">
      <ul className="flex flex-wrap gap-2" aria-label={t('history.legend')}>
        {shaped.series.map((s, index) => {
          const off = hidden.has(s.key)
          return (
            <li key={s.key}>
              <button
                type="button"
                aria-pressed={!off}
                onClick={() => toggle(s.key)}
                className={cn(
                  'inline-flex items-center gap-2 rounded-md border px-2 py-1 text-sm',
                  off && 'text-muted-foreground line-through opacity-60'
                )}
              >
                <span
                  aria-hidden
                  className="inline-block h-0.5 w-4 rounded"
                  style={{ background: colourOf(index), height: index === 0 ? 3 : 2 }}
                />
                {names[s.key]}
              </button>
            </li>
          )
        })}
        <li className="inline-flex items-center gap-2 px-2 py-1 text-sm text-muted-foreground">
          <span aria-hidden className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: 'var(--viz-ref)' }} />
          {t('history.triggerLine', { pct: triggerPct })}
        </li>
        <li className="inline-flex items-center gap-2 px-2 py-1 text-sm text-muted-foreground">
          <span aria-hidden className="inline-block w-4 border-t-2 border-dotted" style={{ borderColor: 'var(--viz-ref)' }} />
          {t('history.resetLine', { pct: resetPct })}
        </li>
      </ul>

      <div className="h-80 w-full" role="img" aria-label={t('history.chartLabel', { site: siteName })}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={shaped.rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--viz-grid)" vertical={false} />
            <XAxis
              dataKey="t"
              type="number"
              scale="time"
              domain={shaped.domain}
              ticks={ticks}
              tickFormatter={(v: number) => formatClock(new Date(v).toISOString(), timeZone) ?? ''}
              stroke="var(--viz-ref)"
              tick={{ fill: 'var(--viz-ref)', fontSize: 12 }}
            />
            <YAxis
              domain={[0, 100]}
              ticks={[0, 25, 50, 75, 100]}
              tickFormatter={(v: number) => `${v}%`}
              stroke="var(--viz-ref)"
              tick={{ fill: 'var(--viz-ref)', fontSize: 12 }}
              width={44}
            />
            <ReferenceLine y={triggerPct} stroke="var(--viz-ref)" strokeDasharray="6 4" strokeWidth={1.5} />
            <ReferenceLine y={resetPct} stroke="var(--viz-ref)" strokeDasharray="2 3" strokeWidth={1.5} />
            <Tooltip
              content={(props) => (
                <ChartTooltip {...(props as TooltipContentProps<number, string>)} names={names} timeZone={timeZone} />
              )}
              isAnimationActive={false}
            />
            {visible.map((s) => {
              const index = shaped.series.indexOf(s)
              return (
                <Line
                  key={s.key}
                  dataKey={s.key}
                  type="monotone"
                  stroke={colourOf(index)}
                  strokeWidth={index === 0 ? 3 : 2}
                  dot={false}
                  activeDot={{ r: 4, stroke: 'var(--background)', strokeWidth: 2 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              )
            })}
          </LineChart>
        </ResponsiveContainer>
      </div>

      <button
        type="button"
        className="text-sm underline underline-offset-2"
        aria-expanded={showTable}
        onClick={() => setShowTable((v) => !v)}
      >
        {showTable ? t('history.hideTable') : t('history.showTable')}
      </button>
      {showTable && (
        <div className="max-h-72 overflow-auto rounded-md border">
          <table className="w-full text-sm" data-testid="history-table">
            <thead className="sticky top-0 bg-muted text-left">
              <tr>
                <th className="px-3 py-2">{t('history.time')}</th>
                {shaped.series.map((s) => (
                  <th key={s.key} className="px-3 py-2">{names[s.key]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shaped.rows.map((row) => (
                <tr key={row.t} className="border-t">
                  <td className="px-3 py-1 tabular-nums">
                    {formatClock(new Date(row.t).toISOString(), timeZone)}
                  </td>
                  {shaped.series.map((s) => (
                    <td key={s.key} className="px-3 py-1 tabular-nums">
                      {row[s.key] === null ? t('history.noData') : `${row[s.key]}%`}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
