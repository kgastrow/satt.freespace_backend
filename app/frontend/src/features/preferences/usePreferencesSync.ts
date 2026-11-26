import { useEffect, useRef } from 'react'
import { useTheme } from 'next-themes'
import { useTranslation } from 'react-i18next'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { syncFromExternal, type DisplayMode } from './preferencesSlice'

/**
 * Hook that synchronizes external library state (next-themes, i18next) to Redux.
 *
 * This creates bidirectional sync:
 * - External → Redux: This hook watches for changes in next-themes and i18next
 *   and updates Redux state via syncFromExternal (doesn't re-persist to avoid loops)
 * - Redux → External: The usePreferences hook updates external libraries when
 *   preferences are changed through Redux actions
 *
 * Must be used once at the app root level, inside both ThemeProvider and Redux Provider.
 */
export function usePreferencesSync(): void {
  const dispatch = useAppDispatch()
  const { theme, resolvedTheme } = useTheme()
  const { i18n } = useTranslation()

  const reduxDisplayMode = useAppSelector((state) => state.preferences.displayMode)
  const reduxLanguage = useAppSelector((state) => state.preferences.language)

  // Track previous values to detect external changes
  const prevThemeRef = useRef<string | undefined>(theme)
  const prevLanguageRef = useRef<string>(i18n.language)

  // Sync theme changes from next-themes to Redux
  useEffect(() => {
    // Skip if theme hasn't actually changed
    if (theme === prevThemeRef.current) return

    prevThemeRef.current = theme

    // Only sync if the theme differs from Redux state
    // This prevents unnecessary updates when we set the theme from Redux
    if (theme && theme !== reduxDisplayMode) {
      dispatch(syncFromExternal({ displayMode: theme as DisplayMode }))
    }
  }, [theme, reduxDisplayMode, dispatch])

  // Sync language changes from i18next to Redux
  useEffect(() => {
    const handleLanguageChanged = (lang: string) => {
      // Skip if it's the same as what Redux has
      if (lang === reduxLanguage) return

      prevLanguageRef.current = lang
      dispatch(syncFromExternal({ language: lang }))
    }

    i18n.on('languageChanged', handleLanguageChanged)

    // Initial sync if different
    if (i18n.language !== reduxLanguage && i18n.language !== prevLanguageRef.current) {
      handleLanguageChanged(i18n.language)
    }

    return () => {
      i18n.off('languageChanged', handleLanguageChanged)
    }
  }, [i18n, reduxLanguage, dispatch])

  // On mount, sync initial library state to Redux if they differ
  // This handles the case where next-themes/i18next loaded from their own storage
  useEffect(() => {
    // Use resolved theme for the actual value being used
    const effectiveTheme = theme || resolvedTheme

    if (effectiveTheme && effectiveTheme !== reduxDisplayMode) {
      dispatch(syncFromExternal({ displayMode: effectiveTheme as DisplayMode }))
    }

    if (i18n.language && i18n.language !== reduxLanguage) {
      dispatch(syncFromExternal({ language: i18n.language }))
    }
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}

/**
 * Component wrapper that sets up preferences synchronization.
 * Place this inside both ThemeProvider and Redux Provider.
 */
export function PreferencesSync({ children }: { children: React.ReactNode }): React.ReactNode {
  usePreferencesSync()
  return children
}
