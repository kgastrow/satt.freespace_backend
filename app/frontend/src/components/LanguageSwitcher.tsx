import { useTranslation } from 'react-i18next'
import { Languages } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { supportedLanguages, languageNames, type SupportedLanguage } from '@/i18n/config'

export function LanguageSwitcher() {
  const { i18n } = useTranslation()
  const currentLanguage = i18n.language as SupportedLanguage

  // Don't render if only one language is supported
  if (supportedLanguages.length <= 1) {
    return null
  }

  const changeLanguage = (language: SupportedLanguage) => {
    i18n.changeLanguage(language)
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className="gap-2">
          <Languages className="h-4 w-4" />
          <span className="uppercase">{currentLanguage}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {supportedLanguages.map((language) => (
          <DropdownMenuItem
            key={language}
            onClick={() => changeLanguage(language)}
            className={currentLanguage === language ? 'bg-accent' : ''}
          >
            <span className="uppercase mr-2">{language}</span>
            {languageNames[language]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
