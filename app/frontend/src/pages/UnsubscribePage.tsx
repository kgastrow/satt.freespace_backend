import { useState } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle, XCircle, Loader2, Mail } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  useGetUnsubscribeInfoQuery,
  useProcessUnsubscribeMutation,
} from '@/features/notifications/notificationsApi'

export function UnsubscribePage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const {
    data: info,
    isLoading: isLoadingInfo,
    error: infoError,
  } = useGetUnsubscribeInfoQuery(token || '', {
    skip: !token,
  })

  const [processUnsubscribe, { isLoading: isProcessing }] = useProcessUnsubscribeMutation()
  const [unsubscribed, setUnsubscribed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleUnsubscribe = async () => {
    if (!token) return

    try {
      const result = await processUnsubscribe(token).unwrap()
      if (result.success) {
        setUnsubscribed(true)
      } else {
        setError(t('unsubscribe.error.failed'))
      }
    } catch (err: unknown) {
      const apiError = err as { data?: { detail?: string } }
      setError(apiError.data?.detail || t('unsubscribe.error.generic'))
    }
  }

  // No token provided
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <XCircle className="mx-auto h-12 w-12 text-destructive mb-4" />
            <CardTitle>{t('unsubscribe.invalidLink.title')}</CardTitle>
            <CardDescription>
              {t('unsubscribe.invalidLink.description')}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-muted-foreground mb-4">
              {t('unsubscribe.invalidLink.instructions')}
            </p>
            <Button asChild variant="outline">
              <Link to="/">{t('unsubscribe.goToHomepage')}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Loading state
  if (isLoadingInfo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
        <Card className="w-full max-w-md">
          <CardContent className="py-12 text-center">
            <Loader2 className="mx-auto h-12 w-12 animate-spin text-muted-foreground mb-4" />
            <p className="text-muted-foreground">{t('common:loading')}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Error loading info
  if (infoError || !info) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <XCircle className="mx-auto h-12 w-12 text-destructive mb-4" />
            <CardTitle>{t('unsubscribe.expired.title')}</CardTitle>
            <CardDescription>
              {t('unsubscribe.expired.description')}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-muted-foreground mb-4">
              {t('unsubscribe.expired.instructions')}
            </p>
            <Button asChild variant="outline">
              <Link to="/login">{t('unsubscribe.loginToManage')}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Already unsubscribed
  if (info.is_already_unsubscribed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500/90 dark:text-green-400/90 mb-4" />
            <CardTitle>{t('unsubscribe.alreadyUnsubscribed.title')}</CardTitle>
            <CardDescription>
              {t('unsubscribe.alreadyUnsubscribed.description')}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-muted-foreground mb-4">
              <strong>{info.user_email}</strong> {t('unsubscribe.isNotReceiving')}{' '}
              {info.category_name ? `"${info.category_name}"` : info.channel} {t('unsubscribe.notificationsFrom')}{' '}
              {info.organization_name}.
            </p>
            <Button asChild variant="outline">
              <Link to="/login">{t('unsubscribe.loginToManage')}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Successfully unsubscribed
  if (unsubscribed) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500/90 dark:text-green-400/90 mb-4" />
            <CardTitle>{t('unsubscribe.success.title')}</CardTitle>
            <CardDescription>
              {t('unsubscribe.success.description')}
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <p className="text-muted-foreground mb-4">
              <strong>{info.user_email}</strong> {t('unsubscribe.willNoLongerReceive')}{' '}
              {info.category_name ? `"${info.category_name}"` : info.channel} {t('unsubscribe.notificationsFrom')}{' '}
              {info.organization_name}.
            </p>
            <p className="text-sm text-muted-foreground mb-4">
              {t('unsubscribe.changedYourMind')}
            </p>
            <Button asChild variant="outline">
              <Link to="/login">{t('unsubscribe.loginToManage')}</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Confirmation screen
  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <Mail className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
          <CardTitle>{t('unsubscribe.confirm.title')}</CardTitle>
          <CardDescription>
            {t('unsubscribe.confirm.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="bg-muted rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('unsubscribe.labels.email')}</span>
              <span className="font-medium">{info.user_email}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('unsubscribe.labels.organization')}</span>
              <span className="font-medium">{info.organization_name}</span>
            </div>
            {info.category_name && (
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">{t('unsubscribe.labels.category')}</span>
                <span className="font-medium">{info.category_name}</span>
              </div>
            )}
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">{t('unsubscribe.labels.channel')}</span>
              <span className="font-medium capitalize">{info.channel}</span>
            </div>
          </div>

          {error && (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertTitle>{t('common:error')}</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <div className="flex flex-col gap-2">
            <Button
              onClick={handleUnsubscribe}
              disabled={isProcessing}
              className="w-full"
            >
              {isProcessing ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('unsubscribe.processing')}
                </>
              ) : (
                t('unsubscribe.confirmButton')
              )}
            </Button>
            <Button asChild variant="outline" className="w-full">
              <Link to="/">{t('common:cancel')}</Link>
            </Button>
          </div>

          <p className="text-xs text-center text-muted-foreground">
            {t('unsubscribe.reEnableNote')}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
