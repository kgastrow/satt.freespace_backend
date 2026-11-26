import { useTranslation } from 'react-i18next'
import { describeAge } from '../engineTimers'

/** "3 minutes ago" for an age in seconds; a dash when there is no data. */
export function AgeText({ seconds }: { seconds: number | null | undefined }) {
  const { t } = useTranslation('sites')
  const phrase = describeAge(seconds)
  if (!phrase) return <span className="text-muted-foreground">{t('live.noData')}</span>
  return <>{t(phrase.key, phrase.values)}</>
}
