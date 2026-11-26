import { createSlice } from '@reduxjs/toolkit'
import type { ImpersonationState } from '@/types/impersonation'
import { impersonationApi } from './impersonationApi'

const initialState: ImpersonationState = {
  isImpersonating: false,
  originalUser: null,
  targetUser: null,
  sessionId: null,
  sessionStartedAt: null,
  originalToken: null,
  originalRefreshToken: null,
}

const impersonationSlice = createSlice({
  name: 'impersonation',
  initialState,
  reducers: {
    /**
     * Clear impersonation state
     */
    clearImpersonation: (state) => {
      state.isImpersonating = false
      state.originalUser = null
      state.targetUser = null
      state.sessionId = null
      state.sessionStartedAt = null
      state.originalToken = null
      state.originalRefreshToken = null
    },
  },
  extraReducers: (builder) => {
    // Handle successful impersonation start
    builder.addMatcher(
      impersonationApi.endpoints.startImpersonation.matchFulfilled,
      (state, action) => {
        // Set impersonation state - original token kept in Redux only (in-memory)
        // On page refresh, AuthProvider calls /auth/refresh (admin cookie) then /resume
        state.isImpersonating = true
        state.sessionId = action.payload.session.id
        state.sessionStartedAt = action.payload.session.created_time
        state.targetUser = null
      }
    )

    // Handle successful impersonation end
    builder.addMatcher(
      impersonationApi.endpoints.endImpersonation.matchFulfilled,
      (state) => {
        state.isImpersonating = false
        state.originalUser = null
        state.targetUser = null
        state.sessionId = null
        state.sessionStartedAt = null
        state.originalToken = null
        state.originalRefreshToken = null
      }
    )

    // Handle getCurrentSession to restore impersonation state on page refresh
    builder.addMatcher(
      impersonationApi.endpoints.getCurrentSession.matchFulfilled,
      (state, action) => {
        if (action.payload.active && action.payload.session) {
          state.isImpersonating = true
          state.sessionId = action.payload.session.id
          state.sessionStartedAt = action.payload.session.created_time
        }
      }
    )
  },
})

export const { clearImpersonation } = impersonationSlice.actions

export default impersonationSlice.reducer
