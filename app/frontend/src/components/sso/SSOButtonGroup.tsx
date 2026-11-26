import { useGetEnabledSSOProvidersQuery } from '@/features/auth/ssoApi'
import { GoogleLoginButton } from './GoogleLoginButton'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface SSOButtonGroupProps {
  organizationSlug: string
}

export function SSOButtonGroup({ organizationSlug }: SSOButtonGroupProps) {
  const { data, isLoading, error } = useGetEnabledSSOProvidersQuery({ orgSlug: organizationSlug })

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          Failed to load SSO providers. Please try again later.
        </AlertDescription>
      </Alert>
    )
  }

  if (!data?.providers || data.providers.length === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-2">
      {data.providers.includes('google') && (
        <GoogleLoginButton organizationSlug={organizationSlug} />
      )}
    </div>
  )
}
