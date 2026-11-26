import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Megaphone, Send } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Textarea } from '@/components/ui/textarea'
import { useSendAnnouncementMutation, useSendTestPushMutation } from '../eventsApi'
import { useSitePermissions } from '../permissions'
import { getServerError } from '../errors'
import type { Site } from '@/types/site'
import type { PushResponse } from '@/types/siteLive'

const SUFFIX_RE = /^[A-Za-z0-9_-]{6}$/

/** Result of a send: "accepted by FCM", never "delivered" (BF-69). */
function PushResult({ result, onClose }: { result: PushResponse; onClose: () => void }) {
  const { t } = useTranslation('sites')
  return (
    <>
      <Alert data-testid="push-result">
        <AlertTitle>
          {result.accepted_by_fcm ? t('push.result.accepted') : t('push.result.notAccepted')}
        </AlertTitle>
        <AlertDescription className="space-y-1">
          <p>{t(`push.result.target.${result.target}`)}</p>
          <p>{t('push.result.latency', { ms: result.latency_ms })}</p>
          <p className="text-muted-foreground">{t('push.result.note')}</p>
        </AlertDescription>
      </Alert>
      <DialogFooter>
        <Button onClick={onClose}>{t('push.close')}</Button>
      </DialogFooter>
    </>
  )
}

function TopicConfirmation({
  site,
  value,
  onChange,
}: {
  site: Site
  value: string
  onChange: (value: string) => void
}) {
  const { t } = useTranslation('sites')
  return (
    <div className="space-y-2">
      <Alert variant="destructive">
        <AlertDescription>{t('push.topicWarning', { topic: site.fcm_topic })}</AlertDescription>
      </Alert>
      <Label htmlFor="push-confirm-topic">{t('push.confirmLabel', { topic: site.fcm_topic })}</Label>
      <Input
        id="push-confirm-topic"
        value={value}
        autoComplete="off"
        onChange={(e) => onChange(e.target.value)}
        placeholder={site.fcm_topic}
      />
    </div>
  )
}

function TestPushForm({ site, onClose }: { site: Site; onClose: () => void }) {
  const { t } = useTranslation(['sites', 'backend'])
  const [target, setTarget] = useState<'device' | 'topic'>('device')
  const [suffix, setSuffix] = useState('')
  const [confirm, setConfirm] = useState('')
  const [send, { isLoading, error, data, reset }] = useSendTestPushMutation()

  const valid =
    target === 'device' ? SUFFIX_RE.test(suffix) : confirm === site.fcm_topic && site.fcm_topic !== ''

  if (data) return <PushResult result={data} onClose={onClose} />

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    send({
      siteId: site.id,
      data:
        target === 'device'
          ? { target, device_suffix: suffix }
          : { target, confirm_topic: confirm },
    })
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      )}
      <RadioGroup
        value={target}
        onValueChange={(v) => {
          setTarget(v as 'device' | 'topic')
          reset()
        }}
        aria-label={t('sites:push.test.target')}
      >
        <div className="flex items-center gap-2">
          <RadioGroupItem value="device" id="target-device" />
          <Label htmlFor="target-device">{t('sites:push.test.targetDevice')}</Label>
        </div>
        <div className="flex items-center gap-2">
          <RadioGroupItem value="topic" id="target-topic" />
          <Label htmlFor="target-topic">{t('sites:push.test.targetTopic')}</Label>
        </div>
      </RadioGroup>

      {target === 'device' ? (
        <div className="space-y-2">
          <Label htmlFor="push-suffix">{t('sites:push.test.suffixLabel')}</Label>
          <Input
            id="push-suffix"
            value={suffix}
            maxLength={6}
            autoComplete="off"
            onChange={(e) => setSuffix(e.target.value.trim())}
            className="font-mono"
            aria-invalid={suffix !== '' && !SUFFIX_RE.test(suffix)}
          />
          <p className="text-sm text-muted-foreground">{t('sites:push.test.suffixHelp')}</p>
        </div>
      ) : (
        <TopicConfirmation site={site} value={confirm} onChange={setConfirm} />
      )}

      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          {t('sites:actions.cancel')}
        </Button>
        <Button type="submit" disabled={!valid || isLoading}>
          {isLoading ? t('sites:push.sending') : t('sites:push.test.send')}
        </Button>
      </DialogFooter>
    </form>
  )
}

