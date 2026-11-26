import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

export function TextareaPropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      <div className="grid grid-cols-3 gap-4">
        <div className="space-y-2">
          <Label htmlFor="field-minLength">{t('fieldBuilder.properties.minLength')}</Label>
          <Input
            id="field-minLength"
            type="number"
            min={0}
            value={field.config.minLength ?? ''}
            onChange={(e) =>
              onChange({
                minLength: e.target.value ? parseInt(e.target.value) : undefined,
              })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="field-maxLength">{t('fieldBuilder.properties.maxLength')}</Label>
          <Input
            id="field-maxLength"
            type="number"
            min={0}
            value={field.config.maxLength ?? ''}
            onChange={(e) =>
              onChange({
                maxLength: e.target.value ? parseInt(e.target.value) : undefined,
              })
            }
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="field-rows">{t('fieldBuilder.properties.rows')}</Label>
          <Input
            id="field-rows"
            type="number"
            min={1}
            max={20}
            value={field.config.rows ?? 4}
            onChange={(e) =>
              onChange({
                rows: e.target.value ? parseInt(e.target.value) : 4,
              })
            }
          />
        </div>
      </div>
    </div>
  )
}
