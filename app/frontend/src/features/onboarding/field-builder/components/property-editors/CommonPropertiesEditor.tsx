import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { PropertyEditorProps } from '../../types'

interface CommonPropertiesEditorProps extends PropertyEditorProps {
  showPlaceholder?: boolean
}

export function CommonPropertiesEditor({
  field,
  onChange,
  showPlaceholder = true,
}: CommonPropertiesEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="field-label">{t('fieldBuilder.properties.label')}</Label>
        <Input
          id="field-label"
          value={field.config.label || ''}
          onChange={(e) => onChange({ label: e.target.value })}
          placeholder={t('fieldBuilder.properties.labelDescription')}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="field-description">{t('fieldBuilder.properties.description')}</Label>
        <Textarea
          id="field-description"
          value={field.config.description || ''}
          onChange={(e) => onChange({ description: e.target.value })}
          placeholder={t('fieldBuilder.properties.descriptionDescription')}
          rows={2}
        />
      </div>

      {showPlaceholder && (
        <div className="space-y-2">
          <Label htmlFor="field-placeholder">{t('fieldBuilder.properties.placeholder')}</Label>
          <Input
            id="field-placeholder"
            value={field.config.placeholder || ''}
            onChange={(e) => onChange({ placeholder: e.target.value })}
            placeholder={t('fieldBuilder.properties.placeholderDescription')}
          />
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>{t('fieldBuilder.properties.required')}</Label>
          <p className="text-xs text-muted-foreground">
            {t('fieldBuilder.properties.requiredDescription')}
          </p>
        </div>
        <Switch
          checked={field.config.required !== false}
          onCheckedChange={(checked) => onChange({ required: checked })}
        />
      </div>
    </div>
  )
}
