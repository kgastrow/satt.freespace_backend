import { createContext, useContext, useCallback, useMemo, useReducer, useEffect, useRef } from 'react'
import type { BuilderField, FieldBuilderState, FieldConfig, FieldType } from './types'
import {
  createBuilderField,
  jsonToBuilderFields,
  builderFieldsToJson,
  formatJson,
  parseJson,
  normalizeFieldsForComparison,
} from './utils'

// Action types
type FieldBuilderAction =
  | { type: 'ADD_FIELD'; payload: FieldType }
  | { type: 'UPDATE_FIELD'; payload: { id: string; updates: Partial<BuilderField> } }
  | { type: 'UPDATE_FIELD_CONFIG'; payload: { id: string; updates: Partial<FieldConfig> } }
  | { type: 'DELETE_FIELD'; payload: string }
  | { type: 'REORDER_FIELDS'; payload: BuilderField[] }
  | { type: 'SELECT_FIELD'; payload: string | null }
  | { type: 'SET_MODE'; payload: 'visual' | 'json' }
  | { type: 'SET_JSON_VALUE'; payload: string }
  | { type: 'SET_JSON_ERROR'; payload: string | null }
  | { type: 'SYNC_FROM_JSON' }
  | { type: 'SYNC_TO_JSON' }
  | { type: 'INITIALIZE'; payload: Record<string, FieldConfig> }
  | { type: 'SET_FIELDS_FROM_EXTERNAL'; payload: Record<string, FieldConfig> }

