import { useTranslation } from 'react-i18next'
import { Check } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Label } from '@/components/ui/label'
import { supportedLanguages, languageNames, type SupportedLanguage } from '@/i18n/config'
import { cn } from '@/lib/utils'

export function LanguagePage() {
  const { t, i18n } = useTranslation(['settings'])
  const currentLanguage = i18n.language as SupportedLanguage

  const handleLanguageChange = (language: string) => {
    i18n.changeLanguage(language)
  }

  return (
    <div className="max-w-2xl space-y-6">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('settings:language.sections.language.title')}</CardTitle>
          <CardDescription>{t('settings:language.sections.language.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <RadioGroup
            value={currentLanguage}
            onValueChange={handleLanguageChange}
            className="space-y-2"
          >
            {supportedLanguages.map((language) => (
              <div
                key={language}
                className={cn(
                  'flex cursor-pointer items-center justify-between rounded-lg border p-4 transition-all hover:border-primary/50',
                  currentLanguage === language && 'border-primary bg-primary/5'
                )}
                onClick={() => handleLanguageChange(language)}
              >
                <div className="flex items-center gap-4">
                  <RadioGroupItem value={language} id={language} />
                  <Label htmlFor={language} className="flex cursor-pointer items-center gap-3">
                    <span className="rounded bg-muted px-2 py-1 font-mono text-xs uppercase">
                      {language}
                    </span>
                    <span className="font-medium">{languageNames[language]}</span>
                  </Label>
                </div>
                {currentLanguage === language && <Check className="h-5 w-5 text-primary" />}
              </div>
            ))}
          </RadioGroup>
        </CardContent>
      </Card>
    </div>
  )
}