function AnnouncementForm({ site, onClose }: { site: Site; onClose: () => void }) {
  const { t } = useTranslation(['sites', 'backend'])
  const [title, setTitle] = useState('')
  const [message, setMessage] = useState('')
  const [confirm, setConfirm] = useState('')
  const [send, { isLoading, error, data }] = useSendAnnouncementMutation()

  const valid =
    message.trim() !== '' && confirm === site.fcm_topic && site.fcm_topic !== ''

  if (data) return <PushResult result={data} onClose={onClose} />

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!valid) return
    send({
      siteId: site.id,
      data: {
        message: message.trim(),
        ...(title.trim() ? { title: title.trim() } : {}),
        confirm_topic: confirm,
      },
    })
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      )}
      <div className="space-y-2">
        <Label htmlFor="announce-title">{t('sites:push.announce.titleLabel')}</Label>
        <Input
          id="announce-title"
          value={title}
          maxLength={65}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t('sites:push.announce.titlePlaceholder')}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="announce-message">{t('sites:push.announce.messageLabel')}</Label>
        <Textarea
          id="announce-message"
          value={message}
          maxLength={500}
          rows={4}
          onChange={(e) => setMessage(e.target.value)}
        />
        <p className="text-sm text-muted-foreground">
          {t('sites:push.announce.counter', { count: message.length, max: 500 })}
        </p>
      </div>
      <TopicConfirmation site={site} value={confirm} onChange={setConfirm} />
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          {t('sites:actions.cancel')}
        </Button>
        <Button type="submit" disabled={!valid || isLoading}>
          {isLoading ? t('sites:push.sending') : t('sites:push.announce.send')}
        </Button>
      </DialogFooter>
    </form>
  )
}

type Which = 'test' | 'announce' | null

/**
 * Buttons and dialogs of the site shell: test push (`site_push:test`) and
 * announcement (`site_push:announce`). Each button only exists for users who
 * hold its permission.
 */
export function SitePushActions({ site }: { site: Site }) {
  const { t } = useTranslation('sites')
  const { canTestPush, canAnnounce } = useSitePermissions()
  const [open, setOpen] = useState<Which>(null)
  const close = () => setOpen(null)

  if (!canTestPush && !canAnnounce) return null

  return (
    <>
      {canTestPush && (
        <Button variant="outline" onClick={() => setOpen('test')}>
          <Send className="mr-2 h-4 w-4" />
          {t('push.test.open')}
        </Button>
      )}
      {canAnnounce && (
        <Button variant="outline" onClick={() => setOpen('announce')}>
          <Megaphone className="mr-2 h-4 w-4" />
          {t('push.announce.open')}
        </Button>
      )}

      {/* Content mounts only while open, so each use starts with a clean form. */}
      <Dialog open={open === 'test'} onOpenChange={(o) => !o && close()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('push.test.title')}</DialogTitle>
            <DialogDescription>{t('push.test.description')}</DialogDescription>
          </DialogHeader>
          <TestPushForm site={site} onClose={close} />
        </DialogContent>
      </Dialog>
      <Dialog open={open === 'announce'} onOpenChange={(o) => !o && close()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('push.announce.title')}</DialogTitle>
            <DialogDescription>{t('push.announce.description')}</DialogDescription>
          </DialogHeader>
          <AnnouncementForm site={site} onClose={close} />
        </DialogContent>
      </Dialog>
    </>
  )
}
