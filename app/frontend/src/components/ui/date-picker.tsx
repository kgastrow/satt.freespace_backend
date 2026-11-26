import * as React from 'react'
import { format, parse, isValid } from 'date-fns'
import { Calendar as CalendarIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Calendar } from '@/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

interface DatePickerProps {
  value?: string // ISO date string
  onChange?: (value: string | undefined) => void
  placeholder?: string
  minDate?: Date
  maxDate?: Date
  dateFormat?: string
  disabled?: boolean
  className?: string
}

export function DatePicker({
  value,
  onChange,
  placeholder = 'Select a date',
  minDate,
  maxDate,
  dateFormat = 'yyyy-MM-dd',
  disabled,
  className,
}: DatePickerProps) {
  const [open, setOpen] = React.useState(false)

  // Parse the string value to a Date object
  const selectedDate = React.useMemo(() => {
    if (!value) return undefined
    const parsed = parse(value, 'yyyy-MM-dd', new Date())
    return isValid(parsed) ? parsed : undefined
  }, [value])

  // Handle date selection
  const handleSelect = React.useCallback(
    (date: Date | undefined) => {
      if (date) {
        onChange?.(format(date, 'yyyy-MM-dd'))
      } else {
        onChange?.(undefined)
      }
      setOpen(false)
    },
    [onChange]
  )

  // Format the display value
  const displayValue = React.useMemo(() => {
    if (!selectedDate) return null
    try {
      return format(selectedDate, dateFormat)
    } catch {
      return format(selectedDate, 'yyyy-MM-dd')
    }
  }, [selectedDate, dateFormat])

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          className={cn(
            'w-full justify-start text-left font-normal',
            !displayValue && 'text-muted-foreground',
            className
          )}
          disabled={disabled}
        >
          <CalendarIcon className="mr-2 h-4 w-4" />
          {displayValue || placeholder}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Calendar
          mode="single"
          selected={selectedDate}
          onSelect={handleSelect}
          disabled={(date) => {
            if (minDate && date < minDate) return true
            if (maxDate && date > maxDate) return true
            return false
          }}
          captionLayout="dropdown"
          startMonth={minDate || new Date(1900, 0)}
          endMonth={maxDate || new Date(2100, 11)}
          defaultMonth={selectedDate}
          initialFocus
        />
      </PopoverContent>
    </Popover>
  )
}
