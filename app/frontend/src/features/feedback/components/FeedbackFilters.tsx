import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import { X } from 'lucide-react'
import type { FeedbackType, FeedbackStatus } from '../types'
import type { Organization } from '@/types/generated'

interface FeedbackFiltersProps {
  typeFilter?: FeedbackType
  statusFilter?: FeedbackStatus
  ratingFilter?: number
  dateFrom?: string
  dateTo?: string
  organizationFilter?: string
  onTypeChange: (type?: FeedbackType) => void
  onStatusChange: (status?: FeedbackStatus) => void
  onRatingChange: (rating?: number) => void
  onDateFromChange: (date?: string) => void
  onDateToChange: (date?: string) => void
  onOrganizationChange: (orgId?: string) => void
  onClearFilters: () => void
  organizations?: Organization[]
  isSuperAdmin?: boolean
}

export function FeedbackFilters({
  typeFilter,
  statusFilter,
  ratingFilter,
  dateFrom,
  dateTo,
  organizationFilter,
  onTypeChange,
  onStatusChange,
  onRatingChange,
  onDateFromChange,
  onDateToChange,
  onOrganizationChange,
  onClearFilters,
  organizations,
  isSuperAdmin,
}: FeedbackFiltersProps) {
  const { t } = useTranslation('feedback')

  const hasActiveFilters = typeFilter || statusFilter || ratingFilter || dateFrom || dateTo || organizationFilter

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium">{t('admin.filters.title')}</h3>
        {hasActiveFilters && (
          <Button variant="ghost" size="sm" onClick={onClearFilters}>
            <X className="mr-2 h-4 w-4" />
            {t('admin.filters.clearAll')}
          </Button>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-6">
        <div className="space-y-2">
          <Label>{t('admin.filters.type')}</Label>
          <Select
            value={typeFilter || 'all'}
            onValueChange={(value) => onTypeChange(value === 'all' ? undefined : (value as FeedbackType))}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('admin.filters.allTypes')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('admin.filters.allTypes')}</SelectItem>
              <SelectItem value="bug">{t('form.fields.type.options.bug')}</SelectItem>
              <SelectItem value="suggestion">{t('form.fields.type.options.suggestion')}</SelectItem>
              <SelectItem value="complaint">{t('form.fields.type.options.complaint')}</SelectItem>
              <SelectItem value="praise">{t('form.fields.type.options.praise')}</SelectItem>
              <SelectItem value="other">{t('form.fields.type.options.other')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>{t('admin.filters.status')}</Label>
          <Select
            value={statusFilter || 'all'}
            onValueChange={(value) => onStatusChange(value === 'all' ? undefined : (value as FeedbackStatus))}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('admin.filters.allStatuses')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('admin.filters.allStatuses')}</SelectItem>
              <SelectItem value="new">{t('admin.status.new')}</SelectItem>
              <SelectItem value="in_review">{t('admin.status.in_review')}</SelectItem>
              <SelectItem value="resolved">{t('admin.status.resolved')}</SelectItem>
              <SelectItem value="dismissed">{t('admin.status.dismissed')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>{t('admin.filters.minRating')}</Label>
          <Select
            value={ratingFilter?.toString() || 'all'}
            onValueChange={(value) => onRatingChange(value === 'all' ? undefined : parseInt(value))}
          >
            <SelectTrigger>
              <SelectValue placeholder={t('admin.filters.anyRating')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('admin.filters.anyRating')}</SelectItem>
              <SelectItem value="1">1+ ★</SelectItem>
              <SelectItem value="2">2+ ★</SelectItem>
              <SelectItem value="3">3+ ★</SelectItem>
              <SelectItem value="4">4+ ★</SelectItem>
              <SelectItem value="5">5 ★</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>{t('admin.filters.dateFrom')}</Label>
          <DatePicker
            value={dateFrom}
            onChange={onDateFromChange}
            placeholder={t('admin.filters.dateFrom')}
            maxDate={dateTo ? new Date(dateTo) : undefined}
          />
        </div>

        <div className="space-y-2">
          <Label>{t('admin.filters.dateTo')}</Label>
          <DatePicker
            value={dateTo}
            onChange={onDateToChange}
            placeholder={t('admin.filters.dateTo')}
            minDate={dateFrom ? new Date(dateFrom) : undefined}
          />
        </div>

        {isSuperAdmin && (
          <div className="space-y-2">
            <Label>{t('admin.filters.organization')}</Label>
            <Select
              value={organizationFilter || 'all'}
              onValueChange={(value) => onOrganizationChange(value === 'all' ? undefined : value)}
            >
              <SelectTrigger>
                <SelectValue placeholder={t('admin.filters.allOrganizations')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t('admin.filters.allOrganizations')}</SelectItem>
                {organizations?.map((org) => (
                  <SelectItem key={org.id} value={org.id}>
                    {org.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>
    </div>
  )
}
