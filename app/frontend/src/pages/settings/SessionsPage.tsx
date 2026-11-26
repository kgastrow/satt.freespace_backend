import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, LogOut } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { SessionCard } from '@/components/sessions/SessionCard'
import {
  useGetSessionsQuery,
  useRevokeSessionMutation,
  useRevokeOtherSessionsMutation,
} from '@/store/api/sessionsApi'
import { toast } from 'sonner'
import { getErrorMessage } from '@/types/api'

export function SessionsPage() {
  const { t } = useTranslation(['settings', 'backend'])

  const { data, isLoading, error } = useGetSessionsQuery()

  const [revokeSession, { isLoading: isRevoking }] = useRevokeSessionMutation()
  const [revokeOtherSessions, { isLoading: isRevokingOthers }] = useRevokeOtherSessionsMutation()
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(null)

  const handleRevokeSession = async (sessionId: string) => {
    setRevokingSessionId(sessionId)
    try {
      await revokeSession(sessionId).unwrap()
      toast.success(t('settings:sessions.messages.revokeSuccess'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    } finally {
      setRevokingSessionId(null)
    }
  }

  const handleRevokeOtherSessions = async () => {
    try {
      const result = await revokeOtherSessions().unwrap()
      toast.success(
        t('settings:sessions.messages.revokeOthersSuccess', { count: result.revoked_count })
      )
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  // Count non-current sessions
  const otherSessionsCount = data?.items.filter((s) => !s.is_current).length || 0

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-72" />
          </CardHeader>
          <CardContent className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="bg-muted/50">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-4">
                    <Skeleton className="h-10 w-10 rounded-full" />
                    <div className="space-y-2 flex-1">
                      <Skeleton className="h-5 w-32" />
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('settings:sessions.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:sessions.error.description')}</AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-start justify-between">
            <div>
              <CardTitle>{t('settings:sessions.title')}</CardTitle>
              <CardDescription>{t('settings:sessions.description')}</CardDescription>
            </div>
            {otherSessionsCount > 0 && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" className="gap-2" disabled={isRevokingOthers}>
                    {isRevokingOthers ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('settings:sessions.buttons.revoking')}
                      </>
                    ) : (
                      <>
                        <LogOut className="h-4 w-4" />
                        {t('settings:sessions.buttons.revokeOthers')}
                      </>
                    )}
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      {t('settings:sessions.dialogs.revokeOthers.title')}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      {t('settings:sessions.dialogs.revokeOthers.description')}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>{t('common:cancel')}</AlertDialogCancel>
                    <AlertDialogAction onClick={handleRevokeOtherSessions}>
                      {t('settings:sessions.dialogs.revokeOthers.confirm')}
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {data?.items && data.items.length > 0 ? (
            data.items.map((session) => (
              <SessionCard
                key={session.id}
                session={session}
                onRevoke={handleRevokeSession}
                isRevoking={isRevoking && revokingSessionId === session.id}
              />
            ))
          ) : (
            <p className="text-sm text-muted-foreground text-center py-8">
              {t('settings:sessions.messages.noSessions')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
