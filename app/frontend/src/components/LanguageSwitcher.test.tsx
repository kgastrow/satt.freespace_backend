import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { LanguageSwitcher } from './LanguageSwitcher'
import { supportedLanguages, languageNames } from '@/i18n/config'

describe('LanguageSwitcher', () => {
  describe('with single language', () => {
    it('returns null when only one language is supported', () => {
      // With only English configured, the component should not render
      if (supportedLanguages.length <= 1) {
        const { container } = render(<LanguageSwitcher />)
        expect(container.firstChild).toBeNull()
      }
    })
  })

  describe('with multiple languages', () => {
    // These tests are for when multiple languages are configured
    // Skip if only one language is supported
    const skipIfSingleLanguage = supportedLanguages.length <= 1

    it.skipIf(skipIfSingleLanguage)('renders language button with current language', () => {
      render(<LanguageSwitcher />)
      expect(screen.getByText('en')).toBeInTheDocument()
    })

    it.skipIf(skipIfSingleLanguage)('opens dropdown menu when clicked', async () => {
      const { user } = render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        supportedLanguages.forEach((lang) => {
          expect(screen.getByText(languageNames[lang])).toBeInTheDocument()
        })
      })
    })

    it.skipIf(skipIfSingleLanguage)('renders Languages icon', () => {
      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      expect(button.querySelector('svg')).toBeInTheDocument()
    })
  })
})