// Reducer
function fieldBuilderReducer(
  state: FieldBuilderState,
  action: FieldBuilderAction
): FieldBuilderState {
  switch (action.type) {
    case 'ADD_FIELD': {
      const newField = createBuilderField(action.payload, state.fields)
      const newFields = [...state.fields, newField]
      return {
        ...state,
        fields: newFields,
        selectedFieldId: newField.id,
        jsonValue: formatJson(builderFieldsToJson(newFields)),
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'UPDATE_FIELD': {
      const newFields = state.fields.map((field) =>
        field.id === action.payload.id
          ? { ...field, ...action.payload.updates }
          : field
      )
      return {
        ...state,
        fields: newFields,
        jsonValue: formatJson(builderFieldsToJson(newFields)),
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'UPDATE_FIELD_CONFIG': {
      const newFields = state.fields.map((field) =>
        field.id === action.payload.id
          ? { ...field, config: { ...field.config, ...action.payload.updates } }
          : field
      )
      return {
        ...state,
        fields: newFields,
        jsonValue: formatJson(builderFieldsToJson(newFields)),
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'DELETE_FIELD': {
      const newFields = state.fields
        .filter((field) => field.id !== action.payload)
        .map((field, index) => ({ ...field, display_order: index }))
      return {
        ...state,
        fields: newFields,
        selectedFieldId:
          state.selectedFieldId === action.payload ? null : state.selectedFieldId,
        jsonValue: formatJson(builderFieldsToJson(newFields)),
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'REORDER_FIELDS': {
      const newFields = action.payload.map((field, index) => ({
        ...field,
        display_order: index,
      }))
      return {
        ...state,
        fields: newFields,
        jsonValue: formatJson(builderFieldsToJson(newFields)),
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'SELECT_FIELD':
      return {
        ...state,
        selectedFieldId: action.payload,
      }

    case 'SET_MODE':
      return {
        ...state,
        mode: action.payload,
      }

    case 'SET_JSON_VALUE':
      return {
        ...state,
        jsonValue: action.payload,
      }

    case 'SET_JSON_ERROR':
      return {
        ...state,
        jsonError: action.payload,
      }

    case 'SYNC_FROM_JSON': {
      const result = parseJson(state.jsonValue)
      if (!result.success) {
        return {
          ...state,
          jsonError: result.error,
        }
      }
      const newFields = jsonToBuilderFields(result.data)
      return {
        ...state,
        fields: newFields,
        selectedFieldId: null,
        jsonError: null,
        lastChangeSource: 'user',
      }
    }

    case 'SYNC_TO_JSON':
      return {
        ...state,
        jsonValue: formatJson(builderFieldsToJson(state.fields)),
        jsonError: null,
      }

    case 'INITIALIZE': {
      const fields = jsonToBuilderFields(action.payload)
      return {
        ...state,
        fields,
        jsonValue: formatJson(action.payload),
        jsonError: null,
        selectedFieldId: null,
      }
    }

    case 'SET_FIELDS_FROM_EXTERNAL': {
      const fields = jsonToBuilderFields(action.payload)
      return {
        ...state,
        fields,
        jsonValue: formatJson(action.payload),
        jsonError: null,
        selectedFieldId: null,
        lastChangeSource: 'external',
        externalValueFingerprint: normalizeFieldsForComparison(action.payload),
      }
    }

    default:
      return state
  }
}

// Initial state
const initialState: FieldBuilderState = {
  fields: [],
  selectedFieldId: null,
  mode: 'visual',
  jsonValue: '{}',
  jsonError: null,
  lastChangeSource: null,
  externalValueFingerprint: null,
}

// Context value interface
interface FieldBuilderContextValue {
  state: FieldBuilderState
  actions: {
    addField: (type: FieldType) => void
    updateField: (id: string, updates: Partial<BuilderField>) => void
    updateFieldConfig: (id: string, updates: Partial<FieldConfig>) => void
    deleteField: (id: string) => void
    reorderFields: (fields: BuilderField[]) => void
    selectField: (id: string | null) => void
    setMode: (mode: 'visual' | 'json') => void
    setJsonValue: (value: string) => void
    syncFromJson: () => void
    syncToJson: () => void
  }
  selectedField: BuilderField | undefined
}

const FieldBuilderContext = createContext<FieldBuilderContextValue | null>(null)

interface FieldBuilderProviderProps {
  children: React.ReactNode
  initialValue: Record<string, FieldConfig>
  onChange: (value: Record<string, FieldConfig>) => void
}

export function FieldBuilderProvider({
  children,
  initialValue,
  onChange,
}: FieldBuilderProviderProps) {
  const [state, dispatch] = useReducer(fieldBuilderReducer, initialState)

  // Track external value changes with memoized fingerprint
  const externalFingerprint = useMemo(
    () => normalizeFieldsForComparison(initialValue),
    [initialValue]
  )

  // Initialize only when external value actually changes (normalized comparison)
  useEffect(() => {
    if (state.externalValueFingerprint !== externalFingerprint) {
      dispatch({ type: 'SET_FIELDS_FROM_EXTERNAL', payload: initialValue })
    }
  }, [externalFingerprint, state.externalValueFingerprint, initialValue])

  // Stable onChange ref to avoid effect dependency issues
  const onChangeRef = useRef(onChange)
  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  // Notify parent only for user-initiated changes
  useEffect(() => {
    if (state.lastChangeSource === 'user') {
      const json = builderFieldsToJson(state.fields)
      onChangeRef.current(json)
    }
  }, [state.fields, state.lastChangeSource])

  // Actions
  const addField = useCallback((type: FieldType) => {
    dispatch({ type: 'ADD_FIELD', payload: type })
  }, [])

  const updateField = useCallback((id: string, updates: Partial<BuilderField>) => {
    dispatch({ type: 'UPDATE_FIELD', payload: { id, updates } })
  }, [])

  const updateFieldConfig = useCallback((id: string, updates: Partial<FieldConfig>) => {
    dispatch({ type: 'UPDATE_FIELD_CONFIG', payload: { id, updates } })
  }, [])

  const deleteField = useCallback((id: string) => {
    dispatch({ type: 'DELETE_FIELD', payload: id })
  }, [])

  const reorderFields = useCallback((fields: BuilderField[]) => {
    dispatch({ type: 'REORDER_FIELDS', payload: fields })
  }, [])

  const selectField = useCallback((id: string | null) => {
    dispatch({ type: 'SELECT_FIELD', payload: id })
  }, [])

  const setMode = useCallback((mode: 'visual' | 'json') => {
    dispatch({ type: 'SET_MODE', payload: mode })
  }, [])

  const setJsonValue = useCallback((value: string) => {
    dispatch({ type: 'SET_JSON_VALUE', payload: value })
  }, [])

  const syncFromJson = useCallback(() => {
    dispatch({ type: 'SYNC_FROM_JSON' })
  }, [])

  const syncToJson = useCallback(() => {
    dispatch({ type: 'SYNC_TO_JSON' })
  }, [])

  const selectedField = useMemo(
    () => state.fields.find((f) => f.id === state.selectedFieldId),
    [state.fields, state.selectedFieldId]
  )

  const value = useMemo(
    () => ({
      state,
      actions: {
        addField,
        updateField,
        updateFieldConfig,
        deleteField,
        reorderFields,
        selectField,
        setMode,
        setJsonValue,
        syncFromJson,
        syncToJson,
      },
      selectedField,
    }),
    [
      state,
      addField,
      updateField,
      updateFieldConfig,
      deleteField,
      reorderFields,
      selectField,
      setMode,
      setJsonValue,
      syncFromJson,
      syncToJson,
      selectedField,
    ]
  )

  return (
    <FieldBuilderContext.Provider value={value}>
      {children}
    </FieldBuilderContext.Provider>
  )
}

export function useFieldBuilder(): FieldBuilderContextValue {
  const context = useContext(FieldBuilderContext)
  if (!context) {
    throw new Error('useFieldBuilder must be used within a FieldBuilderProvider')
  }
  return context
}
