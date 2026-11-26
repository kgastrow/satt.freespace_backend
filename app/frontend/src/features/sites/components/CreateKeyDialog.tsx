import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { DatePicker } from '@/components/ui/date-picker'
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
import { Alert, AlertDescription } from '@/components/ui/alert'

export interface CreateKeyValues {
  name: string
  /** ISO datetime (end of the chosen day) or undefined */
  expires_at?: string
}

interface CreateKeyDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  /** App keys have no expiry */
  withExpiry?: boolean
  isLoading: boolean
  /** Server error text, shown inside the dialog */
  error?: string | null
  onSubmit: (values: CreateKeyValues) => void
}

/** Shared create form for ingest keys (name + optional expiry) and app keys (name). */
export function CreateKeyDialog({ open, onOpenChange, ...rest }: CreateKeyDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* The content only mounts while open, so the form state resets each time. */}
      <DialogContent>
        <CreateKeyForm onOpenChange={onOpenChange} {...rest} />
      </DialogContent>
    </Dialog>
  )
}

function CreateKeyForm({
  onOpenChange,
  title,
  description,
  withExpiry = false,
  isLoading,
  error,
  onSubmit,
}: Omit<CreateKeyDialogProps, 'open'>) {
  const { t } = useTranslation('sites')
  const [name, setName] = useState('')
  const [expires, setExpires] = useState<string | undefined>(undefined)
  const [touched, setTouched] = useState(false)

  const nameError = touched && name.trim() === ''

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (name.trim() === '') return
    let expires_at: string | undefined
    if (withExpiry && expires) {
      const date = new Date(expires)
      date.setHours(23, 59, 59, 999)
      expires_at = date.toISOString()
    }
    onSubmit({ name: name.trim(), expires_at })
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
      </DialogHeader>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="space-y-2">
          <Label htmlFor="key-name">{t('keys.fields.name')}</Label>
          <Input
            id="key-name"
            value={name}
            maxLength={255}
            onChange={(e) => setName(e.target.value)}
            aria-invalid={nameError}
            placeholder={t('keys.fields.namePlaceholder')}
          />
          {nameError && (
            <p role="alert" className="text-sm text-destructive">
              {t('validation.required')}
            </p>
          )}
        </div>
        {withExpiry && (
          <div className="space-y-2">
            <Label>{t('keys.fields.expires')}</Label>
            <DatePicker
              value={expires}
              onChange={setExpires}
              placeholder={t('keys.fields.expiresPlaceholder')}
              minDate={new Date()}
              dateFormat="PP"
            />
            <p className="text-sm text-muted-foreground">{t('keys.fields.expiresHelp')}</p>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('actions.cancel')}
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? t('keys.creating') : t('keys.create')}
          </Button>
        </DialogFooter>
      </form>
    </>
  )
}
