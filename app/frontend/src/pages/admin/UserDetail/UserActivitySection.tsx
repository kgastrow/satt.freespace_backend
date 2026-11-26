import { useTranslation } from 'react-i18next'
import { format, formatDistanceToNow } from 'date-fns'
import {
  Download,
  Users,
  FileDown,
  LogIn,
  CheckCircle,
  XCircle,
  Globe,
  Monitor,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes } from '@/lib/utils'
import {
  useGetUserLoginHistoryQuery,
  type UserFullDetail,
  type DataExportInfo,
  type ImpersonationHistoryInfo,
  type LoginHistoryEntry,
} from '@/features/users/usersApi'

interface UserActivitySectionProps {
  user: UserFullDetail
}

function LoginHistoryCard({ entry }: { entry: LoginHistoryEntry }) {
  const { t } = useTranslation('admin')

  const getAuthMethodLabel = (method?: string | null) => {
    if (!method) return t('users.detail.loginHistory.email')
    switch (method.toLowerCase()) {
      case 'google':
        return 'Google'
      case 'microsoft':
        return 'Microsoft'
      case 'apple':
        return 'Apple'
      case 'github':
        return 'GitHub'
      default:
        return method
    }
  }

  return (
    <div className="p-3 rounded-lg border">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <div
            className={`p-2 rounded-full ${entry.success ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}
          >
            {entry.success ? (
              <CheckCircle className="h-4 w-4" />
            ) : (
              <XCircle className="h-4 w-4" />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium">
                {entry.success
                  ? t('users.detail.loginHistory.success')
                  : t('users.detail.loginHistory.failed')}
              </p>
              <Badge variant="outline" className="text-xs">
                {getAuthMethodLabel(entry.auth_method)}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {format(new Date(entry.created_time), 'PPp')}
            </p>
          </div>
        </div>
        <div className="text-right text-xs text-muted-foreground">
          {entry.city && entry.country && (
            <div className="flex items-center gap-1 justify-end">
              <Globe className="h-3 w-3" />
              <span>
                {entry.city}, {entry.country_code || entry.country}
              </span>
            </div>
          )}
          {entry.ip_address && (
            <div className="flex items-center gap-1 justify-end mt-1">
              <Monitor className="h-3 w-3" />
              <span>{entry.ip_address}</span>
            </div>
          )}
        </div>
      </div>
      {entry.failure_reason && (
        <p className="text-xs text-destructive mt-2">{entry.failure_reason}</p>
      )}
    </div>
  )
}

function DataExportCard({ dataExport }: { dataExport: DataExportInfo }) {
  const { t } = useTranslation('admin')

  const isExpired = dataExport.expires_at && new Date(dataExport.expires_at) < new Date()

  return (
    <div className="p-3 rounded-lg border">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <FileDown className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">
              {format(new Date(dataExport.created_time), 'PPp')}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <Badge
                variant={
                  dataExport.status === 'completed'
                    ? 'default'
                    : dataExport.status === 'failed'
                      ? 'destructive'
                      : 'secondary'
                }
                className="text-xs"
              >
                {t(`users.detail.exportStatus.${dataExport.status}`)}
              </Badge>
              {dataExport.file_size_bytes && (
                <span className="text-xs text-muted-foreground">
                  {formatBytes(dataExport.file_size_bytes)}
                </span>
              )}
              {isExpired && (
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  {t('users.detail.exportExpired')}
                </Badge>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Download className="h-4 w-4" />
          <span>{dataExport.download_count}</span>
        </div>
      </div>
    </div>
  )
}

function ImpersonationCard({ impersonation }: { impersonation: ImpersonationHistoryInfo }) {
  const { t } = useTranslation('admin')

  const duration = impersonation.ended_time
    ? formatDistanceToNow(new Date(impersonation.ended_time), {
        includeSeconds: true,
      }).replace(' ago', '')
    : t('users.detail.impersonationOngoing')

  return (
    <div className="p-3 rounded-lg border">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-3">
          <Users className="h-5 w-5 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium">
              {impersonation.impersonator_name || impersonation.impersonator_id}
            </p>
            <p className="text-xs text-muted-foreground">
              {format(new Date(impersonation.created_time), 'PPp')}
            </p>
          </div>
        </div>
        <div className="text-right">
          <Badge variant={impersonation.ended_time ? 'outline' : 'secondary'} className="text-xs">
            {impersonation.ended_time ? t('users.detail.impersonationEnded') : t('users.detail.impersonationOngoing')}
          </Badge>
          {impersonation.ended_time && (
            <p className="text-xs text-muted-foreground mt-1">{duration}</p>
          )}
        </div>
      </div>
    </div>
  )
}

export function UserActivitySection({ user }: UserActivitySectionProps) {
  const { t } = useTranslation('admin')
  const { data: loginHistory, isLoading: isLoadingLoginHistory } =
    useGetUserLoginHistoryQuery({ userId: user.id, limit: 10 })

  const hasActivity =
    user.data_exports.length > 0 ||
    user.impersonation_history.length > 0 ||
    (loginHistory?.items && loginHistory.items.length > 0)

  if (!hasActivity && !isLoadingLoginHistory) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <LogIn className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="text-lg font-medium">{t('users.detail.noActivity')}</h3>
          <p className="text-muted-foreground">{t('users.detail.noActivityDescription')}</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Login History */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <LogIn className="h-5 w-5" />
            {t('users.detail.sections.loginHistory')}
            {loginHistory?.total && loginHistory.total > 0 && (
              <Badge variant="secondary" className="ml-auto">
                {loginHistory.total}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoadingLoginHistory ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : loginHistory?.items && loginHistory.items.length > 0 ? (
            <div className="space-y-2">
              {loginHistory.items.slice(0, 5).map((entry) => (
                <LoginHistoryCard key={entry.id} entry={entry} />
              ))}
              {loginHistory.total > 5 && (
                <p className="text-sm text-muted-foreground text-center pt-2">
                  {t('users.detail.andMore', { count: loginHistory.total - 5 })}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              {t('users.detail.noLoginHistory')}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Data Exports */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Download className="h-5 w-5" />
            {t('users.detail.sections.dataExports')}
            {user.data_exports.length > 0 && (
              <Badge variant="secondary" className="ml-auto">
                {user.data_exports.length}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {user.data_exports.length > 0 ? (
            <div className="space-y-2">
              {user.data_exports.slice(0, 5).map((exp) => (
                <DataExportCard key={exp.id} dataExport={exp} />
              ))}
              {user.data_exports.length > 5 && (
                <p className="text-sm text-muted-foreground text-center pt-2">
                  {t('users.detail.andMore', { count: user.data_exports.length - 5 })}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              {t('users.detail.noDataExports')}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Impersonation History (full width if present) */}
      {user.impersonation_history.length > 0 && (
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Users className="h-5 w-5" />
              {t('users.detail.sections.impersonationHistory')}
              <Badge variant="secondary" className="ml-auto">
                {user.impersonation_history.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 md:grid-cols-2">
              {user.impersonation_history.map((imp) => (
                <ImpersonationCard key={imp.id} impersonation={imp} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
