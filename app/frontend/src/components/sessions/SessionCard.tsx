import { useTranslation } from 'react-i18next'
import { Monitor, Smartphone, Tablet, HelpCircle, MapPin, Clock, Loader2, Mail, KeyRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { Session } from '@/store/api/sessionsApi'
import { formatDistanceToNow } from 'date-fns'

const getAuthProviderIcon = (provider: string | null) => {
  switch (provider) {
    case 'email':
      return <Mail className="h-3 w-3" />
    case 'google':
      return (
        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor">
          <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
          <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
          <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
          <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
        </svg>
      )
    default:
      return <KeyRound className="h-3 w-3" />
  }
}

interface SessionCardProps {
  session: Session
  onRevoke: (sessionId: string) => void
  isRevoking: boolean
}

const getDeviceIcon = (deviceType: string) => {
  switch (deviceType) {
    case 'mobile':
      return <Smartphone className="h-5 w-5" />
    case 'tablet':
      return <Tablet className="h-5 w-5" />
    case 'desktop':
      return <Monitor className="h-5 w-5" />
    default:
      return <HelpCircle className="h-5 w-5" />
  }
}

const getCountryFlag = (countryCode: string | null): string => {
  if (!countryCode) return ''
  // Convert country code to flag emoji
  const codePoints = countryCode
    .toUpperCase()
    .split('')
    .map((char) => 127397 + char.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}

export function SessionCard({ session, onRevoke, isRevoking }: SessionCardProps) {
  const { t } = useTranslation(['settings'])

  const locationDisplay = (() => {
    const parts: string[] = []
    const flag = getCountryFlag(session.location.country_code)
    if (flag) parts.push(flag)
    if (session.location.city) parts.push(session.location.city)
    if (session.location.country) parts.push(session.location.country)

    if (parts.length === 0) {
      return t('settings:sessions.location.unknown')
    }
    return parts.join(' ')
  })()

  const deviceTypeLabel = t(`settings:sessions.deviceTypes.${session.device.device_type}`)
  const authProviderLabel = t(`settings:sessions.authProviders.${session.auth_provider || 'unknown'}`)

  return (
    <Card className={session.is_current ? 'border-primary' : 'bg-muted/50'}>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between gap-4">
          <div className="flex gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
              {getDeviceIcon(session.device.device_type)}
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{deviceTypeLabel}</span>
                {session.is_current && (
                  <Badge variant="default">
                    {t('settings:sessions.currentSession')}
                  </Badge>
                )}
              </div>
              <div className="text-sm text-muted-foreground">
                {session.device.browser} &middot; {session.device.os}
              </div>
              <div className="flex items-center gap-1 text-sm text-muted-foreground">
                {getAuthProviderIcon(session.auth_provider)}
                <span>{authProviderLabel}</span>
              </div>
              <div className="flex items-center gap-4 text-sm text-muted-foreground">
                {locationDisplay && (
                  <span className="flex items-center gap-1">
                    <MapPin className="h-3 w-3" />
                    {locationDisplay}
                  </span>
                )}
                {session.ip_address && (
                  <span className="font-mono text-xs">{session.ip_address}</span>
                )}
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                {t('settings:sessions.lastActive')}{' '}
                {formatDistanceToNow(new Date(session.updated_time), { addSuffix: true })}
              </div>
            </div>
          </div>
          {!session.is_current && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRevoke(session.id)}
              disabled={isRevoking}
            >
              {isRevoking ? (
                <>
                  <Loader2 className="h-3 w-3 animate-spin mr-1" />
                  {t('settings:sessions.buttons.revoking')}
                </>
              ) : (
                t('settings:sessions.buttons.revokeSession')
              )}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
