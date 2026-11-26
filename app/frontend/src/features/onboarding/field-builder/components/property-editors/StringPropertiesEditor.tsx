import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

export function StringPropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')
  const fieldType = field.config.type || 'string'

  // Email and URL don't need pattern/length validation - handled by Zod
  const showAdvancedValidation = fieldType === 'string'

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      {showAdvancedValidation && (
        <>
          <div className="grid grid-cols-2 gap-4">
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
          </div>

          <div className="space-y-2">
            <Label htmlFor="field-pattern">{t('fieldBuilder.properties.pattern')}</Label>
            <Input
              id="field-pattern"
              value={field.config.pattern || ''}
              onChange={(e) => onChange({ pattern: e.target.value || undefined })}
              placeholder="^[A-Z].*"
            />
            <p className="text-xs text-muted-foreground">
              {t('fieldBuilder.properties.patternDescription')}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
