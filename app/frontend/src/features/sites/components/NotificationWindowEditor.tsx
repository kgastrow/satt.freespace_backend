import { useTranslation } from 'react-i18next'
import { Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { NotificationWindowRule } from '@/types/site'
import {
  MAX_NOTIFICATION_RULES,
  WEEKDAYS,
  addRule,
  removeRule,
  toggleWeekday,
  updateRule,
  validateWindow,
} from '../notificationWindow'

interface NotificationWindowEditorProps {
  value: NotificationWindowRule[]
  onChange: (rules: NotificationWindowRule[]) => void
  disabled?: boolean
}

const WEEKDAY_KEYS: Record<number, string> = {
  1: 'mon',
  2: 'tue',
  3: 'wed',
  4: 'thu',
  5: 'fri',
  6: 'sat',
  7: 'sun',
}

/**
 * Notification window: a list of {weekdays, start, end} in site local time.
 * An empty list means "any time". Overnight spans are not supported.
 */
export function NotificationWindowEditor({
  value,
  onChange,
  disabled,
}: NotificationWindowEditorProps) {
  const { t } = useTranslation('sites')
  const validation = validateWindow(value)

  return (
    <div className="space-y-3" data-testid="notification-window-editor">
      {value.length === 0 && (
        <p className="text-sm text-muted-foreground">{t('settings.window.anyTime')}</p>
      )}

      {value.map((rule, index) => {
        const error = validation.rules[index]
        return (
          <div key={index} className="space-y-2 rounded-md border p-3">
            <div className="flex flex-wrap items-end gap-4">
              <div className="space-y-1">
                <Label>{t('settings.window.weekdays')}</Label>
                <div
                  role="group"
                  aria-label={t('settings.window.weekdays')}
                  className="flex flex-wrap gap-1"
                >
                  {WEEKDAYS.map((day) => {
                    const selected = rule.weekdays.includes(day)
                    return (
                      <Button
                        key={day}
                        type="button"
                        size="sm"
                        variant={selected ? 'default' : 'outline'}
                        aria-pressed={selected}
                        disabled={disabled}
                        onClick={() => onChange(updateRule(value, index, toggleWeekday(rule, day)))}
                      >
                        {t(`settings.window.days.${WEEKDAY_KEYS[day]}`)}
                      </Button>
                    )
                  })}
                </div>
              </div>
              <div className="space-y-1">
                <Label htmlFor={`window-start-${index}`}>{t('settings.window.start')}</Label>
                <Input
                  id={`window-start-${index}`}
                  type="time"
                  value={rule.start}
                  disabled={disabled}
                  onChange={(e) => onChange(updateRule(value, index, { start: e.target.value }))}
                  className="w-32"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor={`window-end-${index}`}>{t('settings.window.end')}</Label>
                <Input
                  id={`window-end-${index}`}
                  type="time"
                  value={rule.end}
                  disabled={disabled}
                  onChange={(e) => onChange(updateRule(value, index, { end: e.target.value }))}
                  className="w-32"
                />
              </div>
              {!disabled && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={t('settings.window.remove')}
                  onClick={() => onChange(removeRule(value, index))}
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              )}
            </div>
            {error && (
              <p role="alert" className={cn('text-sm text-destructive')}>
                {t(`validation.window.${error}`)}
              </p>
            )}
          </div>
        )
      })}

      {validation.list && (
        <p role="alert" className="text-sm text-destructive">
          {t('validation.tooManyRules', { max: MAX_NOTIFICATION_RULES })}
        </p>
      )}

      {!disabled && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={value.length >= MAX_NOTIFICATION_RULES}
          onClick={() => onChange(addRule(value))}
        >
          <Plus className="mr-2 h-4 w-4" />
          {t('settings.window.add')}
        </Button>
      )}
    </div>
  )
}
