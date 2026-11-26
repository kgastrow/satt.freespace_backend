import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { featureFlagsApi } from './featureFlagsApi'

export interface FeatureFlagsState {
  flags: Record<string, boolean>
  isLoaded: boolean
}

const initialState: FeatureFlagsState = {
  flags: {},
  isLoaded: false,
}

const featureFlagsSlice = createSlice({
  name: 'featureFlags',
  initialState,
  reducers: {
    /**
     * Set feature flags directly
     */
    setFeatureFlags: (state, action: PayloadAction<Record<string, boolean>>) => {
      state.flags = action.payload
      state.isLoaded = true
    },

    /**
     * Clear feature flags (e.g., on logout)
     */
    clearFeatureFlags: (state) => {
      state.flags = {}
      state.isLoaded = false
    },
  },
  extraReducers: (builder) => {
    // Sync flags to Redux state when resolved flags are fetched
    builder.addMatcher(
      featureFlagsApi.endpoints.getResolvedFeatureFlags.matchFulfilled,
      (state, action) => {
        state.flags = action.payload.flags
        state.isLoaded = true
      }
    )

    // Clear flags on error
    builder.addMatcher(
      featureFlagsApi.endpoints.getResolvedFeatureFlags.matchRejected,
      (state) => {
        state.flags = {}
        state.isLoaded = false
      }
    )
  },
})

export const { setFeatureFlags, clearFeatureFlags } = featureFlagsSlice.actions
export default featureFlagsSlice.reducer
