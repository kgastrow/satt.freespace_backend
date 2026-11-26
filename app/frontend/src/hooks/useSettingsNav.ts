import { useMemo } from 'react'
import {
  settingsNavConfig,
  filterSettingsNav,
  type SettingsNavCategory,
  type SettingsVisibilityFlags,
} from '@/config/settingsNav'
import { useGetTwoFactorPolicyQuery } from '@/store/api/twoFactorApi'
import { useAppSelector } from '@/store/hooks'
import { supportedLanguages } from '@/i18n/config'

/**
 * Hook that provides filtered settings navigation based on user's organization settings.
 * Automatically hides items that the user shouldn't see (e.g., 2FA when disabled for org).
 */
export function useSettingsNav(): {
  navConfig: SettingsNavCategory[]
  isLoading: boolean
  twoFactorPolicy: ReturnType<typeof useGetTwoFactorPolicyQuery>['data']
} {
  const { isAuthenticated } = useAppSelector((state) => state.auth)

  // Only fetch policy if authenticated
  const { data: twoFactorPolicy, isLoading } = useGetTwoFactorPolicyQuery(undefined, {
    skip: !isAuthenticated,
  })

  const navConfig = useMemo(() => {
    // Build visibility flags based on fetched data and config
    const flags: SettingsVisibilityFlags = {
      twoFactorAvailable: twoFactorPolicy?.two_factor_available ?? false,
      multipleLanguagesAvailable: supportedLanguages.length > 1,
    }

    return filterSettingsNav(settingsNavConfig, flags)
  }, [twoFactorPolicy])

  return {
    navConfig,
    isLoading,
    twoFactorPolicy,
  }
}
