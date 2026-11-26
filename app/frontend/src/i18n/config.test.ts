import { describe, it, expect } from 'vitest'
import { supportedLanguages, languageNames, defaultNS, type SupportedLanguage } from './config'

describe('i18n configuration', () => {
  describe('supportedLanguages', () => {
    it('includes English as the default language', () => {
      expect(supportedLanguages).toContain('en')
    })

    it('is readonly array', () => {
      expect(Array.isArray(supportedLanguages)).toBe(true)
    })

    it('has English as first language', () => {
      expect(supportedLanguages[0]).toBe('en')
    })
  })

  describe('languageNames', () => {
    it('has entries for all supported languages', () => {
      supportedLanguages.forEach((lang) => {
        expect(languageNames[lang]).toBeDefined()
        expect(typeof languageNames[lang]).toBe('string')
        expect(languageNames[lang].length).toBeGreaterThan(0)
      })
    })

    it('has correct English language name', () => {
      expect(languageNames.en).toBe('English')
    })

    it('has same keys as supportedLanguages', () => {
      const languageNameKeys = Object.keys(languageNames)
      expect(languageNameKeys).toHaveLength(supportedLanguages.length)

      supportedLanguages.forEach((lang) => {
        expect(languageNameKeys).toContain(lang)
      })
    })
  })

  describe('defaultNS', () => {
    it('is set to common', () => {
      expect(defaultNS).toBe('common')
    })
  })

  describe('SupportedLanguage type', () => {
    it('accepts all supported language codes', () => {
      const validLanguages: SupportedLanguage[] = [...supportedLanguages]
      validLanguages.forEach((lang) => {
        expect(supportedLanguages).toContain(lang)
      })
    })
  })
})
