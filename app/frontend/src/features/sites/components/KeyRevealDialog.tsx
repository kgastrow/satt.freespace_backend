import { useTranslation } from 'react-i18next'
import { Copy } from 'lucide-react'
import { toast } from '@/lib/toast'
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

interface KeyRevealDialogProps {
  /** The plaintext key; the dialog is open while this is non-null. */
  secret: string | null
  onClose: () => void
  title: string
  description: string
}

/** "Shown once" dialog for a freshly created ingest or app key. */
export function KeyRevealDialog({ secret, onClose, title, description }: KeyRevealDialogProps) {
  const { t } = useTranslation('sites')

  const copy = async () => {
    if (!secret) return
    try {
      await navigator.clipboard.writeText(secret)
      toast.success(t('keys.reveal.copied'))
    } catch {
      toast.error(t('keys.reveal.copyFailed'))
    }
  }

  return (
    <Dialog open={secret !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <Alert>
            <AlertTitle>{t('keys.reveal.warningTitle')}</AlertTitle>
            <AlertDescription>{t('keys.reveal.warning')}</AlertDescription>
          </Alert>
          <div className="flex items-center gap-2">
            <Input
              readOnly
              value={secret ?? ''}
              aria-label={t('keys.reveal.keyLabel')}
              className="font-mono text-sm"
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label={t('keys.reveal.copy')}
              onClick={copy}
            >
              <Copy className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={onClose}>{t('keys.reveal.close')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
