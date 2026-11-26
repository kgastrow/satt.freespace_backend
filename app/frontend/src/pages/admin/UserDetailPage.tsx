import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, User, Monitor, Shield, HardDrive, Activity, MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useGetUserDetailQuery } from '@/features/users/usersApi'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import {
  UserDetailHeader,
  UserOverviewSection,
  UserSessionsSection,
  UserSecuritySection,
  UserFilesSection,
  UserActivitySection,
  UserFeedbackSection,
} from './UserDetail'

export function UserDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const currentUser = useCurrentUser()

  const isSuperAdmin = currentUser?.isAdmin ?? false

  const { data: user, isLoading, error, refetch } = useGetUserDetailQuery(id!)

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/admin/users')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('users.detail.backToList')}
        </Button>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center gap-6">
              <Skeleton className="h-20 w-20 rounded-full" />
              <div className="space-y-2">
                <Skeleton className="h-8 w-48" />
                <Skeleton className="h-4 w-64" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="space-y-6">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/admin/users')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('users.detail.backToList')}
        </Button>

        <Card>
          <CardContent className="py-12 text-center">
            <User className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-medium">{t('users.detail.notFound')}</h3>
            <p className="text-muted-foreground">{t('users.detail.notFoundDescription')}</p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => navigate('/admin/users')}
            >
              {t('users.detail.backToList')}
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/admin/users')}
      >
        <ArrowLeft className="mr-2 h-4 w-4" />
        {t('users.detail.backToList')}
      </Button>

      <UserDetailHeader user={user} />

      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList className="w-full overflow-x-auto justify-start">
          <TabsTrigger value="overview" className="gap-2">
            <User className="h-4 w-4" />
            {t('users.detail.tabs.overview')}
          </TabsTrigger>
          <TabsTrigger value="sessions" className="gap-2">
            <Monitor className="h-4 w-4" />
            {t('users.detail.tabs.sessions')}
            {user.sessions.length > 0 && (
              <span className="ml-1 text-xs bg-muted px-1.5 py-0.5 rounded-full">
                {user.sessions.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Shield className="h-4 w-4" />
            {t('users.detail.tabs.security')}
          </TabsTrigger>
          <TabsTrigger value="files" className="gap-2">
            <HardDrive className="h-4 w-4" />
            {t('users.detail.tabs.files')}
          </TabsTrigger>
          <TabsTrigger value="feedback" className="gap-2">
            <MessageSquare className="h-4 w-4" />
            {t('users.detail.tabs.feedback')}
            {user.feedback.length > 0 && (
              <span className="ml-1 text-xs bg-muted px-1.5 py-0.5 rounded-full">
                {user.feedback.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="activity" className="gap-2">
            <Activity className="h-4 w-4" />
            {t('users.detail.tabs.activity')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <UserOverviewSection user={user} isSuperAdmin={isSuperAdmin} />
        </TabsContent>

        <TabsContent value="sessions">
          <UserSessionsSection user={user} onRefresh={refetch} />
        </TabsContent>

        <TabsContent value="security">
          <UserSecuritySection user={user} isSuperAdmin={isSuperAdmin} />
        </TabsContent>

        <TabsContent value="files">
          <UserFilesSection user={user} />
        </TabsContent>

        <TabsContent value="feedback">
          <UserFeedbackSection user={user} />
        </TabsContent>

        <TabsContent value="activity">
          <UserActivitySection user={user} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
