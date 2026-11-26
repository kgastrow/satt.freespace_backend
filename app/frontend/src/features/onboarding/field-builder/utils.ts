import type { BuilderField, FieldConfig, FieldType } from './types'
import { getDefaultConfig } from './fieldTypeRegistry'

/**
 * Generate a unique ID for fields (used for user-added fields)
 */
export function generateFieldId(): string {
  return crypto.randomUUID()
}

/**
 * Generate a deterministic ID for fields loaded from external data
 */
export function generateDeterministicFieldId(name: string, index: number): string {
  return `field-${name}-${index}`
}

/**
 * Generate a unique field name based on type
 */
export function generateFieldName(type: FieldType, existingFields: BuilderField[]): string {
  const baseName = type.toLowerCase()
  const existingNames = new Set(existingFields.map((f) => f.name))

  if (!existingNames.has(baseName)) {
    return baseName
  }

  let counter = 1
  while (existingNames.has(`${baseName}_${counter}`)) {
    counter++
  }
  return `${baseName}_${counter}`
}

/**
 * Create a new BuilderField from a field type
 */
export function createBuilderField(
  type: FieldType,
  existingFields: BuilderField[]
): BuilderField {
  const name = generateFieldName(type, existingFields)
  return {
    id: generateFieldId(),
    name,
    display_order: existingFields.length,
    config: getDefaultConfig(type),
  }
}

/**
 * Convert JSON required_fields object to BuilderField array
 */
export function jsonToBuilderFields(
  json: Record<string, FieldConfig>
): BuilderField[] {
  return Object.entries(json).map(([name, config], index) => ({
    id: generateDeterministicFieldId(name, index),
    name,
    display_order: index,
    config: { ...config },
  }))
}

/**
 * Convert BuilderField array to JSON required_fields object
 */
export function builderFieldsToJson(
  fields: BuilderField[]
): Record<string, FieldConfig> {
  const sorted = [...fields].sort((a, b) => a.display_order - b.display_order)
  const result: Record<string, FieldConfig> = {}

  for (const field of sorted) {
    // Clean up config - remove undefined values
    const cleanConfig: FieldConfig = {}
    for (const [key, value] of Object.entries(field.config)) {
      if (value !== undefined && value !== '') {
        (cleanConfig as Record<string, unknown>)[key] = value
      }
    }
    result[field.name] = cleanConfig
  }

  return result
}

/**
 * Validate field name format
 */
export function isValidFieldName(name: string): boolean {
  // Field names should be lowercase with underscores, no spaces
  return /^[a-z][a-z0-9_]*$/.test(name)
}

/**
 * Check if a field name is unique among existing fields
 */
export function isFieldNameUnique(
  name: string,
  existingFields: BuilderField[],
  excludeId?: string
): boolean {
  return !existingFields.some(
    (f) => f.name === name && f.id !== excludeId
  )
}

/**
 * Parse JSON string safely
 */
export function parseJson(
  jsonString: string
): { success: true; data: Record<string, FieldConfig> } | { success: false; error: string } {
  try {
    const parsed = JSON.parse(jsonString)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { success: false, error: 'JSON must be an object' }
    }
    return { success: true, data: parsed as Record<string, FieldConfig> }
  } catch (e) {
    return { success: false, error: e instanceof Error ? e.message : 'Invalid JSON' }
  }
}

/**
 * Format JSON for display
 */
export function formatJson(data: Record<string, FieldConfig>): string {
  return JSON.stringify(data, null, 2)
}

/**
 * Normalize fields for deep comparison (used to detect external value changes)
 */
export function normalizeFieldsForComparison(fields: Record<string, FieldConfig>): string {
  const sorted = Object.keys(fields).sort()
  const normalized: Record<string, FieldConfig> = {}
  for (const key of sorted) {
    const config = fields[key]
    const cleanConfig: FieldConfig = {}
    for (const [k, v] of Object.entries(config)) {
      if (v !== undefined && v !== '') {
        (cleanConfig as Record<string, unknown>)[k] = v
      }
    }
    normalized[key] = cleanConfig
  }
  return JSON.stringify(normalized)
}
