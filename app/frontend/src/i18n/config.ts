import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import resourcesToBackend from 'i18next-resources-to-backend'

export const defaultNS = 'common'

/**
 * Supported languages configuration.
 *
 * To add a new language:
 * 1. Add the language code to supportedLanguages array (e.g., 'de', 'fr', 'es')
 * 2. Add the display name to languageNames
 * 3. Create a new directory under src/locales/{code}/
 * 4. Copy all JSON files from src/locales/en/ to the new directory
 * 5. Translate all strings in each JSON file
 * 6. Add the language code to the 'preload' array below
 *
 * The LanguageSwitcher component will automatically show when multiple languages are available.
 */
export const supportedLanguages = ['en'] as const
export type SupportedLanguage = (typeof supportedLanguages)[number]

export const languageNames: Record<SupportedLanguage, string> = {
  en: 'English',
}

// Lazy loading backend - namespaces are loaded on-demand
const lazyLoadResources = resourcesToBackend(
  (language: string, namespace: string) =>
    import(`../locales/${language}/${namespace}.json`)
)

i18n
  .use(lazyLoadResources)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    defaultNS,
    supportedLngs: supportedLanguages,
    ns: ['common', 'auth', 'dashboard', 'files', 'admin', 'platformAdmin', 'errors', 'settings', 'backend', 'push', 'sites'],
    interpolation: {
      escapeValue: false,
    },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'i18nextLng',
    },
    react: {
      useSuspense: true,
    },
    // Preload only common namespace for initial render
    preload: supportedLanguages as unknown as string[],
    load: 'currentOnly',
  })

export default i18n
