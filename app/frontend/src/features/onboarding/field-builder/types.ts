// All supported field types
export type FieldType =
  // Existing types (already rendered in OnboardingStep.tsx)
  | 'string'
  | 'email'
  | 'number'
  | 'url'
  | 'textarea'
  | 'select'
  | 'file'
  // New types (must add rendering in OnboardingStep.tsx)
  | 'checkbox'
  | 'date'
  | 'phone'
  | 'radio'
  | 'multiselect'

export interface SelectOption {
  value: string
  label: string
}

// Extended FieldConfig (matches OnboardingStep.tsx + new properties)
export interface FieldConfig {
  // Common properties
  type?: FieldType
  label?: string
  description?: string
  placeholder?: string
  required?: boolean

  // String/textarea properties
  minLength?: number
  maxLength?: number
  pattern?: string

  // Number properties
  min?: number
  max?: number

  // Textarea properties
  rows?: number

  // Select/radio/multiselect properties
  options?: SelectOption[] | string[]

  // File properties
  accept?: string
  maxSize?: number

  // Checkbox properties (NEW)
  defaultChecked?: boolean

  // Date properties (NEW)
  minDate?: string // ISO date string
  maxDate?: string // ISO date string
  dateFormat?: string // Display format, e.g., 'yyyy-MM-dd'

  // Phone properties (NEW)
  phoneFormat?: string // E.g., 'international', 'national'
  defaultCountry?: string // ISO country code, e.g., 'ZA'

  // Radio properties (NEW)
  layout?: 'horizontal' | 'vertical'

  // Multiselect properties (NEW)
  maxSelections?: number
}

// Internal builder field representation
export interface BuilderField {
  id: string // UUID for drag-drop identity
  name: string // Field key in output JSON
  display_order: number // For SortableList compatibility
  config: FieldConfig
}

// Field builder state
export interface FieldBuilderState {
  fields: BuilderField[]
  selectedFieldId: string | null
  mode: 'visual' | 'json'
  jsonValue: string
  jsonError: string | null
  lastChangeSource: 'external' | 'user' | null
  externalValueFingerprint: string | null
}

// Field type registry entry
export interface FieldTypeDefinition {
  type: FieldType
  label: string // i18n key: 'fieldBuilder.types.{type}'
  icon: React.ComponentType<{ className?: string }>
  description: string // i18n key: 'fieldBuilder.types.{type}Description'
  defaultConfig: FieldConfig
  availableProperties: (keyof FieldConfig)[]
}

// Props for property editor components
export interface PropertyEditorProps {
  field: BuilderField
  onChange: (updates: Partial<FieldConfig>) => void
}
