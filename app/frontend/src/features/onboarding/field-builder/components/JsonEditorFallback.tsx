import { useTranslation } from 'react-i18next'
import { AlertCircle } from 'lucide-react'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useFieldBuilder } from '../FieldBuilderContext'

export function JsonEditorFallback() {
  const { t } = useTranslation('admin')
  const { state, actions } = useFieldBuilder()

  const handleChange = (value: string) => {
    actions.setJsonValue(value)
    // Try to parse and clear error if valid
    try {
      JSON.parse(value)
      actions.syncFromJson()
    } catch {
      // Error will be shown below
    }
  }

  const handleBlur = () => {
    try {
      JSON.parse(state.jsonValue)
    } catch {
      // Keep value on blur if invalid - error state is managed by isValidJson check
      actions.setJsonValue(state.jsonValue)
    }
  }

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(state.jsonValue)
      actions.setJsonValue(JSON.stringify(parsed, null, 2))
    } catch {
      // Can't format invalid JSON
    }
  }

  const isValidJson = (() => {
    try {
      JSON.parse(state.jsonValue)
      return true
    } catch {
      return false
    }
  })()

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleFormat}
          disabled={!isValidJson}
        >
          {t('fieldBuilder.formatJson')}
        </Button>
      </div>

      <Textarea
        value={state.jsonValue}
        onChange={(e) => handleChange(e.target.value)}
        onBlur={handleBlur}
        rows={16}
        className="font-mono text-sm"
        placeholder="{}"
      />

      {state.jsonError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{state.jsonError}</AlertDescription>
        </Alert>
      )}

      {!isValidJson && !state.jsonError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{t('fieldBuilder.jsonError')}</AlertDescription>
        </Alert>
      )}

      <p className="text-xs text-muted-foreground">
        {t('fieldBuilder.jsonDescription')}
      </p>
    </div>
  )
}
