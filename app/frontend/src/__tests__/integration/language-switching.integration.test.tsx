import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { supportedLanguages, languageNames } from '@/i18n/config'

/**
 * Integration tests for language switching functionality
 *
 * Note: The template ships with English only. When additional languages
 * are added, uncomment and update the multi-language tests below.
 *
 * To add language tests:
 * 1. Add the language to supportedLanguages in i18n/config.ts
 * 2. Create the locale directory with translations
 * 3. Update tests to verify the new language appears
 */
describe('Language Switching Integration', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  describe('Single Language Configuration (English Only)', () => {
    it('does not render language switcher when only one language is configured', () => {
      if (supportedLanguages.length === 1) {
        const { container } = render(<LanguageSwitcher />)
        expect(container.firstChild).toBeNull()
      }
    })

    it('has English as the only supported language', () => {
      expect(supportedLanguages).toContain('en')
      expect(languageNames.en).toBe('English')
    })

    it('uses English as fallback language', () => {
      // Fallback language is configured in i18n/config.ts
      expect(supportedLanguages[0]).toBe('en')
    })
  })

  describe('Multi-Language Configuration', () => {
    // These tests only run when multiple languages are configured
    const hasMultipleLanguages = supportedLanguages.length > 1

    it.skipIf(!hasMultipleLanguages)('displays all supported languages in dropdown', async () => {
      const { user } = render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        supportedLanguages.forEach((lang) => {
          expect(screen.getByText(languageNames[lang])).toBeInTheDocument()
        })
      })
    })

    it.skipIf(!hasMultipleLanguages)('highlights currently selected language', async () => {
      const { user } = render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        const englishOption = screen.getByText('English').closest('div')
        expect(englishOption).toHaveClass('bg-accent')
      })
    })

    it.skipIf(!hasMultipleLanguages)('shows current language code in button', () => {
      render(<LanguageSwitcher />)
      expect(screen.getByText('en')).toBeInTheDocument()
    })

    it.skipIf(!hasMultipleLanguages)('renders Languages icon', () => {
      render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      const icon = button.querySelector('svg')
      expect(icon).toBeInTheDocument()
    })

    it.skipIf(!hasMultipleLanguages)('matches supportedLanguages array length', async () => {
      const { user } = render(<LanguageSwitcher />)

      const button = screen.getByRole('button')
      await user.click(button)

      await waitFor(() => {
        const menuItems = screen.getAllByRole('menuitem')
        expect(menuItems).toHaveLength(supportedLanguages.length)
      })
    })

    it.skipIf(!hasMultipleLanguages)('is keyboard accessible', async () => {
      const { user } = render(<LanguageSwitcher />)

      const button = screen.getByRole('button')

      await user.tab()
      expect(button).toHaveFocus()

      await user.keyboard('{Enter}')

      await waitFor(() => {
        expect(screen.getByText('English')).toBeInTheDocument()
      })
    })
  })
})
