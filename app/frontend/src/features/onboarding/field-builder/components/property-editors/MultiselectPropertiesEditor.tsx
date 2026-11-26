import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps, SelectOption } from '../../types'

export function MultiselectPropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  // Normalize options to SelectOption format
  const options: SelectOption[] = (field.config.options || []).map((opt) =>
    typeof opt === 'string' ? { value: opt, label: opt } : opt
  )

  const handleOptionChange = useCallback(
    (index: number, updates: Partial<SelectOption>) => {
      const newOptions = options.map((opt, i) =>
        i === index ? { ...opt, ...updates } : opt
      )
      onChange({ options: newOptions })
    },
    [options, onChange]
  )

  const handleAddOption = useCallback(() => {
    const newOptions = [...options, { value: '', label: '' }]
    onChange({ options: newOptions })
  }, [options, onChange])

  const handleRemoveOption = useCallback(
    (index: number) => {
      const newOptions = options.filter((_, i) => i !== index)
      onChange({ options: newOptions })
    },
    [options, onChange]
  )

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      <div className="space-y-2">
        <Label htmlFor="field-maxSelections">{t('fieldBuilder.properties.maxSelections')}</Label>
        <Input
          id="field-maxSelections"
          type="number"
          min={1}
          value={field.config.maxSelections ?? ''}
          onChange={(e) =>
            onChange({
              maxSelections: e.target.value ? parseInt(e.target.value) : undefined,
            })
          }
          placeholder={t('fieldBuilder.properties.maxSelectionsPlaceholder')}
        />
        <p className="text-xs text-muted-foreground">
          {t('fieldBuilder.properties.maxSelectionsDescription')}
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>{t('fieldBuilder.properties.options')}</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleAddOption}
          >
            <Plus className="h-4 w-4 mr-1" />
            {t('fieldBuilder.properties.addOption')}
          </Button>
        </div>

        {options.length === 0 ? (
          <p className="text-sm text-muted-foreground py-4 text-center border rounded-lg border-dashed">
            {t('fieldBuilder.properties.noOptions')}
          </p>
        ) : (
          <div className="space-y-2">
            {options.map((option, index) => (
              <div key={index} className="flex items-center gap-2">
                <GripVertical className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                <Input
                  value={option.value}
                  onChange={(e) => handleOptionChange(index, { value: e.target.value })}
                  placeholder={t('fieldBuilder.properties.optionValue')}
                  className="flex-1"
                />
                <Input
                  value={option.label}
                  onChange={(e) => handleOptionChange(index, { label: e.target.value })}
                  placeholder={t('fieldBuilder.properties.optionLabel')}
                  className="flex-1"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive flex-shrink-0"
                  onClick={() => handleRemoveOption(index)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
