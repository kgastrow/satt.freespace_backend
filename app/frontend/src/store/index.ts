import { configureStore } from '@reduxjs/toolkit'
import { setupListeners } from '@reduxjs/toolkit/query'
import { enableMapSet } from 'immer'
import { api } from './api'
import authReducer from '@/features/auth/authSlice'
import impersonationReducer from '@/features/impersonation/impersonationSlice'
import websocketReducer from '@/features/websocket/websocketSlice'
import inAppNotificationsReducer from '@/features/in-app-notifications/inAppNotificationsSlice'
import announcementsReducer from '@/features/announcements/announcementsSlice'
import featureFlagsReducer from '@/features/featureFlags/featureFlagsSlice'
import maintenanceReducer from '@/features/maintenance/maintenanceSlice'
import preferencesReducer from '@/features/preferences/preferencesSlice'
import changelogReducer from '@/features/changelog/changelogSlice'
import { authMiddleware } from './authMiddleware'

// Enable Immer support for Map and Set objects in Redux state
enableMapSet()

export const store = configureStore({
  reducer: {
    [api.reducerPath]: api.reducer,
    auth: authReducer,
    impersonation: impersonationReducer,
    websocket: websocketReducer,
    inAppNotifications: inAppNotificationsReducer,
    announcements: announcementsReducer,
    featureFlags: featureFlagsReducer,
    maintenance: maintenanceReducer,
    preferences: preferencesReducer,
    changelog: changelogReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore Set objects in announcements state - Immer's enableMapSet() handles these
        ignoredPaths: ['announcements.locallyDismissedIds'],
        ignoredActions: [],
      },
    }).concat(api.middleware, authMiddleware),
})

setupListeners(store.dispatch)

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
