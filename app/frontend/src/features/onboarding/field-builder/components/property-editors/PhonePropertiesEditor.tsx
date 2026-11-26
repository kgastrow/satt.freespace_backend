import { useTranslation } from 'react-i18next'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { CommonPropertiesEditor } from './CommonPropertiesEditor'
import type { PropertyEditorProps } from '../../types'

const PHONE_FORMATS = [
  { value: 'international', label: 'International (+27 12 345 6789)' },
  { value: 'national', label: 'National (012 345 6789)' },
]

const COUNTRIES = [
  { value: 'ZA', label: 'South Africa (+27)' },
  { value: 'US', label: 'United States (+1)' },
  { value: 'GB', label: 'United Kingdom (+44)' },
  { value: 'DE', label: 'Germany (+49)' },
  { value: 'FR', label: 'France (+33)' },
  { value: 'AU', label: 'Australia (+61)' },
  { value: 'NZ', label: 'New Zealand (+64)' },
  { value: 'CA', label: 'Canada (+1)' },
  { value: 'IN', label: 'India (+91)' },
  { value: 'BR', label: 'Brazil (+55)' },
]

export function PhonePropertiesEditor({ field, onChange }: PropertyEditorProps) {
  const { t } = useTranslation('admin')

  return (
    <div className="space-y-4">
      <CommonPropertiesEditor field={field} onChange={onChange} />

      <div className="space-y-2">
        <Label htmlFor="field-defaultCountry">{t('fieldBuilder.properties.defaultCountry')}</Label>
        <Select
          value={field.config.defaultCountry || 'ZA'}
          onValueChange={(value) => onChange({ defaultCountry: value })}
        >
          <SelectTrigger id="field-defaultCountry">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {COUNTRIES.map((country) => (
              <SelectItem key={country.value} value={country.value}>
                {country.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="field-phoneFormat">{t('fieldBuilder.properties.phoneFormat')}</Label>
        <Select
          value={field.config.phoneFormat || 'international'}
          onValueChange={(value) => onChange({ phoneFormat: value })}
        >
          <SelectTrigger id="field-phoneFormat">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PHONE_FORMATS.map((format) => (
              <SelectItem key={format.value} value={format.value}>
                {format.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  )
}
