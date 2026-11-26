import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { DragEndEvent } from '@dnd-kit/core'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useFieldBuilder } from '../FieldBuilderContext'
import { FieldListItem } from './FieldListItem'
import { FieldTypeSelector } from './FieldTypeSelector'

export function FieldList() {
  const { t } = useTranslation('admin')
  const { state, actions } = useFieldBuilder()
  const [isTypeSelectorOpen, setIsTypeSelectorOpen] = useState(false)

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      const oldIndex = state.fields.findIndex((field) => field.id === active.id)
      const newIndex = state.fields.findIndex((field) => field.id === over.id)

      const newItems = arrayMove(state.fields, oldIndex, newIndex).map(
        (item, index) => ({
          ...item,
          display_order: index,
        })
      )

      actions.reorderFields(newItems)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-medium">{t('fieldBuilder.title')}</h3>
        <Button
          type="button"
          size="sm"
          onClick={() => setIsTypeSelectorOpen(true)}
        >
          <Plus className="h-4 w-4 mr-2" />
          {t('fieldBuilder.addField')}
        </Button>
      </div>

      {state.fields.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground border rounded-lg border-dashed">
          <p className="text-sm">{t('fieldBuilder.emptyMessage')}</p>
          <Button
            type="button"
            variant="link"
            size="sm"
            onClick={() => setIsTypeSelectorOpen(true)}
          >
            {t('fieldBuilder.addField')}
          </Button>
        </div>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={state.fields.map((field) => field.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {state.fields
                .slice()
                .sort((a, b) => a.display_order - b.display_order)
                .map((field) => (
                  <FieldListItem
                    key={field.id}
                    field={field}
                    isSelected={field.id === state.selectedFieldId}
                    onSelect={() => actions.selectField(field.id)}
                    onDelete={() => actions.deleteField(field.id)}
                  />
                ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <FieldTypeSelector
        open={isTypeSelectorOpen}
        onOpenChange={setIsTypeSelectorOpen}
        onSelect={(type) => {
          actions.addField(type)
          setIsTypeSelectorOpen(false)
        }}
      />
    </div>
  )
}
