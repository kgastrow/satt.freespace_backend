import { useCallback } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  setDisplayMode as setDisplayModeAction,
  setLanguage as setLanguageAction,
  setSidebarCollapsed as setSidebarCollapsedAction,
  toggleSidebar as toggleSidebarAction,
  setTableColumnVisibility as setTableColumnVisibilityAction,
  type DisplayMode,
} from './preferencesSlice'
import { useTheme } from 'next-themes'
import { useTranslation } from 'react-i18next'

export interface UsePreferencesReturn {
  displayMode: DisplayMode
  language: string
  sidebarCollapsed: boolean
  tableColumns: Record<string, string[]>
  setDisplayMode: (mode: DisplayMode) => void
  setLanguage: (lang: string) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleSidebar: () => void
  setTableColumnVisibility: (tableId: string, columns: string[]) => void
  getTableColumnVisibility: (tableId: string, defaultColumns: string[]) => string[]
}

/**
 * Unified hook for accessing and modifying user preferences.
 *
 * This hook provides a single API for managing all user preferences:
 * - displayMode (theme): Syncs with next-themes
 * - language: Syncs with i18next
 * - sidebarCollapsed: Persisted via localStorage
 *
 * Changes made through this hook will update both Redux state and the
 * underlying library (next-themes/i18next) ensuring consistency.
 */
export function usePreferences(): UsePreferencesReturn {
  const dispatch = useAppDispatch()
  const { setTheme } = useTheme()
  const { i18n } = useTranslation()

  const { displayMode, language, sidebarCollapsed, tableColumns } = useAppSelector(
    (state) => state.preferences
  )

  const setDisplayMode = useCallback(
    (mode: DisplayMode) => {
      dispatch(setDisplayModeAction(mode))
      // Sync to next-themes
      setTheme(mode)
    },
    [dispatch, setTheme]
  )

  const setLanguage = useCallback(
    (lang: string) => {
      dispatch(setLanguageAction(lang))
      // Sync to i18next
      i18n.changeLanguage(lang)
    },
    [dispatch, i18n]
  )

  const setSidebarCollapsed = useCallback(
    (collapsed: boolean) => {
      dispatch(setSidebarCollapsedAction(collapsed))
    },
    [dispatch]
  )

  const toggleSidebar = useCallback(() => {
    dispatch(toggleSidebarAction())
  }, [dispatch])

  const setTableColumnVisibility = useCallback(
    (tableId: string, columns: string[]) => {
      dispatch(setTableColumnVisibilityAction({ tableId, columns }))
    },
    [dispatch]
  )

  const getTableColumnVisibility = useCallback(
    (tableId: string, defaultColumns: string[]) => {
      return tableColumns[tableId] || defaultColumns
    },
    [tableColumns]
  )

  return {
    displayMode,
    language,
    sidebarCollapsed,
    tableColumns,
    setDisplayMode,
    setLanguage,
    setSidebarCollapsed,
    toggleSidebar,
    setTableColumnVisibility,
    getTableColumnVisibility,
  }
}
