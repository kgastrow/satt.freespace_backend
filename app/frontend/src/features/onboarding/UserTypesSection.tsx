import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { useGetOnboardingStatusQuery } from '@/store/api/onboardingApi'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Plus } from 'lucide-react'

function getStatusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'approved':
      return 'default'
    case 'pending_review':
      return 'secondary'
    case 'in_progress':
      return 'outline'
    case 'rejected':
      return 'destructive'
    default:
      return 'secondary'
  }
}

export function UserTypesSection() {
  const { t } = useTranslation('onboarding')
  const isOnboardingEnabled = useFeatureFlag('user_onboarding')
  const { data: status, isLoading } = useGetOnboardingStatusQuery(undefined, {
    skip: !isOnboardingEnabled,
  })

  // Don't show if feature flag is disabled
  if (!isOnboardingEnabled) {
    return null
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-6 w-32" />
      </div>
    )
  }

  const userTypes = status?.all_user_types || []

  if (userTypes.length === 0) {
    return null
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {userTypes.map((ut) => (
          <div
            key={ut.user_user_type_id}
            className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2"
          >
            <span className="text-sm font-medium">{ut.user_type_name}</span>
            <Badge variant={getStatusVariant(ut.onboarding_status)}>
              {t(`myUserTypes.status.${ut.onboarding_status}`)}
            </Badge>
          </div>
        ))}
      </div>
      {status?.can_add_more_types && (
        <Button asChild variant="outline" size="sm" className="mt-2">
          <Link to="/onboarding">
            <Plus className="h-4 w-4 mr-1" />
            {t('myUserTypes.addAnother')}
          </Link>
        </Button>
      )}
    </div>
  )
}
