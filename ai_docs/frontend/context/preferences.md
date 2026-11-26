# User Preferences Store

Redux store for user preferences with localStorage persistence. Maintains bidirectional sync with next-themes (theming) and i18next (language).

## Key Files

- `preferencesSlice.ts` - Redux slice with state, actions, and persistence
- `usePreferences.ts` - Consumer hook for components
- `usePreferencesSync.ts` - Sync hook and `PreferencesSync` component

## State Shape

```typescript
interface PreferencesState {
  displayMode: 'light' | 'dark' | 'system'
  language: string
  sidebarCollapsed: boolean
  tableColumns: Record<string, string[]>  // Column visibility by table ID
  pwaInstallDismissed: boolean
}
```

## Usage

```typescript
import { usePreferences } from '@/features/preferences'

function MyComponent() {
  const {
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
  } = usePreferences()

  return <button onClick={() => setDisplayMode('dark')}>Dark Mode</button>
}
```

### Required Setup

`PreferencesSync` must wrap the app inside both `ThemeProvider` and Redux `Provider`:

```tsx
<ThemeProvider>
  <Provider store={store}>
    <PreferencesSync>
      <App />
    </PreferencesSync>
  </Provider>
</ThemeProvider>
```

## Storage

All preferences stored under `user_preferences` localStorage key.

**Migration**: On first load, migrates from legacy sources (`theme`, `i18nextLng`, `sidebar_state` cookie).

## Sync Behavior

- **External to Redux**: `usePreferencesSync` listens to `useTheme()` and `i18n.on('languageChanged')`, updates Redux via `syncFromExternal` (no re-persistence to avoid loops)
- **Redux to External**: `setDisplayMode` calls `setTheme()`, `setLanguage` calls `i18n.changeLanguage()`

## Adding New Preferences

1. Add property to `PreferencesState` with default in `getInitialState()`
2. Create action in `reducers` that calls `persistToStorage`
3. Export action from slice and `index.ts`
4. Add getter/setter to `usePreferences` hook
