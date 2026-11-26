import { useTranslation } from 'react-i18next'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

const DATE_FORMATS = [
  { value: 'yyyy-MM-dd', label: 'YYYY-MM-DD (2024-01-15)' },
  { value: 'MM/dd/yyyy', label: 'MM/DD/YYYY (01/15/2024)' },
  { value: 'dd/MM/yyyy', label: 'DD/MM/YYYY (15/01/2024)' },
  { value: 'dd.MM.yyyy', label: 'DD.MM.YYYY (15.01.2024)' },
]

export function DatePropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>{t('fieldBuilder.properties.minDate')}</Label>
          <DatePicker
            value={field.config.minDate}
            onChange={(value) => onChange({ minDate: value })}
            placeholder={t('fieldBuilder.properties.minDate')}
            maxDate={field.config.maxDate ? new Date(field.config.maxDate) : undefined}
          />
        </div>
        <div className="space-y-2">
          <Label>{t('fieldBuilder.properties.maxDate')}</Label>
          <DatePicker
            value={field.config.maxDate}
            onChange={(value) => onChange({ maxDate: value })}
            placeholder={t('fieldBuilder.properties.maxDate')}
            minDate={field.config.minDate ? new Date(field.config.minDate) : undefined}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="field-dateFormat">{t('fieldBuilder.properties.dateFormat')}</Label>
        <Select
          value={field.config.dateFormat || 'yyyy-MM-dd'}
          onValueChange={(value) => onChange({ dateFormat: value })}
        >
          <SelectTrigger id="field-dateFormat">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DATE_FORMATS.map((format) => (
              <SelectItem key={format.value} value={format.value}>
                {format.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
