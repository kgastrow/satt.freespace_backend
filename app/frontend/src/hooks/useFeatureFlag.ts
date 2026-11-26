import { useAppSelector } from '@/store/hooks'
import { selectUser } from '@/features/auth/authSelectors'

/**
 * Hook to check if a feature flag is enabled for the current organization
 * @param flagKey - The key of the feature flag to check
 * @returns boolean indicating if the flag is enabled
 *
 * Users with is_admin=true or feature_flags:bypass permission will always see features as enabled
 */
export function useFeatureFlag(flagKey: string): boolean {
  const flags = useAppSelector((state) => state.featureFlags.flags)
  const user = useAppSelector(selectUser)

  // Super admins and users with bypass permission see all features as enabled
  if (user?.is_admin || user?.permissions?.includes('feature_flags:bypass')) {
    return true
  }

  return flags[flagKey] ?? false
}
