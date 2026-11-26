import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { getAllFieldTypes } from '../fieldTypeRegistry'
import type { FieldType } from '../types'

interface FieldTypeSelectorProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (type: FieldType) => void
}

export function FieldTypeSelector({
  open,
  onOpenChange,
  onSelect,
}: FieldTypeSelectorProps) {
  const { t } = useTranslation('admin')
  const fieldTypes = getAllFieldTypes()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t('fieldBuilder.addField')}</DialogTitle>
          <DialogDescription>
            {t('fieldBuilder.selectFieldType')}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {fieldTypes.map((fieldType) => {
            const Icon = fieldType.icon
            return (
              <button
                key={fieldType.type}
                type="button"
                className={cn(
                  'flex flex-col items-start gap-2 p-4 rounded-lg border bg-card text-left',
                  'hover:border-primary hover:bg-accent transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2'
                )}
                onClick={() => onSelect(fieldType.type)}
              >
                <div className="flex items-center gap-2">
                  <Icon className="h-5 w-5 text-primary" />
                  <span className="font-medium">{t(fieldType.label)}</span>
                </div>
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {t(fieldType.description)}
                </p>
              </button>
            )
          })}
        </div>
      </DialogContent>
    </Dialog>
  )
}
