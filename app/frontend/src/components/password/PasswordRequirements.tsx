import { useTranslation } from 'react-i18next'
import { useWatch } from 'react-hook-form'
import type { Control, FieldValues, Path } from 'react-hook-form'
import { CheckCircle2, XCircle, Circle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { PASSWORD_REQUIREMENTS } from '@/lib/password-validation'

interface PasswordRequirementsProps<T extends FieldValues> {
  control: Control<T>
  name: Path<T>
  compact?: boolean
  className?: string
}

export function PasswordRequirements<T extends FieldValues>({
  control,
  name,
  compact = false,
  className,
}: PasswordRequirementsProps<T>) {
  const { t } = useTranslation('auth')
  const password = useWatch({ control, name }) as string | undefined

  const isEmpty = !password || password.length === 0

  return (
    <div
      className={cn('space-y-1', compact ? 'text-xs' : 'text-sm', className)}
      role="status"
      aria-live="polite"
    >
      <p className="text-muted-foreground font-medium">
        {t('passwordRequirements.title')}
      </p>
      <ul className="space-y-0.5">
        {PASSWORD_REQUIREMENTS.map((req) => {
          const isMet = !isEmpty && req.test(password ?? '')
          const isNeutral = isEmpty

          return (
            <li
              key={req.id}
              className={cn(
                'flex items-center gap-1.5',
                isNeutral && 'text-muted-foreground',
                !isNeutral && isMet && 'text-green-600 dark:text-green-500',
                !isNeutral && !isMet && 'text-destructive'
              )}
            >
              {isNeutral ? (
                <Circle className={cn('shrink-0', compact ? 'h-3 w-3' : 'h-4 w-4')} />
              ) : isMet ? (
                <CheckCircle2 className={cn('shrink-0', compact ? 'h-3 w-3' : 'h-4 w-4')} />
              ) : (
                <XCircle className={cn('shrink-0', compact ? 'h-3 w-3' : 'h-4 w-4')} />
              )}
              <span>{t(req.translationKey)}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
