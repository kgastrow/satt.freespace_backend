import { useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { FieldBuilderProvider, useFieldBuilder } from './FieldBuilderContext'
import { FieldList } from './components/FieldList'
import { FieldEditorPanel } from './components/FieldEditorPanel'
import { FieldPreview } from './components/FieldPreview'
import { JsonEditorFallback } from './components/JsonEditorFallback'
import type { FieldConfig } from './types'

interface FieldBuilderProps {
  value: Record<string, FieldConfig>
  onChange: (value: Record<string, FieldConfig>) => void
}

function FieldBuilderContent() {
  const { t } = useTranslation('admin')
  const { state, actions } = useFieldBuilder()

  const handleModeChange = useCallback(
    (value: string) => {
      actions.setMode(value as 'visual' | 'json')
      if (value === 'visual') {
        actions.syncFromJson()
      }
    },
    [actions]
  )

  return (
    <div className="space-y-4">
      <Tabs value={state.mode} onValueChange={handleModeChange}>
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="visual">
            {t('fieldBuilder.tabs.visual')}
          </TabsTrigger>
          <TabsTrigger value="json">
            {t('fieldBuilder.tabs.json')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="visual" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="space-y-4">
              <FieldList />
            </div>
            <div>
              <FieldEditorPanel />
            </div>
          </div>
          <FieldPreview />
        </TabsContent>

        <TabsContent value="json">
          <JsonEditorFallback />
        </TabsContent>
      </Tabs>
    </div>
  )
}

export function FieldBuilder({ value, onChange }: FieldBuilderProps) {
  return (
    <FieldBuilderProvider initialValue={value} onChange={onChange}>
      <FieldBuilderContent />
    </FieldBuilderProvider>
  )
}
