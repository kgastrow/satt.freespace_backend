import { useTheme } from 'next-themes'
import { useTranslation } from 'react-i18next'
import { Sun, Moon, Monitor, Check } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const themeOptions = ['light', 'dark', 'system'] as const
type ThemeOption = (typeof themeOptions)[number]

const themeIcons: Record<ThemeOption, typeof Sun> = {
  light: Sun,
  dark: Moon,
  system: Monitor,
}

interface ThemeCardProps {
  value: ThemeOption
  selected: boolean
  onSelect: () => void
  label: string
}

function ThemeCard({ value, selected, onSelect, label }: ThemeCardProps) {
  const Icon = themeIcons[value]

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'relative flex flex-col items-center gap-3 rounded-lg border-2 p-4 transition-all hover:border-primary/50',
        selected ? 'border-primary bg-primary/5' : 'border-muted'
      )}
    >
      {/* Preview area - intentionally uses hardcoded colors for theme preview visualization */}
      <div
        className={cn(
          'flex h-20 w-full items-center justify-center rounded-md border',
          value === 'light' && 'bg-[oklch(1_0_0)]',
          value === 'dark' && 'bg-[oklch(0.145_0_0)]',
          value === 'system' && 'bg-gradient-to-r from-[oklch(1_0_0)] to-[oklch(0.145_0_0)]'
        )}
      >
        <Icon
          className={cn(
            'h-8 w-8',
            value === 'light' && 'text-[oklch(0.145_0_0)]',
            value === 'dark' && 'text-[oklch(0.985_0_0)]',
            value === 'system' && 'text-muted-foreground'
          )}
        />
      </div>

      {/* Label */}
      <span className="text-sm font-medium">{label}</span>

      {/* Selected indicator */}
      {selected && (
        <div className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-primary">
          <Check className="h-3 w-3 text-primary-foreground" />
        </div>
      )}
    </button>
  )
}

export function AppearancePage() {
  const { t } = useTranslation(['settings', 'common'])
  const { theme, setTheme } = useTheme()

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('settings:appearance.sections.theme.title')}</CardTitle>
          <CardDescription>{t('settings:appearance.sections.theme.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            {themeOptions.map((option) => (
              <ThemeCard
                key={option}
                value={option}
                selected={theme === option}
                onSelect={() => setTheme(option)}
                label={t(`common:theme.${option}`)}
              />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
