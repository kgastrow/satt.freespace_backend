import {
  Type,
  Mail,
  Hash,
  Link,
  AlignLeft,
  List,
  Upload,
  CheckSquare,
  Calendar,
  Phone,
  CircleDot,
  ListChecks,
} from 'lucide-react'
import type { FieldType, FieldTypeDefinition, FieldConfig } from './types'

const registry = new Map<FieldType, FieldTypeDefinition>()

// Existing types
registry.set('string', {
  type: 'string',
  label: 'fieldBuilder.types.string',
  icon: Type,
  description: 'fieldBuilder.types.stringDescription',
  defaultConfig: { type: 'string', required: true },
  availableProperties: [
    'label',
    'description',
    'placeholder',
    'required',
    'minLength',
    'maxLength',
    'pattern',
  ],
})

registry.set('email', {
  type: 'email',
  label: 'fieldBuilder.types.email',
  icon: Mail,
  description: 'fieldBuilder.types.emailDescription',
  defaultConfig: { type: 'email', required: true },
  availableProperties: ['label', 'description', 'placeholder', 'required'],
})

registry.set('number', {
  type: 'number',
  label: 'fieldBuilder.types.number',
  icon: Hash,
  description: 'fieldBuilder.types.numberDescription',
  defaultConfig: { type: 'number', required: true },
  availableProperties: ['label', 'description', 'placeholder', 'required', 'min', 'max'],
})

registry.set('url', {
  type: 'url',
  label: 'fieldBuilder.types.url',
  icon: Link,
  description: 'fieldBuilder.types.urlDescription',
  defaultConfig: { type: 'url', required: true },
  availableProperties: ['label', 'description', 'placeholder', 'required'],
})

registry.set('textarea', {
  type: 'textarea',
  label: 'fieldBuilder.types.textarea',
  icon: AlignLeft,
  description: 'fieldBuilder.types.textareaDescription',
  defaultConfig: { type: 'textarea', required: true, rows: 4 },
  availableProperties: [
    'label',
    'description',
    'placeholder',
    'required',
    'minLength',
    'maxLength',
    'rows',
  ],
})

registry.set('select', {
  type: 'select',
  label: 'fieldBuilder.types.select',
  icon: List,
  description: 'fieldBuilder.types.selectDescription',
  defaultConfig: { type: 'select', required: true, options: [] },
  availableProperties: ['label', 'description', 'placeholder', 'required', 'options'],
})

registry.set('file', {
  type: 'file',
  label: 'fieldBuilder.types.file',
  icon: Upload,
  description: 'fieldBuilder.types.fileDescription',
  defaultConfig: { type: 'file', required: true, maxSize: 5 * 1024 * 1024 },
  availableProperties: ['label', 'description', 'required', 'accept', 'maxSize'],
})

// New types
registry.set('checkbox', {
  type: 'checkbox',
  label: 'fieldBuilder.types.checkbox',
  icon: CheckSquare,
  description: 'fieldBuilder.types.checkboxDescription',
  defaultConfig: { type: 'checkbox', required: false, defaultChecked: false },
  availableProperties: ['label', 'description', 'required', 'defaultChecked'],
})

registry.set('date', {
  type: 'date',
  label: 'fieldBuilder.types.date',
  icon: Calendar,
  description: 'fieldBuilder.types.dateDescription',
  defaultConfig: { type: 'date', required: true, dateFormat: 'yyyy-MM-dd' },
  availableProperties: [
    'label',
    'description',
    'placeholder',
    'required',
    'minDate',
    'maxDate',
    'dateFormat',
  ],
})

registry.set('phone', {
  type: 'phone',
  label: 'fieldBuilder.types.phone',
  icon: Phone,
  description: 'fieldBuilder.types.phoneDescription',
  defaultConfig: { type: 'phone', required: true, defaultCountry: 'ZA' },
  availableProperties: [
    'label',
    'description',
    'placeholder',
    'required',
    'phoneFormat',
    'defaultCountry',
  ],
})

registry.set('radio', {
  type: 'radio',
  label: 'fieldBuilder.types.radio',
  icon: CircleDot,
  description: 'fieldBuilder.types.radioDescription',
  defaultConfig: { type: 'radio', required: true, options: [], layout: 'vertical' },
  availableProperties: ['label', 'description', 'required', 'options', 'layout'],
})

registry.set('multiselect', {
  type: 'multiselect',
  label: 'fieldBuilder.types.multiselect',
  icon: ListChecks,
  description: 'fieldBuilder.types.multiselectDescription',
  defaultConfig: { type: 'multiselect', required: true, options: [], maxSelections: undefined },
  availableProperties: [
    'label',
    'description',
    'placeholder',
    'required',
    'options',
    'maxSelections',
  ],
})

export function getFieldType(type: FieldType): FieldTypeDefinition | undefined {
  return registry.get(type)
}

export function getAllFieldTypes(): FieldTypeDefinition[] {
  return Array.from(registry.values())
}

export function registerFieldType(definition: FieldTypeDefinition): void {
  registry.set(definition.type, definition)
}

export function getDefaultConfig(type: FieldType): FieldConfig {
  const definition = registry.get(type)
  return definition ? { ...definition.defaultConfig } : { type, required: true }
}
