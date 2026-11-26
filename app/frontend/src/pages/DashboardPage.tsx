import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAppSelector } from '@/store/hooks'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { OnboardingProgressCard } from '@/features/onboarding/OnboardingProgressCard'

export function DashboardPage() {
  const { t } = useTranslation('dashboard')
  const { user } = useAppSelector((state) => state.auth)

  const isAdmin = user?.is_admin || user?.roles?.includes('user_admin')
  const isSuperAdmin = user?.roles?.includes('super_admin')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t('welcome', { name: user?.first_name || 'User' })}
        </h1>
        <p className="text-muted-foreground">
          {t('subtitle')}
        </p>
      </div>

      <OnboardingProgressCard />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {isAdmin && (
          <>
            <Card>
              <CardHeader>
                <CardTitle>{t('cards.userManagement.title')}</CardTitle>
                <CardDescription>
                  {t('cards.userManagement.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/admin/users">{t('cards.userManagement.action')}</Link>
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t('cards.roleManagement.title')}</CardTitle>
                <CardDescription>
                  {t('cards.roleManagement.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/admin/roles">{t('cards.roleManagement.action')}</Link>
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t('cards.auditLogs.title')}</CardTitle>
                <CardDescription>
                  {t('cards.auditLogs.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/admin/audit-logs">{t('cards.auditLogs.action')}</Link>
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>{t('cards.systemMetrics.title')}</CardTitle>
                <CardDescription>
                  {t('cards.systemMetrics.description')}
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild variant="outline">
                  <Link to="/platform-admin/metrics">{t('cards.systemMetrics.action')}</Link>
                </Button>
              </CardContent>
            </Card>
          </>
        )}

        {isSuperAdmin && (
          <Card>
            <CardHeader>
              <CardTitle>{t('cards.organizations.title')}</CardTitle>
              <CardDescription>
                {t('cards.organizations.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link to="/admin/organizations">{t('cards.organizations.action')}</Link>
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
