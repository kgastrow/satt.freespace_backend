import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '@/store'

// Base selector
const selectImpersonationState = (state: RootState) => state.impersonation

// Memoized impersonation selectors
export const selectIsImpersonating = createSelector(
  selectImpersonationState,
  (impersonation) => impersonation.isImpersonating
)

export const selectOriginalUser = createSelector(
  selectImpersonationState,
  (impersonation) => impersonation.originalUser
)

export const selectTargetUser = createSelector(
  selectImpersonationState,
  (impersonation) => impersonation.targetUser
)

export const selectSessionId = createSelector(
  selectImpersonationState,
  (impersonation) => impersonation.sessionId
)

export const selectSessionStartedAt = createSelector(
  selectImpersonationState,
  (impersonation) => impersonation.sessionStartedAt
)

// Derived selectors
export const selectImpersonationSession = createSelector(
  [selectSessionId, selectSessionStartedAt],
  (sessionId, sessionStartedAt) => {
    if (!sessionId) return null
    return {
      id: sessionId,
      startedAt: sessionStartedAt,
    }
  }
)

export const selectHasActiveSession = createSelector(
  [selectIsImpersonating, selectSessionId],
  (isImpersonating, sessionId) => isImpersonating && sessionId !== null
)
