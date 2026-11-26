import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import { maintenanceApi } from './maintenanceApi'

export interface MaintenanceState {
  isMaintenanceActive: boolean
  scheduledEnd: string | null
  message: string | null
  lastChecked: number | null
}

const initialState: MaintenanceState = {
  isMaintenanceActive: false,
  scheduledEnd: null,
  message: null,
  lastChecked: null,
}

const maintenanceSlice = createSlice({
  name: 'maintenance',
  initialState,
  reducers: {
    updateMaintenanceStatus: (
      state,
      action: PayloadAction<{
        enabled: boolean
        scheduledEnd: string | null
        message: string | null
      }>
    ) => {
      state.isMaintenanceActive = action.payload.enabled
      state.scheduledEnd = action.payload.scheduledEnd
      state.message = action.payload.message
      state.lastChecked = Date.now()
    },
    clearMaintenanceStatus: (state) => {
      state.isMaintenanceActive = false
      state.scheduledEnd = null
      state.message = null
      state.lastChecked = null
    },
  },
  extraReducers: (builder) => {
    builder.addMatcher(
      maintenanceApi.endpoints.getMaintenanceStatus.matchFulfilled,
      (state, action) => {
        state.isMaintenanceActive = action.payload.enabled
        state.scheduledEnd = action.payload.scheduled_end
        state.message = action.payload.message
        state.lastChecked = Date.now()
      }
    )

    builder.addMatcher(
      maintenanceApi.endpoints.updateMaintenance.matchFulfilled,
      (state, action) => {
        state.isMaintenanceActive = action.payload.config.enabled
        state.scheduledEnd = action.payload.config.scheduled_end
        state.message = action.payload.config.message
        state.lastChecked = Date.now()
      }
    )
  },
})

export const { updateMaintenanceStatus, clearMaintenanceStatus } = maintenanceSlice.actions
export default maintenanceSlice.reducer
