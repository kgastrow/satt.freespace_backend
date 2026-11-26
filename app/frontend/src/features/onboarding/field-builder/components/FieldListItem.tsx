import { useTranslation } from 'react-i18next'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { getFieldType } from '../fieldTypeRegistry'
import type { BuilderField } from '../types'

interface FieldListItemProps {
  field: BuilderField
  isSelected: boolean
  onSelect: () => void
  onDelete: () => void
}

export function FieldListItem({
  field,
  isSelected,
  onSelect,
  onDelete,
}: FieldListItemProps) {
  const { t } = useTranslation('admin')
  const fieldType = getFieldType(field.config.type || 'string')
  const Icon = fieldType?.icon

  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: field.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'flex items-center gap-3 p-3 border rounded-lg bg-card cursor-pointer transition-colors',
        isSelected && 'border-primary ring-1 ring-primary',
        isDragging && 'opacity-50 shadow-lg z-50'
      )}
      onClick={onSelect}
    >
      <button
        type="button"
        className="cursor-grab touch-none text-muted-foreground hover:text-foreground focus:outline-none"
        {...attributes}
        {...listeners}
        onClick={(e) => e.stopPropagation()}
      >
        <GripVertical className="h-5 w-5" />
      </button>

      {Icon && <Icon className="h-4 w-4 text-muted-foreground flex-shrink-0" />}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{field.name}</span>
          {field.config.label && (
            <span className="text-xs text-muted-foreground truncate">
              {field.config.label}
            </span>
          )}
        </div>
      </div>

      <Badge variant="outline" className="flex-shrink-0">
        {fieldType ? t(fieldType.label) : field.config.type}
      </Badge>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-destructive flex-shrink-0"
        onClick={(e) => {
          e.stopPropagation()
          onDelete()
        }}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}
