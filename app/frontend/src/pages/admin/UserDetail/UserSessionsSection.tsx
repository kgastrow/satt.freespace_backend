import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { format, formatDistanceToNow } from 'date-fns'
import {
  Monitor,
  Smartphone,
  Globe,
  Clock,
  MapPin,
  XCircle,
  Shield,
  Laptop,
  RefreshCw,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { toast } from '@/lib/toast'
import {
  useInvalidateUserSessionMutation,
  type UserFullDetail,
} from '@/features/users/usersApi'
import { usePermission } from '@/hooks/usePermission'

interface UserSessionsSectionProps {
  user: UserFullDetail
  onRefresh?: () => void
}

function getDeviceIcon(userAgent?: string | null) {
  if (!userAgent) return Monitor
  const ua = userAgent.toLowerCase()
  if (ua.includes('mobile') || ua.includes('android') || ua.includes('iphone')) {
    return Smartphone
  }
  if (ua.includes('tablet') || ua.includes('ipad')) {
    return Laptop
  }
  return Monitor
}

function parseUserAgent(userAgent?: string | null) {
  if (!userAgent) return { browser: 'Unknown', os: 'Unknown' }

  let browser = 'Unknown'
  let os = 'Unknown'

  // Simple browser detection
  if (userAgent.includes('Firefox')) browser = 'Firefox'
  else if (userAgent.includes('Chrome') && !userAgent.includes('Edg')) browser = 'Chrome'
  else if (userAgent.includes('Safari') && !userAgent.includes('Chrome')) browser = 'Safari'
  else if (userAgent.includes('Edg')) browser = 'Edge'

  // Simple OS detection
  if (userAgent.includes('Windows')) os = 'Windows'
  else if (userAgent.includes('Mac OS')) os = 'macOS'
  else if (userAgent.includes('Linux')) os = 'Linux'
  else if (userAgent.includes('Android')) os = 'Android'
  else if (userAgent.includes('iOS') || userAgent.includes('iPhone')) os = 'iOS'

  return { browser, os }
}

function maskIpAddress(ip?: string | null) {
  if (!ip) return '-'
  const parts = ip.split('.')
  if (parts.length === 4) {
    return `${parts[0]}.${parts[1]}.***.***`
  }
  // IPv6 or other format
  return ip.substring(0, Math.min(ip.length, 10)) + '...'
}

export function UserSessionsSection({ user, onRefresh }: UserSessionsSectionProps) {
  const { t } = useTranslation('admin')
  const { canWrite } = usePermission('users')
  const [invalidatingSessionId, setInvalidatingSessionId] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [invalidateSession, { isLoading }] = useInvalidateUserSessionMutation()

  const handleRefresh = async () => {
    if (!onRefresh) return
    setIsRefreshing(true)
    try {
      await onRefresh()
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleInvalidateSession = async () => {
    if (!invalidatingSessionId) return
    try {
      await invalidateSession({
        userId: user.id,
        sessionId: invalidatingSessionId,
      }).unwrap()
      toast.success(t('users.detail.toast.sessionInvalidated'))
      setInvalidatingSessionId(null)
    } catch {
      toast.error(t('users.detail.toast.sessionInvalidateError'))
    }
  }

  const formatSessionDate = (dateString: string) => {
    const date = new Date(dateString)
    return {
      absolute: format(date, 'PPp'),
      relative: formatDistanceToNow(date, { addSuffix: true }),
    }
  }

  if (user.sessions.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <Shield className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium">{t('users.detail.noSessions')}</h3>
          <p className="text-muted-foreground">{t('users.detail.noSessionsDescription')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <div className="flex justify-end mb-4">
        {onRefresh && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${isRefreshing ? 'animate-spin' : ''}`} />
            {t('common.refresh')}
          </Button>
        )}
      </div>
      <div className="space-y-4">
        {user.sessions.map((session) => {
          const DeviceIcon = getDeviceIcon(session.user_agent)
          const { browser, os } = parseUserAgent(session.user_agent)
          const updatedDate = session.updated_time
            ? formatSessionDate(session.updated_time)
            : formatSessionDate(session.created_time)

          return (
            <Card key={session.id} className={session.is_current ? 'border-primary' : ''}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-4">
                    <div className="p-2 rounded-lg bg-muted">
                      <DeviceIcon className="h-6 w-6" />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{browser}</span>
                        <span className="text-muted-foreground">on {os}</span>
                        {session.is_current && (
                          <Badge variant="default">{t('users.detail.currentSession')}</Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-4 text-sm text-muted-foreground">
                        {session.auth_provider && (
                          <div className="flex items-center gap-1">
                            <Shield className="h-3.5 w-3.5" />
                            <span>{session.auth_provider}</span>
                          </div>
                        )}
                        <div className="flex items-center gap-1">
                          <Globe className="h-3.5 w-3.5" />
                          <span>{maskIpAddress(session.ip_address)}</span>
                        </div>
                        {(session.city || session.country) && (
                          <div className="flex items-center gap-1">
                            <MapPin className="h-3.5 w-3.5" />
                            <span>
                              {[session.city, session.country].filter(Boolean).join(', ')}
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-1 text-sm text-muted-foreground">
                        <Clock className="h-3.5 w-3.5" />
                        <span title={updatedDate.absolute}>
                          {t('users.detail.lastActive')}: {updatedDate.relative}
                        </span>
                      </div>
                    </div>
                  </div>

                  {canWrite && !session.is_current && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setInvalidatingSessionId(session.id)}
                    >
                      <XCircle className="h-4 w-4 mr-2" />
                      {t('users.detail.invalidateSession')}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <ConfirmDialog
        open={!!invalidatingSessionId}
        onOpenChange={() => setInvalidatingSessionId(null)}
        onConfirm={handleInvalidateSession}
        title={t('users.detail.invalidateSessionDialog.title')}
        description={t('users.detail.invalidateSessionDialog.description')}
        confirmLabel={t('users.detail.invalidateSession')}
        cancelLabel={t('common.cancel')}
        isLoading={isLoading}
        variant="destructive"
      />
    </>
  )
}
