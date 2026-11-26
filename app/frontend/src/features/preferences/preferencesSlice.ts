import { createSlice, type PayloadAction } from '@reduxjs/toolkit'

export type DisplayMode = 'light' | 'dark' | 'system'

export interface PreferencesState {
  displayMode: DisplayMode
  language: string
  sidebarCollapsed: boolean
  /** Table column visibility settings, keyed by table ID */
  tableColumns: Record<string, string[]>
  /** Whether the PWA install banner has been permanently dismissed */
  pwaInstallDismissed: boolean
}

const STORAGE_KEY = 'user_preferences'

/**
 * Read initial state from existing storage sources:
 * - next-themes stores theme in localStorage under 'theme'
 * - i18next stores language in localStorage under 'i18nextLng'
 * - sidebar previously used cookies, now check our preferences store
 */
function getInitialState(): PreferencesState {
  const defaults: PreferencesState = {
    displayMode: 'system',
    language: 'en',
    sidebarCollapsed: false,
    tableColumns: {},
    pwaInstallDismissed: false,
  }

  if (typeof window === 'undefined') {
    return defaults
  }

  try {
    // First try to load from our preferences store
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed = JSON.parse(stored) as Partial<PreferencesState>
      return {
        displayMode: parsed.displayMode ?? defaults.displayMode,
        language: parsed.language ?? defaults.language,
        sidebarCollapsed: parsed.sidebarCollapsed ?? defaults.sidebarCollapsed,
        tableColumns: parsed.tableColumns ?? defaults.tableColumns,
        pwaInstallDismissed: parsed.pwaInstallDismissed ?? defaults.pwaInstallDismissed,
      }
    }

    // Fall back to reading from existing sources for migration
    const themeValue = localStorage.getItem('theme')
    const i18nValue = localStorage.getItem('i18nextLng')

    // Check old sidebar cookie
    let sidebarFromCookie = defaults.sidebarCollapsed
    const sidebarCookie = document.cookie
      .split('; ')
      .find((row) => row.startsWith('sidebar_state='))
    if (sidebarCookie) {
      sidebarFromCookie = sidebarCookie.split('=')[1] !== 'true'
    }

    return {
      displayMode: (themeValue as DisplayMode) ?? defaults.displayMode,
      language: i18nValue ?? defaults.language,
      sidebarCollapsed: sidebarFromCookie,
      tableColumns: {},
      pwaInstallDismissed: false,
    }
  } catch {
    return defaults
  }
}

function persistToStorage(state: PreferencesState): void {
  if (typeof window === 'undefined') return

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // Storage might be full or disabled
  }
}

const preferencesSlice = createSlice({
  name: 'preferences',
  initialState: getInitialState,
  reducers: {
    setDisplayMode: (state, action: PayloadAction<DisplayMode>) => {
      state.displayMode = action.payload
      persistToStorage(state)
    },
    setLanguage: (state, action: PayloadAction<string>) => {
      state.language = action.payload
      persistToStorage(state)
    },
    setSidebarCollapsed: (state, action: PayloadAction<boolean>) => {
      state.sidebarCollapsed = action.payload
      persistToStorage(state)
    },
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed
      persistToStorage(state)
    },
    /**
     * Set column visibility for a specific table
     */
    setTableColumnVisibility: (
      state,
      action: PayloadAction<{ tableId: string; columns: string[] }>
    ) => {
      state.tableColumns[action.payload.tableId] = action.payload.columns
      persistToStorage(state)
    },
    setPwaInstallDismissed: (state, action: PayloadAction<boolean>) => {
      state.pwaInstallDismissed = action.payload
      persistToStorage(state)
    },
    /**
     * Sync action used by usePreferencesSync to update Redux state
     * without triggering persistence (to avoid loops)
     */
    syncFromExternal: (
      state,
      action: PayloadAction<Partial<Pick<PreferencesState, 'displayMode' | 'language'>>>
    ) => {
      if (action.payload.displayMode !== undefined) {
        state.displayMode = action.payload.displayMode
      }
      if (action.payload.language !== undefined) {
        state.language = action.payload.language
      }
      // Don't persist here - external sources are the source of truth for these
    },
  },
})

export const {
  setDisplayMode,
  setLanguage,
  setSidebarCollapsed,
  toggleSidebar,
  setTableColumnVisibility,
  setPwaInstallDismissed,
  syncFromExternal,
} = preferencesSlice.actions

export default preferencesSlice.reducer
