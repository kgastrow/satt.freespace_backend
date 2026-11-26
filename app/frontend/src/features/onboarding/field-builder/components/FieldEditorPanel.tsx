import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useFieldBuilder } from '../FieldBuilderContext'
import { getFieldType } from '../fieldTypeRegistry'
import { isValidFieldName, isFieldNameUnique } from '../utils'
import { CommonPropertiesEditor } from './property-editors/CommonPropertiesEditor'
import { StringPropertiesEditor } from './property-editors/StringPropertiesEditor'
import { NumberPropertiesEditor } from './property-editors/NumberPropertiesEditor'
import { TextareaPropertiesEditor } from './property-editors/TextareaPropertiesEditor'
import { SelectPropertiesEditor } from './property-editors/SelectPropertiesEditor'
import { FilePropertiesEditor } from './property-editors/FilePropertiesEditor'
import { CheckboxPropertiesEditor } from './property-editors/CheckboxPropertiesEditor'
import { DatePropertiesEditor } from './property-editors/DatePropertiesEditor'
import { PhonePropertiesEditor } from './property-editors/PhonePropertiesEditor'
import { RadioPropertiesEditor } from './property-editors/RadioPropertiesEditor'
import { MultiselectPropertiesEditor } from './property-editors/MultiselectPropertiesEditor'
import type { FieldConfig } from '../types'

export function FieldEditorPanel() {
  const { t } = useTranslation('admin')
  const { state, selectedField, actions } = useFieldBuilder()

  const handleNameChange = useCallback(
    (name: string) => {
      if (selectedField) {
        actions.updateField(selectedField.id, { name })
      }
    },
    [selectedField, actions]
  )

  const handleConfigChange = useCallback(
    (updates: Partial<FieldConfig>) => {
      if (selectedField) {
        actions.updateFieldConfig(selectedField.id, updates)
      }
    },
    [selectedField, actions]
  )

  if (!selectedField) {
    return (
      <Card>
        <CardContent className="py-8">
          <p className="text-center text-muted-foreground">
            {t('fieldBuilder.selectField')}
          </p>
        </CardContent>
      </Card>
    )
  }

  const fieldType = getFieldType(selectedField.config.type || 'string')
  const nameError = !isValidFieldName(selectedField.name)
    ? t('fieldBuilder.validation.invalidFieldName')
    : !isFieldNameUnique(selectedField.name, state.fields, selectedField.id)
      ? t('fieldBuilder.validation.duplicateFieldName')
      : null

  // Render the appropriate property editor based on field type
  const renderPropertyEditor = () => {
    const type = selectedField.config.type || 'string'

    switch (type) {
      case 'string':
      case 'email':
      case 'url':
        return (
          <StringPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'number':
        return (
          <NumberPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'textarea':
        return (
          <TextareaPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'select':
        return (
          <SelectPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'file':
        return (
          <FilePropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'checkbox':
        return (
          <CheckboxPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'date':
        return (
          <DatePropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'phone':
        return (
          <PhonePropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'radio':
        return (
          <RadioPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      case 'multiselect':
        return (
          <MultiselectPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
      default:
        return (
          <CommonPropertiesEditor
            field={selectedField}
            onChange={handleConfigChange}
          />
        )
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          {fieldType && <fieldType.icon className="h-4 w-4" />}
          {fieldType ? t(fieldType.label) : selectedField.config.type}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="field-name">{t('fieldBuilder.fieldName')}</Label>
          <Input
            id="field-name"
            value={selectedField.name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="field_name"
            className={nameError ? 'border-destructive' : ''}
          />
          {nameError ? (
            <p className="text-xs text-destructive">{nameError}</p>
          ) : (
            <p className="text-xs text-muted-foreground">
              {t('fieldBuilder.fieldNameDescription')}
            </p>
          )}
        </div>

        {renderPropertyEditor()}
      </CardContent>
    </Card>
  )
}
