import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '@/store'

// Base selectors (not memoized, just extract state slice)
const selectAuthState = (state: RootState) => state.auth

// Memoized auth selectors
export const selectUser = createSelector(
  selectAuthState,
  (auth) => auth.user
)

export const selectToken = createSelector(
  selectAuthState,
  (auth) => auth.token
)

export const selectIsAuthenticated = createSelector(
  selectAuthState,
  (auth) => auth.isAuthenticated
)

export const selectIsLoading = createSelector(
  selectAuthState,
  (auth) => auth.isLoading
)

export const selectTwoFactor = createSelector(
  selectAuthState,
  (auth) => auth.twoFactor
)

export const selectTwoFactorSetupRequired = createSelector(
  selectAuthState,
  (auth) => auth.twoFactorSetupRequired
)

export const selectEnforcementActive = createSelector(
  selectAuthState,
  (auth) => auth.enforcementActive
)

export const selectSSOState = createSelector(
  selectAuthState,
  (auth) => auth.sso
)

// Derived selectors
export const selectUserPermissions = createSelector(
  selectUser,
  (user) => user?.permissions ?? []
)

export const selectUserRoles = createSelector(
  selectUser,
  (user) => user?.roles ?? []
)

export const selectIsAdmin = createSelector(
  selectUser,
  (user) => user?.is_admin ?? false
)

export const selectOrganizationId = createSelector(
  selectUser,
  (user) => user?.organization_id ?? null
)

export const selectRequiresTwoFactor = createSelector(
  selectTwoFactor,
  (twoFactor) => twoFactor?.required ?? false
)

// Parameterized selector for checking specific permission
export const selectHasPermission = createSelector(
  [selectUserPermissions, (_state: RootState, permission: string) => permission],
  (permissions, permission) => permissions.includes(permission)
)

// Parameterized selector for checking multiple permissions (any)
export const selectHasAnyPermission = createSelector(
  [
    selectUserPermissions,
    (_state: RootState, permissions: string[]) => permissions,
  ],
  (userPermissions, requiredPermissions) =>
    requiredPermissions.some((p) => userPermissions.includes(p))
)

// Parameterized selector for checking multiple permissions (all)
export const selectHasAllPermissions = createSelector(
  [
    selectUserPermissions,
    (_state: RootState, permissions: string[]) => permissions,
  ],
  (userPermissions, requiredPermissions) =>
    requiredPermissions.every((p) => userPermissions.includes(p))
)
