import { useTranslation } from 'react-i18next'
import { useAppSelector } from '@/store/hooks'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertCircle } from 'lucide-react'

export function MaintenancePage() {
  const { t } = useTranslation('errors')
  const { message, scheduledEnd } = useAppSelector((state) => state.maintenance)

  const formatEndTime = (isoString: string | null) => {
    if (!isoString) return null

    try {
      const date = new Date(isoString)
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      }).format(date)
    } catch {
      return null
    }
  }

  const formattedEndTime = formatEndTime(scheduledEnd)

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-yellow-100 dark:bg-yellow-900">
            <AlertCircle className="h-8 w-8 text-yellow-600 dark:text-yellow-400" />
          </div>
          <CardTitle className="text-2xl">{t('maintenance.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <p className="text-muted-foreground">
            {message || t('maintenance.defaultMessage')}
          </p>
          {formattedEndTime && (
            <p className="text-sm text-muted-foreground">
              {t('maintenance.estimatedEnd')}: <strong>{formattedEndTime}</strong>
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            {t('maintenance.autoRefresh')}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
