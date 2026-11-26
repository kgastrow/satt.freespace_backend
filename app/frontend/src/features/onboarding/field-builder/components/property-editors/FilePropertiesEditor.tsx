import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
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

const FILE_SIZE_UNITS = [
  { value: 'KB', multiplier: 1024 },
  { value: 'MB', multiplier: 1024 * 1024 },
]

export function FilePropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  // Convert bytes to display value and unit
  const maxSizeBytes = field.config.maxSize || 5 * 1024 * 1024
  const isKB = maxSizeBytes < 1024 * 1024
  const displayUnit = isKB ? 'KB' : 'MB'
  const displayValue = isKB ? maxSizeBytes / 1024 : maxSizeBytes / (1024 * 1024)

  const handleSizeChange = (value: string, unit: string) => {
    const numValue = parseFloat(value) || 0
    const multiplier = unit === 'KB' ? 1024 : 1024 * 1024
    onChange({ maxSize: Math.round(numValue * multiplier) })
  }

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} showPlaceholder={false} />

      <div className="space-y-2">
        <Label htmlFor="field-accept">{t('fieldBuilder.properties.accept')}</Label>
        <Input
          id="field-accept"
          value={field.config.accept || ''}
          onChange={(e) => onChange({ accept: e.target.value || undefined })}
          placeholder="image/*,.pdf,.doc,.docx"
        />
        <p className="text-xs text-muted-foreground">
          {t('fieldBuilder.properties.acceptDescription')}
        </p>
      </div>

      <div className="space-y-2">
        <Label>{t('fieldBuilder.properties.maxSize')}</Label>
        <div className="flex gap-2">
          <Input
            type="number"
            min={1}
            value={displayValue}
            onChange={(e) => handleSizeChange(e.target.value, displayUnit)}
            className="flex-1"
          />
          <Select
            value={displayUnit}
            onValueChange={(unit) => handleSizeChange(displayValue.toString(), unit)}
          >
            <SelectTrigger className="w-20">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {FILE_SIZE_UNITS.map((unit) => (
                <SelectItem key={unit.value} value={unit.value}>
                  {unit.value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  )
}
