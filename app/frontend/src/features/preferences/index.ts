export { default as preferencesReducer } from './preferencesSlice'
export {
  setDisplayMode,
  setLanguage,
  setSidebarCollapsed,
  toggleSidebar,
  setPwaInstallDismissed,
  syncFromExternal,
  type DisplayMode,
  type PreferencesState,
} from './preferencesSlice'
export { usePreferences, type UsePreferencesReturn } from './usePreferences'
export { usePreferencesSync, PreferencesSync } from './usePreferencesSync'
