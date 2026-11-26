import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronUp, Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { cn } from '@/lib/utils'
import { useFieldBuilder } from '../FieldBuilderContext'
import type { BuilderField, SelectOption } from '../types'

export function FieldPreview() {
  const { t } = useTranslation('admin')
  const { state } = useFieldBuilder()
  const [isOpen, setIsOpen] = useState(false)

  const sortedFields = [...state.fields].sort(
    (a, b) => a.display_order - b.display_order
  )

  if (sortedFields.length === 0) {
    return null
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className="w-full justify-between"
        >
          <span className="flex items-center gap-2">
            <Eye className="h-4 w-4" />
            {t('fieldBuilder.preview')}
          </span>
          {isOpen ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="pt-4">
        <div className="border rounded-lg p-4 bg-muted/30 space-y-4">
          {sortedFields.map((field) => (
            <PreviewField key={field.id} field={field} />
          ))}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

function PreviewField({ field }: { field: BuilderField }) {
  const { t } = useTranslation('common')
  const config = field.config
  const fieldType = config.type || 'string'
  const label = config.label || field.name
  const isOptional = config.required === false

  // Normalize options
  const options: SelectOption[] = (config.options || []).map((opt) =>
    typeof opt === 'string' ? { value: opt, label: opt } : opt
  )

  const renderField = () => {
    switch (fieldType) {
      case 'textarea':
        return (
          <Textarea
            placeholder={config.placeholder}
            rows={config.rows || 4}
            disabled
          />
        )

      case 'select':
        return (
          <Select disabled>
            <SelectTrigger>
              <SelectValue placeholder={config.placeholder || label} />
            </SelectTrigger>
            <SelectContent>
              {options.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )

      case 'file':
        return (
          <div className="border-2 border-dashed rounded-lg p-4 text-center text-muted-foreground text-sm">
            {t('onboarding:fileUpload.placeholder')}
          </div>
        )

      case 'checkbox':
        return (
          <div className="flex items-center gap-2">
            <Checkbox id={field.id} disabled checked={config.defaultChecked} />
            <Label htmlFor={field.id} className="font-normal">
              {label}
            </Label>
          </div>
        )

      case 'date':
        return (
          <DatePicker
            placeholder={config.placeholder}
            disabled
          />
        )

      case 'phone':
        return (
          <Input
            type="tel"
            placeholder={config.placeholder || '+27 12 345 6789'}
            disabled
          />
        )

      case 'radio':
        return (
          <RadioGroup
            disabled
            className={cn(
              config.layout === 'horizontal' ? 'flex gap-4' : 'space-y-2'
            )}
          >
            {options.map((opt) => (
              <div key={opt.value} className="flex items-center gap-2">
                <RadioGroupItem value={opt.value} id={`${field.id}-${opt.value}`} />
                <Label htmlFor={`${field.id}-${opt.value}`} className="font-normal">
                  {opt.label}
                </Label>
              </div>
            ))}
          </RadioGroup>
        )

      case 'multiselect':
        return (
          <div className="space-y-2 border rounded-lg p-3">
            {options.map((opt) => (
              <div key={opt.value} className="flex items-center gap-2">
                <Checkbox id={`${field.id}-${opt.value}`} disabled />
                <Label htmlFor={`${field.id}-${opt.value}`} className="font-normal">
                  {opt.label}
                </Label>
              </div>
            ))}
            {options.length === 0 && (
              <p className="text-sm text-muted-foreground">No options configured</p>
            )}
          </div>
        )

      case 'number':
        return (
          <Input
            type="number"
            placeholder={config.placeholder}
            min={config.min}
            max={config.max}
            disabled
          />
        )

      case 'email':
        return (
          <Input
            type="email"
            placeholder={config.placeholder || 'email@example.com'}
            disabled
          />
        )

      case 'url':
        return (
          <Input
            type="url"
            placeholder={config.placeholder || 'https://example.com'}
            disabled
          />
        )

      default:
        return (
          <Input
            type="text"
            placeholder={config.placeholder}
            disabled
          />
        )
    }
  }

  // Checkbox has its own label handling
  if (fieldType === 'checkbox') {
    return (
      <div className="space-y-1">
        {renderField()}
        {config.description && (
          <p className="text-xs text-muted-foreground">{config.description}</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <Label>
        {label}
        {isOptional && (
          <span className="text-muted-foreground text-sm ml-1">
            ({t('optional')})
          </span>
        )}
      </Label>
      {renderField()}
      {config.description && (
        <p className="text-xs text-muted-foreground">{config.description}</p>
      )}
    </div>
  )
}
