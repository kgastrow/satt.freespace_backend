import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

export function NumberPropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="field-min">{t('fieldBuilder.properties.min')}</Label>
          <Input
            id="field-min"
            type="number"
            value={field.config.min ?? ''}
            onChange={(e) =>
              onChange({
                min: e.target.value ? parseFloat(e.target.value) : undefined,
              })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="field-max">{t('fieldBuilder.properties.max')}</Label>
          <Input
            id="field-max"
            type="number"
            value={field.config.max ?? ''}
            onChange={(e) =>
              onChange({
                max: e.target.value ? parseFloat(e.target.value) : undefined,
              })
            }
          />
        </div>
      </div>
    </div>
  )
}
