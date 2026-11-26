import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { MessageSquare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import { useAppSelector } from '@/store/hooks'
import { FeedbackForm } from './FeedbackForm'

export function FeedbackWidget() {
  const { t } = useTranslation(['feedback'])
  const [isOpen, setIsOpen] = useState(false)
  const isEnabled = useFeatureFlag('feedback_widget')
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)

  if (!isEnabled || !isAuthenticated) {
    return null
  }

  return (
    <>
      <Button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 z-50 h-14 w-14 rounded-full shadow-lg"
        size="icon"
        aria-label={t('feedback:widget.openButton')}
      >
        <MessageSquare className="h-6 w-6" />
      </Button>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('feedback:widget.title')}</DialogTitle>
          </DialogHeader>
          <div className="mt-2">
            <FeedbackForm onSuccess={() => setIsOpen(false)} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
