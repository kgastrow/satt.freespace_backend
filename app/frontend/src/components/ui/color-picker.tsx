import * as React from 'react'
import { cn } from '@/lib/utils'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Paintbrush, X } from 'lucide-react'

export interface ColorPickerProps {
  value?: string
  onChange?: (value: string) => void
  className?: string
}

const presetColors = [
  // Row 1 - Vibrant colors
  '#ef4444', // red-500
  '#f97316', // orange-500
  '#eab308', // yellow-500
  '#22c55e', // green-500
  '#3b82f6', // blue-500
  '#8b5cf6', // violet-500
  '#ec4899', // pink-500
  '#6b7280', // gray-500
  // Row 2 - Light colors
  '#fecaca', // red-200
  '#fed7aa', // orange-200
  '#fef08a', // yellow-200
  '#bbf7d0', // green-200
  '#bfdbfe', // blue-200
  '#ddd6fe', // violet-200
  '#fbcfe8', // pink-200
  '#e5e7eb', // gray-200
  // Row 3 - Dark colors
  '#991b1b', // red-800
  '#9a3412', // orange-800
  '#854d0e', // yellow-800
  '#166534', // green-800
  '#1e40af', // blue-800
  '#5b21b6', // violet-800
  '#9d174d', // pink-800
  '#1f2937', // gray-800
]

const ColorPicker = React.forwardRef<HTMLInputElement, ColorPickerProps>(
  ({ value, onChange, className }, ref) => {
    const [open, setOpen] = React.useState(false)
    const colorInputRef = React.useRef<HTMLInputElement>(null)

    const handleColorInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      onChange?.(e.target.value)
    }

    const handlePresetClick = (color: string) => {
      onChange?.(color)
      setOpen(false)
    }

    const handleClear = (e: React.MouseEvent) => {
      e.stopPropagation()
      onChange?.('')
    }

    return (
      <div className={cn('flex items-center gap-2', className)}>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <button
              type="button"
              className={cn(
                'h-9 w-9 rounded-md border border-input cursor-pointer hover:ring-2 hover:ring-ring hover:ring-offset-2 transition-all',
                !value && 'bg-muted'
              )}
              style={value ? { backgroundColor: value } : undefined}
              aria-label={value ? `Selected color: ${value}` : 'Select color'}
            >
              {!value && <Paintbrush className="h-4 w-4 text-muted-foreground m-auto" />}
            </button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-3" align="start">
            <div className="space-y-3">
              {/* Preset colors grid */}
              <div className="grid grid-cols-8 gap-1.5">
                {presetColors.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={cn(
                      'w-7 h-7 rounded-md border border-input cursor-pointer hover:scale-110 transition-transform',
                      value === color && 'ring-2 ring-primary ring-offset-2'
                    )}
                    style={{ backgroundColor: color }}
                    onClick={() => handlePresetClick(color)}
                    aria-label={`Select color ${color}`}
                  />
                ))}
              </div>
              {/* Custom color picker */}
              <div className="flex items-center gap-2 pt-2 border-t">
                <button
                  type="button"
                  className={cn(
                    'flex items-center gap-2 px-3 py-1.5 text-sm border rounded-md hover:bg-accent transition-colors',
                    value && !presetColors.includes(value) && 'ring-2 ring-primary ring-offset-1'
                  )}
                  onClick={() => colorInputRef.current?.click()}
                >
                  <span
                    className="w-4 h-4 rounded border border-input"
                    style={{ backgroundColor: value || '#ffffff' }}
                  />
                  Custom color
                </button>
                {/* Hidden native color input */}
                <input
                  ref={(el) => {
                    colorInputRef.current = el
                    if (typeof ref === 'function') ref(el)
                    else if (ref) ref.current = el
                  }}
                  type="color"
                  value={value || '#ffffff'}
                  onChange={handleColorInputChange}
                  className="sr-only"
                />
              </div>
            </div>
          </PopoverContent>
        </Popover>
        {value && (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={handleClear}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Clear color</span>
          </Button>
        )}
      </div>
    )
  }
)
ColorPicker.displayName = 'ColorPicker'

export { ColorPicker }
