/**
 * WebPushCard — Web Push opt-in toggle for the notification-preferences page.
 *
 * This is the *device* half of push. The "Web push" switch in the channel list
 * is the *account* half — whether the app may push to this user at all. Both
 * have to be on, so the card says which one is missing rather than leaving a
 * greyed switch to explain itself: one switch on and one greyed off reads as a
 * broken toggle, not as a two-step opt-in.
 *
 * The iPhone case gets its own copy. iOS grants Web Push only to a site added
 * to the Home Screen, so in a Safari tab the API is absent and the generic
 * "your browser doesn't support this" line is both true and useless — the user
 * can fix it in two taps once told how.
 */
import { useTranslation } from 'react-i18next'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { useWebPush } from '@/hooks/useWebPush'
import { pushBlockReason } from '@/lib/webPush'

export interface WebPushCardProps {
  /**
   * The account-level `web_push_enabled` channel preference. When it is off,
   * subscribing this device would still deliver nothing, so the card says so.
   */
  channelEnabled?: boolean
}

export function WebPushCard({ channelEnabled = true }: WebPushCardProps) {
  const { t } = useTranslation('push')
  const { t: tSettings } = useTranslation('settings')
  const { state, isSupported, isSubscribed, isBusy, error, enable, disable } = useWebPush()

  const blocked = pushBlockReason(state)

  const helperText = (() => {
    switch (blocked) {
      case 'ios-needs-install':
        return t('iosInstall')
      case 'unsupported':
        return t('unsupported')
      case 'blocked':
        return t('blocked')
      default:
        break
    }
    // The account-level switch's label is INTERPOLATED, not copied. Spelling it
    // out here would quote a label that stops existing the moment
    // settings:notifications.channels.webPush.label is reworded, and would stay
    // in English regardless of the user's locale.
    if (isSubscribed && !channelEnabled)
      return t('channelOff', {
        channelLabel: tSettings('notifications.channels.webPush.label'),
      })
    if (isSubscribed) return t('enabled')
    return t('description')
  })()

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t('title')}</CardTitle>
        <CardDescription>{t('description')}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between rounded-lg border p-3">
          <div className="space-y-0.5">
            <p className="text-sm font-medium">{t('enable')}</p>
            <p className="text-muted-foreground text-xs">{helperText}</p>
            {/* The failure used to be invisible: a bare catch, and a switch
                that animated on and snapped back. 503 / 422 / offline / denied
                are different problems with different fixes, so say which. */}
            {error && (
              <p role="alert" className="text-destructive text-xs">
                {t(`error.${error === 'not-configured' ? 'notConfigured' : error}`)}
              </p>
            )}
          </div>
          <Switch
            checked={isSubscribed}
            disabled={!isSupported || state === 'blocked' || isBusy}
            onCheckedChange={(checked) => {
              if (checked) {
                void enable()
              } else {
                void disable()
              }
            }}
            aria-label={t('enable')}
          />
        </div>
      </CardContent>
    </Card>
  )
}
