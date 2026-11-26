import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/hooks/useAuth'

export function HomePage() {
  const { t } = useTranslation()
  const { user, logout, isLoggingOut } = useAuth()

  return (
    <div className="container mx-auto flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{t('home.welcome', { appName: t('app.name') })}</CardTitle>
          <CardDescription>
            {t('home.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {user && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                {t('home.loggedInAs')}{' '}
                <span className="font-medium text-foreground">
                  {user.first_name} {user.last_name}
                </span>
              </p>
              <p className="text-sm text-muted-foreground">{user.email}</p>
            </div>
          )}
          <Button
            onClick={logout}
            variant="outline"
            className="w-full"
            disabled={isLoggingOut}
          >
            {isLoggingOut ? t('navigation.signingOut') : t('navigation.signOut')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
