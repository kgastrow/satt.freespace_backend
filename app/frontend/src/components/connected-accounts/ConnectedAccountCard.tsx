import { useTranslation } from 'react-i18next'
import { Mail, Unlink } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { UserIdentityResponse } from '@/types/identity'

interface ConnectedAccountCardProps {
  identity: UserIdentityResponse
  onUnlink: (identity: UserIdentityResponse) => void
  isUnlinking?: boolean
}

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
    </svg>
  )
}

function ProviderIcon({ provider, className }: { provider: string; className?: string }) {
  switch (provider.toLowerCase()) {
    case 'google':
      return <GoogleIcon className={className} />
    case 'email':
    default:
      return <Mail className={className} />
  }
}

export function ConnectedAccountCard({
  identity,
  onUnlink,
  isUnlinking = false,
}: ConnectedAccountCardProps) {
  const { t, i18n } = useTranslation(['settings'])

  const providerName = t(`settings:connectedAccounts.providers.${identity.provider}`, {
    defaultValue: identity.provider.charAt(0).toUpperCase() + identity.provider.slice(1),
  })

  const linkedDate = new Date(identity.linked_at).toLocaleDateString(i18n.language, {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })

  return (
    <Card>
      <CardContent className="flex items-center gap-4 p-4">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <ProviderIcon provider={identity.provider} className="h-6 w-6" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium">{providerName}</span>
            {identity.is_primary && (
              <Badge variant="secondary">{t('settings:connectedAccounts.primary')}</Badge>
            )}
          </div>
          {identity.provider_email && (
            <p className="text-sm text-muted-foreground truncate">{identity.provider_email}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {t('settings:connectedAccounts.linkedOn', { date: linkedDate })}
          </p>
        </div>

        <div>
          {identity.can_unlink ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onUnlink(identity)}
              disabled={isUnlinking}
            >
              <Unlink className="h-4 w-4 mr-2" />
              {t('settings:connectedAccounts.unlink')}
            </Button>
          ) : (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="outline" size="sm" disabled>
                    <Unlink className="h-4 w-4 mr-2" />
                    {t('settings:connectedAccounts.unlink')}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{t('settings:connectedAccounts.cannotUnlink')}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
