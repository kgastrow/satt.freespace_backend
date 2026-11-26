import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

export function CheckboxPropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} showPlaceholder={false} />

      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <Label>{t('fieldBuilder.properties.defaultChecked')}</Label>
          <p className="text-xs text-muted-foreground">
            {t('fieldBuilder.properties.defaultCheckedDescription')}
          </p>
        </div>
        <Switch
          checked={field.config.defaultChecked || false}
          onCheckedChange={(checked) => onChange({ defaultChecked: checked })}
        />
      </div>
    </div>
  )
}
