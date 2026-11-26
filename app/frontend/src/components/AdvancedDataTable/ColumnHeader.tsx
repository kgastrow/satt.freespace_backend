import { ArrowDown, ArrowUp, ArrowUpDown, Filter } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { AdvancedColumn, SortState, FilterState } from './types'

interface ColumnHeaderProps<T> {
  column: AdvancedColumn<T>
  sort?: SortState
  onSortChange?: (sort: SortState | undefined) => void
  filters?: FilterState
  onFiltersChange?: (filters: FilterState) => void
}

/**
 * Sortable and filterable column header component
 */
export function ColumnHeader<T>({
  column,
  sort,
  onSortChange,
  filters,
  onFiltersChange,
}: ColumnHeaderProps<T>) {
  const { t } = useTranslation('admin')
  const sortKey = column.sortKey || column.key
  const isSorted = sort?.field === sortKey
  const sortDirection = isSorted ? sort.direction : undefined

  const filterKey = column.key
  const filterValue = filters?.[filterKey]
  const hasActiveFilter = filterValue !== undefined && filterValue !== '' &&
    (Array.isArray(filterValue) ? filterValue.length > 0 : true)

  const handleSort = () => {
    if (!column.sortable || !onSortChange) return

    if (!isSorted) {
      onSortChange({ field: sortKey, direction: 'asc' })
    } else if (sortDirection === 'asc') {
      onSortChange({ field: sortKey, direction: 'desc' })
    } else {
      onSortChange(undefined)
    }
  }

  const handleFilterChange = (value: string | string[] | boolean | undefined) => {
    if (!onFiltersChange || !filters) return

    const newFilters = { ...filters }
    if (value === undefined || value === '' || (Array.isArray(value) && value.length === 0)) {
      delete newFilters[filterKey]
    } else {
      newFilters[filterKey] = value
    }
    onFiltersChange(newFilters)
  }

  const handleClearFilter = () => {
    handleFilterChange(undefined)
  }

  const renderFilterContent = () => {
    if (!column.filterConfig) return null

    const { type, options = [] } = column.filterConfig

    if (type === 'boolean') {
      return (
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t('users.filters.filterBy', 'Filter by')} {column.header}
          </Label>
          <Select
            value={filterValue === true ? 'true' : filterValue === false ? 'false' : ''}
            onValueChange={(val) => {
              if (val === '') {
                handleFilterChange(undefined)
              } else {
                handleFilterChange(val === 'true')
              }
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('users.filters.selectOption', 'Select option')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">{t('users.filters.all', 'All')}</SelectItem>
              <SelectItem value="true">{t('users.filters.yes', 'Yes')}</SelectItem>
              <SelectItem value="false">{t('users.filters.no', 'No')}</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )
    }

    if (type === 'select') {
      return (
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t('users.filters.filterBy', 'Filter by')} {column.header}
          </Label>
          <Select
            value={typeof filterValue === 'string' ? filterValue : ''}
            onValueChange={(val) => handleFilterChange(val || undefined)}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder={t('users.filters.selectOption', 'Select option')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">{t('users.filters.all', 'All')}</SelectItem>
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )
    }

    if (type === 'multiselect') {
      const selectedValues = Array.isArray(filterValue) ? filterValue : []

      return (
        <div className="space-y-2">
          <Label className="text-sm font-medium">
            {t('users.filters.filterBy', 'Filter by')} {column.header}
          </Label>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {options.map((option) => (
              <div key={option.value} className="flex items-center space-x-2">
                <Checkbox
                  id={`filter-${filterKey}-${option.value}`}
                  checked={selectedValues.includes(option.value)}
                  onCheckedChange={(checked) => {
                    const newValues = checked
                      ? [...selectedValues, option.value]
                      : selectedValues.filter((v) => v !== option.value)
                    handleFilterChange(newValues.length > 0 ? newValues : undefined)
                  }}
                />
                <Label
                  htmlFor={`filter-${filterKey}-${option.value}`}
                  className="text-sm font-normal cursor-pointer"
                >
                  {option.label}
                </Label>
              </div>
            ))}
          </div>
        </div>
      )
    }

    return null
  }

  // Non-interactive header
  if (!column.sortable && !column.filterable) {
    return <span>{column.header}</span>
  }

  // Sortable only header
  if (column.sortable && !column.filterable) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className="-ml-3 h-8 data-[state=open]:bg-accent"
        onClick={handleSort}
      >
        {column.header}
        {isSorted ? (
          sortDirection === 'asc' ? (
            <ArrowUp className="ml-2 h-4 w-4" />
          ) : (
            <ArrowDown className="ml-2 h-4 w-4" />
          )
        ) : (
          <ArrowUpDown className="ml-2 h-4 w-4 text-muted-foreground" />
        )}
      </Button>
    )
  }

  // Filterable (with optional sorting)
  return (
    <div className="flex items-center gap-1">
      {column.sortable ? (
        <Button
          variant="ghost"
          size="sm"
          className="-ml-3 h-8"
          onClick={handleSort}
        >
          {column.header}
          {isSorted ? (
            sortDirection === 'asc' ? (
              <ArrowUp className="ml-2 h-4 w-4" />
            ) : (
              <ArrowDown className="ml-2 h-4 w-4" />
            )
          ) : (
            <ArrowUpDown className="ml-2 h-4 w-4 text-muted-foreground" />
          )}
        </Button>
      ) : (
        <span>{column.header}</span>
      )}

      <Popover>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn('h-8 w-8 p-0', hasActiveFilter && 'text-primary')}
          >
            <Filter className="h-4 w-4" />
            <span className="sr-only">{t('users.filters.filter', 'Filter')}</span>
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-60" align="start">
          {renderFilterContent()}
          {hasActiveFilter && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-2 w-full"
              onClick={handleClearFilter}
            >
              {t('users.filters.clearFilter', 'Clear filter')}
            </Button>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}
