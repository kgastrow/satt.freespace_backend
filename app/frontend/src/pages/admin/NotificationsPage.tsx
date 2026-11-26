import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Send, Users, FileText, FolderOpen, Settings, Mail, MessageSquare, Phone, Bell } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CardSkeleton } from '@/components/skeletons'
import {
  useGetNotificationsQuery,
  type Notification,
  type NotificationChannel,
  type NotificationStatus,
} from '@/features/notifications/notificationsApi'
import { usePermission } from '@/hooks/usePermission'

const statusColors: Record<NotificationStatus, string> = {
  pending: 'bg-yellow-500/10 text-yellow-600 dark:bg-yellow-500/20 dark:text-yellow-400',
  queued: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
  sent: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
  delivered: 'bg-green-600/10 text-green-700 dark:bg-green-600/20 dark:text-green-300',
  failed: 'bg-red-500/10 text-red-600 dark:bg-red-500/20 dark:text-red-400',
}

const channelIcons: Record<NotificationChannel, React.ReactNode> = {
  email: <Mail className="h-4 w-4" />,
  sms: <Phone className="h-4 w-4" />,
  whatsapp: <MessageSquare className="h-4 w-4" />,
  in_app: <Bell className="h-4 w-4" />,
}

export function NotificationsPage() {
  const { t } = useTranslation('admin')
  const { canWrite } = usePermission('notifications')
  const [page, setPage] = useState(1)
  const [channelFilter, setChannelFilter] = useState<NotificationChannel | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<NotificationStatus | 'all'>('all')
  const pageSize = 10

  const { data, isLoading } = useGetNotificationsQuery({
    channel: channelFilter === 'all' ? undefined : channelFilter,
    status: statusFilter === 'all' ? undefined : statusFilter,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  // Calculate stats (in real app, these would come from a dedicated stats endpoint)
  const stats = {
    sentToday: data?.items.filter((n) => n.status === 'sent' || n.status === 'delivered').length || 0,
    deliveryRate: 98.5,
    failedToday: data?.items.filter((n) => n.status === 'failed').length || 0,
    pendingQueue: data?.items.filter((n) => n.status === 'pending' || n.status === 'queued').length || 0,
  }

  const columns: Column<Notification>[] = [
    {
      key: 'channel',
      header: t('notifications.table.channel'),
      cell: (notification) => {
        const channel = notification.channel as NotificationChannel
        return (
          <div className="flex items-center gap-2">
            {channelIcons[channel] || null}
            <span className="capitalize">{notification.channel}</span>
          </div>
        )
      },
    },
    {
      key: 'recipient',
      header: t('notifications.table.recipient'),
      cell: (notification) => (
        <span className="truncate max-w-[200px] block">{notification.recipient}</span>
      ),
    },
    {
      key: 'status',
      header: t('notifications.table.status'),
      cell: (notification) => {
        const status = notification.status as NotificationStatus
        const colorClass = statusColors[status] || ''
        return <Badge className={colorClass}>{notification.status}</Badge>
      },
    },
    {
      key: 'created_time',
      header: t('notifications.table.sentTime'),
      cell: (notification) => {
        if (!notification.created_time) return <span className="text-muted-foreground">-</span>
        const date = new Date(notification.created_time)
        return (
          <span className="text-muted-foreground">
            {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        )
      },
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader title={t('notifications.pageTitle')} description={t('notifications.pageDescription')}>
        {canWrite && (
          <div className="flex gap-2">
            <Button asChild>
              <Link to="/admin/notifications/send">
                <Send className="h-4 w-4 mr-2" />
                {t('notifications.sendButton')}
              </Link>
            </Button>
          </div>
        )}
      </PageHeader>

      {/* Stats Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} variant="stats" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{t('notifications.stats.sentToday')}</CardTitle>
              <Mail className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.sentToday.toLocaleString()}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{t('notifications.stats.deliveryRate')}</CardTitle>
              <Badge variant="secondary">{stats.deliveryRate}%</Badge>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-green-600 dark:text-green-400">{stats.deliveryRate}%</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{t('notifications.stats.failedToday')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-red-600 dark:text-red-400">{stats.failedToday}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{t('notifications.stats.pendingQueue')}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.pendingQueue}</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Quick Actions */}
      {canWrite && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Button variant="outline" asChild className="h-auto py-4 flex-col gap-2">
            <Link to="/admin/notifications/bulk">
              <Users className="h-6 w-6" />
              <span>{t('notifications.quickActions.bulkCampaign')}</span>
            </Link>
          </Button>
          <Button variant="outline" asChild className="h-auto py-4 flex-col gap-2">
            <Link to="/admin/notifications/templates">
              <FileText className="h-6 w-6" />
              <span>{t('notifications.quickActions.templates')}</span>
            </Link>
          </Button>
          <Button variant="outline" asChild className="h-auto py-4 flex-col gap-2">
            <Link to="/admin/notifications/categories">
              <FolderOpen className="h-6 w-6" />
              <span>{t('notifications.quickActions.categories')}</span>
            </Link>
          </Button>
          <Button variant="outline" asChild className="h-auto py-4 flex-col gap-2">
            <Link to="/admin/notifications/settings">
              <Settings className="h-6 w-6" />
              <span>{t('notifications.quickActions.settings')}</span>
            </Link>
          </Button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <Tabs value={channelFilter} onValueChange={(v) => setChannelFilter(v as NotificationChannel | 'all')}>
          <TabsList>
            <TabsTrigger value="all">{t('notifications.filters.allChannels')}</TabsTrigger>
            <TabsTrigger value="email">{t('notifications.filters.email')}</TabsTrigger>
            <TabsTrigger value="sms">{t('notifications.filters.sms')}</TabsTrigger>
            <TabsTrigger value="whatsapp">{t('notifications.filters.whatsapp')}</TabsTrigger>
            <TabsTrigger value="in_app">{t('notifications.filters.inApp')}</TabsTrigger>
          </TabsList>
        </Tabs>

        <Tabs value={statusFilter} onValueChange={(v) => setStatusFilter(v as NotificationStatus | 'all')}>
          <TabsList>
            <TabsTrigger value="all">{t('notifications.filters.allStatus')}</TabsTrigger>
            <TabsTrigger value="sent">{t('notifications.filters.sent')}</TabsTrigger>
            <TabsTrigger value="queued">{t('notifications.filters.queued')}</TabsTrigger>
            <TabsTrigger value="delivered">{t('notifications.filters.delivered')}</TabsTrigger>
            <TabsTrigger value="failed">{t('notifications.filters.failed')}</TabsTrigger>
            <TabsTrigger value="pending">{t('notifications.filters.pending')}</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Recent Notifications Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('notifications.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />
    </div>
  )
}
