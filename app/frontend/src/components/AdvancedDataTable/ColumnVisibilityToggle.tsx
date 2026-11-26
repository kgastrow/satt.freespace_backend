import { Settings2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { useTranslation } from 'react-i18next'
import type { AdvancedColumn } from './types'

interface ColumnVisibilityToggleProps<T> {
  columns: AdvancedColumn<T>[]
  visibleColumns: string[]
  onVisibleColumnsChange: (columns: string[]) => void
}

/**
 * Column visibility toggle dropdown
 */
export function ColumnVisibilityToggle<T>({
  columns,
  visibleColumns,
  onVisibleColumnsChange,
}: ColumnVisibilityToggleProps<T>) {
  const { t } = useTranslation('admin')

  // Get toggleable columns (exclude always visible)
  const toggleableColumns = columns.filter((col) => !col.alwaysVisible)

  const handleToggle = (columnKey: string, checked: boolean) => {
    if (checked) {
      onVisibleColumnsChange([...visibleColumns, columnKey])
    } else {
      onVisibleColumnsChange(visibleColumns.filter((key) => key !== columnKey))
    }
  }

  const handleReset = () => {
    // Reset to default visibility
    const defaultVisible = columns
      .filter((col) => col.alwaysVisible || col.defaultVisible !== false)
      .map((col) => col.key)
    onVisibleColumnsChange(defaultVisible)
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="ml-auto h-8">
          <Settings2 className="mr-2 h-4 w-4" />
          {t('users.table.columns', 'Columns')}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56" align="end">
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label className="text-sm font-medium">
              {t('users.table.toggleColumns', 'Toggle columns')}
            </Label>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={handleReset}
            >
              {t('users.table.reset', 'Reset')}
            </Button>
          </div>
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {toggleableColumns.map((column) => (
              <div key={column.key} className="flex items-center space-x-2">
                <Checkbox
                  id={`column-${column.key}`}
                  checked={visibleColumns.includes(column.key)}
                  onCheckedChange={(checked) => handleToggle(column.key, !!checked)}
                />
                <Label
                  htmlFor={`column-${column.key}`}
                  className="text-sm font-normal cursor-pointer flex-1"
                >
                  {column.header}
                </Label>
              </div>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
